# SPEC — node facts, model inventory, and the profile matcher

> Design: Opus 5, 2026-08-02. Implementation: Sonnet 5.
> Source of truth is the WSL tree at `/home/sy5/projects/local-system-engineer`.
> This is **Layer 0+1** of the inference-profile work
> (`docs/ROADMAP-2026-08.md` §1b). It deliberately does not generate or tune
> profiles — it produces the facts that tuning will later consume.

---

## 1. Why

The operator's goal is an LSE that starts inference engines with parameters
matched to each node's hardware and the workload at hand — and eventually
decides between an 80B MoE and a dense 27B, or which quant suits coding
versus planning.

Every one of those decisions references facts nobody currently collects in a
structured way: what GPU/VRAM/RAM/ISA a node has, which models exist and
where, and which canonical profile is actually running right now.

**Measured 2026-08-02, and the reason this comes first:** the full hardware
baseline for node4090 took one command and no network calls —
`RTX 4090 / 24564 MiB · i9-14900KF / 20 CPU · 47 GB RAM`, plus 7 local GGUFs.
Hardware facts prune the search space *before* any web research: "24 GB VRAM,
47 GB RAM" already reframes "80B MoE vs dense 27B" from an open question into
a narrow, testable one about offload throughput.

---

## 2. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| Canonical profile format | a **literal, runnable `llama-server` invocation** — not a config schema. See `/mnt/c/Goethe3.0/*.gguf.md` |
| Naming convention | `<ROLE>-<model-file>.gguf.md`; roles seen: `ACTUAL`, `131K`, `-165000` suffix |
| Known profile files | 4, under `/mnt/c/Goethe3.0/` |
| Local models | `/home/sy5/models` — 7 GGUF as of 2026-08-02 |
| Remote models | `//n45.home.arpa/Models` — host responds to ping |
| node4090 | **is LUCIFER itself** (`goethe_node.py:293`), 192.168.1.57 |
| Remote nodes | node3090, node5090 (`_NODE_REGISTRY`, `goethe_node.py:54`) |
| Existing profile seed | `_NODE_REGISTRY[n].agent_profile` + `_PROFILE_FLAGS` |
| Suite baseline | 728 passed (2026-08-02) |

**This table was compiled by reading and probing on 2026-08-02. The fleet
changes fast — the live engine config changed twice in one day during
authoring. Re-verify before depending on any row.**

---

## 3. Hazards

### Hazard A — a flat diff is the wrong instrument

The obvious matcher — diff the canonical file against `/proc/<pid>/cmdline`
and report every difference — produces false alarms, because llama-server
flags fall into three classes and only one is drift:

| Class | Examples | A difference means |
|---|---|---|
| **Identity** | `-m`, `--alias`, `--ctx-size`, `--cache-type-k/v`, `--spec-type` | a **different profile** is running |
| **Hardware-derived** | `--threads`, `--threads-batch`, `-ngl`, `--batch-size`, `--ubatch-size` | legitimate per-node variation |
| **Deployment** | `--host`, `--port`, `--path`, `--log-file`, `--slot-save-path` | **operator choice — never drift** |

Confirmed by the operator 2026-08-02: `--host` is deliberately selectable in
the Goethe GUI — `127.0.0.1` for local-only (and specifically *not*
`localhost`, which resolves to `::1` first on a dual-stack host, so the
literal IPv4 address is what forces IPv4), or `0.0.0.0` to serve other
workstations on the LAN. Reporting that as drift would train the operator to
ignore the tool.

### Hazard B — the question is "which profile is live", not "is this profile live"

With several canonical files present and a config that changed twice in one
day, validating one file against reality answers almost nothing. The tool
must **rank all known profiles** against the live process and name the best
match, with its identity-level differences.

### Hazard C — probes must not assume a node is awake

Nodes do not auto-start services **by design**; the LSE starts what a task
needs. A probe must degrade to "unknown, node unreachable" rather than hang
or report zeros as facts. Never treat an unreachable node as a node with no
GPU.

### Hazard D — do not conflate documented with observed

`agent_profile` in `_NODE_REGISTRY` is *intent*. `/proc/<pid>/cmdline` is
*reality*. `<ROLE>.gguf.md` is *intent*. Every emitted fact must record which
it is; the whole point is to make divergence visible rather than average it
away.

---

## 4. What to implement

A new module `tools/node_facts.py`, plus tests. **Read-only throughout** —
it starts nothing, stops nothing, writes no config.

### 4.1 `collect_hardware(node) -> dict`

For the local node, probe directly; for remote nodes, over SSH. Emit:

