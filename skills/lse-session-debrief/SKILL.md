---
name: lse-session-debrief
description: >
  Writes a structured learning entry to /opt/local-se/kb/session-learnings.md
  at the end of a session where something non-obvious was discovered or corrected,
  and proposes matching index_to_kb/skill_record calls into the lse-kb/lse-skills
  retrieval indexes — file write and ES calls confirmed together in one gate
  (SCRIBE-1 unified write path). Also checks whether the session disproved an
  existing KB entry and, if so, proposes a record_outcome demotion alongside the
  corrected fact instead of leaving two contradicting entries live (SCRIBE-3).
  Use when the user says "log this session", "update the KB with what we learned",
  "write up what went wrong", "debrief", or "add that to the KB". Also use
  proactively when a config error, silent failure, or wrong path/port was
  corrected mid-session — especially if hours were spent on it. The goal is that
  the next session starts with hard-won knowledge already grounded and retrievable,
  not rediscovered or sitting unread in prose.
---

# LSE Session Debrief

Captures non-obvious learnings and appends them to the session KB so the LSE
doesn't repeat the same mistakes in future sessions. The SearxNG `suspended_times`
placement mistake — silently ignored when placed under `outgoing:` instead of
`search:` — is the canonical example of what this skill exists to prevent repeating.

---

## WHAT TO CAPTURE

Capture only things that are non-obvious and would prevent a future mistake.

**Worth capturing:**
- Config key placed in the wrong section (silently ignored by the parser)
- Wrong path, port, or key name that looked plausible but was incorrect
- A command or sequence that failed in a non-obvious way, and the fix
- A correct behaviour that contradicts what you'd assume from documentation or training

**Not worth capturing:**
- Straight-line work that succeeded without surprises
- Things already in the KB (`read_file /opt/local-se/kb/` to check before writing)
- Generic Linux/bash knowledge with no LSE-specific angle

If nothing non-obvious happened, say so — do not write an empty or vague entry.
A vague entry ("config was wrong") is worse than no entry — it wastes future read budget
without preventing anything.

---

## ENTRY FORMAT

Every entry must follow this structure exactly:

```
## Session YYYY-MM-DD — <one-line topic, ≤60 chars>

### What worked
- <reusable pattern or command — concrete enough to copy-paste>

### What failed and why
- **Attempted:** <what was tried>
  **Failed because:** <specific root cause — not "config was wrong" but which key, which section, why>
  **Fix:** <exact command, config change, or correct value>

### Key facts
- <one fact per line: correct path / port / key name / placement rule>
```

Multiple failure/fix pairs are allowed under "What failed and why" — one block per failure.
If a session had only a discovery with no failure (e.g. learning a new correct path),
omit "What failed and why" and use "What worked" + "Key facts" only.

---

## STRUCTURED ES PROPOSALS (SCRIBE-1 — unified write path)

The file write is the human journal. It is no longer the only output of this
skill: Step 4 also proposes structured `index_to_kb` / `skill_record` calls so
the retrieval indexes (`lse-kb`, `lse-skills`) learn from the same session,
instead of the debrief prose sitting unread forever (the exact failure mode
this workstream — TRAUM, `docs/traum-dreaming-plan.md` — exists to fix).
Both the file write and every structured call are shown together and
committed on ONE human yes — see WRITE SEQUENCE below. `kb/session-learnings.md`
stays the append-only human-readable journal; ES stays the retrieval surface
other sessions actually query via `search_kb`/`skill_search`.

**Classify, don't transcribe.** Not every bullet becomes a call. Use the same
bar `index_to_kb`'s and `skill_record`'s own docstrings use:

- **`### Key facts` bullet → candidate `index_to_kb` proposal** when the fact
  is a standalone, independently-retrievable value (a config key's correct
  section, a path, a port, a placement rule) — something a *different* future
  session would plausibly `search_kb` for on its own, not just context for
  this specific entry.
