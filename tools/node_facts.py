#!/usr/bin/env python3
"""tools/node_facts.py — node hardware, model inventory, and profile-vs-live matcher.

Layer 0+1 of the inference-profile work (docs/ROADMAP-2026-08.md §1b; see
docs/SPEC-node-facts-and-profile-matcher-2026-08.md for the full design).
This module is READ-ONLY: it starts nothing, stops nothing, writes no
config, and fetches nothing from the web. It produces facts; tuning and
profile generation are later layers.

Three hazards this module is careful about, because the obvious
implementation of each is wrong (spec §3):

  Hazard A — llama-server flags are not a flat diff. They fall into three
  classes (identity / hardware-derived / deployment) and only identity-class
  differences are drift. `--host 0.0.0.0` vs `127.0.0.1` is an operator
  choice, never drift. See classify_flag().

  Hazard B — the question is "which profile is live", not "is this one
  profile live". match_live() ranks every known canonical profile against
  the running process rather than validating a single file.

  Hazard C — a node that does not respond is unreachable, not empty. Probes
  must degrade to reachable=False with null hardware fields, never zeros.
  This module never wakes a sleeping node; it only attempts a short,
  non-blocking connection and reports what happened.

Hazard D — agent_profile (goethe_node.NodeLifecycleMixin._NODE_REGISTRY) is
intent, a <ROLE>.gguf.md file is also intent, and /proc/<pid>/cmdline (or an
SSH pgrep of it) is the only observed reality. Every fact this module emits
carries a `source` field so the distinction is never silently averaged away.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import goethe_node  # noqa: E402  (path insert above must run first)

_NODE_REGISTRY = goethe_node.NodeLifecycleMixin._NODE_REGISTRY

LOCAL_NODE_NAMES = frozenset({"node4090", "local", "lucifer", "LUCIFER"})

DEFAULT_MODEL_ROOTS = [
    "/home/sy5/models",
    "/opt/local-se/nas/Models",
]

DEFAULT_PROFILE_DIR = "/mnt/c/Goethe3.0"

# ── Hazard A: flag classification (spec §3) ──────────────────────────────────
# Only IDENTITY differences are drift. HARDWARE differences are legitimate
# per-node variation. DEPLOYMENT differences are operator choice and must
# never be reported as drift. Anything not listed defaults to identity —
# fail loud (report a difference) rather than silently swallow one that
# might matter (test 1: classification must be total).
IDENTITY_FLAGS = frozenset({
    "-m", "--model", "--alias", "--ctx-size", "--cache-type-k", "--cache-type-v", "--spec-type",
})
HARDWARE_FLAGS = frozenset({
    "--threads", "--threads-batch", "-ngl", "--n-gpu-layers", "--batch-size", "--ubatch-size",
})
DEPLOYMENT_FLAGS = frozenset({
    "--host", "--port", "--path", "--log-file", "--slot-save-path",
})

# CPU ISA flags worth surfacing; the ones AVX512/AMX-capable inference builds
# actually branch on. Anything else in `lscpu`'s Flags line is noise here.
_INTERESTING_ISA_FLAGS = (
    "avx", "avx2", "avx_vnni",
    "avx512f", "avx512bw", "avx512vl", "avx512_vnni", "avx512_bf16", "avx512_fp16",
    "amx_bf16", "amx_int8", "amx_tile", "amx_fp16",
)

_QUANT_RE = re.compile(r"((?:UD-)?Q\d+_K(?:_[A-Za-z0-9]+)?)", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_flag(flag: str) -> str:
    """Classify a single llama-server flag per spec §3. Total by
    construction: every input either matches one of the two non-identity
    sets or falls through to "identity", so no flag is ever unclassified.
    """
    if flag in HARDWARE_FLAGS:
        return "hardware"
    if flag in DEPLOYMENT_FLAGS:
        return "deployment"
    if flag in IDENTITY_FLAGS:
        return "identity"
    return "identity"  # unknown flag — defaults to identity, per spec test 1


# ── 4.1 collect_hardware ─────────────────────────────────────────────────────

def _parse_gpu_csv(text: str) -> list:
    gpus = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        name, mem, driver = parts[0], parts[1], parts[2]
        digits = re.sub(r"[^\d]", "", mem)
        vram_mib = int(digits) if digits else None
        gpus.append({
            "name": name,
            "vram_total_mib": vram_mib,
            "driver": driver,
            "cuda": None,
            "vram_bandwidth_gbps": None,
            "bandwidth_source": "not-probed",
        })
    return gpus


def _parse_cuda(nvidia_smi_text: str):
    m = re.search(r"CUDA(?:\s+UMD)?\s+Version:\s*([\d.]+)", nvidia_smi_text, re.IGNORECASE)
    return m.group(1) if m else None


def _parse_lscpu(text: str):
    if not text.strip():
        return None
    model = re.search(r"^Model name:\s*(.+)$", text, re.MULTILINE)
    sockets = re.search(r"^Socket\(s\):\s*(\d+)", text, re.MULTILINE)
    cores_per_socket = re.search(r"^Core\(s\) per socket:\s*(\d+)", text, re.MULTILINE)
    total_cpus = re.search(r"^CPU\(s\):\s*(\d+)", text, re.MULTILINE)
    flags_line = re.search(r"^Flags:\s*(.+)$", text, re.MULTILINE)
    flags_set = set(flags_line.group(1).split()) if flags_line else set()
    isa_flags = sorted(f for f in _INTERESTING_ISA_FLAGS if f in flags_set)
    cores = None
    if cores_per_socket and sockets:
        cores = int(cores_per_socket.group(1)) * int(sockets.group(1))
    return {
        "model": model.group(1).strip() if model else None,
        "sockets": int(sockets.group(1)) if sockets else None,
        "cores": cores,
        "threads": int(total_cpus.group(1)) if total_cpus else None,
        "isa_flags": isa_flags,
    }


def _parse_free_b(text: str):
    for line in text.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            if len(parts) < 7:
                return None
            total_b, avail_b = int(parts[1]), int(parts[6])
            return {
                "total_gib": round(total_b / (1024 ** 3), 2),
                "available_gib": round(avail_b / (1024 ** 3), 2),
            }
    return None


def _split_sections(text: str) -> dict:
    sections: dict = {}
    current = None
    buf: list = []
    for line in text.splitlines():
        m = re.match(r"^__([A-Z]+)__$", line.strip())
        if m:
            if current is not None:
                sections[current] = "\n".join(buf)
            current = m.group(1)
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf)
    return sections


def _unreachable(node: str, now: str) -> dict:
    return {
        "node": node,
        "gpu": None,
        "cpu": None,
        "ram": None,
        "host": {"hostname": None, "kernel": None, "reachable": False},
        "probed_at": now,
        "source": "unreachable",
    }


def _collect_hardware_local(node: str, now: str) -> dict:
    try:
        gpu_csv = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        gpus = _parse_gpu_csv(gpu_csv.stdout) if gpu_csv.returncode == 0 else []
        if gpus:
            cuda_raw = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
            cuda_version = _parse_cuda(cuda_raw.stdout) if cuda_raw.returncode == 0 else None
            for g in gpus:
                g["cuda"] = cuda_version
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        gpus = []

    try:
        lscpu_raw = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=10)
        cpu = _parse_lscpu(lscpu_raw.stdout) if lscpu_raw.returncode == 0 else None
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        cpu = None

    try:
        free_raw = subprocess.run(["free", "-b"], capture_output=True, text=True, timeout=10)
        ram = _parse_free_b(free_raw.stdout) if free_raw.returncode == 0 else None
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        ram = None

    try:
        hostname = subprocess.run(["hostname"], capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        hostname = None

    try:
        kernel = subprocess.run(["uname", "-r"], capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        kernel = None

    return {
        "node": node,
        "gpu": gpus,
        "cpu": cpu,
        "ram": ram,
        "host": {"hostname": hostname, "kernel": kernel, "reachable": True},
        "probed_at": now,
        "source": "local-probe",
    }


def _collect_hardware_remote(node: str, reg: dict, now: str) -> dict:
    user, hostname = reg.get("ssh_user"), reg.get("hostname")
    if not user or not hostname:
        return _unreachable(node, now)
    remote_cmd = (
        "echo __HOST__; hostname; "
        "echo __KERNEL__; uname -r; "
        "echo __GPU__; nvidia-smi --query-gpu=name,memory.total,driver_version "
        "--format=csv,noheader,nounits 2>/dev/null; "
        "echo __CUDA__; nvidia-smi 2>/dev/null | grep -i cuda; "
        "echo __CPU__; lscpu; "
        "echo __RAM__; free -b"
    )
    try:
        r = subprocess.run(
            [
                "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
                "-o", "BatchMode=yes", f"{user}@{hostname}", remote_cmd,
            ],
            capture_output=True, text=True, timeout=12,
        )
    except (subprocess.SubprocessError, OSError):
        return _unreachable(node, now)

    if r.returncode != 0:
        return _unreachable(node, now)

    sections = _split_sections(r.stdout)
    gpus = _parse_gpu_csv(sections.get("GPU", ""))
    cuda_version = _parse_cuda(sections.get("CUDA", ""))
    for g in gpus:
        g["cuda"] = cuda_version
    cpu = _parse_lscpu(sections.get("CPU", ""))
    ram = _parse_free_b(sections.get("RAM", ""))
    remote_hostname = sections.get("HOST", "").strip() or hostname
    kernel = sections.get("KERNEL", "").strip() or None

    return {
        "node": node,
        "gpu": gpus,
        "cpu": cpu,
        "ram": ram,
        "host": {"hostname": remote_hostname, "kernel": kernel, "reachable": True},
        "probed_at": now,
        "source": "ssh",
    }


def collect_hardware(node: str = "node4090") -> dict:
    """Hardware facts for one node. Never wakes a sleeping node — a remote
    probe is a single short SSH connection attempt (no Wake-on-LAN), and an
    unreachable node yields `host.reachable: False` with every hardware
    field `null`, never zeroed values (Hazard C).
    """
    now = _now_iso()
    if node in LOCAL_NODE_NAMES:
        return _collect_hardware_local(node, now)
    reg = _NODE_REGISTRY.get(node)
    if reg is None:
        out = _unreachable(node, now)
        out["error"] = f"unknown node '{node}'. Known: node4090 (local), {list(_NODE_REGISTRY.keys())}"
        return out
    return _collect_hardware_remote(node, reg, now)


# ── 4.2 collect_models ───────────────────────────────────────────────────────

def _parse_quant(filename: str):
    m = _QUANT_RE.search(filename)
    return m.group(1) if m else None


def _scan_root(root: str) -> dict:
    quoted = shlex.quote(root)
    probe = f"test -d {quoted} || exit 2; find {quoted} -iname '*.gguf' -printf '%s|%T@|%p\\n'"
    try:
        r = subprocess.run(["bash", "-c", probe], capture_output=True, text=True, timeout=15)
    except (subprocess.SubprocessError, OSError):
        return {"root": root, "reachable": False, "source": "unreachable", "files": []}
    if r.returncode == 2:
        return {"root": root, "reachable": False, "source": "unreachable", "files": []}

    files = []
    for line in r.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        size_s, mtime_s, path = parts
        try:
            size_bytes, mtime = int(size_s), float(mtime_s)
        except ValueError:
            continue
        files.append({
            "path": path,
            "size_bytes": size_bytes,
            "mtime": mtime,
            "quant": _parse_quant(os.path.basename(path)),
        })
    return {"root": root, "reachable": True, "source": "local-scan", "files": files}


def collect_models(roots=None) -> dict:
    """Enumerate *.gguf under each root. Does not open or hash file
    contents — size/mtime/quant-from-filename only, so this stays fast on a
    network share. An unreachable root is `reachable: False`, not an
    exception (spec §4.2, test 7).
    """
    roots = list(DEFAULT_MODEL_ROOTS) if roots is None else list(roots)
    return {"probed_at": _now_iso(), "roots": [_scan_root(root) for root in roots]}


# ── 4.3 parse_profile / match_live ──────────────────────────────────────────

def _parse_flags_from_tokens(tokens: list) -> dict:
    """argv tokens (already split, argv0 excluded) -> {flag: value_or_True}.

    A flag is treated as boolean (True, no argument) when there is no next
    token or the next token itself looks like a long flag (starts with
    "--"). This mirrors goethe.py's _parse_llama_cmdline heuristic so
    `--reasoning-budget -1` (a negative *value*, single dash) is still
    consumed as an argument rather than misread as the next flag.
    """
    out: dict = {}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if not t.startswith("-"):
            i += 1
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        has_val = bool(nxt) and not nxt.startswith("--")
        if has_val:
            out[t] = nxt
            i += 2
        else:
            out[t] = True
            i += 1
    return out


def parse_profile(path: str) -> dict:
    """Parse a canonical `<ROLE>-<model>.gguf.md` file — a literal, runnable
    llama-server invocation with backslash-newline continuations — into
    {"file", "flags", "source": "documented"}. Files may carry a UTF-8 BOM
    (spec §4.3); some also use CRLF line endings without a BOM. Both are
    normalized before tokenizing.

    A profile file may carry free-text documentation AFTER the command
    block, separated by a line that is exactly "---" (see
    profiles/node3090/*.gguf.md, added 2026-08-02/03 for the on-demand
    engine-start work). Only the command block is the profile; everything
    from that separator onward is prose and must never be tokenized as
    flags (found 2026-08-03: without this cut, match_live() against a
    documented profile spuriously reports "closest" instead of "exact"
    because markdown text after "---" gets shlex-split into garbage
    pseudo-flags). Files with no such line are unaffected -- this is a
    strict prefix truncation, not a reinterpretation of existing profiles.
    """
    with open(path, encoding="utf-8-sig", newline="") as fh:
        text = fh.read()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cmd_lines = []
    for line in text.split("\n"):
        if line.strip() == "---":
            break
        cmd_lines.append(line)
    text = "\n".join(cmd_lines)
    joined = text.replace("\\\n", " ")
    tokens = shlex.split(joined, comments=False)
    flags = _parse_flags_from_tokens(tokens[1:]) if tokens else {}
    return {"file": path, "flags": flags, "source": "documented"}


def list_profiles(profile_dir: str = DEFAULT_PROFILE_DIR) -> dict:
    """{path: parse_profile(path)} for every *.gguf.md under profile_dir."""
    profiles = {}
    try:
        names = sorted(os.listdir(profile_dir))
    except OSError:
        return profiles
    for name in names:
        if not name.endswith(".gguf.md"):
            continue
        path = os.path.join(profile_dir, name)
        try:
            profiles[path] = parse_profile(path)
        except (OSError, ValueError):
            continue
    return profiles


def read_live_cmdline_local(pid: int):
    """/proc/<pid>/cmdline, NUL-joined argv turned into a space-joined
    string. None if the process is gone or unreadable — never raises.
    """
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if not raw:
        return None
    return raw.decode("utf-8", "replace").replace("\x00", " ").strip()


def find_local_llama_server_pid():
    """(pid, cmdline) of a running local llama-server, or (None, None).
    Local-only: reads /proc directly, no SSH, no wake.
    """
    try:
        r = subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True, text=True, timeout=5)
    except (subprocess.SubprocessError, OSError):
        return None, None
    pids = [p for p in r.stdout.split() if p.isdigit()]
    if not pids:
        return None, None
    pid = int(pids[0])
    return pid, read_live_cmdline_local(pid)


def _diff_profile(canonical_flags: dict, live_flags: dict) -> dict:
    all_flags = set(canonical_flags) | set(live_flags)
    identity_diffs, hardware_diffs, deployment_diffs = [], [], []
    identity_total = identity_matches = 0
    for flag in sorted(all_flags):
        cls = classify_flag(flag)
        cval = canonical_flags.get(flag, "<absent>")
        lval = live_flags.get(flag, "<absent>")
        same = cval == lval
        entry = {"flag": flag, "canonical": cval, "live": lval}
        if cls == "identity":
            identity_total += 1
            if same:
                identity_matches += 1
            else:
                identity_diffs.append(entry)
        elif cls == "hardware":
            if not same:
                hardware_diffs.append(entry)
        else:
            if not same:
                deployment_diffs.append(entry)
    return {
        "identity_diffs": identity_diffs,
        "hardware_diffs": hardware_diffs,
        "deployment_diffs": deployment_diffs,
        "identity_matches": identity_matches,
        "identity_total": identity_total,
    }


def match_live(profiles: dict, live_pid, live_flags: dict = None) -> dict:
    """Rank every known canonical profile against the live process (Hazard
    B — "which profile is live", not "is this one profile live").

    Args:
        profiles:   {file_path: parse_profile(file_path)} — e.g. from
                    list_profiles().
        live_pid:   PID of the running llama-server, or None if none found.
        live_flags: Pre-parsed live flag dict. If omitted and live_pid is
                    set, read and parse /proc/<live_pid>/cmdline locally.

    verdict "exact" requires every identity flag to agree. hardware and
    deployment differences never block "exact" but are still listed.
    verdict "none" means there is no live process, or no known profiles, to
    compare — never inferred from a bad match.
    """
    if live_flags is None and live_pid is not None:
        cmdline = read_live_cmdline_local(live_pid)
        live_flags = _parse_flags_from_tokens(shlex.split(cmdline)[1:]) if cmdline else {}
    live_flags = live_flags or {}
    live_model = live_flags.get("-m") or live_flags.get("--model")

    if not profiles or live_pid is None:
        return {
            "live_pid": live_pid,
            "live_model": live_model,
            "best_match": None,
            "ranked": [],
            "verdict": "none",
        }

    ranked = []
    for file, prof in profiles.items():
        d = _diff_profile(prof["flags"], live_flags)
        exact = d["identity_matches"] == d["identity_total"]
        ranked.append({"file": file, "exact": exact, **d})
    ranked.sort(key=lambda r: (-r["identity_matches"], len(r["identity_diffs"])))

    best = ranked[0]
    verdict = "exact" if best["exact"] else "closest"
    return {
        "live_pid": live_pid,
        "live_model": live_model,
        "best_match": {
            "file": best["file"],
            "identity_matches": best["identity_matches"],
            "identity_total": best["identity_total"],
        },
        "ranked": ranked,
        "verdict": verdict,
    }


# ── 4.4 CLI ──────────────────────────────────────────────────────────────────

def _fmt_hardware(node: str, hw: dict) -> str:
    lines = [f"{node}:"]
    if not hw["host"]["reachable"]:
        lines.append(f"  UNREACHABLE (source: {hw['source']})")
        if hw.get("error"):
            lines.append(f"  error: {hw['error']}")
        return "\n".join(lines)
    if hw["gpu"]:
        for g in hw["gpu"]:
            cuda = g["cuda"] or "n/a"
            lines.append(
                f"  GPU: {g['name']} — {g['vram_total_mib']} MiB — driver {g['driver']} — "
                f"CUDA {cuda} (bandwidth: {g['bandwidth_source']})"
            )
    else:
        lines.append("  GPU: none detected")
    cpu = hw["cpu"]
    if cpu:
        isa = ", ".join(cpu["isa_flags"]) or "none of the tracked flags"
        lines.append(f"  CPU: {cpu['model']} — {cpu['sockets']} socket(s) — {cpu['threads']} threads — ISA: {isa}")
    ram = hw["ram"]
    if ram:
        lines.append(f"  RAM: {ram['total_gib']} GiB total / {ram['available_gib']} GiB available")
    lines.append(f"  Host: {hw['host']['hostname']} (kernel {hw['host']['kernel']})")
    lines.append(f"  source: {hw['source']}, probed_at: {hw['probed_at']}")
    return "\n".join(lines)


def _fmt_models(models: dict) -> str:
    lines = []
    for root in models["roots"]:
        if not root["reachable"]:
            lines.append(f"Models under {root['root']}: UNREACHABLE")
            continue
        lines.append(f"Models under {root['root']} (reachable, {len(root['files'])} files):")
        for f in root["files"]:
            gib = round(f["size_bytes"] / (1024 ** 3), 1)
            quant = f["quant"] or "?"
            lines.append(f"  {gib:>7} GiB  [{quant}]  {f['path']}")
    return "\n".join(lines)


def _fmt_match(match: dict) -> str:
    if match["verdict"] == "none" and match["live_pid"] is None:
        return "No live llama-server process found on this node — nothing to match."
    lines = [f"Live: pid {match['live_pid']}, model {match['live_model']}"]
    if match["best_match"]:
        bm = match["best_match"]
        lines.append(
            f"Best match: {bm['file']} (identity {bm['identity_matches']}/{bm['identity_total']}) "
            f"— verdict: {match['verdict']}"
        )
    for r in match["ranked"]:
        lines.append(
            f"  {r['file']}: identity {r['identity_matches']}/{r['identity_total']}"
            f", hardware_diffs={len(r['hardware_diffs'])}, deployment_diffs={len(r['deployment_diffs'])}"
        )
        for d in r["identity_diffs"]:
            lines.append(f"      IDENTITY {d['flag']}: canonical={d['canonical']!r} live={d['live']!r}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hardware", action="store_true", help="collect hardware facts")
    parser.add_argument("--models", action="store_true", help="enumerate local GGUF model files")
    parser.add_argument("--match", action="store_true", help="match the live process against known profiles")
    parser.add_argument("--all", action="store_true", help="hardware + models + match")
    parser.add_argument("--node", default="node4090", help="node name for --hardware (default: node4090 / local)")
    parser.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR, help="canonical profile directory")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if not (args.hardware or args.models or args.match or args.all):
        parser.print_help()
        return 1

    report: dict = {}
    human: list = []

    if args.all or args.hardware:
        if args.all:
            nodes = ["node4090", *sorted(_NODE_REGISTRY.keys())]
            report["hardware"] = {n: collect_hardware(n) for n in nodes}
        else:
            report["hardware"] = {args.node: collect_hardware(args.node)}
        for n, hw in report["hardware"].items():
            human.append(_fmt_hardware(n, hw))

    if args.all or args.models:
        report["models"] = collect_models()
        human.append(_fmt_models(report["models"]))

    if args.all or args.match:
        profiles = list_profiles(args.profile_dir)
        pid, cmdline = find_local_llama_server_pid()
        live_flags = _parse_flags_from_tokens(shlex.split(cmdline)[1:]) if cmdline else None
        report["match"] = match_live(profiles, pid, live_flags)
        human.append(_fmt_match(report["match"]))

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("\n\n".join(human))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
