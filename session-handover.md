# Session Handover — 2026-06-14 (P29 Cowork → P30)

> *"All that has been thought has already been thought; it is only a matter of thinking
> it again."* The difference between mere repetition and genuine rethinking lies in the
> context and purpose of the thinking. — the Goethe principle (see §The Goethe Ascension)

## State at end of P29

### Deployed / built versions

| Component | Version | Status |
|---|---|---|
| Tool | **Cogitator v1.7.21** | ✅ DEPLOYED — black-norm `79b74fde…` — sudo blocks now surface as a copyable ```bash fence in the visible reply (no longer memory-dependent) |
| Tool | **Cogitator v1.7.22** | 🟡 BUILT, NOT DEPLOYED — black-norm `142f155a…` — = v1.7.21 + inbox poll `max_tokens` 8→1024 (Path B marker fit). Deploy candidate for P30 |
| System Prompt | v0.5.15 | ✅ deployed |
| Routing Filter | v1.2.0 | ✅ deployed |
| Hermes channel skill | `hermes-skill/` | 🟡 BUILT + round-trip-verified offline; staged to node3090 `/tmp/lse-channel`; NOT self-installed |

### Verify deployed Cogitator v1.7.21
```bash
python3 -c "import black,hashlib; print(hashlib.sha256(black.format_str(open('tools/cogitator-v1.7.21.py').read(), mode=black.Mode()).encode()).hexdigest())"
# expect: 79b74fde5bb76131621c831635ac7d9225919e8c2dc3d8352eb9938a69918f7d
# v1.7.22 (deploy candidate): 142f155ac7dba7708b3fcb5d969224af2f789c96d5d8e28dddaed88608878116
```

### Cogitator lineage built P29 (cumulative on the P28 deploy v1.7.19, black-norm sha)

| Ver | black-norm sha256 | lines | What |
|---|---|---|---|
| v1.7.20 | `75ad4a6a…` | 4993 | sudo_delegation_block async + `__event_emitter__` force-surface (insufficient alone — emitted content lands in open `<think>`) |
| **v1.7.21** | **`79b74fde…`** | 5009 | sudo block → copyable ```bash fence + RETURN-directive forces the visible post-`<think>` reply. **DEPLOYED & confirmed** |
| v1.7.22 | `142f155a…` | 5015 | inbox poll `max_tokens` 8→1024 (Path B companion). **Deploy candidate** |

## What shipped in P29

