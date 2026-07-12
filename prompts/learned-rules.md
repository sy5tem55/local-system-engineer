# Learned Rules — TRAUM prompt-rule proposals (generated, human-gated)

> Populated ONLY by `tools/dream_apply.py`, one entry per human-confirmed
> `prompt-rule` proposal (TRAUM Thread 3, Prompt 3.6). Full merge workflow:
> `docs/dreaming/DESIGN.md` §8.
>
> This file is a STAGING AREA, not a live prompt — nothing here is loaded by
> `goethe.py`/llama-ui today, and it must never become an `#include` of
> `prompts/node4090-*` without an explicit, separately-reviewed change to
> that loading path. NEVER edit `prompts/node4090-*` directly from this
> file, from `dream_apply.py`, or from any dream. The operator reviews each
> "## Pending" entry by hand and, if accepted, folds its `rule` text into
> the NEXT `prompts/node4090-vX.Y.Z` version bump (the same v0.5.x -> v0.6.0
> discipline every other prompt change already follows), then moves the
> entry down to "## Merged" annotated with the version that absorbed it.
> Entries are append-only otherwise — never delete a pending or rejected
> entry, edit its status instead, so this file stays a legible history of
> every rule TRAUM has ever proposed.

## Pending

### 2026-07-12 — No prompt-rule insight yet (Prompts 3.2-3.3 seed check) [status: null-result]
- rule: (none — this is a null result, not a proposed instruction; do not merge)
- rationale: Prompt 3.6 asks to seed this file "with any accepted insights
  from prompts 3.2-3.3." Prompt 3.2 (the cross-session insights pass,
  `tools/dream_runner.py`'s `insights` pass) has so far only been exercised
  against synthetic test fixtures in-thread — no live `/opt/local-se`
  episode corpus, `tasks.db`, or `agent_commands.log` has been available in
  this Cowork session to generate a real, evidence-backed insight from (see
  the 2026-07-12 Prompt 3.4/3.5 `CHANGELOG.md` entries' own "no live
  `/opt/local-se` ... available in this session" notes). Prompt 3.3
  (skill-candidate/KB-fact mining from `tasks.db`'s ledger) has not been
  implemented at all yet — both prior Thread 3 `CHANGELOG.md` entries list
  it as not-done. There is therefore no real `prompt-rule` insight to seed.
  Recording this as an explicit null result rather than fabricating a rule
  to fill this section — fabricating one would violate the verbatim-
  evidence discipline this whole workstream (TRAUM) exists to enforce (plan
  Prompt 3.2: "verbatim-evidence rule"; Prompt 3.8: "a pass that finds
  nothing emits ... so we can distinguish 'nothing there' from 'didn't
  look'").
- section_hint: (not applicable)
- evidence: docs/dreaming/DESIGN.md §8.6; CHANGELOG.md 2026-07-12 entries (TRAUM Thread 3, Prompts 3.4-3.5)
- dream: n/a — recorded by hand during Prompt 3.6 (this file's own creation), not by an actual `dream_apply.py` run

## Merged