```
gpu:   [{name, vram_total_mib, driver, cuda}]      # nvidia-smi --query-gpu
cpu:   {model, sockets, cores, threads, isa_flags} # lscpu (avx512/amx are the ones that matter)
ram:   {total_gib, available_gib}                  # free
host:  {hostname, kernel, reachable: bool}
probed_at, source: "local-probe" | "ssh" | "unreachable"
```

VRAM **bandwidth** is a published spec, not a probe. Leave it `null` with
`bandwidth_source: "not-probed"`. Filling it is Layer 2's job (web research);
do not guess it here.

### 4.2 `collect_models(roots) -> dict`

Enumerate `*.gguf` under each root — default `/home/sy5/models` and the
`n45` share. Per file: path, size_bytes, mtime, and the quant string parsed
from the filename (`Q4_K_M`, `UD-Q4_K_XL`, `Q5_K_M`) when derivable, `null`
otherwise. **Do not** open or hash the files — this must stay fast on a
network share, and an unreachable share is `reachable: false`, not an error.

### 4.3 `parse_profile(path) -> dict` and `match_live(profiles, pid) -> dict`

`parse_profile` turns a `<ROLE>-<model>.gguf.md` into `{flag: value}`.
Note the files may carry a UTF-8 BOM — read with `encoding="utf-8-sig"`.

`match_live` compares every known profile against the live process and
returns them ranked by identity-flag agreement:

```
{
  "live_pid": int, "live_model": str,
  "best_match": {"file": str, "identity_matches": int, "identity_total": int},
  "ranked": [{file, identity_diffs: [...], hardware_diffs: [...], deployment_diffs: [...]}, ...],
  "verdict": "exact" | "closest" | "none"
}
```

`verdict: "exact"` requires **all identity flags** to agree. Hardware and
deployment differences never prevent `exact`, but are still listed.

### 4.4 CLI

```
python3 tools/node_facts.py --hardware [--node NAME]
python3 tools/node_facts.py --models
python3 tools/node_facts.py --match [--profile-dir DIR]
python3 tools/node_facts.py --all --json
```

Human-readable by default; `--json` for machine consumption. No writes.

---

## 5. Anti-goals

- Do **not** generate, tune or recommend profiles. Layer 3.
- Do **not** start, stop or restart any engine.
- Do **not** fetch anything from the web, including VRAM bandwidth.
- Do **not** modify `_NODE_REGISTRY` or `goethe_node.py`.
- Do **not** wake a sleeping node to probe it — report unreachable.
- Do **not** hash or read model file contents.

---

## 6. Tests — `tests/test_node_facts.py`

1. **Flag classification is total** — every flag in all four real profile
   files lands in exactly one class; an unknown flag defaults to *identity*
   (fail loud rather than silently ignore a difference that matters).
2. **Deployment differences never produce drift** — same profile, `--host`
   `0.0.0.0` vs `127.0.0.1`, still `verdict: "exact"`. Load-bearing:
   Hazard A.
3. **Identity difference downgrades to `closest`** — change `-m`, assert not
   `exact` and that the model appears in `identity_diffs`.
4. **Ranking picks the right file** among several similar profiles.
5. **BOM-prefixed file parses** — `ACTUAL-…gguf.md` has one.
6. **Unreachable node yields `reachable: false`**, never zeroed hardware.
   Load-bearing: Hazard C.
7. **Missing model root is `reachable: false`**, not an exception.
8. **Every fact carries its `source`** (`local-probe` / `ssh` / `documented`).

**Break tests 2 and 6, confirm red, restore.** Report what you saw.

---

## 7. Invariants

```bash
cd ~/projects/local-system-engineer
/home/sy5/owui/bin/python3 -m py_compile tools/node_facts.py
/home/sy5/miniforge3/bin/ruff check tools/node_facts.py tests/test_node_facts.py
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Baseline **728 passed**. Record ruff counts before/after.

Then run it for real against LUCIFER and report the output verbatim — this is
a facts tool, and its first real output is the acceptance evidence. If
node3090 is asleep, that is a valid and expected result: show it.

---

## 8. Report

`/tmp/node-facts-report.md`: what changed, before/after ruff and test counts,
break-and-restore results for tests 2 and 6, the verbatim first real run, and
anything in §2's ground-truth table that turned out wrong.

---

## 9. Housekeeping

- `tools/node_facts.py` is new and not mirror-watched, but the mirror is a
  full repo copy — copy it and the test file across.
- Commit on `codex/fix-sudo-grants-live`. Do not `git push`.
- Commit with `git commit -F <file>`; inline `-m` trips the privilege gate on
  this branch name.

---

## 10. Context

- Roadmap: `docs/ROADMAP-2026-08.md` §1b.
- Canonical profile examples: `/mnt/c/Goethe3.0/*.gguf.md`.
- Handover conventions: `docs/WORKFLOW-thread-handover.md`.
