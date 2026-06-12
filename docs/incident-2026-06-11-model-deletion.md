# Incident Postmortem — node3090 Model File Deletion (2026-06-11, P20)
> Severity: HIGH (single point of recovery; no user-facing outage — llama-server never went down)
> Status: RECOVERED (pending final restart verification)

## Timeline (all 2026-06-11)
- ~13:00 — Session handover states: "Duplicate GGUF exists at /opt/models/... (~15GB, stale). Canonical: /home/sy5/.lmstudio/..." — **this premise was false** (see Root Causes).
- 18:2x–22:2x — Episodes #32–35 (node-t3-005) all TRUNCATED 2/4; investigation reveals the episode harness has no actuation path (separate finding, v1.7.0-a).
- 22:32:51 — Interactive LSE chat session executes `rm -v /opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf`. Because `/opt/models/lmstudio-community` is a **symlink to `/home/sy5/.lmstudio/models/lmstudio-community`**, this deleted the ONLY copy (16,547,398,784 bytes).
- 22:33–22:36 — LSE detects the canonical path empty, concludes (incorrectly) "the file never existed", escalates to Hermes.
- 22:36–22:39 — Two recoveries start in parallel: Hermes launches `aria2c` from HF (→ `/home/hermes-admin/tmp_dl/`); LSE finds a local copy on LUCIFER (`/home/sy5/models/Qwen3.6-27B-Q4_K_M/`, 17,984,872,960 bytes — a different build) and starts scp. OWUI frontend shows "NetworkError" but backend actions continue.
- 22:4x — Claude-guided triage initially kills LSE's in-flight scp and rm's its partial destination (wrong call — based on the assumption the partial was a junk HF download). map_files analysis proves the canonical inode was mmapped by the running server and is "(deleted)" — server stays up on VRAM throughout.
- 22:47 — Hermes's aria2c completes: **exact original size 16,547,398,784** — the chosen restore source. LUCIFER scp also completed (wrong build, replaced).
- 23:0x — Original-size file verified vs HF LFS sha256, swapped into canonical path, controlled restart, health ok. ~15.4GB of deleted-inode space released on restart.

## Root causes (ordered)
1. **False KB/handover premise at high confidence.** "A duplicate exists" was never verified at the inode level. The two paths were one file via symlink. Every downstream action trusted this premise.
2. **No inode verification before deletion.** Every safety check (running-process path, file sizes, health) passed because both paths resolved to the same healthy file. The ONLY check that would have caught it: `stat -c "%i %h"` + `readlink -f` on BOTH paths — duplicate means *distinct inodes with identical content*, not two names.
3. **Symlinked model store.** `/opt/models/*` on node3090 is a symlink farm into `~/.lmstudio/models/`. Path aliasing made "delete the copy at path A, keep path B" a logical impossibility that looked safe.
4. **Episode harness gap (contributing).** Four episodes burned on an unactionable challenge delayed scrutiny of the premise itself.
5. **Verification steps weren't read-only by construction (contributing).** The same chat session that verified also deleted; later, triage instructions killed a healthy recovery transfer.

## What went right
- llama-server never dropped — mmap'd model in VRAM survived the entire incident.
- LSE↔Hermes protocol worked under fire: notify → acknowledge → urgent escalation → Hermes autonomously executed the correct recovery (aria2c, correct repo, correct file, landed byte-exact).
- The audit log (`agent_commands.log`) made the full forensic timeline reconstructable in minutes.
- Multiple independent recovery sources existed (HF, LUCIFER local build).

## Action items
| # | Action | Where |
|---|---|---|
| 1 | **Cluster-wide model store reconciliation** (SY5 directive): every node gets ONE real directory `/opt/models/` — no symlinks, no `~/.lmstudio` aliasing. node3090 migration: move real files from `~/.lmstudio/models/` into `/opt/models/`, delete the symlink farm, update `--model` paths, KB, and LM Studio config. node5090 already specified this way (design §3) | new roadmap item |
| 2 | **Immutable bit on model files**: `sudo chattr +i /opt/models/**/*.gguf` after placement. Deletion then requires a deliberate human `chattr -i` first — agents physically cannot rm a model file. Add/remove steps documented in each node's launch KB | reconciliation plan |
| 3 | **Skill #1 rewrite** (trajectory S0.3): "duplicate file cleanup" procedure MUST begin: (a) `readlink -f` both paths; (b) `stat -c '%i %h'` both — proceed only if inodes differ; (c) verify survivor integrity (size + sha256) BEFORE deleting; (d) verification steps are read-only by construction | `kb/skills/` |
| 4 | Challenge premises require ground-truth verification at seed time — a `starting_state` claim like "duplicate exists" gets a `verify_ssh` precondition probe that runs at episode reset and ABORTS the episode if false | lse_challenge_env v2 |
| 5 | Record sha256 of every model file in the node's launch KB at deploy time — recovery tonight had no reference hash and had to lean on HF LFS metadata | KB convention |
| 6 | OWUI "NetworkError" + post-disconnect autonomy: LSE continued acting after the UI detached. Investigate session-layer timeout; consider a tool-side halt when the chat stream is gone | GUI & Stack backlog |
| 7 | Hermes recovery debrief: aria2c ran as hermes-admin, invisible to lse-admin's pkill — agent-launched background jobs need an ownership/registry convention | Hermes protocol (1.7.0-b) |

## Measured outcome
- Data loss: none (restored byte-exact from HF).
- Downtime: zero.
- Disk: net unchanged (~739G used after cleanup — the "15GB to free" never existed).
- node-t3-005: challenge retired as designed — premise was false. Replace with `node-t3-006`: "Model Store Reconciliation" implementing action items 1–2, with inode-level assertions.
