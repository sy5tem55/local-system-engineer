#!/usr/bin/env python3
"""
lse_agent.py — Planner → Worker → Verifier pipeline for LSE coding tasks.

Prevents cross-file invariant drift by:
  1. Planner: reads source files, extracts canonical IPs/ports/constants as JSON
  2. Worker: generates code with facts prepended — cannot hallucinate known values
  3. Verifier: checks IPs/ports, structural keys, truncation, Python syntax;
               retries Worker once with violation list if anything fails

Usage (from WSL):
  cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer

  python3 lse_agent.py \\
    --task "Rewrite echarts_topology.py: fix tier edges so ASUS/Netgear/RUTX50 are not floating islands" \\
    --files net-discovery/snapshot.json net-discovery/echarts_topology.py net-discovery/discovery_engine.py \\
    --target net-discovery/echarts_topology.py

Options:
  --llm-url       llama-server base URL       (default: http://localhost:8080)
  --model         model name                  (auto-detect from server if omitted)
  --facts         path to save extracted facts (default: /tmp/lse_facts.json)
  --max-retries   Worker retry limit          (default: 1)
  --dry-run       print output; do not write to --target
  --skip-planner  reuse existing --facts file (skip extraction step)
  --no-llm-verify skip LLM structural check  (programmatic checks only, faster)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import urllib.request
import urllib.error

# ─── LLM client ───────────────────────────────────────────────────────────────

def _post_json(url: str, payload: dict, timeout: int = 180) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        print(f"❌  LLM request failed: {e}", file=sys.stderr)
        sys.exit(1)


def llm_chat(
    messages: list,
    url: str = "http://localhost:8080",
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 8192,
    reasoning_budget: int | None = None,
    enable_thinking: bool = True,
) -> str:
    payload: dict = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if model:
        payload["model"] = model
    if reasoning_budget is not None:
        payload["reasoning_budget"] = reasoning_budget
    if not enable_thinking:
        # Qwen3.6 + llama.cpp: disable think block at template level
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    resp = _post_json(f"{url}/v1/chat/completions", payload)
    msg = resp["choices"][0]["message"]
    # llama.cpp with Qwen3.6 reasoning mode puts thinking in "reasoning_content"
    # and may leave "content" empty — fall back to reasoning_content.
    content = (msg.get("content") or "").strip()
    if not content:
        content = (msg.get("reasoning_content") or "").strip()
    return content


def detect_model(url: str) -> str | None:
    try:
        req = urllib.request.Request(f"{url}/v1/models")
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return data["data"][0]["id"]
    except Exception:
        return None


def _strip_fences(text: str) -> str:
    """Remove <think> blocks, leading/trailing markdown code fences.

    Qwen3.6 thinking mode sometimes puts the answer inside the <think> block
    and emits nothing after it. Fallback: if stripping leaves empty string,
    extract the last JSON object / code block found inside the think block.
    """
    import re
    # Strip think blocks; capture content for fallback
    think_content = ""
    m = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
    if m:
        think_content = m.group(1)
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # If something remains after the think block, use it
    if t:
        if t.startswith("```"):
            lines = t.splitlines()
            inner = lines[1:]
            if inner and inner[-1].strip() == "```":
                inner = inner[:-1]
            return "\n".join(inner).strip()
        return t

    # Fallback: model put answer inside think block — extract last {...} or ```...```
    if think_content:
        # Try last JSON object
        brace = think_content.rfind("{")
        if brace != -1:
            candidate = think_content[brace:].strip()
            # Find matching closing brace
            depth, end = 0, -1
            for i, ch in enumerate(candidate):
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end != -1:
                return candidate[:end].strip()
        # Try last fenced block
        fence_m = re.findall(r"```[^\n]*\n(.*?)```", think_content, flags=re.DOTALL)
        if fence_m:
            return fence_m[-1].strip()
    return t


# ─── Phase 1: Planner ─────────────────────────────────────────────────────────

PLANNER_SYSTEM = """\
You are a code auditor specialising in cross-file invariants.
Read the provided source files and output a SINGLE JSON object — no markdown fences,
no explanation, no preamble — containing every value that must remain consistent
across files:

