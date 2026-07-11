# TRAUM Corpus Audit — Thread 1 Prep

> Read-only survey of the four memory surfaces named in `docs/traum-dreaming-plan.md` §1
> ("the evidence is already on disk"). No writes made outside this file.
> Run 2026-07-11, against the live system (figures for `agent_commands.log` and
> `tasks.db` are moving targets — this session's own commands are landing in both
> as the audit runs).

---

## (a) `/opt/local-se/agent_commands.log`

**Size / count:** 134,251 lines at time of audit; ~25,257 `CMD` entries (paired with
~24,436 `DONE` entries — the gap is in-flight/unterminated commands, mostly from
process interruptions). Line count is climbing live during this session.

**Date range:** 2026-05-23 22:12:51 → present (2026-07-11), continuous, ~7 weeks.

**Format eras — two, not one:**

1. **Bootstrap block format** — exactly 2 lines total, both at the very start of the
   log (2026-05-23 22:12:51–22:12:57), before the logger switched formats mid-session:
   ```
   [2026-05-23 22:12:51] ▶ COMMAND
     cmd : find /home/sy5/ -name "Qwen3.6-27B-Q5_K_M.gguf" 2>/dev/null
     cwd : /home/sy5
   ────────────────────────────────────────────────────────────

   [2026-05-23 22:12:57] ✔ OK RESULT
   (no output)
     truncated: False
   ────────────────────────────────────────────────────────────
   ```
   This era is a rounding error (2 of 134,251 lines) and can be ignored or hand-skipped
   by any parser rather than special-cased.

2. **Compact tag-line format** — everything from 2026-05-23 23:15:11 onward (99.998%
   of the log). One event per line: `[YYYY-MM-DD HH:MM:SS] TAG: detail (cwd=...)`,
   commands paired with a following `DONE rc=<n> len=<n>` line. 46 distinct tags
   observed beyond CMD/DONE — SEARCH (2,818), READ (1,336), WRITE (1,147), PFSENSE (873),
   FETCH (773), TIMEOUT (766), SUDO (514), INDEX (249), TASK (241), CTX (216), WAKE (179),
   DEVICE (168), MENTOR (155), PRIV (134), PLAN (104), RECORD (102), HARD (88), NODE (80),
   SKILL (77), GITHUB (75), HERMES (72), SNAPSHOT (69), CHECK (61), START (48), BG (46),
   BUDGET (39), SHUTDOWN (36), DOWNLOAD (35), STOP (30), ERROR (26), QUERY (23), ASSERT (22),
   NMAP (20), REDDIT (16), RUN (14), KANBAN (10), PLANNER (8), COOP (8), VERIFY (2), SIZE (2),
   NETDISC (2), TIME (1), KB (1), CAMOUFOX (1). Samples:
   ```
   [2026-05-24 03:32:48] SEARCH: llama.cpp latest stable release version 2025 max=5
   [2026-05-24 02:35:30] READ: /etc/sysctl.conf lines=0..100
   [2026-05-24 02:33:19] WRITE: /tmp/lse/hello.txt mode=overwrite len=18
   [2026-05-25 01:48:52] ERROR: 'utf-8' codec can't decode byte 0xda in position 223: invalid continuation byte
   [2026-06-04 05:41:41] PFSENSE: GET https://pfsense.home.arpa/api/v2/status/logs/firewall
   ```

**Corpus readiness verdict — agent_commands.log:** READY for Thread 3 (TRAUM-INSIGHT)
cross-session mining as-is. Single stable format covers 99.998% of the corpus; the
bootstrap-era 2 lines are trivially skippable. 46 tag types give the miner clean
event-type filtering for free. Caveat: the file is unrotated and growing (9.4MB now);
a dream pass should windowed-read (date range or tail -N) rather than load whole-file.

---

## (b) `/opt/local-se/tasks.db`

**Schema — single table, no joins needed:**
```sql
CREATE TABLE task_blocks (
  task_id TEXT PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL,
  plan TEXT, done_steps TEXT, findings TEXT, unverified TEXT,
  next_prompt TEXT, checkpoints INTEGER DEFAULT 0,
  created_at TEXT, updated_at TEXT, steps_json TEXT
);
```

