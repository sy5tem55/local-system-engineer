# Copy-paste prompt — create the TRAUM operations KB entry

Use this prompt when onboarding the Local System Engineer, refreshing the KB
after a TRAUM change, or giving a general-purpose assistant enough structure to
produce a safe operator entry. It creates documentation; it does **not** approve
or apply dream proposals.

```text
Create or refresh a knowledge-base entry explaining how to operate the local
TRAUM dreaming system correctly.

Audience modes:
- If GOETHE/LSE tools and the local host are available, use CONNECTED mode.
- Otherwise use PORTABLE mode. Never imply that a command was executed in
  PORTABLE mode; mark system-specific values UNVERIFIED.

Safety rules:
1. Dreams propose; only dream_apply.py can apply, and semantic proposals remain
   human-gated. Do not apply, reject, expire, re-dream, start a service, or edit
   DREAM_AUTO_APPLY while creating this entry.
2. Never copy secrets, tokens, raw episode contents, or sensitive command
   arguments into the entry. Evidence should be compact command output.
3. DREAM_AUTO_APPLY must remain empty unless a newer DESIGN.md decision-log
   entry explicitly changes it with eval evidence.
4. A failed or unavailable check stays UNVERIFIED; do not infer success.

CONNECTED mode procedure:
1. Search the KB once for an existing TRAUM/dreaming operations entry. Reuse its
   doc_id if this is a refresh; do not create a duplicate.
2. Read these sources as the documentation authority:
   - docs/dreaming/DESIGN.md §7.4
   - docs/07-operations-runbook.md §10
   - VALVES.md TRAUM rows
   - docs/traum-dreaming-plan.md §5
3. Run these read-only checks and retain concise outputs as evidence:
   - systemctl is-enabled goethe-dream.timer
   - systemctl is-active goethe-dream.timer
   - systemctl show goethe-dream.timer -p NextElapseUSecRealtime --value
   - cat /opt/local-se/dreams/latest-digest.md
   - cd /home/sy5/local-system-engineer && python3 tools/dream_apply.py --queue
   - inspect whether GOETHE_DREAM_AUTO_APPLY is empty, but report only
     EMPTY / NON-EMPTY / UNREADABLE — never reveal its value
4. Do not use sudo. If a read check is permission-blocked, record that fact.
5. Draft the entry using the required shape below, show it to the user, and ask
   for an explicit yes/no before calling index_to_kb or mentor_correct.
6. On yes: update the existing doc with mentor_correct when a matching doc_id
   exists; otherwise call index_to_kb once. Trust the tool result; do not search
   again merely to verify the write.

PORTABLE mode procedure:
1. Ask the user for the contents of the four authority sections and the compact
   outputs of the read-only checks above. Do not request secrets.env contents.
2. If evidence is missing, keep placeholders marked UNVERIFIED.
3. Produce the proposed entry as Markdown plus an index_to_kb-compatible JSON
   object. Do not claim it was indexed.

Required KB entry:
Title: TRAUM dreaming operations — nightly review, gated apply, and recovery
Topic: lse-operations
Volatility: slow
Source tier: ground_truth only in CONNECTED mode when live checks succeeded;
otherwise inferred
Quality score: 0.90 when live-verified, otherwise 0.65

Content sections:
- Purpose and dataflow: episodes -> five dream passes -> pass-scoped reports and
  proposals -> morning digest/queue -> human-gated dream_apply -> KB/skills.
- Safety invariants: runner read-only against ES; no quality raise or ground-truth
  minting; origin/provenance; redaction; dream-of-dream exclusion; auto-apply
  decision; expiry behavior.
- Nightly schedule and current timer evidence.
- Five-minute morning workflow, with exact commands.
- How to review one proposal batch safely; clearly distinguish default dry-run
  from --no-dry-run and require the human confirmation gate.
- Failed-night signals, crash files, lock handling, and escalation after three
  consecutive failed nights. Never recommend deleting a live lock until its PID
  is proved dead.
- Re-dream and provenance-tracing procedures by reference to runbook §10; do not
  duplicate destructive SQL as a casual quick-start command.
- Key paths and valves.
- Verification evidence, timestamped in Europe/Berlin.
- Known limitations and UNVERIFIED items.

Before writing, print:
1. The full proposed entry.
2. The exact metadata/tool call you intend to use.
3. A redaction statement confirming no secret values are present.
4. "Create/update this KB entry? (yes/no)"
```

## Expected outcome

A connected LSE produces one evidence-backed KB document and no duplicate. A
portable assistant produces a reviewable artifact with honest verification
labels. Neither mode changes the dream queue, autonomy setting, timer, corpus,
or Elasticsearch documents other than the single user-approved KB entry.
