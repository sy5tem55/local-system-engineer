# Hermes Skill Learning — Analysis & the Cogitator Surpass Design
> Status: FINAL · 2026-06-12 (P22 Cowork)
> Ground truth gathered live from node3090 (hermes-agent v0.16.0, hermes-admin)
> Companion to: `docs/lse-1.7.0-design.md` §3 · `docs/self-learning-trajectory.md` S0–S6

---

## 1. Hermes' mechanism (observed, not inferred)

Evidence: `~/.hermes/skills/` listing, `.skills_prompt_snapshot.json`, `config.yaml`
(skills + curator sections), `.hermes/skills/.curator_state`, package modules
(`hermes_cli/curator.py`, `hermes_cli/skills_config.py`, `hermes_cli/skills_hub.py`,
`agent/curator.py`, `tools/skill_usage.py`).

- **Storage:** skills are files/folders under `~/.hermes/skills/` (SKILL.md style),
  plus optional `external_dirs`. No database, no embeddings, no schema.
- **Injection:** the whole skills manifest is compiled into the system prompt at
  session start (`.skills_prompt_snapshot.json` = `{manifest, skills[], category_descriptions}`).
  Prompt-injection, not retrieval — token cost grows linearly with corpus size.
- **Acquisition:** (a) the agent may write its own skill files
  (`guard_agent_created: false` — unguarded), (b) downloads from a skills hub
  (`skills_hub` provider slot, unconfigured here). There is **no automatic
  acquisition trigger** — no post-task distillation, no error promotion.
- **Lifecycle:** a **curator** background job — weekly (`interval_hours: 168`),
  only when idle ≥2h, prunes stale (30d), archives (90d, merges under "umbrella"
  names), pins/unpins, `prune_builtins: true`. Staleness is judged by **age and
  usage counts** (`tools/skill_usage.py`), not by outcome evidence.
- **Observed state after 44h of production operation:** 0 skills created,
  curator `run_count: 0` (first run deferred a full interval). The feature is
  wired and completely inert under real workload.

## 2. Verdict — where it's weak, what to keep

| Axis | Hermes v0.16.0 | Weakness |
|---|---|---|
| Acquisition | passive (agent whim / hub download) | 0 skills in 44h — nothing fires it |
| Quality | binary existence; age-based staleness | no evidence gating; a wrong skill lives 30–90 days |
| Injection | full manifest in prompt | token cost scales with corpus; irrelevant skills always present |
| Provenance | none | not auditable, not contamination-checkable |
| Measurement | usage counts only | usage ≠ usefulness; no lift measurement |

**Worth stealing (the curator's good ideas):**
1. **Pin/unpin** — human override that exempts a skill from lifecycle automation.
2. **Idle-time scheduling** — consolidation never competes with live work.
3. **Umbrella archiving** — merged skills keep a discoverable name trail.
4. **Snapshot file** — the exact injected corpus is inspectable on disk at any time.

## 3. How Cogitator surpasses it (design deltas, all already in lse-1.7.0-design §3)

1. **Acquisition is event-driven, not optional:** episode distillation after every
   arena episode, error-KB promotion at ≥2 identical fingerprints, curriculum
   batches. Hermes' 0-skills-in-44h is the null hypothesis Cogitator must beat —
   first measurable target: ≥5 evidence-backed skills within the first week of
   1.7.0-c operation.
2. **Quality moves on verified evidence only** (P2): +0.1 verified success,
   −0.15 verified failure, +0.2 authoritative cross-ref; floor 0.2 → archive.
   Hermes ages skills out; Cogitator *proves* them in or out.
3. **Retrieval beats injection:** top-2 kNN+BM25 match per task from `lse-skills`,
   constant context cost. (Adopt Hermes' snapshot idea: log every injected
   skill-set to the audit log for inspectability.)
4. **Provenance is mandatory** — episode ids + URLs in every skill doc; enables
   the S6 contamination audit which Hermes structurally cannot do.
5. **Measured, not vibed:** LSE-bench Condition A/B lift curve (S1/S6).
   Hermes has no equivalent.
6. **Adopted from Hermes:** `pinned` flag in the skill schema (exempt from
   consolidation/archive), idle-time consolidation job, umbrella merge naming.

## 4. Naming

`tools/openwebui-tool-v1.6.4.py` → **`tools/cogitator-v1.7.0.py`** (title:
"LSE Cogitator"). The version registry tracks it as Tool v1.7.0; OpenWebUI
deployment name stays a drop-in replacement.

New functions in v1.7.0 (release-train phase 1.7.0-c, pulled forward):
`skill_search`, `skill_record`, `skill_outcome` — schemas per design doc §3.2,
all passed through lse-docstring-optimizer before deployment (P6).

Out of scope for the tool file (live elsewhere per trajectory doc):
distillation hook (`run_episode.py` v3), consolidation job (`rag/skill_consolidate.py`),
curriculum batches (`rag/curriculum_batch.py`), `lse-skills` index mapping
(`rag/02-es-setup.py` extension → shipped here as `rag/06-skills-index-setup.py`).