- **`### What worked` item → candidate `skill_record` proposal** ONLY when it
  is a multi-step, reusable PROCEDURE with a verification step — not a single
  fact. `skill_record`'s own docstring example is the bar:
  ```
  GOOD: task="free disk space by removing duplicate downloads",
        procedure="find /downloads -name '*.dup' ... then df -h to confirm"
        ← multi-step, has its own verification → skill_record
  BAD:  task="llama-server port", procedure="8080"
        ← single fact, no steps, nothing to "replay" → index_to_kb instead,
          not here
  ```
- If nothing in the entry clears either bar, propose **zero** structured
  calls and say so explicitly at the confirm gate — do not force a call to
  avoid an empty list, the same "no vague entries" discipline as the file
  itself.

**Field mapping — fixed, do not improvise field names:**

`index_to_kb(content, title, topic, source_tier, evidence, verified_against, volatility, quality_score)`
- `content` — the fact, in enough detail to stand alone without the rest of
  the debrief entry for context.
- `title` — short, human-readable.
- `topic` — reuse an existing tag if the session fits one (see `index_to_kb`'s
  own docstring for the current list); use `lse-operations` or `general` if
  none fit — do not invent a new tag casually.
- `source_tier` — pick honestly, per `index_to_kb`'s own ceiling rules:
  `ground_truth` (you personally ran the command/tool and observed the result
  THIS session — the normal case for a debrief fact) requires `evidence` to
  be the actual tool output, ≥40 chars; `primary` if the fact came from
  vendor docs/README/RFC consulted this session, not a live test; `secondary`
  for forum/blog-sourced facts. Never `inferred` for something you verified —
  that tier is for untested hypotheses, which shouldn't be in this skill's
  output at all (see "WHAT TO CAPTURE").
- `evidence` — required whenever `source_tier=ground_truth`: paste the actual
  command/output that proves the fact, not a paraphrase.
- `verified_against` — the version/config snapshot this was verified against
  (e.g. `"SearxNG docker image tag X"`, `"pfSense Plus 26.03"`) if a version
  is relevant to how long the fact stays true; empty string if not applicable.
- `volatility` — `static` for topology/hardware/protocol facts that don't
  decay, `fast` for version/CVE/firmware/price facts (7d TTL), `slow`
  (default) for everything else.
- `quality_score` — 0.8–1.0 for a clean `ground_truth` fact with solid
  evidence; do not leave the tool's 0.5 default for something you just
  verified firsthand, that under-ranks it against the ceiling `source_tier`
  already grants it.

`skill_record(task, occupation, procedure, verification, preconditions, failure_modes, provenance, source_tier, quality)`
- `task` — one line, what the skill accomplishes.
- `occupation` — reuse an existing tag from the `lse-skills` index when the
  session fits one (`linux-sysadmin`, `network-engineer`, `sre`,
  `homeassistant_admin`); default to `Local System Engineer` as the general
  catch-all rather than coining a new tag.
- `procedure` — the actual steps, concrete enough to replay.
- `verification` — the ground-truth check that proved the procedure worked
  THIS session (required — `skill_record`'s evidence gate: no unverified
  procedures).
- `preconditions` / `failure_modes` — fill in when known, empty string
  otherwise.
- `provenance` — literally `"debrief YYYY-MM-DD"` (today's date, this exact
  format — SCRIBE-1 fixes this string so it's greppable/traceable back to a
  debrief session, matching the `dream-YYYY-MM-DD` convention Thread 2 dreams
  use for their own writes).
- `source_tier` — `ground_truth` (default choice here; the evidence gate
  already requires this to be a verified procedure).
- `quality` — 0.6–0.7 for a procedure verified once this session (it hasn't
  been proven across multiple sessions yet — don't claim top confidence
  prematurely); raise on later `skill_outcome` confirmations, not here.

**The exact confirm-gate render** (this format is fixed — Thread 2's
`dream_apply.py` reuses it verbatim for its own proposals, per
`docs/dreaming/DESIGN.md` §6, so a human reviewing either a debrief-confirm or
a dream-apply-confirm sees the same shape):