{
  "ips":           { "<role>": "<ip>", ... },
  "ports":         { "<service>": <port>, ... },
  "paths":         { "<role>": "<path>", ... },
  "tier_nodes":    { "<ip>": ["<label>", "<category>", <tier>], ... },
  "tier_edges":    [["<src_ip>", "<dst_ip>", "<label>"], ...],
  "subnet_parents": { "<cidr>": "<parent_ip>", ... },
  "top_level_dicts": ["<NAME>", ...],
  "other":         { "<key>": "<value>", ... }
}

Include only keys that are relevant (omit empty sections).
Output ONLY valid JSON."""


def run_planner(file_contents: dict, url: str, model: str | None) -> dict:
    print("🔍  Planner: extracting canonical facts …")
    files_text = "\n\n".join(
        f"=== {name} ===\n{content[:10_000]}"
        for name, content in file_contents.items()
    )
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM},
        {"role": "user", "content": f"Extract cross-file invariants:\n\n{files_text}\n\n/no_think"},
    ]
    raw = llm_chat(messages, url=url, model=model, temperature=0.05, max_tokens=2048)
    raw = _strip_fences(raw)
    try:
        facts = json.loads(raw)
        cats = ", ".join(f"{k}({len(v) if isinstance(v,(dict,list)) else 1})" for k, v in facts.items())
        print(f"   ✓  {cats}")
        return facts
    except json.JSONDecodeError as e:
        print(f"   ⚠  Planner output is not valid JSON ({e}); using empty facts", file=sys.stderr)
        print(f"   Raw (first 400 chars): {raw[:400]}", file=sys.stderr)
        return {}


# ─── Phase 2: Worker ──────────────────────────────────────────────────────────

WORKER_SYSTEM = """\
You are an expert systems programmer.
You receive:
  • CANONICAL FACTS  — ground-truth values you MUST use exactly as given
  • REFERENCE FILES  — existing code for context
  • TASK             — what to write or rewrite

