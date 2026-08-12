# Skill feedback loop — fork resolution (2026-08-12)

> Measured this session, LUCIFER, branch `codex/fix-sudo-grants-live`. Every
> number below is a live command run this session, not carried over.

## The fork, and the answer

Neither (a) as literally framed ("failed silently and recorded nothing") nor
(b) ("just schema echo") is exactly right. The true shape:

**The model does call `skill_outcome` for real — 27 times, 2026-07-11 through
2026-08-09 — and it is not silent: every failing call returns an explicit
`"SKILL outcome error: skill_id '...' not found."` string that a downstream
episode-outcome derivation could have picked up at any time.**

## Evidence

Episode logs at `/opt/local-se/episodes/*/*.jsonl`, one JSON object per tool
call, `"tool"` field names the MCP tool actually invoked (not a schema/prompt
echo):

```
grep -rh '"tool": "skill_outcome"' /opt/local-se/episodes/*/*.jsonl | wc -l   → 27
grep -rh '"tool": "skill_search"'  /opt/local-se/episodes/*/*.jsonl | wc -l   → 96
grep -rh '"tool": "skill_record"'  /opt/local-se/episodes/*/*.jsonl | wc -l   → 64
```

These are structured entries with real args (`skill_id`, `success`,
`evidence`, `source_tier`) and a real `result_truncated` — this is the actual
per-turn tool-call log, not a prompt/schema dump (confirmed by inspecting a
2026-08-12 investigation-session file where `"skill_outcome"` appears only as
a grep *argument string* inside `execute_command` entries — that pattern is
visually distinct from the 27 genuine `"tool": "skill_outcome"` entries).

Timeline of the 27 real calls (`result_truncated`, chronological):

- **2026-07-11 → 2026-07-15T04:14** (9 calls): all succeed —
  `"SKILL outcome recorded: ... | quality X -> Y"`.
- **2026-07-14T10:10 onward**: calls start failing —
  `"SKILL outcome error: skill_id '...' not found."` — and *every* call from
  here to the end of the corpus fails this way. No exceptions, no other error
  shape.
- **Last call: 2026-08-09T21:22:57**, 41 minutes after commit `95ca984`
  (2026-08-09T20:41:48+02:00, the `.keyword` fix) landed. Still
  `"not found"` for skill_id
  `Local System Engineer/push-a-subset-of-local-commits-to-a-remote-branch`.

**Why the early calls succeeded and the later ones didn't — it isn't only
the query bug:**

```
GET /lse-skills/_settings → creation_date = 2026-07-15T13:45:03
```

The current `lse-skills-1024` index (the only index matching `skill` in
`_cat/indices`) was created **2026-07-15T13:45**. The nine successful calls
(2026-07-11 → 2026-07-15T04:14) all predate it — they wrote to a predecessor
index that no longer exists. Its history was lost when the index was
rebuilt, not recovered by `95ca984`. So even "the loop worked once" is only
true against an index that isn't the one being queried today.

**Is `95ca984`'s fix actually correct, and is it live?**

Correct, verified directly against ES right now, bypassing the MCP layer
entirely:

```
sid = "Local System Engineer/push-a-subset-of-local-commits-to-a-remote-branch"
term on skill_id.keyword  → 1 hit  (the exact doc, stats: uses=1, episode_successes=0)
term on skill_id (no .keyword) → 0 hits
```

So the fixed query is correct and the target document genuinely exists
today. Yet the 21:22:57 call — 41 minutes after the fix commit — still
returned "not found" for this exact id. The only way both of those are true
is that **the gateway process serving that 21:22 call had not reloaded
`tools/goethe_kb.py` since the fix landed** — exactly the AGENTS.md §7
hazard ("the process serving your MCP calls may not be the one listening on
`:9700`"; six stale gateway instances were found alive on 2026-08-09, the
same day). This is the same shape as the two other changes on this branch
already known to be "committed but not live until next gateway restart" —
it's just not yet been named as a third instance of that pattern.

## Which downstream hypothesis this supports

**(a)-shaped, not (b)-shaped, but not simply "already alive, needs one
cycle."** More precisely:

1. The model *does* call the tool on its own initiative (roughly once per
   1–2 sessions across the corpus) — this is not a wiring/caller gap the way
   ROADMAP item 2's current text implies ("Nothing calls it"). That line is
   now known to be wrong and is corrected below.
2. The query fix (`95ca984`) is correct in source and independently verified
   against live ES this session.
3. **No call has yet succeeded against the fix** — not because the fix is
   wrong, but because (most likely) no `skill_outcome` call has happened
   since a gateway restart that includes it. This has not been proven either
   way — no call at all has landed since 2026-08-09T21:22.
4. Therefore the open work is *not* "derive outcomes from `episode_index`
   because the model never calls it" (option b's downstream fix) — the
   model-calls-it path is real and cheap to finish verifying. The next
   concrete step is to let one real `skill_outcome` call happen against a
   freshly-restarted (or already-current) gateway and confirm it writes.
   `episode_index.py`'s per-session `tools_used`/`n_errors` derivation
   remains valuable as a *second, independent* signal for the Part 2B audit
   check (it doesn't depend on the model choosing to call `skill_outcome` at
   all), but it is not required to "fix" this fork — it's complementary, not
   a replacement.

## Roadmap correction

`docs/ROADMAP-2026-08.md` item 2 currently reads "Nothing calls it." — this
session's episode-log evidence (27 real calls, not zero) contradicts that.
Corrected in the same commit as this report.
