# TRAUM Operator's Manual

> Audience: the LSE operator. Covers day-to-day operation of the nightly
> dreaming loop. Installation, acceptance history, and design rationale live
> elsewhere — see [§8 Related documents](#8-related-documents).
> Verified against the live system 2026-07-17.

---

## 1. What TRAUM is, in one paragraph

TRAUM is the LSE's overnight reflection loop. During the day, every tool call
is journaled to an episode file (redacted at write time, capped at 2,000 chars
per result). At night — 03:30 ± 15 min — a systemd timer runs five analysis
passes over the accumulated corpus using the local model. The passes emit
**proposals, never writes**: nothing reaches Elasticsearch or the KB without
your explicit per-proposal yes through `dream_apply.py`. Your morning cost is
about 5 minutes; the payoff is a KB that curates itself instead of silting up.

## 2. The mental model — what can and cannot happen

Hard invariants, enforced in code (not prompts), covered by contract tests:

- A dream **proposes**; only you **apply**. `DREAM_AUTO_APPLY` is empty and
  stays empty (the 2026-07-14 A/B eval returned a LOSS verdict — see
  `eval/eval-report-traum-1.md` — so no proposal type has earned auto-apply).
- A dream can never raise `quality`, never write `source_tier=ground_truth`,
  never touch quarantined docs except to propose deletion to you.
- Every dream-applied write is stamped `origin=dream` +
  `provenance=dream-YYYY-MM-DD` — always traceable back to its run (§5.4).
- The dreamer's own tool calls never enter the corpus (no dream-of-dreams).
- Nothing is ever deleted — quarantine and expiry only (KB-DECAY rule).
- Episodes and the audit log are redacted **at write time**
  (`tools/redact.py`, deployed 2026-07-17): vendor-prefix keys, CLI
  credentials, env assignments, URL query params, Bearer/JWT shapes.

If a proposal ever looks like it violates one of these, do not apply it —
file it to `lse-errors` and treat it as a validator bug.

## 3. The five passes

| Pass | Reads | Proposes |
|---|---|---|
| `dedup` | `lse-kb` embeddings | merge near-duplicate docs (keeps higher quality, unions trust stats) |
| `stale-contradiction` | KB TTLs + recent episodes | `reverify` probes for TTL-expired docs; `demote` (with verbatim evidence) where a session disproved a doc |
| `error-cluster` | `lse-errors` + failed episodes | skill candidates for error patterns seen ≥3 times across ≥2 sessions |
| `patterns` | `agent_commands.log` (mechanical, no LLM) | frequency/retry/repeated-sequence stats → `patterns.json` |
| `insights` | `patterns.json` + session summaries | KB facts, skills, or `prompt-rule` additions to `prompts/learned-rules.md` (never the canonical prompt) |

A pass that finds nothing emits an explicit null record — "nothing there" is
distinguished from "didn't look."

## 4. Daily operation

### 4.1 The morning review (≈5 minutes)

The `[DREAM]` banner on your first `search_kb`/`time_check` of a session shows
the digest date and pending-gate count. If pending > 0:

```bash
# 1. What happened overnight (≤30 lines)
cat /opt/local-se/dreams/latest-digest.md

# 2. Everything waiting on you (oldest first, grouped by type;
#    proposals >14 days auto-expire with reason on this call)
cd /home/sy5/projects/local-system-engineer
/usr/bin/python3 tools/dream_apply.py --queue

# 3. Review a batch — per-proposal yes/no, invariants validated regardless
/usr/bin/python3 tools/dream_apply.py \
  --proposals /opt/local-se/dreams/<date>/proposals-<pass>.jsonl --no-dry-run
```

**Gate fatigue is a named threat** (threat model §gate-fatigue): if you catch
yourself rubber-stamping, stop — an unreviewed apply is worse than an expired
proposal, because re-dreaming will re-propose anything still true.

### 4.2 What a normal night looks like

```bash
journalctl -u goethe-dream --no-pager -n 50
```

Three healthy outcomes:

- **Ran** — five `[dream_runner] done` lines with proposal counts, digest
  refreshed. Proposals wait in the queue.
- **Skipped** — `SKIPPING run (pass=…): session '…' was active N min ago`.
  The 30-minute live-session guard refused to dream while you (or any gateway
  session) were active. This is correct behavior, not a failure. If you
  routinely work past 03:00, expect skips; the corpus just carries over.
- **Budget-truncated** — a truncation note in the report. Budgets (45-min
  wall clock, session/LLM-call caps) exhausted normally; partial results are
  kept, unconsumed sessions re-dream tomorrow.

## 5. Occasional operations

### 5.1 Timer health

```bash
systemctl list-timers goethe-dream.timer --no-pager  # NEXT ≈ 03:30–03:45
systemctl status goethe-dream.timer --no-pager       # enabled, active (waiting)
sudo systemctl start goethe-dream.service            # fire a cycle by hand
```

A daytime hand-run will usually be (correctly) refused by the session guard;
`dream_runner.py --ignore-guards` overrides it for a single supervised run.

### 5.2 Failed nights

A crashed pass writes `report-<pass>.md` with a `## FAILED` banner, appends
`crashes.jsonl` in the day-dir, files a `record_error`
(context=`dream-runner`), and leaves sessions un-consumed for safe re-dream.
The timer keeps firing (`Restart=no`). **Three consecutive failed nights
escalates in the digest header** — that banner means read the newest
`crashes.jsonl`:

```bash
tail -1 "$(ls -t /opt/local-se/dreams/*/crashes.jsonl 2>/dev/null | head -1)"
```

A dead runner's lock self-expires (4 h, PID liveness-probed). Manual clear
only if the PID inside is dead:

```bash
cat /opt/local-se/dreams/.dream.lock
rm /opt/local-se/dreams/.dream.lock
```

### 5.3 Re-dreaming a session

```bash
sqlite3 /opt/local-se/episodes/manifest.db \
  "UPDATE sessions SET dreamed_at=NULL WHERE session_id='<session_id>';"
# then wait for tonight, or run one pass supervised:
/usr/bin/python3 tools/dream_runner.py --pass <pass> --no-dry-run --ignore-guards
```

### 5.4 Tracing a KB doc back to its dream

```bash
curl -s "http://127.0.0.1:9200/lse-kb/_search" -H 'Content-Type: application/json' \
  -d '{"query":{"term":{"origin":"dream"}},"size":10,"_source":["title","provenance","origin"]}'
```

The provenance date names the day-dir: `report-<pass>.md` is the WHY,
`proposals-<pass>.jsonl` the exact call, `applied.jsonl` your yes,
`rejected.jsonl`/`expired.jsonl` everything that didn't land, with reason.
(Day-dirs before 2026-07-13 use legacy shared `report.md`/`proposals.jsonl`.)

### 5.5 After changing gateway code

The HTTP gateway (`:9700`, serves llama-ui) loads `goethe.py`/`goethe_mcp.py`
at start: run `bash tools/start-goethe.sh` (its kill pattern only touches the
HTTP instance) and start a **fresh llama-ui thread**. Cowork stdio gateway
instances keep old code in memory until their session ends — a patch is not
fully live until both have cycled.

## 6. Troubleshooting quick table

| Symptom | Likely cause | Action |
|---|---|---|
| Digest says "no applied.jsonl" every day | Morning review not being run | §4.1 — queue is accumulating; >14 days silently expires |
| Every night skips | Sessions active at 03:30+ (guard window 30 min) | Normal if you work late; check `journalctl` for the session id it saw |
| FAILED banner in digest header | 3 consecutive crashed nights | §5.2 — read `crashes.jsonl`, file/inspect the lse-errors record |
| Proposals look wrong en masse | Endpoint fell back to CPU/small model, or corpus contamination | Check report header for the endpoint used; spot-check episode files |
| `[DREAM]` banner missing at session start | Gateway restarted without fresh thread, or digest never generated | §5.5; `ls -la /opt/local-se/dreams/latest-digest.md` |
| Retrieval metrics regress after applies | Bad merge/demote landed | Stop applying; compare `run_tests(scope=retrieval)` before/after; trace via §5.4 and demote/reverify |

## 7. Configuration reference (env vars, all optional)

| Valve | Default | Purpose |
|---|---|---|
| `GOETHE_EPISODE_DIR` | `/opt/local-se/episodes` | Journaling root; empty string disables journaling |
| `DREAM_DIR` | `/opt/local-se/dreams` | Runner output root |
| `DREAM_LLM_URL` | (empty) | Force dreamer endpoint; falls through node3090 llama-server → Ollama |
| `DREAM_AUTO_APPLY` | (empty) | Per-type auto-apply allowlist — **keep empty** (eval LOSS, §2) |
| `DREAM_RUNNER_SESSION_PREFIX` | (empty) | Exclude sessions by id prefix (no dream-of-dreams) |
| `DREAM_DEDUP_FLOOR` | `0.75` | Dedup candidate-pair cosine floor |
| `GOETHE_REDACT_SECRETS` | `true` | Write-time redaction master switch — never disable in production |

Full registry with per-valve notes: `VALVES.md` §dreaming.

## 8. Related documents

- `docs/07-operations-runbook.md` §10 — canonical procedures incl. timer
  install/reconcile (10.2) and the KB-entry refresh prompt (10.8)
- `docs/dreaming/DESIGN.md` — architecture invariants, schema, decision log
- `docs/threat-model-kb.md` — dream-path threat model and mitigation→test map
- `docs/traum-dreaming-plan.md` — implementation history and prompt ledger
- `eval/traum-ab-design.md`, `eval/eval-report-traum-1.md` — the pre-registered
  A/B eval and its LOSS verdict
- `kb/secrets-propagation-report.md` — redaction deployment history and
  credential rotation checklist