Hard rules:
  1. Use ONLY the IPs, ports, and constants from CANONICAL FACTS. Never invent values.
  2. Output ONLY the complete file content — no markdown fences, no explanation, no preamble.
  3. Do not truncate. Write every line from the opening shebang/import to the final statement."""


def _worker_messages(task: str, facts: dict, file_contents: dict, violations: list | None = None) -> list:
    facts_block = json.dumps(facts, indent=2)
    files_block = "\n\n".join(
        f"=== {name} ===\n{content[:7_000]}"
        for name, content in file_contents.items()
    )
    user_parts = [
        f"CANONICAL FACTS (use these exact values — no substitutions):\n{facts_block}",
        f"REFERENCE FILES:\n{files_block}",
        f"TASK:\n{task}",
    ]
    if violations:
        vlist = "\n".join(f"  • {v}" for v in violations)
        user_parts.append(
            f"YOUR PREVIOUS ATTEMPT FAILED VERIFICATION — fix ALL of these before responding:\n{vlist}"
        )
    return [
        {"role": "system", "content": WORKER_SYSTEM},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def run_worker(task: str, facts: dict, file_contents: dict,
               url: str, model: str | None, violations: list | None = None) -> str:
    label = "retrying" if violations else "generating"
    print(f"⚙️   Worker: {label} …")
    messages = _worker_messages(task, facts, file_contents, violations)
    output = llm_chat(messages, url=url, model=model, temperature=0.15, max_tokens=10_000)
    return _strip_fences(output)


# ─── Phase 3: Verifier ────────────────────────────────────────────────────────

VERIFIER_SYSTEM = """\
You are a code verifier. Compare generated code against canonical facts.
For each violation output exactly:  VIOLATION: <one-line description>
If there are no violations output exactly:  OK
Nothing else."""


def _programmatic_checks(output: str, facts: dict, target: str) -> list[str]:
    """Fast checks that do not need the LLM."""
    violations: list[str] = []

    # 1 — truncation: suspiciously short
    if len(output) < 80:
        violations.append(f"Output is only {len(output)} chars — likely truncated or empty")
        return violations  # no point continuing

    last = output.rstrip().splitlines()[-1].strip()

    # bare single/double character last line (the infamous `l` bug)
    if 0 < len(last) <= 2 and last not in (")", "]", "}", '"""', "'''"):
        violations.append(f"Suspicious final line {last!r} — probable truncation")

    stale_endings = ("# ...", "# etc", "# more code", "# TODO: fill in", "pass  #")
    if any(last.endswith(s) for s in stale_endings):
        violations.append(f"File appears cut off — final line: {last!r}")

    # 2 — IP correctness: known IPs from facts must appear in output when referenced
    known_ips: dict[str, str] = {}
    for section in ("ips", "tier_nodes", "subnet_parents"):
        val = facts.get(section, {})
        if isinstance(val, dict):
            for k, v in val.items():
                ip = v[0] if isinstance(v, list) else v
                if isinstance(ip, str) and ip.count(".") == 3:
                    known_ips[k] = ip

    for role, correct_ip in known_ips.items():
        if "192.168" in correct_ip and correct_ip not in output:
            role_key = role.replace(" ", "_").upper()
            if role_key in output or role.lower() in output.lower():
                violations.append(
                    f"Expected IP {correct_ip!r} for {role!r} not found in output"
                )

    # 3 — TIER_EDGES topology: verify intermediate hops are not collapsed.
    # Common regression: model connects leaf nodes directly to pfSense LAN
    # instead of preserving the OPT1→Netgear→RUTX50 chain.
    tier_edges = facts.get("tier_edges", [])
    if tier_edges and "TIER_EDGES" in output:
        for edge in tier_edges:
            if not isinstance(edge, (list, tuple)) or len(edge) < 2:
                continue
            src, dst = str(edge[0]), str(edge[1])
            # Check the edge tuple appears in code (order matters)
            edge_pattern = f'"{src}"'
            dst_pattern  = f'"{dst}"'
            # Find all occurrences of src in output, check dst follows nearby
            idx = 0
            found = False
            while True:
                i = output.find(edge_pattern, idx)
                if i == -1:
                    break
                # Look for dst within 60 chars after src
                window = output[i:i+80]
                if dst_pattern in window:
                    found = True
                    break
                idx = i + 1
            if not found:
                violations.append(
                    f"TIER_EDGE ({src!r} → {dst!r}) missing or wrong — "
                    f"check intermediate hops are not collapsed to pfSense LAN"
                )

    # 3 — Python syntax
    if target.endswith(".py"):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tf:
            tf.write(output)
            tmp = tf.name
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", tmp],
            capture_output=True, text=True,
        )
        os.unlink(tmp)
        if result.returncode != 0:
            err = result.stderr.replace(tmp, "<generated>").strip()
            violations.append(f"Python syntax error: {err}")

    return violations


def _llm_verify(output: str, facts: dict, url: str, model: str | None) -> list[str]:
    print("   LLM structural check …")
    facts_block = json.dumps(facts, indent=2)
    sample = output[:5_000] + ("\n… [truncated for review]" if len(output) > 5_000 else "")
    messages = [
        {"role": "system", "content": VERIFIER_SYSTEM},
        {"role": "user", "content": (
            f"CANONICAL FACTS:\n{facts_block}\n\n"
            f"GENERATED CODE:\n{sample}\n\n"
            "Check:\n"
            "1. Are all IP addresses correct per facts?\n"
            "2. Are required structural dicts present "
            "(e.g. TIER_NODES, TIER_EDGES, SUBNET_PARENT, SUBNET_PARENTS)?\n"
            "3. Are port numbers correct?\n"
            "4. Are tier edges complete (no floating island nodes)?"
        )},
    ]
    raw = llm_chat(messages, url=url, model=model, temperature=0.0, max_tokens=512)
    if raw.strip().upper() == "OK":
        return []
    return [
        line[len("VIOLATION:"):].strip()
        for line in raw.splitlines()
        if line.strip().upper().startswith("VIOLATION:")
    ]