```
――― FILE: kb/session-learnings.md (append) ―――
<the full entry text, exactly as it will be appended>

――― ES PROPOSAL 1/N: index_to_kb ―――
title:             <title>
topic:             <topic>
source_tier:       <tier>
quality_score:     <0.0-1.0>
verified_against:  <version/config, or "(not applicable)">
volatility:        <static|slow|fast>
evidence:          <evidence text, or "(none — source_tier is not ground_truth)">
content:
  <content>
why:               <one line: why this clears the "standalone fact" bar>

――― ES PROPOSAL 2/N: skill_record ―――
task:              <task>
occupation:        <occupation>
provenance:        debrief YYYY-MM-DD
source_tier:       ground_truth
quality:           <0.0-1.0>
preconditions:     <preconditions, or "(none)">
verification:      <verification>
failure_modes:     <failure_modes, or "(none)">
procedure:
  <procedure>
why:               <one line: why this clears the "reusable procedure" bar>

[... one numbered block per proposal, in the order: index_to_kb proposals
first, then skill_record proposals ...]
```

If zero structured calls were proposed, omit the `ES PROPOSAL` blocks
entirely and say so in the confirm question (see Step 3).

---

## CONTRADICTS EXISTING KB? (SCRIBE-3 — close the loop with decay)

Before finalizing any `index_to_kb` proposal, check whether it contradicts —
not just resembles — an existing KB entry. This runs as part of Step 2,
before drafting the confirm-gate block.

**Why this exists:** without this check, SCRIBE-1 alone would let a session
that disproves an old KB entry just write the new fact ALONGSIDE the old one.
Both stay live and equally trusted; `search_kb` now returns two contradicting
answers with no signal about which is current. KB-DECAY already has the
mechanism to fix this (`record_outcome(doc_id, success=False, evidence=...)`
demotes quality and, at the floor, quarantines the doc — never deletes it) —
this step is what actually calls it from the debrief flow instead of leaving
stale entries for a human to notice by accident.

**Procedure, for each candidate `index_to_kb` proposal:**

1. `search_kb(query=<the fact's core claim>)` — the same call the "WHAT TO
   CAPTURE" gate already implies you'd make to check for duplicates, now
   also read for conflict, not just overlap.
2. Read the top result(s). Three outcomes:
   - **No relevant hit** → proceed with the `index_to_kb` proposal alone, as
     in SCRIBE-1. Nothing to demote.
   - **A near-duplicate, not a conflict** (the existing doc says essentially
     the same thing) → this is `index_to_kb`'s own dedup path (cosine>0.92
     UPDATES the existing entry automatically). Not a contradiction. Do not
     propose `record_outcome` for a doc that merely restates the same fact.
   - **A genuine conflict** (the existing doc asserts something this session
     directly observed to be false — not "outdated in general," but
     specifically disproved by a concrete tool result THIS session) → this
     is a contradiction. Continue to step 3.
3. Add a `record_outcome` proposal alongside the `index_to_kb` proposal — NOT
   instead of it. The corrected fact still needs to enter the KB; the
   difference SCRIBE-3 makes is that the old, now-wrong entry is
   simultaneously demoted rather than left standing unaddressed:
   ```
   record_outcome(doc_id=<contradicted doc's doc_id>, success=False,
                  evidence=<verbatim quote of the OLD doc's conflicting
                  claim> + " — CONTRADICTED THIS SESSION: " +
                  <verbatim quote of what this session actually observed>)
   ```
   Same verbatim-quote discipline Thread 2's own contradiction pass uses
   (`docs/traum-dreaming-plan.md` Prompt 2.3): quote BOTH sides, not a
   paraphrase of either, evidence ≥20 chars. A human reviewing the confirm
   gate must be able to see the actual conflicting text, not your summary of
   it, and judge for themselves whether it's really a contradiction.