**Row counts:** 80 tasks total. Status: 44 `open`, 35 `done`, 1 `abandoned`.
Date range: 2026-06-12 → 2026-07-11 (created_at).

**Field population — this is the key finding:** `plan` (free-text) is populated on
73/80 rows (91%); `steps_json` (structured planner-v2 format) is populated on only
17/80 rows (21%). The two are not consistently either/or — some rows have both.
This means any dream/mining pass over task history has to handle two representations
of "the plan," one of which (steps_json) is a minority format that only recent tasks use.

**`steps_json` shape** (sampled from task `fc795f1f`, a real completed task — "Integrate
3 API-only CodeScene MCP tools into offline build"): a JSON array of step objects, each
with `n` (int), `what` (str), `depends_on` (array of step numbers), `inputs` (str),
`output` (str), `web_calls`/`tool_calls` (int), `verify` (a shell command or check
string), `packaged_prompt` (the full instruction text handed to the executing agent),
`status` (`done`/etc.), `evidence` (free text describing what was actually observed),
and `done_at` (ISO timestamp). Every step in the sample carries per-step evidence tied
to a verify command — this is exactly the "per-step evidence and failure routes" the
plan doc promises, but only for the 21% of tasks using steps_json.

**Corpus readiness verdict — tasks.db:** PARTIALLY READY. Structure is clean (one
table, no schema drift), and where steps_json exists it's rich and well-shaped for
mining (verify/evidence pairs per step are gold for a dream pass looking for
failure-route patterns). But 79% of tasks only have the free-text `plan`/`done_steps`/
`findings` fields, which need an LLM read rather than structured parsing — Thread 2's
`dream_runner.py` will need two code paths (structured steps_json walk + free-text
summarization) or accept degraded coverage on 63/80 tasks.

---

## (c) Elasticsearch indices — `lse-kb`, `lse-errors`, `lse-skills`

(Also present but out of scope per the prompt: `lse-rfc-kb` (628 docs) and
`lse-search-cache` (0 docs, all green health).)

### `lse-kb` — 234 docs, 3.5MB
Mapping (selected fields): `content`/`title` (text), `doc_id`/`filename` (keyword),
`embedding` (dense_vector, 768-dim, cosine, int8_hnsw), `quality_score` (float),
`stale` (boolean), `volatility` (keyword), `source_tier`/`source_url`/`source_path`,
`topic` (keyword), `tags`, `version` (long), `refinement_count`, `success_count`/
`consecutive_failures`, `mentor_corrected_at`/`mentor_demoted_at`, `verified_against`,
`created_at`/`updated_at`/`indexed_at`.

Quality distribution (`quality_score`, 234/234 docs populated): min 0.20, max 1.00,
avg 0.71. Histogram is bimodal-ish with clusters at 0.5 (44 docs), 0.6 (64 docs), 0.8
(66 docs), 1.0 (26 docs) — a thin middle at 0.7 (only 3 docs) suggests scores cluster
at round decision points rather than a smooth distribution, consistent with rule-based
scoring rather than continuous confidence.

Stale/volatility coverage is sparse, not full: `stale` is only set on 27/234 docs
(207 have no value at all — not "false", *absent*); of those 27, 25 are `false` and 2
`true`. `volatility` is set on only 49/234 docs (185 absent): 43 `slow`, 4 `fast`,
2 `static`. This matters directly for Thread 2's hard invariant #3 ("never touch
quarantined [stale=true, q=0.2] docs except to propose deletion") — that invariant
only has visibility into 2 explicitly-stale docs out of a corpus where 207 docs have
simply never been scored for staleness at all.

### `lse-errors` — 32 docs, 425KB
Mapping: `error_hash` (keyword), `error_text`/`context`/`resolution` (text),
`occurrence_count` (integer), `first_seen`/`last_seen` (date), `embedding`
(same 768-dim setup as lse-kb). No `quality`/`stale`/`volatility` fields exist on
this index at all — it's a flat error-dedup ledger, not a curated-knowledge index.
`resolution` is populated on all 32/32 docs (100% — every recorded error has a
resolution attached), which is a healthier coverage story than lse-kb's stale field.

### `lse-skills` — 11 docs, 194KB
Mapping: `skill_id` (keyword), `task`/`procedure`/`preconditions`/`failure_modes`/
`verification` (text), `quality` (float), `source_tier`, `occupation` (keyword),
`pinned`/`archived` (booleans), `evidence_log` (nested: `ts`/`success`/`evidence`),
`stats` (nested: `uses`/`last_used`/`episode_successes`/`episode_failures`),
`version` (int), `embedding`. Quality range 0.40–0.90, avg 0.68, all 11/11 populated.
0 archived, 0 pinned — nothing has been curated out or locked in yet. Occupation
tags: linux-sysadmin (7), Local System Engineer (1), homeassistant_admin (1),
network-engineer (1), sre (1).

**Corpus readiness verdict — ES indices:**
- `lse-kb`: READY for read/mining, NOT READY for the stale/volatility invariant as
  currently scoped — Thread 1 or Thread 2 needs a decision on how a dream treats
  the 88% of docs with no stale/volatility value (treat absent as "unknown, hands
  off" is the safe default, matching the "never touch quarantined... except to
  propose deletion" spirit).
- `lse-errors`: READY. Small (32 docs), fully populated on the fields that matter,
  simple flat schema — good first target for a dedup/contradiction pass.
- `lse-skills`: READY but tiny (11 docs) — too small a sample to validate a mining
  pass against; Thread 2's first supervised dream should not lean on lse-skills
  volume for its eval.

---

## (d) `kb/session-learnings.md`

**Location:** `/opt/local-se/kb` is a symlink to
`/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/kb` — this file lives in the
Cowork-visible repo, not purely in the sandbox.

**Size:** 860 lines — matches the plan doc's "860 lines of debrief prose" exactly.

**Entry count:** 24 `## Session` entries.

**Date range:** 2026-06-07 → 2026-07-06 (one month of debriefs). Note this trails
5 days behind the current agent_commands.log activity (through 2026-07-11) and the
most recent tasks.db rows (through 2026-07-11) — the debrief skill is not being
invoked on every session, or at least not on the most recent ones.

**Section-structure consistency:** Mostly consistent but not uniform. All 24 entries
(100%) have a `### Key facts` section. 23/24 (96%) have `### What failed and why`.
18/24 (75%) have `### What worked`. One entry uses a nonstandard header —
`### What is safe across a full Docker reset` — instead of (or alongside) the usual
three, from the 2026-06-08 WSL2 Docker-corruption session. A parser built against a
fixed 3-heading template will silently drop that section's content unless it falls
back to "any H3 under a session H2."

**Corpus readiness verdict — session-learnings.md:** READY with a caveat. The
structure is regular enough (Key facts near-universal, two other standard headings
dominant) for a template-based extractor, but Thread 1's ingestion needs a fallback
path for off-template H3 headers rather than assuming exactly 3 fixed section names,
and needs to flag the 5-day staleness gap as exactly the kind of thing TRAUM-INSIGHT's
"morning dream digest" should surface ("debrief hasn't run in N days").

---

## Summary verdict

| Surface | Verdict | Blocking issue for Thread 1/2 |
|---|---|---|
| agent_commands.log | Ready | None — window reads by date/tail, not whole-file |
| tasks.db | Partially ready | 79% of tasks lack steps_json; need free-text fallback path |
| lse-kb (ES) | Ready to read, invariant gap | stale/volatility absent (not false) on 79–88% of docs — must default absent to "unknown/hands-off" |
| lse-errors (ES) | Ready | None — small, flat, fully populated |
| lse-skills (ES) | Ready, too small to eval on | Only 11 docs — don't use as the Thread 2 eval sample |
| session-learnings.md | Ready, with fallback needed | 1/24 entries off-template; corpus is 5 days stale as of this audit |

No blocking failures. The main design input for Thread 1 (TRAUM-CORPUS) is that
"missing field" and "false" are not the same thing in `lse-kb`, and any dream logic
built against `stale`/`volatility` must treat absence as unscored rather than as a
default value.
