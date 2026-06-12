# LSE session handover — P20 (2026-06-11)

## Stack state (verified end of session)
- llama-server on node3090: PID 40769, healthy, canonical model restored **byte-exact**
  (sha256 33625d8d... matches HF LFS; size 16547398784)
- hermes-gateway + hermes-socat: active; `TimeoutStopSec=210s` fix applied (SIGKILL-mid-drain bug fixed)
- Hermes knows LSE: SOUL.md "## Principals" section installed and verified via fresh Telegram session
  (`/new` required — SOUL.md is read at SESSION START only; frozen snapshot per hermes-agent docs)
- lse-admin is in the sy5 group on node3090 (group write on /opt/models — WRITE-OK verified)
- Leaderboard: 35 episodes (#32–35 were node-t3-005, all TRUNCATED 2/4 — see incident)
- "Hermes Restart Procedure" KB entry: SY5 was about to have LSE index it (verify it landed:
  `search_kb('Hermes not responding Telegram')` should hit it)

## THE BIG EVENT — read `docs/incident-2026-06-11-model-deletion.md` first
A "duplicate model cleanup" deleted the ONLY copy of node3090's GGUF: the two paths were
one inode (`/opt/models/lmstudio-community` is a SYMLINK into `~/.lmstudio/models/`).
Recovered byte-exact via Hermes-initiated aria2c from HF. Zero downtime. Four systemic
findings came out of it:
1. **Episode harness has no actuation path** — run_episode.py calls llama-server bare;
   model commands (even native tool_calls JSON, observed ep#35) are never executed;
   verify_ssh overrides self-report → write challenges are deterministic failures.
2. **KB carried a false premise at high quality** (the "duplicate" never existed).
3. **Symlink-aliased model store** made path-based safety checks meaningless.
4. **Verification steps weren't read-only by construction.**

## Open items (priority order)
### 1. [P0] Model store reconciliation — node-t3-006 (roadmap, post-incident)
One real `/opt/models/` per node, NO symlinks. node3090: migrate files out of
`~/.lmstudio/models/`, kill the symlink farm, update --model path + KB + LM Studio config.
Then `chattr +i` every gguf (immutable; human `chattr -i` to delete). Record sha256 per
model in launch KB. node-t3-005 should be marked retired in challenges.db:
`sqlite3 /opt/local-se/challenges.db "UPDATE challenges SET status='retired' WHERE id='node-t3-005';"`

### 2. S0 hygiene (docs/self-learning-trajectory.md)
- Purge 4+ junk `web-search: node-t3-005` ES docs (quality 0.7, stagnation queries, eps #32–35)
- Gate auto-indexing in escalation_wrapper.py (cosine ≥0.6 vs challenge, default quality 0.4)
- Hand-write skill #1 — now includes the inode rule: before deleting any "duplicate",
  readlink -f + stat '%i %h' BOTH paths; verify survivor (size+sha256) BEFORE rm

### 3. 1.7.0-a — episode actuation layer (P0 for the whole bench program)
Env must execute model-emitted commands (parse tool_calls JSON and/or command blocks) via
SSH with the tool's safety gates ported. Then: --eval --no-learn flag, freeze lse-bench-v1,
record Condition A baseline. Full order of operations: docs/self-learning-trajectory.md S0–S6.

### 4. node5090 (NODE3) deployment — when 1BL15 is ready
Kit complete: `scripts/node5090/{deploy,provision,teardown}` + `docs/node5090-deployment-design.md`.
pfSense DHCP+DNS already live (a0:ad:9f:84:d5:bf → 192.168.1.55, node5090.home.arpa).
Before first run: drop LUCIFER pubkeys at /tmp/authorized_keys.{lse-admin,sy5} in the distro.
Remaining external: Prometheus scrape targets on LUCIFER.

### 5. Housekeeping
- VERSION.md says tool v1.6.1; tools/ has v1.6.4 — reconcile
- session-learnings.md appends: P20 main entry + incident addendum + restart-order facts
  (commands were provided in-session; verify they landed: `tail -60 /opt/local-se/kb/session-learnings.md`)
- OWUI "NetworkError" frontend disconnect + LSE acting after UI detach — investigate with
  the 16-tool-call limit (both OWUI session-layer)
- Hermes: firecrawl pip failure (externally-managed-environment), no SSH key to node3090 (by
  design? decide), agent background jobs (aria2c as hermes-admin) invisible to lse-admin pkill

## New documents this session (all in repo)
- `docs/lse-1.7.0-design.md` — Hermes peer protocol · self-learning skills · LSE-bench · 35B-A3B delegation
- `docs/self-learning-trajectory.md` — execution order S0–S6 (incl. SOUL.md curation discipline §5.4)
- `docs/node5090-deployment-design.md` + `scripts/node5090/` — full deploy/teardown kit
- `docs/incident-2026-06-11-model-deletion.md` — postmortem with action items
- `kb/hermes-kb-lse-relationship.md` — full LSE entry (SOUL.md got the short version)
- `scripts/seed_node_t3_duplicate_cleanup.py` — retired with its challenge; keep as verify_ssh reference

## Hard-won facts (do not rediscover)
- hermes-agent: SOUL.md = system-prompt slot #1, loaded at session start, 20k char cap;
  durable facts belong in its memory tool; ALWAYS test SOUL changes in a NEW session
- Stack restart order: llama-server first → poll nvidia-smi for VRAM release (never fixed
  sleep) → canonical launch → poll /health ≤3min → `systemctl reset-failed hermes-gateway` → start
- execute_command blocks "sudo" as substring (even remote via ssh) and rm/cp/mv targeting
  /etc /usr /boot /sys /proc /mnt; /opt is NOT in the privileged list
- agent_commands.log = ground truth for what LSE actually ran; episodes never appear in it
- HF LFS reference hash: `curl -s https://huggingface.co/<repo>/raw/main/<file>` → oid sha256 + size

## Key paths (unchanged)
- run_episode.py: /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/scripts/run_episode.py
- challenges.db: /opt/local-se/challenges.db · leaderboard: /opt/local-se/leaderboard.db
- session-learnings KB: /opt/local-se/kb/session-learnings.md
- node3090: ssh lse-admin@192.168.5.41 · audit log: /opt/local-se/agent_commands.log
- LSE tool: tools/openwebui-tool-v1.6.4.py

## Read before starting
1. docs/incident-2026-06-11-model-deletion.md
2. cat /opt/local-se/kb/session-learnings.md | tail -80
3. ROADMAP.md — "Immediate — P20 Active" + v1.7.0 sections