4. Show both proposals together at the same confirm gate (Step 3) — see the
   render template addition below. This uses the SAME proposal type name
   (`demote`) Thread 2's dream contradiction pass uses for the identical
   call shape — a demotion is a demotion whether a human debrief or an
   offline dream triggered it; only `evidence`'s provenance differs.

**Render template addition** (inserted after any `index_to_kb`/`skill_record`
proposal blocks, before the final question, whenever a contradiction was
found):

```
――― ES PROPOSAL N/N: record_outcome (KB-DECAY demotion) ―――
doc_id:            <contradicted doc's doc_id>
success:           false
evidence:          <old doc's verbatim conflicting line> — CONTRADICTED
                    THIS SESSION: <this session's verbatim finding>
why:               <one line: what changed, and how this session proved it>
```

**Worked example — a real, live contradiction found while writing this very
step** (`lse-kb` doc `a9361df7b6b60bb8`, "Hermes Ports on node3090 — 8642
(API) / 8643 (socat relay) / 8644 (webhook)", verified 2026-06-13,
`quality_score=1.0`, `source_tier=ground_truth`, not stale — this is a
trusted, high-quality entry, exactly the kind of doc a naive SCRIBE-1-only
flow would leave untouched and contradicted):

```
――― ES PROPOSAL 1/2: index_to_kb ―――
title:             Hermes API no longer uses key-based authentication
topic:             infrastructure
source_tier:       ground_truth
quality_score:     0.9
verified_against:  (not applicable)
volatility:        fast
evidence:          Confirmed this session: HERMES_API_KEY-style auth is
                    decommissioned; Hermes no longer requires a bearer/API
                    key for the port 8642 gateway.
content:
  Hermes API authentication (port 8642) no longer uses key-based auth.
  HERMES_API_KEY and the related vault-stored bearer tokens documented in
  the older port-map entry are decommissioned. Do not reference
  HERMES_API_KEY in new valve/config work; if a replacement auth mechanism
  exists, this entry should be updated to describe it once confirmed.
why:               Directly reverses a `ground_truth`, quality=1.0 claim
                    still live in the KB — exactly the case this step exists
                    to catch, not just a new unrelated fact.

――― ES PROPOSAL 2/2: record_outcome (KB-DECAY demotion) ―――
doc_id:            a9361df7b6b60bb8
success:           false
evidence:          Old doc states: "| **8642** | Hermes API server (Python
                    gateway) | Bearer token required | 0.0.0.0 | Primary
                    API..." and lists HERMES_GATEWAY_API_KEY_8642 /
                    HERMES_API_SERVER_KEY as live vault items. CONTRADICTED
                    THIS SESSION: HERMES_API_KEY-style auth is decommissioned
                    — the port 8642 gateway no longer requires a bearer/API
                    key, per direct confirmation.
why:               The auth mechanism this doc documents as required no
                    longer exists; quality=1.0/ground_truth is currently
                    overstating confidence in a claim that's now false.

Write this entry to `/opt/local-se/kb/session-learnings.md` AND commit 2 ES
proposals (1 index_to_kb, 1 record_outcome)? (yes/no)
```

(Note: the old doc's actual key VALUES are never repeated here or in any
proposal — redaction discipline applies to worked examples in this file too,
not just to episode journaling. Quote the *claim* being contradicted, never
the secret values inside it.)

This contradiction was real and, at the time this section was drafted
(2026-07-11), unaddressed in the live KB. Doc `a9361df7b6b60bb8` and its
current quality/stale state may have changed since — do NOT assume this
example still describes live KB state. Before treating it as a template for
"here's a real pending demotion," run `search_kb` on the Hermes port-map
claim yourself; if it's already been demoted or corrected, treat this block
purely as a worked example of the FORMAT, not as an outstanding task.

**Example entry (the SearxNG incident):**