def run_verifier(
    output: str, facts: dict, target: str,
    url: str, model: str | None, llm_verify: bool = True,
) -> list[str]:
    print("✅  Verifier: running checks …")
    violations = _programmatic_checks(output, facts, target)

    if llm_verify:
        violations += _llm_verify(output, facts, url, model)

    if violations:
        print(f"   ⚠  {len(violations)} violation(s):")
        for v in violations:
            print(f"      • {v}")
    else:
        print("   ✓  All checks passed")

    return violations


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="LSE Planner→Worker→Verifier agent pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--task",         required=True, help="What to write/rewrite (quoted string)")
    ap.add_argument("--files",        nargs="+", required=True, help="Context files for Planner and Worker")
    ap.add_argument("--target",       default="",  help="File path to write output (omit for stdout)")
    ap.add_argument("--llm-url",      default="http://localhost:8080")
    ap.add_argument("--planner-url",  default=None,
                    help="LLM URL for Planner (default: same as --llm-url)")
    ap.add_argument("--model",        default=None)
    ap.add_argument("--facts",        default="/tmp/lse_facts.json", help="Where to save extracted facts JSON")
    ap.add_argument("--max-retries",  type=int, default=1)
    ap.add_argument("--dry-run",      action="store_true", help="Print output; do not write to --target")
    ap.add_argument("--skip-planner", action="store_true", help="Load existing --facts file, skip extraction")
    ap.add_argument("--no-llm-verify",action="store_true", help="Skip LLM structural check (faster)")
    args = ap.parse_args()

    url   = args.llm_url
    p_url   = args.planner_url or url
    model   = args.model or detect_model(url)
    p_model = detect_model(p_url) if p_url != url else model
    print(f"📡  Worker/Verifier: {url}  model={model or '(server default)'}")
    if p_url != url:
        print(f"📡  Planner: {p_url}  model={p_model or '(server default)'}")

    # Read input files
    file_contents: dict[str, str] = {}
    for fp in args.files:
        p = Path(fp)
        if not p.exists():
            print(f"⚠   Not found — skipping: {fp}", file=sys.stderr)
            continue
        file_contents[p.name] = p.read_text(errors="replace")
        print(f"   📄 {p.name}  ({len(file_contents[p.name]):,} chars)")

    if not file_contents:
        print("❌  No readable files — aborting", file=sys.stderr)
        sys.exit(1)

    # ── Phase 1: Planner ──
    facts_path = Path(args.facts)
    if args.skip_planner and facts_path.exists():
        facts = json.loads(facts_path.read_text())
        print(f"📋  Loaded facts from {facts_path}")
    else:
        facts = run_planner(file_contents, p_url, p_model)
        facts_path.write_text(json.dumps(facts, indent=2))
        print(f"   💾 Saved to {facts_path}")

    # ── Phase 2 + 3: Worker → Verify → retry ──
    violations: list[str] = []
    output = ""
    for attempt in range(args.max_retries + 1):
        output = run_worker(
            args.task, facts, file_contents, url, model,
            violations=violations if attempt > 0 else None,
        )
        violations = run_verifier(
            output, facts, args.target, url, model,
            llm_verify=not args.no_llm_verify,
        )
        if not violations:
            break
        if attempt < args.max_retries:
            print(f"   Retry {attempt + 1}/{args.max_retries} ...")
        else:
            print(f"   Still failing after {args.max_retries} retry -- writing anyway")

    # Write output
    if args.dry_run or not args.target:
        print("\n" + "-" * 70 + "  OUTPUT  " + "-" * 70)
        print(output)
        print("-" * 150)
    else:
        target = Path(args.target)
        if target.exists():
            bak = target.with_suffix(target.suffix + ".bak")
            bak.write_text(target.read_text(errors="replace"))
            print(f"   Backed up original -> {bak.name}")
        target.write_text(output)
        print(f"\nWritten -> {args.target}")

    # Summary
    status = "PASSED" if not violations else f"WARNINGS ({len(violations)})"
    print(f"\n{'='*40}")
    print(f"Pipeline complete  |  Verifier: {status}")
    if violations:
        for v in violations:
            print(f"  * {v}")


if __name__ == "__main__":
    main()