- **sudo-block surfacing fixed (the long-standing "hidden in thinking / needs explicit ask" bug).**
  v1.7.20 (async emitter) proved insufficient — emitter content emitted mid-tool lands inside the
  open `<think>` and collapses. v1.7.21 routes the surface through the model's visible post-`<think>`
  reply via a return-value directive, and reformats the command as a copyable ```bash fence.
  **Live-confirmed working by SY5.**
- **Hermes↔LSE channel — producer side built** (`hermes-skill/`): `SKILL.md` (lse-channel,
  agentskills.io format) + `lse_channel.py` (atomic JSON outbox: enqueue/flush/reply) + `INSTALL.md`.
  Round-trip **verified offline** against the LSE's exact parser (`_extract_content_marker` →
  `_format_hermes_messages`). Companion LSE fix v1.7.22 raises the poll `max_tokens` so a Path B
  marker fits. **Channel finding (live):** small messages round-trip; large payloads (full ssh logs)
  overflow the reply token cap and truncate the JSON marker → must go BY REFERENCE.
- **Bench re-frozen + Condition A baseline.** `lse-bench-v1` now 1 valid challenge (node-t3-006;
  003/004 dropped — no actuation block; 24 self-report excluded). Condition A (eval, learning off):
  **1/1 SOLVED, 21.0 pts** — `verify_ssh` caught a false self-report on A2 (model claimed success,
  ground truth failed it attempt 1). Eval seal confirmed (no leaderboard / KB write).
- **ctx-size 81920 confirmed universal canon** (4090 + node3090). socat/96000 doc ghosts swept:
  discarded stale socat WIP in LSE-ARCHITECTURE/ROADMAP; documented node3090 gateway `:8642` direct.
- **Docs/safety:** `docs/kv-cache-vq4-128k-experiment.md` (KQ8/VQ4 @ 128k test plan),
  `docs/node-t3-003-004-rebuild-spec.md`, `backups/` (v1.7.19 rollback + `ROLLBACK-cogitator.md`).

## Commit status — ALL P29 WORK COMMITTED (master)

| Commit | What |
|---|---|
| `44e8d31` | P28 (actuation layer, v1.7.15-19, WATERFALL, SearXNG, Firecrawl) |
| `3dfa8e3` | P29 core (v1.7.20-22, hermes-skill, bench Condition A, doc stamps, rollback backup) |
| `f06df3e` | kb session learnings |
| `e038b48` | architecture: node3090 gateway :8642 direct |

Working tree is **clean**. Commit from WSL2 only.

## Open threads (carry to P30, priority order)

1. **Deploy Cogitator v1.7.22** to OWUI Admin → Tools (verify black-norm `142f155a…`). Rollback =
   `backups/cogitator-v1.7.19-DEPLOYED-20260614.py` per `backups/ROLLBACK-cogitator.md`.
2. **Hermes self-installs the lse-channel skill** — files staged at node3090 `/tmp/lse-channel/`.
   Tell Hermes (via its interface) to install `SKILL.md` via `skill_manage` + copy `lse_channel.py`
   to `~/.hermes/bin/` (see `hermes-skill/INSTALL.md`). Then **live-test the loop**: enqueue a test
   message on Hermes, run `check_hermes_inbox` on the LSE → expect "HERMES → LSE (inbound)".
   Watch: gateway clipping the reply to `max_tokens`; Hermes reliably prepending the flush marker.
3. **Add the by-reference convention** to lse-channel for large payloads (Hermes writes a file,
   envelope body carries the path, LSE fetches via `execute_command` SSH — node3090 SSH now fixed).
   Small messages already work; this fixes the large-log truncation.
4. **Rebuild node-t3-003/004** per `docs/node-t3-003-004-rebuild-spec.md` (actuation block, a4 →
   `:8642` direct, allow_sudo `systemctl restart`, ctx 81920). BLOCKED on confirming node3090 has a
   `llama-server` systemd unit with canonical flags in ExecStart (else use a gate-clean `/opt`
   start-script). Then re-seed + re-freeze (bench grows to 3 valid).
5. **Grow the bench** toward the 3-way McNemar instrument: convert the 24 self-report challenges to
   `verify_ssh`-backed ground truth.
6. **Small guard:** docstring nudge so `check_hermes_inbox` empty doesn't make the LSE confabulate
   filesystem paths — it should say "channel requires the Hermes outbox; not installed."

## Ground rules (do not forget)

- **LARGE .py ON NTFS: USE BASH.** Never Write/Edit tools for `.py`. Splice + `ast.parse` + line tally.
- **.md files: use Read/Write/Edit file tools** (HOST), NOT sandbox bash. The sandbox mount serves
  STALE reads of existing repo files (P29: it showed LSE-ARCHITECTURE.md socat-free while the real
  working tree had the uncommitted socat block). Trust host tools + WSL2 git for existing files;
  bash WRITES of NEW files are fine.
- **Deploy identity = black-norm sha** (`python3 -m black …`), not raw sha — OWUI black-formats on save.
- **Sudo/surfacing:** OWUI `__event_emitter__` content emitted mid-tool lands in the open `<think>`
  and collapses. Surface via the model's post-`<think>` reply (return-directive), not the emitter.
- **Hermes inbox is empty until the producer (Hermes outbox) is installed** — that is correct, not a
  bug. Large payloads go by reference (file + SSH), not inline (token cap truncates the marker).
- **Valve UI overrides wiped on redeploy** — fixes live in source Valves defaults.
- **K cache stays Q8_0** — model breaks below; V is the only lever (VQ4 @ 128k experiment pending).
- **Git commits from WSL2/PowerShell**, never the sandbox. Lock recovery: `Get-ChildItem ".git\*.lock" | Remove-Item -Force`.
- **SearXNG**: edits go to repo canonical `docker/searxng_data/settings.yml`; the guard enforces it.

## Infrastructure state at end of P29

| Component | State |
|---|---|
| llama-server LUCIFER | Qwen3.6-27B-Q4_K_M · :8080 · the bare model the Challenge Arena tests · ctx canon 81920 |
| node3090 | llama-server :8080 (Hermes backend) · Hermes gateway :8642 (0.0.0.0 direct, socat eliminated P27) · Firecrawl :3002 + SearXNG :5580 · SSH access fixed (P29) |
| Hermes | Hermes Agent (Nous Research), gateway :8642, hermes-admin@node3090 · web_search → local Firecrawl ✅ · **lse-channel producer skill staged, not yet installed** |
| Challenge Arena | actuation layer live · lse-bench-v1 frozen (1 valid: node-t3-006) · Condition A baseline recorded (1/1, 21.0 pts) |

## The Goethe Ascension

The tool is named **Cogitator** — *one who thinks*. It becomes **Goethe** when the LSE can write
its own skills and wield the RAG knowledge base with high competence, and is demonstrably better for
it — specifically **surpassing Hermes by a good margin**. The gate is the **3-way McNemar test
(LSE agent vs Hermes vs raw Qwen3.6-27B)** on the frozen bench. The freeze + Condition A baseline
built in P28–P29 is the instrument that will measure the ascension; it currently holds **one** valid
challenge, so the near-term work (open threads 4–5) is growing the bench to statistical power. The
path runs through ROADMAP 1.7.0-c (lse-skills ES index, episode distillation, retrieval gold set,
hybrid BM25+kNN) and 1.7.0-d (occupational curriculum, skill lifecycle, learning-lift run #1).