```
## Session 2026-05-24 — SearxNG suspended_times placement

### What worked
- Placing `suspended_times` under `search:` with Python exception class name keys

### What failed and why
- **Attempted:** `suspended_times` under `outgoing:` section
  **Failed because:** SearxNG parser silently ignores `suspended_times` outside `search:` — no error, no warning, just no effect
  **Fix:** Move the block to `search:` in settings.yml and restart: `cd /home/sy5/searxng-docker && docker compose restart searxng`

### Key facts
- `suspended_times` lives under `search:`, not `outgoing:` or top-level
- Keys are Python exception class names: `SearxEngineTooManyRequests`, `SearxEngineCaptcha`, etc.
- Not string literals like `"HTTP error [429]"` — those are silently ignored
- SearxNG port: 8088. llama-server port: 8080. Never swap them.
- Verify after restart: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/` → 200
```

**That same entry's structured proposals, rendered as Step 3 would show them:**

```
――― FILE: kb/session-learnings.md (append) ―――
## Session 2026-05-24 — SearxNG suspended_times placement
[... full entry text above ...]

――― ES PROPOSAL 1/2: index_to_kb ―――
title:             SearxNG suspended_times must be under search:, not outgoing:
topic:             searxng
source_tier:       ground_truth
quality_score:     0.9
verified_against:  (not applicable)
volatility:        slow
evidence:          Moved suspended_times block from outgoing: to search: in
                    settings.yml, restarted (docker compose restart searxng),
                    curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/
                    -> 200. Under outgoing: the same block produced no error
                    and no effect — engine bans were never actually suspended.
content:
  SearxNG's suspended_times config (per-exception-class retry suspension) must
  be placed under the search: section. Placed under outgoing: it is silently
  ignored — no parse error, no warning, the key is simply not read. Keys are
  Python exception class names (SearxEngineTooManyRequests,
  SearxEngineCaptcha), not string literals like "HTTP error [429]".
why:               Standalone, independently-retrievable placement rule a
                    future SearxNG-config session would search_kb for on its
                    own merit, not just as context for this entry.

――― ES PROPOSAL 2/2: index_to_kb ―――
title:             SearxNG port is 8088, llama-server is 8080
topic:             searxng
source_tier:       ground_truth
quality_score:     0.85
verified_against:  (not applicable)
volatility:        static
evidence:          curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/
                    -> 200 confirms SearxNG on 8088 this session.
content:
  SearxNG listens on port 8088. llama-server listens on port 8080. These are
  easy to transpose from memory — verify before assuming either.
why:               A port-collision mistake is exactly the class of "looked
                    plausible but was wrong" fact this skill exists to catch;
                    worth its own doc so search_kb surfaces it independent of
                    the SearxNG incident narrative.

Write this entry to `/opt/local-se/kb/session-learnings.md` AND commit 2 ES
proposals (2 index_to_kb, 0 skill_record)? (yes/no)
```

Note what did NOT get proposed: the "What worked" bullet ("placing
`suspended_times` under `search:`...") is the FIX for the failure already
captured in the `index_to_kb` proposal above and in "What failed and why" —
it is not a separate multi-step reusable procedure with its own verification,
so it does not also become a `skill_record` call. Restating the same fact as
both a fact and a skill would be noise, not signal — when in doubt, prefer
under-proposing over padding the confirm gate with redundant calls.

---

## WRITE SEQUENCE

Follow these steps in order. Skipping any step's CHECK is a protocol
violation — "skip" below always means "never performed the check," not
"the check ran and correctly produced a no-write outcome." A duplicate
found in Step 1, or zero eligible proposals in Step 2, are valid RESULTS of
running a step, not a skipped step. Do not let a valid no-write/no-propose
result read as itself forbidden.

**Step 1 — READ existing KB**
```
execute_command("cat /opt/local-se/kb/session-learnings.md 2>/dev/null || echo '(file does not exist yet)'")
```
Check: is an entry for today's date + topic already present? If yes, this
step's correct outcome is to NOT append a duplicate — stop here, do not
proceed to Step 2. This is the check doing its job, not a skipped step.

**Step 2 — DRAFT the entry, then classify structured proposals**
Write the full entry in the chat using the format above. Do not write to disk yet.
Then apply the classification rules above to the entry's own bullets: zero or
more `index_to_kb` proposals (from `### Key facts`), zero or more
`skill_record` proposals (from `### What worked`). Draft every field per the
mapping above — do not leave a proposal half-filled, the human confirming in
Step 3 must see the exact call that will be made.
For every candidate `index_to_kb` proposal, run the "CONTRADICTS EXISTING
KB?" check (above) before finalizing it — `search_kb` first, and if it
disproves an existing entry, add the matching `record_outcome` demotion
proposal alongside it. This is not optional when a candidate fact exists;
never RUNNING the contradiction check is the same class of violation as
never RUNNING the "already in the KB?" duplicate check in Step 1 — in both
cases the violation is skipping the lookup itself, never a legitimate
no-match/no-conflict result the lookup returns.
The user must be able to read and correct the entry AND every proposed call
before anything is committed.

