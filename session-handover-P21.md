# Session Handover — P21 (2026-06-12, closed ~02:30 CEST)

## State: GREEN, committed (bc1ce88 + 5c06628)

- **node3090 stack**: llama-server healthy via THE canonical launch — `/opt/local-se/scripts/start-llama-server.sh`
  (model `/opt/models/...Qwen3.6-27B-Q4_K_M.gguf`, ctx 81920, q8_0 KV both, threads 7/7, ub/b 512/2048 — benchmarked,
  log `/home/lse-admin/llama-server.log`). hermes-gateway + hermes-socat active; gateway has TimeoutStopSec=210s drop-in.
  `Restart _Hermes.md` step 2 calls the script — edit the script, never inline commands.
- **Model store**: `/opt/models` is a REAL dir, 18 .gguf `chattr +i` (human `chattr -i` before any replace),
  sha256 in `/opt/models/SHA256SUMS` + `kb/node3090-model-sha256sums.md`.
- **KB**: ONE real dir = repo `kb/` (`/opt/local-se/kb` is a symlink to it). lse-kb index: 132 docs (77 file + organic),
  duplicate-free. Reseed procedure: `kb/kb-reseed-procedure.md` (indexed — LSE can search_kb it).
- **ES**: all 4 indices standing (lse-kb, lse-errors, lse-search-cache, lse-rfc-kb 628 chunks/13 RFCs/tagged).
- **Hermes**: carries the LSE-relationship KB in persistent memory (installed via its own memory tool; verified via Telegram).

## Open items (see ROADMAP P21 follow-ups for detail)

1. LM Studio repoint on node3090: My Models → models directory → `/opt/models` (still pending).
2. `search_rfc` triggering review: wired since v1.5.18, 0 calls in 44,637 commands — docstring/prompt problem
   (use lse-docstring-optimizer) or retire the RFC KB.
3. Add ES index-existence probe to stack health check: `curl -s localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache/_count`.
4. node-t3-006 challenge design (model store reconciliation w/ inode assertions); v1.7.0-a actuation layer; VERSION.md reconcile.
5. PS7 DispatcherTimer + Ollama GPU overhead learnings confirmed LOST (never written) — rewrite from memory if still relevant.

## Operating rules (paid for tonight — full detail in kb/session-learnings.md 2026-06-11/12 entries)

- ONE operator at a time on the stack: if LSE is mid-maintenance, no parallel WSL commands (and vice versa).
- Agent self-reports ≠ ground truth: verify with pgrep/curl/systemctl before acting on any "it's healthy/done".
- `pkill -f X` in SSH one-liners: bracket the pattern (`"[X]..."`) or it kills the session itself.
- Cowork sandbox: cannot reach 192.168.x.x (all node ops via user's WSL terminal); cannot mount WSL UNC paths —
  and ATTEMPTING the mount poisons sandbox bash for the whole session (file tools keep working).
- LSE execute_command: 30s timeout, /opt/ writes blocked — long/privileged jobs get delegated to the human with
  a ready-to-paste nohup command.
- Git from WSL only; repo is `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer` (`~/projects/...` is a symlink, not a clone).