**Step 3 — CONFIRM (single gate for file + ES)**
Render the confirm-gate block from the "exact confirm-gate render" template
above (file text, then each ES proposal numbered).
Ask exactly one question, adapted to what was actually proposed:
- If N ≥ 1 structured proposals: "Write this entry to
  `/opt/local-se/kb/session-learnings.md` AND commit `<N>` ES proposal(s)
  (`<n1> index_to_kb, <n2> skill_record, <n3> record_outcome`, omitting any
  that are zero)? (yes/no)"
- If zero: "Write this entry to `/opt/local-se/kb/session-learnings.md`? (yes/no)
  — no ES proposals for this entry."
Wait for an explicit yes. Do not proceed on ambiguous responses. One yes
commits the file write AND every listed ES call — there is no separate
per-call confirmation, and no partial-accept ("yes to the file but not the
ES calls" requires the user to say no and ask for a re-draft with those
proposals removed, not a second prompt here).
Skipping confirmation is a protocol violation.

**Step 4 — WRITE (file, then each ES call, in order)**
On confirmation, append the entry exactly as drafted:
```
execute_command("printf '\n' >> /opt/local-se/kb/session-learnings.md && cat >> /opt/local-se/kb/session-learnings.md << 'DEBRIEF_EOF'\n<entry text>\nDEBRIEF_EOF")
```
Use `>>` to append. Never use `>` — that overwrites the entire file.
If the file doesn't exist yet, create it first with a header:
```
execute_command("echo '# LSE Session Learnings\n\nCumulative KB entries from post-session debriefs.\n' > /opt/local-se/kb/session-learnings.md")
```
Then call each confirmed `index_to_kb` / `skill_record` / `record_outcome`
proposal in order, with exactly the arguments shown at the confirm gate — do
not silently change a value between what was confirmed and what is called.
When a contradiction was found, call `index_to_kb` (the corrected fact)
before `record_outcome` (the demotion) — the KB should never have a moment
where the old claim is demoted but the corrected replacement isn't there yet.
This is "one yes commits file + ES together" in the sense of one human
decision, not a database transaction: there is no rollback across a markdown
file and Elasticsearch. If a structured call fails after the file write
already succeeded, do not retry silently — report it plainly in Step 5 (the
file entry is still correct and stays; only that one ES write needs a
follow-up).

**Step 5 — VERIFY**
```
execute_command("tail -30 /opt/local-se/kb/session-learnings.md")
```
Confirm the entry is present and correctly formatted.
For each structured call made, report the tool's own return value (doc_id /
skill_id, any dedup-update note, or the updated quality/stale state from a
`record_outcome` demotion) as the verification evidence — `index_to_kb` and
`skill_record` say not to re-check via `search_kb`/`skill_search` afterwards
("trust the return value"), so don't; just surface what each call actually
returned, including any failure.
Skipping verification is a protocol violation.

---

## GATE

Trigger on:
- Explicit user request ("log this", "debrief", "add that to the KB")
- Any session where a non-obvious config error, silent failure, or wrong assumption was corrected

Do NOT trigger on routine sessions where everything worked as expected.
Do NOT write an entry just to fill the KB — quality over volume.
