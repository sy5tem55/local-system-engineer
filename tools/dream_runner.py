#!/usr/bin/env python3
"""
dream_runner.py — TRAUM-ENGINE offline dream runner (v0.4.1)
=============================================================================
Companion to docs/dreaming/DESIGN.md (dataflow, §1) and
docs/dreaming/corpus-audit.md (corpus readiness survey). TRAUM Thread 2,
Prompts 2.1 (runner skeleton), 2.2 (dedup), 2.3 (stale/contradiction), and
2.4 (error-cluster), all implemented below. Only Prompt 2.5 (dream_apply.py
— the apply gate) remains for Thread 2.

Offline, unattended, READ-ONLY. Scans manifest.db for sessions the dreamer
hasn't looked at yet (`dreamed_at IS NULL`), reads their episode JSONL, and
reads (never writes) the three lse-* Elasticsearch indices, tasks.db, and
agent_commands.log — the four corpus surfaces corpus-audit.md verified are
READY. Drives the local model through the SAME endpoint cascade as
goethe.py's node planner (tools/goethe.py `_call_node_planner` /
`_request_plan_envelope`, ~line 1322/6860): a PLANNER_FORCE_URL-style forced
endpoint (here: DREAM_LLM_URL) checked first, falling through to the
NODE3090 llama-server / Ollama cascade, with `thinking_budget_tokens=0` and
a two-attempt envelope-parse loop with one corrective retry. As of Prompt
4.1 (TRAUM-AUTO) the llama-server leg is additionally gated on node3090's
own free VRAM via SSH + nvidia-smi (see `_node3090_free_vram_mb`) -- a
remote application of goethe.py's `_planner_free_vram_mb` pattern, which
only gates the LOCAL Gemma-spawn leg and has no remote equivalent for
node3090 itself. Nothing here
imports or calls any Anthropic/Cowork API surface (DESIGN.md §2 invariant 1).

Output: /opt/local-se/dreams/YYYY-MM-DD/{report.md,proposals.jsonl}.
proposal types: dedup | reverify | demote | skill-candidate (DESIGN.md §6.2).

THIS THREAD IS DRY-RUN ONLY: dream_runner.py never writes to Elasticsearch,
full stop — that write path belongs exclusively to the not-yet-written
dream_apply.py (Prompt 2.5), and only after a human confirms each proposal
(DESIGN.md §2 invariant 2, §6.4). There is no ES-write call anywhere in this
file; only `search_index()` (search/get) exists. The --dry-run flag below
controls a *smaller* thing — whether report.md/proposals.jsonl are actually
written to disk vs. printed to stdout — not whether ES is touched.

Passes:
  dedup              Prompt 2.2 — IMPLEMENTED. Near-duplicate lse-kb entries ->
                      "dedup" proposal PAIRS: a mentor_correct call on the
                      keep-doc (merged content, quality raised to the max of
                      the two) plus a record_outcome(success=False) call on
                      the retire-doc (nudges it toward the existing KB-DECAY
                      quarantine path — there is no hard-delete tool, so
                      retirement reuses the same demotion primitive Prompt
                      2.3's contradiction pass will also use). Both calls are
                      EXISTING goethe.py Tools methods — dream_apply.py
                      (Prompt 2.5) needs no new write path for this pass.
  stale-contradiction Prompt 2.3 — IMPLEMENTED, two independent sub-passes:
                      (a) CHRONOS TTL reverify — deterministic, no LLM call.
                      Reuses search_kb's own _TTL_DAYS/_is_expired math
                      (fast=7d, slow=90d, static=never) so this pass and the
                      live reranker agree on "expired." A doc is eligible
                      only with volatility EXPLICITLY set (absent = hands
                      off, corpus-audit.md found 79% of lse-kb never scored
                      for it), verified_against non-empty (else kb_verify's
                      own phase 1 is a no-op), and stale != True (quarantined
                      docs are out of scope here). -> "reverify" proposals
                      carrying a kb_verify(doc_id) probe suggestion.
                      (b) Contradiction detection — for each undreamed
                      session, doc_ids surfaced via search_kb this session
                      are parsed straight out of search_kb's own return text
                      ("doc_id=<_id>" per hit, tools/goethe.py:4741) and
                      cross-checked (model judges) against that session's
                      OTHER tool results. Both the KB claim and the
                      contradicting tool output must be quoted VERBATIM;
                      the validator re-checks each quote is a real substring
                      of the source text it claims to come from and is
                      >=20 chars — code-enforced, not just prompted for.
                      -> "demote" proposals carrying
                      record_outcome(doc_id, success=False, evidence=<verbatim
                      pair, DESIGN.md §6.2 shape>).
  error-cluster       Prompt 2.4 — IMPLEMENTED. Groups lse-errors docs +
                      episode error/timeout occurrences by embedding
                      similarity (union-find over the cosine>=threshold
                      graph, ERROR_CLUSTER_THRESHOLD default 0.80).
                      Clusters with >=3 episode occurrences spanning >=2
                      sessions get a drafted "skill-candidate" proposal
                      (skill_record body: task/trigger/procedure/
                      verification/preconditions/failure_modes,
                      provenance=dream-YYYY-MM-DD, source_tier=inferred so
                      it can never self-grant ground_truth, the cluster's
                      episode ids carried as a top-level `evidence` list).
                      A matching lse-errors doc in the same cluster supplies
                      prior-art context (its resolution text) but never
                      counts toward the occurrence/session bar — it's an
                      aggregate with no per-session breakdown of its own.
  patterns            TRAUM-INSIGHT Thread 3, Prompt 3.1 — IMPLEMENTED.
                      Mechanical audit-log miner over agent_commands.log,
                      NO LLM call anywhere in this pass. Four sub-passes over
                      one parsed event stream (compact tag-line format,
                      corpus-audit.md (a)): (1) command frequency table over
                      CMD-tag detail strings; (2) failure->retry adjacency —
                      a CMD whose paired DONE reports rc!=0, followed by the
                      SAME command re-issued within --patterns-retry-window
                      lines; (3) per-tag ("tool") event counts bucketed by
                      ISO week, zero-filled across every tag x week combo in
                      range so a "this tool went quiet" finding (the
                      RFC-KB-zero-usage class of finding) is directly
                      readable without another pass; (4) longest contiguous
                      command sequences (>=--patterns-min-sequence-len)
                      recurring across >=--patterns-min-sessions distinct
                      SESSIONS — agent_commands.log carries no session_id of
                      its own, so sessions are inferred by inactivity gap
                      (--patterns-session-gap-minutes). Generates ZERO
                      mentor_correct/record_outcome proposals — unlike the
                      other three passes this writes a raw analytics
                      artifact, /opt/local-se/dreams/YYYY-MM-DD/patterns.json
                      (or --patterns-out), for a later prompt to consume.
                      Windowed read (corpus-audit.md (a)'s explicit caveat:
                      the log is unrotated and growing) via
                      --patterns-max-lines (default 50,000 — comfortably
                      covers the ~44k-line corpus this prompt targets without
                      loading the whole, ever-growing file).
  insights            TRAUM-INSIGHT Thread 3, Prompt 3.2 — IMPLEMENTED.
                      Feeds patterns.json's four mined domains (re-derived
                      in-memory, no on-disk dependency on a prior `patterns`
                      run) plus recent session summaries to the local model,
                      ONE insight domain per LLM call: command-frequency,
                      failure-retry, tool-usage, automation-candidates.
                      Structured insight schema per DESIGN.md-style
                      discipline: {observation, evidence_refs, cost_estimate,
                      proposed_change (kb-fact|skill|prompt-rule|tool-change),
                      confidence}. evidence_refs are code-enforced against the
                      exact data shown that call (verbatim-evidence rule) --
                      an insight with zero verified refs is discarded, not
                      trusted on the model's word. ALL insights land in
                      report.md's "## Cross-session insights" section;
                      proposed_change in {kb-fact, skill, prompt-rule}
                      additionally becomes a real proposal that flows
                      through the same validate_proposal_shape() gate as
                      every other pass -- kb-fact/skill dispatch through
                      existing Tools methods (index_to_kb/skill_record,
                      source_tier=inferred); prompt-rule (Prompt 3.6) dispatches
                      through append_learned_rule, dream_apply.py's ONE
                      exception to "writes go through Tools" -- it appends to
                      the generated include file prompts/learned-rules.md,
                      NEVER to a canonical prompts/node4090* file, and the
                      target path is always hard-coded here, never taken from
                      the model's own output (see _insight_to_proposal).
                      tool-change still maps to no write path of any kind and
                      stays report.md-only.

NULL-RESULT DISCIPLINE (Prompt 3.8, PH3-2 formalized): every run_pass_*()
returns a 3-tuple (proposals, narrative, null_record). null_record is a
structured dict (see _null_record) — pass name, reason code, `looked`
(True="nothing there": the pass inspected corpus_size-worth of data at
`thresholds` and still found nothing; False="didn't look": an upstream
gate, e.g. an empty index or unreachable dependency, stopped it first),
corpus_size, thresholds — or None when the pass produced something
non-null. write_report() renders it as report.md's own "## Null result"
section (plain, not buried in prose) and appends it to
<dream-dir>/<date>/null-results.jsonl, which — unlike report.md and
proposals.jsonl, both single-pass-per-invocation snapshots — survives a
full dream cycle's five sequential pass invocations against the same
day-dir intact (same "at"-mode convention as dream_apply.py's
applied.jsonl/rejected.jsonl).

DEDUP THRESHOLD — the labeling exercise (Prompt 2.2):
  Cosine similarity alone is a signal, not a merge decision. Before trusting
  a threshold, sample ~20 borderline candidate pairs at each of 3 candidate
  thresholds and have a human label true-duplicate vs false-merge:
    python3 dream_runner.py --pass dedup --sample-labels
  writes a labeling worksheet (candidate pairs, band by band) instead of
  calling the LLM or generating proposals — cheap, side-effect-free, safe to
  run anytime lse-kb + Ollama are reachable. Zero pairs in a band is a valid
  finding (PH3-2 — null results get recorded, not hidden). Once labeled,
  --dedup-threshold picks the merge cutoff for real runs (default 0.92,
  matching index_to_kb's live dedup threshold, until a labeling round shows
  a different value has zero false merges).

USAGE
  # Dry-run (default): prints what would be written, touches no files, no ES.
  python3 dream_runner.py --pass dedup --sessions 50

  # Threshold-labeling worksheet only (no LLM calls, no proposals).
  python3 dream_runner.py --pass dedup --sample-labels

  # Only sessions since a given date.
  python3 dream_runner.py --pass stale-contradiction --since 2026-07-01

  # Actually write report.md/proposals.jsonl (ES is STILL never touched).
  python3 dream_runner.py --pass error-cluster --sessions 200 --no-dry-run

ENV (mirrors goethe.py / episode_index.py's GOETHE_ prefix valve convention)
  GOETHE_EPISODE_DIR                episode corpus root (default /opt/local-se/episodes)
  GOETHE_DREAM_DIR                  dream output root (default /opt/local-se/dreams)
  GOETHE_ES_URL                     Elasticsearch base URL (default http://127.0.0.1:9200)
  GOETHE_TASKS_DB                   tasks.db path (default /opt/local-se/tasks.db)
  GOETHE_AGENT_COMMANDS_LOG         agent_commands.log path (default /opt/local-se/agent_commands.log)
  GOETHE_DREAM_LLM_URL              forced dreamer endpoint (PLANNER_FORCE_URL-style
                                    valve) — health-probed first; falls through the
                                    cascade below on failure or when unset (default "")
  GOETHE_NODE3090_LLM_URL           primary llama-server, GPU (default matches goethe.py's
                                    NODE3090_LLM_URL: http://node3090.home.arpa:8080)
  GOETHE_NODE3090_OLLAMA_URL        Ollama CPU fallback (default http://node3090.home.arpa:11434)
  GOETHE_NODE3090_PLANNER_FALLBACK_MODEL  Ollama fallback model (default qwen3:4b)
  GOETHE_NODE3090_SSH_HOST          node3090 SSH host for the VRAM gate probe (default
                                    node3090.home.arpa, same as _NODE_REGISTRY)
  GOETHE_NODE3090_SSH_USER          SSH user for the VRAM gate probe (default lse-admin)
  GOETHE_NODE3090_SSH_PORT          SSH port for the VRAM gate probe (default 22)
  GOETHE_NODE3090_VRAM_GATE_MB      free-VRAM floor (MiB) below which node3090's GPU is
                                    treated as busy and the llama-server leg is skipped
                                    in favor of Ollama/CPU (default 2000; Prompt 4.1,
                                    TRAUM-AUTO -- same gate pattern as goethe.py's
                                    _planner_free_vram_mb, applied to the remote box)
  GOETHE_DREAM_RUNNER_SESSION_PREFIX  if set, sessions whose session_id starts with
                                    this are excluded from selection — DESIGN.md §2
                                    invariant 3(e), "no dream-of-dreams". Empty (default)
                                    = no filter; the dreamer does not currently run
                                    through the MCP gateway, so it has no session_id
                                    of its own to exclude yet.
  GOETHE_DREAM_PATTERNS_MAX_LINES   patterns pass windowed tail-read size, in raw log
                                    lines (default 50000 — see corpus-audit.md (a)'s
                                    windowed-read caveat)
  GOETHE_DREAM_PATTERNS_RETRY_WINDOW  failure->retry adjacency lookahead window, in
                                    raw log lines (default 20)
  GOETHE_DREAM_PATTERNS_SESSION_GAP_MINUTES  inactivity gap (minutes) used to infer
                                    session boundaries in agent_commands.log, which
                                    carries no session_id of its own (default 30)
  GOETHE_DREAM_PATTERNS_MIN_SEQUENCE_LEN  shortest command sequence considered an
                                    automation candidate (default 3)
  GOETHE_DREAM_PATTERNS_MAX_SEQUENCE_LEN  longest command sequence window mined
                                    (default 8 — bounds worst-case compute)
  GOETHE_DREAM_PATTERNS_MIN_SESSIONS  minimum distinct inferred sessions a repeated
                                    command sequence must span to qualify (default 3)
  GOETHE_DREAM_PATTERNS_TOP_COMMANDS  command-frequency table size cap (default 50)

INVARIANTS enforced structurally in this file, not just by convention
(DESIGN.md §2 row 1 and row 3(e)):
  - Elasticsearch write calls are limited to exactly ONE function,
    `record_crash_error()` (Prompt 4.3, TRAUM-AUTO) — hardcoded to
    index="lse-errors-1024" only, provenance="dream-infra" only, called from
    exactly one place (main()'s crash handler, on an unhandled exception).
    This is an OPERATIONAL failure record about the dreaming system
    itself, the same class of thing goethe.py's own record_error already
    does for every other LSE subsystem — never dream CONTENT, which still
    flows exclusively through dream_apply.py's human-gated apply path.
    `search_index()` (es.search) remains the only way this file reads ES;
    there is still no es.delete call site anywhere, and no write of any
    kind to lse-kb.
  - Zero import of, or HTTP call to, any Anthropic/Cowork API surface.
  - Episode selection can exclude the dreamer's own session_id prefix.
"""

import argparse
import gzip
import json
import math
import os
import random
import re
import sqlite3
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import date, datetime

import episode_index as _epidx
import dream_digest

__version__ = "0.12.0"


# --- config / valve-style env defaults --------------------------------------

def _episode_dir_default() -> str:
    return os.environ.get("GOETHE_EPISODE_DIR", "/opt/local-se/episodes")


def _dream_dir_default() -> str:
    return os.environ.get("GOETHE_DREAM_DIR", "/opt/local-se/dreams")


def _es_url_default() -> str:
    return os.environ.get("GOETHE_ES_URL", "http://127.0.0.1:9200")


def _tasks_db_default() -> str:
    return os.environ.get("GOETHE_TASKS_DB", "/opt/local-se/tasks.db")


def _agent_log_default() -> str:
    return os.environ.get("GOETHE_AGENT_COMMANDS_LOG", "/opt/local-se/agent_commands.log")


def _dream_llm_url_default() -> str:
    return os.environ.get("GOETHE_DREAM_LLM_URL", "")


def _node3090_llm_url_default() -> str:
    return os.environ.get("GOETHE_NODE3090_LLM_URL", "http://node3090.home.arpa:8080")


def _node3090_ollama_url_default() -> str:
    return os.environ.get("GOETHE_NODE3090_OLLAMA_URL", "http://node3090.home.arpa:11434")


def _node3090_fallback_model_default() -> str:
    return os.environ.get("GOETHE_NODE3090_PLANNER_FALLBACK_MODEL", "qwen3:4b")


def _node3090_ssh_host_default() -> str:
    # Same host as node3090_start_llm.sh / goethe.py's _NODE_REGISTRY["node3090"].
    return os.environ.get("GOETHE_NODE3090_SSH_HOST", "node3090.home.arpa")


def _node3090_ssh_user_default() -> str:
    return os.environ.get("GOETHE_NODE3090_SSH_USER", "lse-admin")


def _node3090_ssh_port_default() -> int:
    return int(os.environ.get("GOETHE_NODE3090_SSH_PORT", "22"))


def _node3090_vram_gate_mb_default() -> int:
    """Free-VRAM floor (MiB) on node3090 below which the GPU is treated as
    'busy' and the llama-server leg of the cascade is skipped in favor of
    Ollama/CPU (Prompt 4.1, TRAUM-AUTO). Same gate PATTERN as goethe.py's
    Tools._planner_free_vram_mb (tools/goethe.py:1486) -- identical
    nvidia-smi query -- but that one runs locally to gate a Gemma spawn on
    whichever box goethe.py itself runs on. dream_runner has no local GPU
    to gate: node3090 is remote, so this queries it over SSH instead.
    node3090's llama-server is already resident with parallel=1 and a
    ctx-size-96000 KV cache pre-allocated at startup, so idle-vs-generating
    free VRAM barely moves -- this floor isn't sized to prevent an OOM from
    THIS call, it's sized to detect 'something else is visibly using the
    GPU right now' (an interactive Gemma/benchmark spawn) and defer to CPU
    rather than pile on. 2000 MiB is a coarse 'basically nothing extra
    loaded' floor, not a tuned budget -- adjust via env if node3090's
    baseline idle-free-VRAM drifts from that.
    """
    return int(os.environ.get("GOETHE_NODE3090_VRAM_GATE_MB", "2000"))


def _lockfile_default() -> str:
    # Empty by default -- build_config() resolves this to
    # <dream-dir>/.dream.lock once cfg.dream_dir is known (same "resolve
    # against another already-known path" pattern as manifest_db's own
    # default, built from episode_dir in build_config rather than here).
    return os.environ.get("GOETHE_DREAM_LOCKFILE", "")


def _lock_max_age_s_default() -> float:
    # Secondary staleness signal alongside the primary PID-liveness check
    # (see acquire_lock) -- catches PID reuse (a dead dream_runner's PID
    # got recycled by an unrelated process) and a run stuck well past its
    # own wall-clock budget. 4h matches goethe-dream.service.tmpl's own
    # TimeoutStartSec outer safety net (Prompt 4.1) for all 5 passes
    # combined, so a lock can never outlive systemd's own dead-man's switch.
    return float(os.environ.get("GOETHE_DREAM_LOCK_MAX_AGE_S", str(4 * 3600)))


def _session_active_window_min_default() -> int:
    return int(os.environ.get("GOETHE_DREAM_SESSION_ACTIVE_WINDOW_MIN", "30"))


def _budget_max_llm_calls_default() -> int:
    return int(os.environ.get("GOETHE_DREAM_BUDGET_MAX_LLM_CALLS", "100"))


def _budget_max_wall_clock_min_default() -> float:
    return float(os.environ.get("GOETHE_DREAM_BUDGET_MAX_WALL_CLOCK_MIN", "45"))


def _dream_runner_prefix_default() -> str:
    return os.environ.get("GOETHE_DREAM_RUNNER_SESSION_PREFIX", "")


def _patterns_max_lines_default() -> int:
    # corpus-audit.md (a): unrotated, growing (9.4MB/134k+ lines and climbing)
    # — windowed tail-read, not whole-file. 50k comfortably covers the
    # ~44k-line working corpus Prompt 3.1 targets.
    return int(os.environ.get("GOETHE_DREAM_PATTERNS_MAX_LINES", "50000"))


def _patterns_retry_window_default() -> int:
    return int(os.environ.get("GOETHE_DREAM_PATTERNS_RETRY_WINDOW", "20"))


def _patterns_session_gap_minutes_default() -> int:
    return int(os.environ.get("GOETHE_DREAM_PATTERNS_SESSION_GAP_MINUTES", "30"))


def _patterns_min_sequence_len_default() -> int:
    return int(os.environ.get("GOETHE_DREAM_PATTERNS_MIN_SEQUENCE_LEN", "3"))


def _patterns_max_sequence_len_default() -> int:
    return int(os.environ.get("GOETHE_DREAM_PATTERNS_MAX_SEQUENCE_LEN", "8"))


def _patterns_min_sessions_default() -> int:
    return int(os.environ.get("GOETHE_DREAM_PATTERNS_MIN_SESSIONS", "3"))


def _patterns_top_commands_default() -> int:
    return int(os.environ.get("GOETHE_DREAM_PATTERNS_TOP_COMMANDS", "50"))


def _insights_max_sessions_in_prompt_default() -> int:
    return int(os.environ.get("GOETHE_DREAM_INSIGHTS_MAX_SESSIONS_IN_PROMPT", "20"))


def _ollama_url_default() -> str:
    # Same valve/default as goethe.py's Tools.Valves.OLLAMA_URL (tools/goethe.py:934).
    return os.environ.get("GOETHE_OLLAMA_URL", "http://127.0.0.1:11434")


def _embed_model_default() -> str:
    # Same as goethe.py's Tools.Valves.EMBED_MODEL (tools/goethe.py:938).
    return os.environ.get("GOETHE_EMBED_MODEL", "qwen3-embedding:0.6b")


def _dedup_floor_default() -> float:
    """Candidate-generation floor — deliberately below the merge threshold.

    CALIBRATION NOTE (Prompt 2.2 build-out, 2026-07-11): a live smoke test
    against Ollama nomic-embed-text (3 synthetic doc pairs, real embed
    calls, not the full corpus) found a genuine same-claim near-duplicate
    pair at cosine=0.8188, against unrelated pairs at 0.51-0.54. That is
    well under index_to_kb's 0.92 dedup threshold. embed_text() matches
    goethe.py's _embed() exactly, including its 'search_query: ' prefix on
    BOTH sides of the comparison (nomic-embed-text's own convention expects
    'search_document: ' for indexed text and 'search_query: ' only for the
    query side) — that mismatch likely compresses this pass's usable
    similarity range well below index_to_kb's write-time dedup band. 0.85
    was the original guess before this test; kept lower (0.75) so the
    labeling exercise (--sample-labels) actually has real pairs to sample
    instead of silently finding nothing. Treat this floor, and
    DEFAULT_LABEL_THRESHOLDS below, as provisional until --sample-labels
    runs against the full ~234-doc lse-kb corpus (blocked as of this
    writing: Elasticsearch was down on LUCIFER during this build-out)."""
    return float(os.environ.get("GOETHE_DREAM_DEDUP_FLOOR", "0.75"))


def _error_cluster_threshold_default() -> float:
    """Cosine similarity floor for grouping error/timeout occurrences as
    'the same underlying failure.' Same embedding path/quirk as the dedup
    pass (search_query: prefix on both sides), so the same calibration
    caution applies -- see build_error_clusters' module docstring note."""
    return float(os.environ.get("GOETHE_DREAM_ERROR_CLUSTER_THRESHOLD", "0.80"))


def _dedup_threshold_default() -> float:
    """Merge cutoff for real (non-labeling) runs. Starts equal to
    index_to_kb's own live dedup threshold (tools/goethe.py:4913,
    `dup_hits[0]["_score"] >= 0.92`) as a placeholder — see the
    CALIBRATION NOTE on _dedup_floor_default above for why this specific
    number is suspect for THIS pass's embedding convention. The labeling
    exercise (--sample-labels) is what actually earns changing it; this is
    not that exercise's result, just where the merge gate starts."""
    return float(os.environ.get("GOETHE_DREAM_DEDUP_THRESHOLD", "0.92"))


# Provisional — see _dedup_floor_default's CALIBRATION NOTE. Spans lower
# than index_to_kb's 0.92 because the 3-pair smoke test done during Prompt
# 2.2 build-out found a real near-duplicate at 0.82, not >=0.90. Re-derive
# these from --sample-labels against the full corpus, don't trust by eye.
DEFAULT_LABEL_THRESHOLDS = (0.78, 0.82, 0.86)
DEFAULT_LABEL_BAND = 0.03
DEFAULT_LABEL_SAMPLE_N = 20


@dataclass
class DreamBudget:
    """Per-run (one dream_runner.py process invocation -- one `--pass X`
    run, matching goethe-dream.service.tmpl's one-ExecStart-per-pass
    design from Prompt 4.1) resource ceiling. Prompt 4.2, TRAUM-AUTO.

    Attached to DreamConfig.budget ONLY by main() for real runs; direct
    DreamConfig(...) construction elsewhere (every existing test, the
    --sample-labels utility path) leaves cfg.budget as None, and every
    budget check in this file (_budget_checkpoint, call_dream_llm) is a
    silent no-op when cfg.budget is None -- budgets are opt-in via main(),
    never assumed present.

    'sessions consumed' only means something to a pass with a natural
    per-session LLM loop -- today that is run_pass_stale_contradiction's
    demote sub-pass alone. Passes without one (dedup batches candidate
    PAIRS, error-cluster batches CLUSTERS, insights batches DOMAINS,
    patterns makes no LLM call at all and explicitly ignores `sessions`)
    simply never call record_session(), and this dimension stays inert
    for them -- not every budget dimension has to bind on every pass.
    """
    max_sessions: int
    max_llm_calls: int
    max_wall_clock_s: float
    started_at: float = field(default_factory=time.monotonic)
    sessions_consumed: int = 0
    llm_calls_made: int = 0
    truncated: bool = False
    truncation_reason: str = ""

    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at

    def exhausted(self) -> str | None:
        """First exhausted dimension's human-readable reason, in a fixed
        check order (wall-clock first -- the one dimension every pass
        shares regardless of its own loop shape), or None if nothing is
        exhausted yet. Does NOT mutate state -- see mark_truncated."""
        if self.elapsed_s() >= self.max_wall_clock_s:
            return f"wall-clock budget exhausted ({self.elapsed_s():.0f}s >= {self.max_wall_clock_s:.0f}s)"
        if self.llm_calls_made >= self.max_llm_calls:
            return f"LLM-call budget exhausted ({self.llm_calls_made} >= {self.max_llm_calls})"
        if self.sessions_consumed >= self.max_sessions:
            return f"session budget exhausted ({self.sessions_consumed} >= {self.max_sessions})"
        return None

    def mark_truncated(self, reason: str) -> None:
        """First reason wins -- if wall-clock trips first and a caller
        checks again later after llm_calls also happens to be over, the
        report should still say what ACTUALLY stopped it first."""
        if not self.truncated:
            self.truncated = True
            self.truncation_reason = reason

    def record_llm_call(self) -> None:
        self.llm_calls_made += 1

    def record_session(self, n: int = 1) -> None:
        self.sessions_consumed += n


def _budget_checkpoint(cfg: "DreamConfig") -> bool:
    """True (and marks cfg.budget.truncated, first reason wins) if a
    budget is attached to cfg and ANY dimension is currently exhausted.
    False -- a silent no-op -- when cfg.budget is None. Call at the top of
    every per-item loop iteration a pass has (one dedup batch, one
    contradiction-check session, one error cluster, one insight domain)
    to stop early and cleanly rather than grinding through remaining
    items that would just immediately re-hit the same exhausted budget."""
    if cfg.budget is None:
        return False
    reason = cfg.budget.exhausted()
    if reason:
        cfg.budget.mark_truncated(reason)
        return True
    return False


@dataclass
class DreamConfig:
    episode_dir: str
    dream_dir: str
    manifest_db: str
    es_url: str
    tasks_db: str
    agent_log: str
    dream_llm_url: str
    node3090_llm_url: str
    node3090_ollama_url: str
    node3090_fallback_model: str
    ollama_url: str
    embed_model: str
    dedup_floor: float
    dedup_threshold: float
    error_cluster_threshold: float
    runner_session_prefix: str
    sessions_limit: int
    since: str | None
    pass_name: str
    dry_run: bool
    label_thresholds: tuple = DEFAULT_LABEL_THRESHOLDS
    label_band: float = DEFAULT_LABEL_BAND
    label_sample_n: int = DEFAULT_LABEL_SAMPLE_N
    labels_out: str | None = None
    patterns_max_lines: int = 50000
    patterns_retry_window: int = 20
    patterns_session_gap_minutes: int = 30
    patterns_min_sequence_len: int = 3
    patterns_max_sequence_len: int = 8
    patterns_min_sessions: int = 3
    patterns_top_commands: int = 50
    patterns_out: str | None = None
    insights_max_sessions_in_prompt: int = 20
    # Prompt 4.1 (TRAUM-AUTO) -- remote VRAM gate for the node3090 llama-server
    # leg. Defaulted (not required) so direct DreamConfig(...) construction
    # elsewhere (tests, ad hoc scripts) keeps working without every caller
    # needing to know about it; build_config() always sets these explicitly
    # from CLI/env via the _node3090_*_default() functions above.
    node3090_ssh_host: str = "node3090.home.arpa"
    node3090_ssh_user: str = "lse-admin"
    node3090_ssh_port: int = 22
    node3090_vram_gate_mb: int = 2000
    # Prompt 4.2 (TRAUM-AUTO) -- lockfile, recent-session-activity guard,
    # and per-run budgets. All defaulted (not required) for the same
    # backward-compatibility reason as the node3090_* fields above: every
    # existing direct DreamConfig(...) call site (5 test files as of
    # Prompt 4.1) keeps working with zero changes. `lockfile=""` is a
    # sentinel build_config() always resolves to a real path
    # (<dream-dir>/.dream.lock) once cfg.dream_dir is known; ad hoc
    # construction that leaves it "" and then calls acquire_lock() directly
    # would resolve it to a lock in the CURRENT directory, which is not
    # sensible for a real run (but harmless for a test that never calls
    # acquire_lock() at all, which is most of them).
    lockfile: str = ""
    lock_max_age_s: float = 4 * 3600
    session_active_window_min: int = 30
    budget_max_sessions: int = 50
    budget_max_llm_calls: int = 100
    budget_max_wall_clock_min: float = 45.0
    ignore_guards: bool = False
    budget: "DreamBudget | None" = None


def build_config(args: argparse.Namespace) -> DreamConfig:
    episode_dir = args.episode_dir
    manifest_db = args.manifest_db or os.path.join(episode_dir, "manifest.db")
    dream_dir = args.dream_dir
    lockfile = args.lockfile or os.path.join(dream_dir, ".dream.lock")
    # Prompt 4.2's own phrasing is "max sessions consumed" as a single
    # concept -- default the CONSUMPTION budget to whatever the SELECTION
    # cap (--sessions) already is, so out of the box this adds no NEW
    # restriction beyond what select_undreamed_sessions() already limits
    # itself to; --budget-max-sessions only matters when explicitly set
    # tighter (or looser) than --sessions.
    budget_max_sessions = (
        args.budget_max_sessions if args.budget_max_sessions is not None else args.sessions
    )
    return DreamConfig(
        episode_dir=episode_dir,
        dream_dir=args.dream_dir,
        manifest_db=manifest_db,
        es_url=args.es_url,
        tasks_db=args.tasks_db,
        agent_log=args.agent_log,
        dream_llm_url=args.dream_llm_url,
        node3090_llm_url=args.node3090_llm_url,
        node3090_ollama_url=args.node3090_ollama_url,
        node3090_fallback_model=args.node3090_fallback_model,
        node3090_ssh_host=args.node3090_ssh_host,
        node3090_ssh_user=args.node3090_ssh_user,
        node3090_ssh_port=args.node3090_ssh_port,
        node3090_vram_gate_mb=args.node3090_vram_gate_mb,
        ollama_url=args.ollama_url,
        embed_model=args.embed_model,
        dedup_floor=args.dedup_floor,
        dedup_threshold=args.dedup_threshold,
        error_cluster_threshold=args.error_cluster_threshold,
        runner_session_prefix=args.runner_session_prefix,
        sessions_limit=args.sessions,
        since=args.since,
        pass_name=args.pass_name,
        dry_run=args.dry_run,
        label_thresholds=tuple(args.label_thresholds),
        label_band=args.label_band,
        label_sample_n=args.label_sample_n,
        labels_out=args.labels_out,
        patterns_max_lines=args.patterns_max_lines,
        patterns_retry_window=args.patterns_retry_window,
        patterns_session_gap_minutes=args.patterns_session_gap_minutes,
        patterns_min_sequence_len=args.patterns_min_sequence_len,
        patterns_max_sequence_len=args.patterns_max_sequence_len,
        patterns_min_sessions=args.patterns_min_sessions,
        patterns_top_commands=args.patterns_top_commands,
        patterns_out=args.patterns_out,
        insights_max_sessions_in_prompt=args.insights_max_sessions_in_prompt,
        lockfile=lockfile,
        lock_max_age_s=args.lock_max_age_s,
        session_active_window_min=args.session_active_window_min,
        budget_max_sessions=budget_max_sessions,
        budget_max_llm_calls=args.budget_max_llm_calls,
        budget_max_wall_clock_min=args.budget_max_wall_clock_min,
        ignore_guards=args.ignore_guards,
    )


# --- manifest.db (READ-ONLY) -------------------------------------------------

def select_undreamed_sessions(cfg: DreamConfig) -> list[sqlite3.Row]:
    """Sessions where dreamed_at IS NULL, newest-selection-bounded by
    --sessions/--since, excluding the dreamer's own session_id prefix when
    GOETHE_DREAM_RUNNER_SESSION_PREFIX is set (DESIGN.md §2 invariant 3(e) —
    no dream-of-dreams). Never writes dreamed_at — only dream_apply.py does."""
    if not os.path.exists(cfg.manifest_db):
        print(f"[dream_runner] manifest.db not found at {cfg.manifest_db} — nothing to do",
              file=sys.stderr)
        return []
    conn = sqlite3.connect(cfg.manifest_db, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM sessions WHERE dreamed_at IS NULL"
        params: list = []
        if cfg.runner_session_prefix:
            query += " AND session_id NOT LIKE ?"
            params.append(f"{cfg.runner_session_prefix}%")
        if cfg.since:
            query += " AND start_ts >= ?"
            params.append(cfg.since)
        query += " ORDER BY start_ts ASC"
        if cfg.sessions_limit:
            query += " LIMIT ?"
            params.append(cfg.sessions_limit)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return rows


# --- episode JSONL (READ-ONLY) ----------------------------------------------

def _open_session_file(path: str):
    """Open a session file for text reading, transparently handling .gz.
    Trivial duplicate of episode_index.py's private helper of the same
    name — kept local rather than reaching into another module's
    underscore-prefixed function."""
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "rt", encoding="utf-8")


def _locate_session_file(cfg: DreamConfig, session_row: sqlite3.Row) -> str | None:
    """Find the episode JSONL(.gz) file for one manifest row. manifest.db
    stores no explicit day-dir, so the fast path derives it from start_ts's
    own date (the file lives in the day-dir matching when the gateway
    created it). Falls back to a full day-dir scan (reusing
    episode_index.py's iter_day_dirs/iter_session_files) if that guess is
    wrong — e.g. clock skew, or a session whose first line landed just
    after local midnight relative to the file's creation."""
    session_id = session_row["session_id"]
    start_ts = session_row["start_ts"] or ""
    day = start_ts[:10] if len(start_ts) >= 10 else None
    if day:
        for suffix in (".jsonl", ".jsonl.gz"):
            candidate = os.path.join(cfg.episode_dir, day, f"{session_id}{suffix}")
            if os.path.exists(candidate):
                return candidate
    for _day, day_dir in _epidx.iter_day_dirs(cfg.episode_dir):
        for path in _epidx.iter_session_files(day_dir):
            if os.path.basename(path).startswith(session_id + ".jsonl"):
                return path
    return None


def read_session_episodes(cfg: DreamConfig, session_row: sqlite3.Row) -> list[dict]:
    """Read one session's episode JSONL(.gz), skipping unparseable lines —
    same tolerance as episode_index.py's parse_session_file (a
    concurrently-appending gateway can leave a truncated trailing line)."""
    path = _locate_session_file(cfg, session_row)
    if not path:
        return []
    lines: list[dict] = []
    try:
        with _open_session_file(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    lines.append(obj)
    except OSError as e:
        print(f"[dream_runner] WARNING: could not read {path}: {e}", file=sys.stderr)
    return lines


# --- Elasticsearch (READ-ONLY — search/get only, never index/update/delete) -

def es_client(cfg: DreamConfig):
    """Lazy ES 8.x client. Same construction as goethe.py's Tools._es
    (tools/goethe.py:4555) — no auth, per-call instantiation."""
    from elasticsearch import Elasticsearch  # noqa: PLC0415

    return Elasticsearch(cfg.es_url, request_timeout=10)


def search_index(cfg: DreamConfig, index: str, body: dict) -> list[dict]:
    """The ONLY ES READ call shape this file is allowed to use. Do not add
    an es.index/update/delete call here — proposing a KB/skill change is
    this file's entire job; applying one is dream_apply.py's (Prompt 2.5),
    and only past a human confirm-gate. The ONE exception to "this file
    never writes ES" anywhere in the module is record_crash_error() below
    (Prompt 4.3) — a completely separate function, hardcoded to
    index="lse-errors-1024" only, never touched by any pass function, never
    reachable from this function."""
    es = es_client(cfg)
    resp = es.search(index=index, body=body)
    return [dict(h["_source"], _id=h["_id"]) for h in resp["hits"]["hits"]]


def record_crash_error(cfg: DreamConfig, error_text: str, context: str = "dream-runner") -> str:
    """THE ONLY Elasticsearch WRITE call anywhere in dream_runner.py --
    Prompt 4.3 (TRAUM-AUTO)'s sanctioned, narrow exception to this file's
    otherwise-absolute read-only invariant (module docstring INVARIANTS
    section above; test_dream_engine.py's TestESReadOnlyBoundary covers
    search_index() specifically, not this function). Hardcoded to
    index="lse-errors-1024" and provenance="dream-infra" -- structurally
    incapable of writing lse-kb. This is an OPERATIONAL failure record
    about the dreaming system itself, the same class of thing goethe.py's
    own Tools.record_error (tools/goethe.py:5099) already writes for every
    other LSE subsystem; dream CONTENT still only ever flows through
    dream_apply.py's human-gated apply path.

    Deliberately does NOT reuse goethe.py's Tools.record_error, which
    would mean instantiating the whole Tools god-class just for this one
    call -- exactly what TRAUM's architecture note (DESIGN.md, "adds code
    mostly in NEW files... to avoid growing the god-class") says to avoid.
    Reimplements just enough of its document shape directly against this
    file's own es_client(cfg) (same one search_index() already uses): a
    sha256-of-normalized-text hash as the doc id (same normalization as
    goethe.py's own error_hash, so an identical error string collides to
    the SAME document whether recorded here or via the interactive tool),
    a plain occurrence_count bump on a repeat via get-then-update, falling
    back to a fresh es.index() when the get fails for ANY reason (not
    found -- the overwhelmingly common case -- or ES genuinely down).
    Deliberately skips goethe.py's embedding-based KNN near-duplicate
    check: a crash handler must be maximally simple and robust, and
    computing an Ollama embedding here would add a second network
    dependency to a code path whose whole job is coping with the FIRST
    one having already failed.

    Best-effort and total: ANY failure anywhere in this function (ES
    unreachable, malformed response, whatever) is caught, logged to
    stderr, and swallowed -- never re-raised. A broken error-reporting
    path must never mask or replace the ORIGINAL crash it exists to
    report; main()'s crash handler always re-raises that original
    exception regardless of what happens here.

    Honors cfg.dry_run exactly like every other write in this file (module
    docstring USAGE section: "touches no files, no ES") -- prints what it
    would have written instead of calling ES.
    """
    import hashlib as _hashlib  # noqa: PLC0415
    import re as _re  # noqa: PLC0415
    from datetime import timezone as _timezone  # noqa: PLC0415

    normalised = _re.sub(r"\s+", " ", error_text.lower().strip())
    error_hash = _hashlib.sha256(normalised.encode()).hexdigest()[:16]
    now = datetime.now(_timezone.utc).isoformat()

    if cfg.dry_run:
        msg = (f"[dry-run] would record_error to lse-errors-1024 (hash={error_hash}, "
               f"context={context!r}, provenance=dream-infra)")
        print(f"[dream_runner] {msg}", file=sys.stderr)
        return msg

    try:
        es = es_client(cfg)
        try:
            existing = es.get(index="lse-errors-1024", id=error_hash)
            new_count = (existing["_source"].get("occurrence_count") or 0) + 1
            es.update(index="lse-errors-1024", id=error_hash, body={
                "doc": {"last_seen": now, "occurrence_count": new_count},
            })
            return f"lse-errors-1024 updated: dream-infra crash pattern now seen {new_count}x (hash={error_hash})"
        except Exception:
            doc = {
                "error_hash": error_hash,
                "error_text": error_text[:4000],
                "context": context,
                "provenance": "dream-infra",
                "resolution": "",
                "occurrence_count": 1,
                "first_seen": now,
                "last_seen": now,
            }
            es.index(index="lse-errors-1024", id=error_hash, document=doc)
            return f"lse-errors-1024 created: new dream-infra crash recorded (hash={error_hash})"
    except Exception as exc:
        msg = f"record_crash_error itself failed ({exc}) -- lse-errors-1024 was NOT updated"
        print(f"[dream_runner] WARNING: {msg}", file=sys.stderr)
        return msg


# --- embeddings / cosine dedup (Prompt 2.2) ---------------------------------

def embed_text(cfg: DreamConfig, text: str) -> list:
    """Embedding from the configured Ollama model — the SAME call shape
    as goethe.py's Tools._embed (tools/goethe.py:4540): 'search_query: '
    prefix, /api/embed, 15s timeout. Kept identical on purpose even though
    nomic's own convention is a 'search_document: ' prefix for indexed text
    — matching the live system's quirk is what keeps a freshly-computed
    embedding here comparable to the ones index_to_kb already stored in
    lse-kb through this exact same function."""
    import requests  # noqa: PLC0415

    r = requests.post(
        f"{cfg.ollama_url.rstrip('/')}/api/embed",
        json={"model": cfg.embed_model, "input": "search_query: " + text[:5000]},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["embeddings"][0]


def embed_kb_docs(cfg: DreamConfig, kb_docs: list) -> dict:
    """Embed every lse-kb doc's content (capped at 8000 chars — same cap
    index_to_kb uses for nomic-embed-text's token limit, tools/goethe.py:4893).
    A single doc's embed failure is logged and skipped, not fatal to the pass."""
    embeddings = {}
    for doc in kb_docs:
        doc_id = doc.get("_id")
        content = (doc.get("content") or "").strip()
        if not doc_id or not content:
            continue
        try:
            embeddings[doc_id] = embed_text(cfg, content[:8000])
        except Exception as exc:
            print(f"[dream_runner] WARNING: embed failed for doc_id={doc_id} ({exc}) — skipped",
                  file=sys.stderr)
    return embeddings


def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def find_candidate_pairs(embeddings: dict, floor: float) -> list:
    """All doc-id pairs with cosine >= floor, sorted descending by
    similarity. O(n^2) comparisons — fine at lse-kb's current scale (234
    docs -> ~27k pairs); revisit with an ANN/kNN prefilter if the KB grows
    an order of magnitude past that."""
    ids = list(embeddings.keys())
    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sim = _cosine(embeddings[ids[i]], embeddings[ids[j]])
            if sim >= floor:
                pairs.append((ids[i], ids[j], sim))
    pairs.sort(key=lambda t: t[2], reverse=True)
    return pairs


_PART_SUFFIX_RE = re.compile(r"\s*\(part\s+\d+\)\s*$", re.IGNORECASE)
_TITLE_WORD_RE = re.compile(r"[a-z0-9]+")

# Generic words that recur across many UNRELATED KB titles in this corpus
# (LSE/Stack prefix a large share of docs; Guide/Plan/Reference/Complete/
# Deployment are common document-type suffixes, not content). Stripped
# before comparing two titles' word sets so the comparison is anchored on
# the words that actually distinguish one document series from another,
# not the boilerplate every title shares.
_TITLE_STOPWORDS = frozenset({
    "lse", "stack", "guide", "plan", "reference", "complete", "deployment",
    "the", "a", "an", "and", "or", "of", "for", "on", "to", "in", "with",
    "doc", "document", "v1", "v2", "v3",
})


def _base_title(title: str) -> str:
    """Strip a trailing '(part N)' suffix so chunks of one larger source
    document collapse to the same key.

    FINDING (Prompt 2.2, live run against the real ~365-doc lse-kb corpus,
    2026-07-11): a large share of high-cosine pairs at the 0.86-0.89 band
    turned out to be adjacent CHUNKS of the same original document — e.g.
    'SearXNG Metrics & Query Tracking - Deployment Guide (part 2)' vs
    '(part 3)' of the same guide — not independently-authored duplicates.
    Those are not a dedup case: merging one chunk into another via
    mentor_correct would DELETE real, distinct content, not remove
    redundancy. Excluded before either the labeling worksheet or the merge
    path ever sees them."""
    return _PART_SUFFIX_RE.sub("", title or "").strip().lower()


def _title_signature(title: str) -> frozenset:
    """Reduce a title to the set of 'significant' words used to catch
    same-document chunks whose base doc was re-indexed under a shortened or
    reworded ALIAS title, which the plain _base_title exact-match misses.

    FINDING (dedup threshold-labeling exercise, 55-pair worksheet,
    2026-07-11): several real same-document-chunk pairs slipped past
    _base_title's exact-match check because the base/root doc existed in
    the corpus under a differently-worded title for the same series —
    e.g. 'SearXNG Metrics & Query Tracking - Deployment Guide (part 4)' vs
    its own base doc filed as 'Searxng Metrics And Query Tracking'
    (different case, '&' respelled 'And', trailing '- Deployment Guide'
    dropped); 'SearXNG SQLite Query Logger - Deployment Plan (part 2)' vs
    'Searxng Sqlite Deployment Plan' (missing 'Query Logger -'); 'LSE Stack
    Troubleshooting Guide (part 2)' vs just 'Troubleshooting'. In each real
    case, once generic/boilerplate words are stripped (see
    _TITLE_STOPWORDS), the shorter alias title's remaining words are
    entirely contained in the fuller title's remaining words.

    KNOWN LIMITATION, found while checking this fix against the labeled
    worksheet: two docs about genuinely DIFFERENT things can still collide
    if their only non-stopword words happen to match — e.g. 'Llama Cpp
    Build' (LUCIFER/RTX4090) vs 'llama.cpp Build Reference' (node3090) both
    reduce to {llama, cpp, build}, but are separately-authored docs for two
    different machines, not chunks of one document. In the labeled
    worksheet this pair was independently judged NOT a duplicate anyway, so
    filtering it here doesn't cause a wrong merge — but it does mean the
    pair would silently stop appearing as a dedup candidate at all. Treat
    this signature match as a stronger signal than a bare word overlap, not
    as certain proof of a chunk relationship — a spot-check of dropped
    pairs is worthwhile if this filter's drop rate looks unusually high."""
    words = _TITLE_WORD_RE.findall(_base_title(title))
    return frozenset(w for w in words if w not in _TITLE_STOPWORDS)


def filter_same_document_chunks(pairs: list, docs_by_id: dict) -> list:
    """Drop candidate pairs that are chunks of the same source document.
    Two independent signals, either sufficient on its own:
      1. exact base-title match once a trailing '(part N)' is stripped
         (the original check) — see _base_title's FINDING note; or
      2. one title's significant-word signature is a non-empty subset of
         the other's (see _title_signature's FINDING note) — catches
         shortened/aliased base titles for the same series that don't
         exact-match.
    A pair with no title on either side (title missing/empty) is never
    filtered by either rule — nothing to compare. Drop counts for each
    signal are reported to stderr separately, since signal 2 is a fuzzier
    heuristic than signal 1 (see _title_signature's KNOWN LIMITATION) and
    is worth keeping visible rather than silently folded into one number."""
    kept = []
    exact_dropped = 0
    alias_dropped = 0
    for a, b, sim in pairs:
        title_a = docs_by_id.get(a, {}).get("title", "")
        title_b = docs_by_id.get(b, {}).get("title", "")
        ta = _base_title(title_a)
        tb = _base_title(title_b)
        if ta and tb and ta == tb:
            exact_dropped += 1
            continue
        sig_a = _title_signature(title_a)
        sig_b = _title_signature(title_b)
        if sig_a and sig_b and (sig_a <= sig_b or sig_b <= sig_a):
            alias_dropped += 1
            continue
        kept.append((a, b, sim))
    if exact_dropped or alias_dropped:
        print(
            f"[dream_runner] filter_same_document_chunks: dropped "
            f"{exact_dropped} exact-title-match pair(s) + {alias_dropped} "
            "alias-title-signature pair(s) as same-document chunks.",
            file=sys.stderr,
        )
    return kept


def sample_pairs_for_labeling(pairs: list, cfg: DreamConfig) -> dict:
    """For each candidate threshold, sample up to label_sample_n pairs whose
    cosine falls in the band [threshold, threshold + label_band) — the
    borderline pairs that actually decide whether that threshold is safe,
    not the obvious high-90s exact restatements. A fixed seed keeps the
    sample reproducible across a labeling session; a band with fewer than
    label_sample_n pairs returns all of them (PH3-2 — a thin or empty band
    is itself a finding, not padded to look like a full sample)."""
    rng = random.Random(20260711)  # fixed seed: reproducible sampling, not a date dependency
    sample = {}
    for t in cfg.label_thresholds:
        band_pairs = [p for p in pairs if t <= p[2] < t + cfg.label_band]
        if len(band_pairs) > cfg.label_sample_n:
            band_pairs = rng.sample(band_pairs, cfg.label_sample_n)
            band_pairs.sort(key=lambda p: p[2], reverse=True)
        sample[t] = band_pairs
    return sample


def render_labeling_worksheet(sample: dict, docs_by_id: dict, cfg: DreamConfig) -> str:
    """Human-labelable plain-text worksheet — 'we label them together
    in-thread' per Prompt 2.2. Each pair gets a blank checkbox line; nothing
    here is auto-decided."""
    lines = [
        "# TRAUM dedup threshold-labeling worksheet",
        "",
        f"floor={cfg.dedup_floor} band-width={cfg.label_band} "
        f"thresholds={cfg.label_thresholds} sample-n={cfg.label_sample_n}",
        "",
    ]
    for t in cfg.label_thresholds:
        band_pairs = sample.get(t, [])
        lines.append(f"## Threshold {t:.2f} — band [{t:.2f}, {t + cfg.label_band:.2f}) "
                      f"— {len(band_pairs)} pair(s) sampled")
        lines.append("")
        if not band_pairs:
            lines.append("_(no candidate pairs fell in this band — null result, not an error)_")
            lines.append("")
            continue
        for i, (a, b, sim) in enumerate(band_pairs, 1):
            da, db = docs_by_id.get(a, {}), docs_by_id.get(b, {})
            lines.append(f"{i}. cosine={sim:.4f}")
            lines.append(f"   A doc_id={a} title={da.get('title', '?')!r}")
            lines.append(f"      {(da.get('content') or '')[:200]!r}")
            lines.append(f"   B doc_id={b} title={db.get('title', '?')!r}")
            lines.append(f"      {(db.get('content') or '')[:200]!r}")
            lines.append("   LABEL: [ ] true-duplicate   [ ] NOT a duplicate (false-merge)")
            lines.append("")
    return "\n".join(lines)


def pick_threshold_from_labels(labeled_pairs: list, thresholds=DEFAULT_LABEL_THRESHOLDS):
    """labeled_pairs: [{"cosine": float, "true_duplicate": bool}, ...],
    merged across every sampled band. Picks the LOWEST candidate threshold
    (most permissive — catches the most merges) with ZERO false merges among
    labeled pairs at or above it. Returns (threshold_or_None, narrative).
    None is a valid outcome (PH3-2): if every candidate threshold has at
    least one false merge at or above it, that is the honest result to
    record, not a reason to silently pick the highest one anyway."""
    for t in sorted(thresholds):
        at_or_above = [p for p in labeled_pairs if p["cosine"] >= t]
        false_merges = [p for p in at_or_above if not p["true_duplicate"]]
        if not false_merges and at_or_above:
            return t, (
                f"Threshold {t:.2f}: zero false merges across "
                f"{len(at_or_above)} labeled pair(s) at/above it."
            )
    return None, (
        f"No threshold in {thresholds} had zero false merges across "
        f"{len(labeled_pairs)} labeled pair(s) — recording a null result "
        "(PH3-2): nothing is safe to merge automatically yet at these "
        "thresholds. Re-run --sample-labels with a wider band or more "
        "samples before revisiting."
    )


# --- tasks.db / agent_commands.log (READ-ONLY) -------------------------------

def read_task_blocks(cfg: DreamConfig, limit: int = 200) -> list[sqlite3.Row]:
    """corpus-audit.md (b): single table, no joins. 79% of rows only have
    free-text plan/done_steps/findings (no steps_json) — callers need a
    free-text fallback path, this function just returns raw rows."""
    if not os.path.exists(cfg.tasks_db):
        return []
    conn = sqlite3.connect(cfg.tasks_db, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM task_blocks ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return rows


def tail_agent_log(cfg: DreamConfig, max_lines: int = 5000) -> list[str]:
    """Windowed read, not whole-file — corpus-audit.md (a)'s explicit
    caveat: the log is unrotated and growing (9.4MB and climbing)."""
    if not os.path.exists(cfg.agent_log):
        return []
    with open(cfg.agent_log, "rt", encoding="utf-8", errors="replace") as f:
        return list(deque(f, maxlen=max_lines))


# --- local-model endpoint cascade (same shape as goethe.py's node planner) --

def _health_probe(url: str, timeout: int = 3) -> bool:
    import urllib.request as _ureq  # noqa: PLC0415

    try:
        with _ureq.urlopen(f"{url.rstrip('/')}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _llama_server_slot_idle(url: str, timeout: int = 3) -> bool | None:
    """Return True when every llama-server slot is idle, False when any
    slot is processing, and None when slot state cannot be established.

    A loaded model legitimately consumes nearly all VRAM. Free-VRAM alone
    therefore cannot distinguish an idle, reusable server from an interactive
    workload. `/slots` is the authoritative activity signal when available;
    callers retain the fail-closed VRAM fallback when it is not.
    """
    import urllib.request as _ureq  # noqa: PLC0415

    try:
        with _ureq.urlopen(f"{url.rstrip('/')}/slots", timeout=timeout) as r:
            if r.status != 200:
                return None
            slots = json.loads(r.read().decode("utf-8"))
        if not isinstance(slots, list) or not slots:
            return None
        valid_slots = [slot for slot in slots if isinstance(slot, dict)]
        if not valid_slots:
            return None
        return not any(bool(slot.get("is_processing")) for slot in valid_slots)
    except Exception:
        return None


def _node3090_free_vram_mb(host: str, user: str, port: int, timeout: int = 8) -> int:
    """Free VRAM (MiB) on node3090's GPU, queried over SSH.

    Remote counterpart to goethe.py's Tools._planner_free_vram_mb
    (tools/goethe.py:1486): the identical `nvidia-smi --query-gpu=memory.free
    --format=csv,noheader,nounits` probe, run on node3090 via a bare `ssh`
    subprocess rather than a local one -- dream_runner has no local GPU to
    gate against (LUCIFER may not even have a model loaded), node3090 is
    the box whose GPU the cascade actually contends for. BatchMode=yes so a
    missing/expired key fails fast instead of hanging on a password prompt.
    Returns 0 (== 'treat as busy', the safe direction) on any SSH failure,
    timeout, or unparseable output -- a flaky link should fail toward the
    CPU-only leg, never toward assuming the GPU is free.
    """
    import subprocess as _sp3  # noqa: PLC0415

    try:
        r = _sp3.run(
            [
                "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
                "-o", "BatchMode=yes", "-p", str(port), f"{user}@{host}",
                "nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        lines = [ln.strip() for ln in r.stdout.strip().splitlines() if ln.strip()]
        if lines:
            return max(int(ln) for ln in lines)
    except Exception:
        pass
    return 0


def _post_chat_completion(base_url: str, payload: bytes, timeout: int) -> str:
    """POST payload to /v1/chat/completions. Returns content or 'ERROR: ...'.
    Identical shape to goethe.py's Tools._post_chat_completion
    (tools/goethe.py:1297) — kept in lockstep so a fix there is easy to
    port here."""
    import urllib.error as _uerr  # noqa: PLC0415
    import urllib.request as _ureq  # noqa: PLC0415

    req = _ureq.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _ureq.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
    except _uerr.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        return f"ERROR: HTTP {exc.code} — {body}"
    except Exception as exc:
        return f"ERROR: {exc}"


def _build_payload(system_prompt: str, user_content: str, no_think: bool, model: str = "") -> bytes:
    messages = [{"role": "system", "content": system_prompt}]
    content = user_content.strip()
    if no_think:
        content += " /no_think"
    messages.append({"role": "user", "content": content})
    payload_obj: dict = {
        "messages": messages,
        "max_tokens": 8192,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        # Same llama-server reasoning-budget kill-switch as goethe.py:1363 —
        # 0 ends thinking immediately, overrides any CLI --reasoning-budget.
        # Endpoints without think-tags (Gemma) ignore this field.
        "thinking_budget_tokens": 0,
    }
    if model:
        payload_obj["model"] = model
    return json.dumps(payload_obj).encode()


def call_dream_llm(system_prompt: str, user_content: str, cfg: DreamConfig, no_think: bool = True) -> str:
    """Same 3-step endpoint cascade as goethe.py's _call_node_planner
    (tools/goethe.py:1322):
      0. DREAM_LLM_URL forced endpoint (PLANNER_FORCE_URL-style valve) —
         health-probed; used directly when up, silently skipped when
         down/unset. Lets a forced dreamer-model experiment become pure
         configuration, same as PLANNER_FORCE_URL does for node_plan().
      1. NODE3090_LLM_URL llama-server (GPU, primary).
      2. NODE3090_OLLAMA_URL Ollama CPU fallback (always-available).
    Returns the model's raw reply string, 'ERROR: <reason>' if every step
    fails, or 'BUDGET_EXHAUSTED: <reason>' (Prompt 4.2, TRAUM-AUTO) if
    cfg.budget is attached and already exhausted -- checked FIRST, before
    even the forced-endpoint leg, so a truncated run makes zero network
    calls of any kind once its budget is spent, not just zero node3090
    calls. request_dream_envelope() special-cases this prefix so a
    deliberate stop is never reported to the operator as "the dreamer
    failed" -- it didn't; we chose not to ask it.
    """
    if _budget_checkpoint(cfg):
        return f"BUDGET_EXHAUSTED: {cfg.budget.truncation_reason}"
    if cfg.budget is not None:
        cfg.budget.record_llm_call()

    if cfg.dream_llm_url:
        force_url = cfg.dream_llm_url.rstrip("/")
        if _health_probe(force_url):
            print(f"[dream_runner] DREAM_LLM_URL healthy -> {force_url}", file=sys.stderr)
            payload = _build_payload(system_prompt, user_content, no_think)
            result = _post_chat_completion(force_url, payload, 180)
            if not result.startswith("ERROR:"):
                return result
            print(f"[dream_runner] DREAM_LLM_URL call failed ({result[:80]}), "
                  "falling back to cascade", file=sys.stderr)
        else:
            print(f"[dream_runner] DREAM_LLM_URL down ({force_url}) — cascade", file=sys.stderr)

    llm_url = cfg.node3090_llm_url.rstrip("/")
    server_healthy = _health_probe(llm_url)
    use_llama_server = False
    if server_healthy:
        slot_idle = _llama_server_slot_idle(llm_url)
        if slot_idle is True:
            use_llama_server = True
            print(
                f"[dream_runner] llama-server healthy with idle slot -> {llm_url}",
                file=sys.stderr,
            )
        elif slot_idle is False:
            print(
                "[dream_runner] llama-server has an active slot -- falling straight "
                "to Ollama to avoid contending with an interactive request",
                file=sys.stderr,
            )
        else:
            free_vram = _node3090_free_vram_mb(
                cfg.node3090_ssh_host,
                cfg.node3090_ssh_user,
                cfg.node3090_ssh_port,
            )
            print(
                "[dream_runner] llama-server slot state unavailable; node3090 free "
                f"VRAM={free_vram} MB (gate={cfg.node3090_vram_gate_mb} MB)",
                file=sys.stderr,
            )
            if free_vram >= cfg.node3090_vram_gate_mb:
                use_llama_server = True
            else:
                print(
                    "[dream_runner] free VRAM below gate -- falling straight to "
                    "Ollama (fail-closed)",
                    file=sys.stderr,
                )

    if use_llama_server:
        payload = _build_payload(system_prompt, user_content, no_think)
        result = _post_chat_completion(llm_url, payload, 120)
        if not result.startswith("ERROR:"):
            return result
        print(f"[dream_runner] llama-server call failed ({result[:80]}), trying Ollama",
              file=sys.stderr)

    ollama_url = cfg.node3090_ollama_url.rstrip("/")
    print(f"[dream_runner] Ollama fallback -> {ollama_url} model={cfg.node3090_fallback_model}",
          file=sys.stderr)
    payload = _build_payload(system_prompt, user_content, no_think, model=cfg.node3090_fallback_model)
    return _post_chat_completion(ollama_url, payload, 300)


def parse_dream_envelope(reply: str, key: str = "proposals") -> tuple[dict | None, str]:
    """Parse a dream-pass reply into its JSON envelope. Same strip +
    raw_decode approach as goethe.py's _parse_planner_envelope
    (tools/goethe.py:6751), adapted to this envelope's required key —
    'proposals' (a list; may be EMPTY, that's a valid outcome per
    DESIGN.md §6.1 "zero proposals is a valid, expected outcome") instead
    of the planner's 'steps'. `key` generalizes this to any single-list-key
    envelope shape (Prompt 3.2's insights pass uses key="insights") without
    duplicating this parse logic — every existing caller relies on the
    "proposals" default, so behavior there is unchanged.
    Returns (envelope_dict, "") on success, (None, fail_reason) on failure.
    """
    clean = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
    clean = re.sub(r"^```[a-z]*\n?", "", clean).rstrip("`").strip()
    idx = clean.find("{")
    if idx == -1:
        return None, f"no JSON object in reply. RAW: {clean[:200]!r}"
    try:
        env, _ = json.JSONDecoder().raw_decode(clean, idx)
    except Exception as exc:
        return None, f"JSON parse failed ({exc}). RAW: {clean[idx:idx + 200]!r}"
    if key not in env or not isinstance(env[key], list):
        return None, f"envelope has no {key!r} array"
    return env, ""


def request_dream_envelope(system_prompt: str, user_content: str, cfg: DreamConfig,
                            key: str = "proposals") -> tuple[dict | None, str | None]:
    """Two-attempt retry loop, same shape as goethe.py's
    _request_plan_envelope (tools/goethe.py:6860): call the LLM, parse the
    envelope; on failure, append a corrective note describing exactly what
    was wrong and retry exactly once. `key` is forwarded to
    parse_dream_envelope (see its docstring) and used in the corrective
    retry message so the model sees the SAME key name it was asked for the
    first time.
    Returns (envelope_dict, None) on success, (None, error_message) on
    failure (both attempts exhausted, or the LLM cascade itself errored).
    """
    env = None
    fail_reason = ""
    content = user_content
    for attempt in (1, 2):
        reply = call_dream_llm(system_prompt, content, cfg, no_think=True)
        if reply and reply.startswith("BUDGET_EXHAUSTED:"):
            # Prompt 4.2: a deliberate stop, not a failure -- return it
            # verbatim as the "error" message so callers' existing
            # not-None-env handling folds it straight into their narrative
            # note, but never retry (attempt 2 would just re-hit the same
            # exhausted budget for free -- pointless).
            return None, reply
        if not reply or reply.startswith("ERROR:"):
            return None, f"DREAMER UNAVAILABLE — ({(reply or 'no reply')[:160]})"
        env, fail_reason = parse_dream_envelope(reply, key=key)
        if env is not None:
            break
        print(f"[dream_runner] attempt {attempt} rejected — {fail_reason[:120]}", file=sys.stderr)
        content = (
            user_content
            + "\n\nPREVIOUS REPLY REJECTED: " + fail_reason[:200]
            + f"\nReturn ONLY the JSON envelope object {{\"{key}\": [...]}} — "
            "no thinking, no prose, no code fences."
        )
    if env is None:
        return None, f"DREAMER UNAVAILABLE — {fail_reason} (after retry)."
    return env, None


# --- proposal shape guard (structural only — NOT the hard-invariant validator) -

REQUIRED_PROPOSAL_KEYS = {"type", "call", "args", "why"}
KNOWN_PROPOSAL_TYPES = {"dedup", "reverify", "demote", "skill-candidate", "kb-fact", "prompt-rule"}

# Prompt 3.6: the ONLY file a prompt-rule proposal may ever target. Fixed
# here as a constant (not read from a proposal's own args at generation
# time) so a hand-edited or malicious proposals.jsonl has no path to point
# this at prompts/node4090* even before dream_apply.py's own apply-time
# invariant re-checks it (DESIGN.md's "code-enforced, not just prompted"
# discipline applied at both layers, same as the demote evidence-length check
# below).
LEARNED_RULES_TARGET = "prompts/learned-rules.md"


def validate_proposal_shape(p: dict) -> str | None:
    """Structural check only. The hard invariants (never raise quality,
    never mint source_tier=ground_truth, never touch quarantined docs
    except to propose deletion, evidence verbatim-quote rule, etc.) are
    dream_apply.py's job (Prompt 2.5, DESIGN.md §2 row 3) — this just
    keeps an obviously-malformed envelope entry out of proposals.jsonl.
    Returns None if OK, else a short reason string.
    """
    if not isinstance(p, dict):
        return "proposal is not an object"
    missing = REQUIRED_PROPOSAL_KEYS - p.keys()
    if missing:
        return f"missing keys: {sorted(missing)}"
    if not isinstance(p.get("args"), dict):
        return "'args' must be an object"
    if p.get("type") not in KNOWN_PROPOSAL_TYPES:
        return f"unknown proposal type: {p.get('type')!r}"
    if p.get("type") == "demote":
        # DESIGN.md §6.2 / Prompt 2.3: "Evidence >=20 chars, verbatim-quote
        # rule enforced in the proposal validator, not just the prompt."
        # This is the cheap, structural half (length only) that applies at
        # this shared layer regardless of which pass produced the demote;
        # the deeper check — each quote is a REAL substring of its claimed
        # source text — happens inside the contradiction pass itself, where
        # the source texts are actually in scope (see _demote_proposals_for_doc).
        evidence = p.get("args", {}).get("evidence", "")
        if not isinstance(evidence, str) or len(evidence) < 20:
            return "demote proposal's args.evidence is missing or under 20 chars"
    if p.get("type") == "prompt-rule":
        # Prompt 3.6, plan §"Prompt 3.9": "learned-rules.md never auto-merged
        # (validator rejects prompt-rule proposals targeting prompts/node4090*)".
        # Structural half of that invariant, checked here at generation time;
        # dream_apply.py's check_prompt_rule_target() re-checks it at apply
        # time against live args, same belt-and-suspenders pattern as the
        # ground-truth/quarantine checks split across both files.
        target = p.get("args", {}).get("target_file")
        if target != LEARNED_RULES_TARGET:
            return (
                f"prompt-rule proposal's args.target_file must be exactly "
                f"{LEARNED_RULES_TARGET!r}, got {target!r} — dreams may never "
                "target prompts/node4090* or any other file"
            )
        for key in ("rule", "rationale"):
            val = p.get("args", {}).get(key, "")
            if not isinstance(val, str) or not val.strip():
                return f"prompt-rule proposal's args.{key} is missing or empty"
    provenance = p.get("args", {}).get("provenance")
    if provenance is not None and not re.fullmatch(r"dream-\d{4}-\d{2}-\d{2}", str(provenance)):
        # DESIGN.md §6.2: a Thread 2 dream always writes "dream-YYYY-MM-DD"
        # (hyphen form) -- fixed per source, not something a pass may vary.
        return f"provenance {provenance!r} does not match the fixed 'dream-YYYY-MM-DD' form"
    return None


# --- stale/contradiction pass (Prompt 2.3) ----------------------------------

# CHRONOS-3 TTLs, copied verbatim from search_kb's own rerank logic
# (tools/goethe.py:4684) so this pass and the live reranker agree on what
# "expired" means. static=never expires.
_CHRONOS_TTL_DAYS = {"static": None, "slow": 90, "fast": 7}


def _age_days(updated_at: str):
    """Same computation as search_kb's _age_days (tools/goethe.py:4686)."""
    try:
        return max(
            0,
            (datetime.now().astimezone() - datetime.fromisoformat(updated_at or "")).days,
        )
    except Exception:
        return None


def find_reverify_candidates(kb_docs: list) -> list:
    """CHRONOS TTL-expired docs eligible for a "reverify" proposal.
    Deterministic — no LLM call, this is exact date arithmetic, not
    judgment. Narrower on purpose than search_kb's own read-time default:

      - volatility must be EXPLICITLY set. Absent is left alone here —
        corpus-audit.md found 79% of lse-kb docs have never been scored
        for it; search_kb's read-time 'slow' default is fine for display
        ranking, not grounds for an actionable write-adjacent proposal.
      - verified_against must be non-empty — kb_verify's own phase 1 is a
        no-op ("nothing to regression-check") without one.
      - stale must not be True — quarantined docs are out of scope for
        this pass (DESIGN.md §2 invariant 3(c): never touch quarantined
        docs except to propose deletion; reverify is a different action).

    Returns a list of (doc, age_days, ttl_days, volatility) tuples.
    """
    out = []
    for doc in kb_docs:
        if doc.get("stale"):
            continue
        volatility = doc.get("volatility")
        if not volatility:
            continue
        if not (doc.get("verified_against") or "").strip():
            continue
        ttl = _CHRONOS_TTL_DAYS.get(volatility)
        if ttl is None:
            continue  # static -- never expires
        age = _age_days(doc.get("updated_at"))
        if age is None or age <= ttl:
            continue
        out.append((doc, age, ttl, volatility))
    return out


def build_reverify_proposals(kb_docs: list) -> tuple:
    """type="reverify" proposals — each just carries a kb_verify(doc_id)
    probe SUGGESTION. Nothing here runs the probe; kb_verify's own
    two-phase protocol (tools/goethe.py:5371) is what the eventual
    dream_apply.py call, or a human, actually executes."""
    candidates = find_reverify_candidates(kb_docs)
    proposals = [
        {
            "type": "reverify",
            "call": "kb_verify",
            "args": {"doc_id": doc["_id"]},
            "why": (
                f"volatility={volatility} TTL={ttl}d exceeded — last updated "
                f"{age}d ago, verified_against={doc.get('verified_against', '')!r}"
            ),
        }
        for doc, age, ttl, volatility in candidates
    ]
    note = (
        f"reverify: {len(proposals)} TTL-expired doc(s) proposed for "
        f"kb_verify, out of {len(kb_docs)} doc(s) considered."
    )
    return proposals, note


CONTRADICTION_MIN_QUALITY = 0.6  # "high-quality" bar — matches search_kb's own
                                  # docstring ("0.6 = reasonable coverage")
CONTRADICTION_MAX_EVIDENCE_LINES = 15  # episode lines fed to the LLM per session
CONTRADICTION_EVIDENCE_SNIPPET_LEN = 500  # cap per-line result shown in the prompt
CONTRADICTION_EVIDENCE_MIN_LEN = 20  # DESIGN.md §6.2's verbatim-quote evidence floor

_DOC_ID_RE = re.compile(r"doc_id=([0-9a-fA-F]{8,32})")

_DEMOTE_SYSTEM_PROMPT = """You are the TRAUM dreamer's contradiction pass (Thread 2, Prompt 2.3).

You will be given ONE high-quality lse-kb document and a numbered list of
tool-call results from the SAME session that document was surfaced in (via
search_kb). Look for a GENUINE, DIRECT contradiction: a tool result that
proves a specific factual claim in the document is currently wrong — not
merely a related-but-different topic, not something that might eventually
make it stale, not a guess.

For each genuine contradiction you must quote BOTH sides VERBATIM —
character-for-character substrings copied from the text you were given, not
a paraphrase or summary of either side. A quote that does not appear
exactly in the source text will be rejected by the validator, not just
disapproved of in this prompt.

Return ONLY this JSON object — no prose, no thinking, no code fences:
{"proposals": [
  {"kb_quote": "<verbatim substring of the document's content proving the claim>",
   "episode_index": <int index from the numbered SESSION TOOL RESULTS list>,
   "tool_quote": "<verbatim substring of that episode's result proving the contradiction>",
   "why": "one line: what changed"}
]}
Zero contradictions is a valid, expected outcome — most sessions will not
contain one. Do not force a match just to have something to report."""


def extract_surfaced_doc_ids(session_episodes: list) -> set:
    """Doc IDs "surfaced" to the model this session — parsed straight out
    of search_kb's OWN return text, which embeds 'doc_id=<_id>' per hit
    (tools/goethe.py:4741). Only search_kb lines are scanned: index_to_kb/
    mentor_correct/record_outcome echo a doc_id too, but that is the
    WRITER's own doc, not something surfaced for a session to have acted
    on and potentially disproved."""
    ids = set()
    for ep in session_episodes:
        if ep.get("tool") != "search_kb":
            continue
        ids.update(_DOC_ID_RE.findall(ep.get("result_truncated") or ""))
    return ids


def find_contradiction_candidates(session_episodes: list, docs_by_id: dict) -> list:
    """(high_quality_doc, evidence_lines) pairs worth sending to the model
    for this session. evidence_lines is every OTHER (non-search_kb),
    successfully-exited tool result in the session, capped at
    CONTRADICTION_MAX_EVIDENCE_LINES. Empty on either side (nothing
    surfaced, or nothing to check it against) short-circuits with zero
    candidates and no LLM call — most sessions will hit this path."""
    surfaced_ids = extract_surfaced_doc_ids(session_episodes)
    if not surfaced_ids:
        return []
    high_quality_docs = [
        docs_by_id[doc_id] for doc_id in surfaced_ids
        if doc_id in docs_by_id
        and float(docs_by_id[doc_id].get("quality_score") or 0.0) >= CONTRADICTION_MIN_QUALITY
    ]
    if not high_quality_docs:
        return []
    evidence_lines = [
        ep for ep in session_episodes
        if ep.get("tool") != "search_kb"
        and ep.get("exit_class") == "ok"
        and (ep.get("result_truncated") or "").strip()
    ][:CONTRADICTION_MAX_EVIDENCE_LINES]
    if not evidence_lines:
        return []
    return [(doc, evidence_lines) for doc in high_quality_docs]


def _demote_proposals_for_doc(cfg: DreamConfig, session_id: str, doc: dict, evidence_lines: list) -> tuple:
    """One request_dream_envelope() call: doc vs. this session's other tool
    results. Returns (proposals, note_or_None). Every accepted proposal has
    passed a REAL substring check against both source texts — this is the
    code-enforced half of the verbatim-quote rule, not just prompt wording."""
    numbered = [
        f"[{i}] tool={ep.get('tool')} result={(ep.get('result_truncated') or '')[:CONTRADICTION_EVIDENCE_SNIPPET_LEN]!r}"
        for i, ep in enumerate(evidence_lines)
    ]
    user_content = (
        f"DOCUMENT (doc_id={doc['_id']}, quality={doc.get('quality_score')}):\n"
        f"title: {doc.get('title', '')}\n"
        f"content: {(doc.get('content') or '')[:3000]!r}\n\n"
        "SESSION TOOL RESULTS:\n" + "\n".join(numbered)
    )
    env, err = request_dream_envelope(_DEMOTE_SYSTEM_PROMPT, user_content, cfg)
    if env is None:
        return [], f"doc_id={doc['_id']} session={session_id}: {err}"

    doc_content = doc.get("content") or ""
    proposals = []
    for item in env.get("proposals", []):
        if not isinstance(item, dict):
            continue
        kb_quote = str(item.get("kb_quote", "")).strip()
        tool_quote = str(item.get("tool_quote", "")).strip()
        why = str(item.get("why", "")).strip()
        idx = item.get("episode_index")
        if not (kb_quote and tool_quote and why) or not isinstance(idx, int):
            continue
        if len(kb_quote) < CONTRADICTION_EVIDENCE_MIN_LEN or len(tool_quote) < CONTRADICTION_EVIDENCE_MIN_LEN:
            continue  # too thin to count as real evidence even if genuine
        if kb_quote not in doc_content:
            continue  # ENFORCED: not a real substring of the doc -- reject, don't trust the model's word
        if not (0 <= idx < len(evidence_lines)):
            continue
        episode_text = evidence_lines[idx].get("result_truncated") or ""
        if tool_quote not in episode_text:
            continue  # ENFORCED: not a real substring of the cited episode -- reject
        evidence = (
            f"{kb_quote!r} (doc_id={doc['_id']}) — CONTRADICTED THIS SESSION: "
            f"{tool_quote!r} (tool={evidence_lines[idx].get('tool')})"
        )[:1000]
        proposals.append({
            "type": "demote",
            "call": "record_outcome",
            "args": {
                "doc_id": doc["_id"],
                "success": False,
                "evidence": evidence,
                "notes": f"stale-contradiction pass, session={session_id}",
            },
            "why": why,
        })
    return proposals, None


# --- error-cluster pass (Prompt 2.4) -----------------------------------

# denied excluded on purpose -- matches episode_index.py's _ERROR_EXIT_CLASSES:
# a gate refusal is the safety system working, not a failure worth clustering.
ERROR_EXIT_CLASSES = {"error", "timeout"}

ERROR_CLUSTER_MIN_OCCURRENCES = 3
ERROR_CLUSTER_MIN_SESSIONS = 2
ERROR_CLUSTER_MAX_EVIDENCE_PER_LLM_CALL = 12  # cap occurrences shown to the model per cluster

ERROR_SOURCE_FIELDS = [
    "error_hash", "error_text", "context", "resolution",
    "occurrence_count", "first_seen", "last_seen",
]  # excludes "embedding" -- re-embedded fresh, same reasoning as KB_SOURCE_FIELDS


def collect_episode_error_occurrences(sessions: list, episodes_by_session: dict) -> list:
    """One item per non-ok episode line across the given sessions. Each
    carries its own session_id/ts so a later cluster can check the
    >=2-distinct-sessions bar for real, not by assumption."""
    items = []
    for row in sessions:
        session_id = row["session_id"]
        for ep in episodes_by_session.get(session_id) or []:
            if ep.get("exit_class") not in ERROR_EXIT_CLASSES:
                continue
            result = (ep.get("result_truncated") or "").strip()
            if not result:
                continue
            tool = ep.get("tool") or "?"
            items.append({
                "key": f"{session_id}@{ep.get('ts', '')}",
                "session_id": session_id,
                "ts": ep.get("ts", ""),
                "tool": tool,
                "exit_class": ep.get("exit_class"),
                "result_truncated": result,
                "embed_text": f"{tool}: {result[:500]}",
                "source": "episode",
            })
    return items


def collect_lse_errors_items(error_docs: list) -> list:
    """lse-errors docs as auxiliary cluster members -- prior-art context
    (existing resolution text) for a matching cluster's drafted skill, NOT
    counted toward the occurrence/session thresholds (an aggregate ES doc
    has no verifiable per-session breakdown of its own occurrence_count)."""
    items = []
    for doc in error_docs:
        doc_id = doc.get("_id")
        text = (doc.get("error_text") or "").strip()
        if not doc_id or not text:
            continue
        items.append({
            "key": f"lse-errors:{doc_id}",
            "doc_id": doc_id,
            "embed_text": f"{text} {doc.get('context') or ''}".strip(),
            "occurrence_count": doc.get("occurrence_count", 1),
            "resolution": doc.get("resolution") or "",
            "source": "lse-errors",
        })
    return items


def embed_items(cfg: DreamConfig, items: list) -> dict:
    """Generic version of embed_kb_docs for non-KB items (error occurrences,
    lse-errors docs) -- same embed_text() call, same per-item failure
    tolerance."""
    embeddings = {}
    for item in items:
        text = (item.get("embed_text") or "").strip()
        if not text:
            continue
        try:
            embeddings[item["key"]] = embed_text(cfg, text[:8000])
        except Exception as exc:
            print(f"[dream_runner] WARNING: embed failed for {item['key']} ({exc}) — skipped",
                  file=sys.stderr)
    return embeddings


def cluster_by_similarity(embeddings: dict, threshold: float) -> list:
    """Union-find connected components over the pairwise-cosine->=threshold
    graph. O(n^2) comparisons, same scale reasoning as find_candidate_pairs
    -- fine for the error/timeout volume this corpus produces per run."""
    keys = list(embeddings)

    parent = {k: k for k in keys}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if _cosine(embeddings[keys[i]], embeddings[keys[j]]) >= threshold:
                union(keys[i], keys[j])

    groups = {}
    for k in keys:
        groups.setdefault(find(k), []).append(k)
    return list(groups.values())


_SKILL_CANDIDATE_SYSTEM_PROMPT = """You are the TRAUM dreamer's error-cluster pass (Thread 2, Prompt 2.4).

You will be given a cluster of tool-call failures/timeouts that repeated
across multiple sessions, already judged to share the same underlying root
cause (grouped by embedding similarity, not by you) -- plus, if one exists,
an existing lse-errors catalog entry's resolution text for the same pattern.

Draft ONE reusable procedure (a skill_record candidate) that would help a
future session recognize and resolve this class of failure faster. Do not
invent facts the evidence doesn't support -- if the evidence doesn't show a
clear fix, say so in failure_modes/preconditions rather than guessing at one.

Return ONLY this JSON object -- no prose, no thinking, no code fences:
{"proposals": [
  {"task": "short imperative description of what this skill helps do",
   "trigger": "how to recognize this failure class is happening (symptoms, tool, exit_class, error text pattern)",
   "occupation": "one of: linux-sysadmin, network-engineer, sre, homeassistant_admin, or 'Local System Engineer' as catch-all",
   "procedure": "the fix/handling steps, grounded in the evidence given",
   "verification": "how to confirm the fix worked",
   "preconditions": "what must be true before applying this (or empty string)",
   "failure_modes": "known ways this fix itself can fail (or empty string)",
   "why": "one line: why this cluster is worth a skill entry now"}
]}
Zero proposals is a valid, expected outcome if the cluster's evidence isn't
actually enough to draft a grounded procedure yet."""


def _draft_skill_candidate(cfg: DreamConfig, cluster_episode_members: list, lse_errors_context: list) -> tuple:
    """One request_dream_envelope() call: a cluster's occurrences (+ any
    existing lse-errors resolution) -> zero or more skill-candidate
    proposals. Returns (proposals, note_or_None)."""
    numbered = [
        f"[{i}] session={m['session_id']} tool={m['tool']} exit_class={m['exit_class']} "
        f"result={m['result_truncated'][:CONTRADICTION_EVIDENCE_SNIPPET_LEN]!r}"
        for i, m in enumerate(cluster_episode_members[:ERROR_CLUSTER_MAX_EVIDENCE_PER_LLM_CALL])
    ]
    user_content = "CLUSTER OCCURRENCES:\n" + "\n".join(numbered)
    if lse_errors_context:
        user_content += "\n\nEXISTING lse-errors CONTEXT:\n" + "\n".join(
            f"- {c['embed_text'][:300]} | resolution: {c['resolution'][:300] or '(none recorded)'}"
            for c in lse_errors_context
        )

    env, err = request_dream_envelope(_SKILL_CANDIDATE_SYSTEM_PROMPT, user_content, cfg)
    if env is None:
        return [], err

    today = date.today().isoformat()
    episode_ids = [m["key"] for m in cluster_episode_members]  # ALL members, not just the capped prompt subset
    proposals = []
    for item in env.get("proposals", []):
        if not isinstance(item, dict):
            continue
        task = str(item.get("task", "")).strip()
        trigger = str(item.get("trigger", "")).strip()
        procedure = str(item.get("procedure", "")).strip()
        verification = str(item.get("verification", "")).strip()
        why = str(item.get("why", "")).strip()
        if not (task and trigger and procedure and verification and why):
            continue  # incomplete draft -- don't propose a half-built skill
        occupation = str(item.get("occupation", "")).strip() or "Local System Engineer"
        # skill_record's real signature has no "trigger" parameter (DESIGN.md
        # §6.3) -- fold it into procedure's own text so the indexed entry is
        # self-contained, while ALSO keeping it as a top-level proposal field
        # (like dedup's pair_id/role) for confirm-gate readability.
        combined_procedure = f"WHEN THIS HAPPENS: {trigger}\n\nFIX: {procedure}"
        proposals.append({
            "type": "skill-candidate",
            "call": "skill_record",
            "args": {
                "task": task,
                "occupation": occupation,
                "procedure": combined_procedure,
                "verification": verification,
                "preconditions": str(item.get("preconditions", "")).strip(),
                "failure_modes": str(item.get("failure_modes", "")).strip(),
                "provenance": f"dream-{today}",
                "source_tier": "inferred",  # DESIGN.md: dream-origin can never self-grant ground_truth
                "quality": 0.45,  # modest -- unverified draft, pending human review at the confirm-gate
            },
            "trigger": trigger,
            "evidence": episode_ids,  # the cluster's episode ids, per Prompt 2.4
            "why": why,
        })
    return proposals, None


# --- passes ------------------------------------------------------------

DEDUP_LLM_BATCH_SIZE = 5  # candidate pairs per request_dream_envelope() call

_DEDUP_SYSTEM_PROMPT = """You are the TRAUM dreamer's dedup pass (Thread 2, Prompt 2.2).

You will be given candidate pairs of lse-kb documents that scored above a
cosine-similarity floor on their embeddings. High cosine similarity is a
SIGNAL, not proof — two documents about the same topic can score high
without making the same claim. Confirm each pair independently. Propose a
merge ONLY when both documents assert the SAME claim in different words.
Do NOT propose a merge for documents that merely share a topic, or that
make related-but-distinct claims — that is exactly the false-merge failure
mode this pass exists to avoid. Also do NOT propose a merge if the two
documents read like sequential CHUNKS of one larger source document
(continuing subject matter, cross-references like "see part N", clearly
picking up where the other leaves off) rather than two independent
descriptions of the same fact — merging a chunk into its neighbor would
delete real content, not remove a duplicate.

Which document survives is already decided for you (keep_doc_id) — do not
second-guess it. Your only job for a confirmed pair is to write
merged_content: the single best version of the text, preserving every
distinct fact from BOTH documents and dropping only exact restatement.

Return ONLY this JSON object — no prose, no thinking, no code fences:
{"proposals": [
  {"pair_id": "<the pair_id you were given>",
   "is_duplicate": true,
   "merged_content": "...",
   "why": "one line: what makes these the same claim"}
],
 "skipped": [
  {"pair_id": "<pair_id>", "why": "one line: why this is NOT a true duplicate"}
]}
Zero confirmed duplicates (empty proposals, everything in skipped) is a
valid, expected outcome — do not force a merge just to have something to
report."""


def _pick_keep_doc(doc_a: dict, doc_b: dict) -> tuple:
    """keep-doc = higher quality_score, ties broken by newer updated_at
    (falling back to created_at). Deterministic and auditable on purpose —
    this is a business rule, not something left to the model's judgment.
    Returns (keep, retire)."""
    qa = float(doc_a.get("quality_score") or 0.0)
    qb = float(doc_b.get("quality_score") or 0.0)
    if qa != qb:
        return (doc_a, doc_b) if qa > qb else (doc_b, doc_a)
    ua = doc_a.get("updated_at") or doc_a.get("created_at") or ""
    ub = doc_b.get("updated_at") or doc_b.get("created_at") or ""
    return (doc_a, doc_b) if ua >= ub else (doc_b, doc_a)


def _dedup_batch_to_proposals(cfg: DreamConfig, batch: list, docs_by_id: dict) -> tuple:
    """One request_dream_envelope() call covering up to DEDUP_LLM_BATCH_SIZE
    candidate pairs. Returns (proposals, note_or_None)."""
    pair_specs = []
    lookup = {}
    for a_id, b_id, sim in batch:
        keep, retire = _pick_keep_doc(docs_by_id[a_id], docs_by_id[b_id])
        pair_id = f"{keep['_id']}::{retire['_id']}"
        lookup[pair_id] = (keep, retire, sim)
        pair_specs.append({
            "pair_id": pair_id,
            "cosine": round(sim, 4),
            "keep_doc_id": keep["_id"],
            "keep_title": keep.get("title", ""),
            "keep_content": (keep.get("content") or "")[:1500],
            "retire_doc_id": retire["_id"],
            "retire_title": retire.get("title", ""),
            "retire_content": (retire.get("content") or "")[:1500],
        })

    user_content = "CANDIDATE PAIRS:\n" + json.dumps(pair_specs, indent=2)
    env, err = request_dream_envelope(_DEDUP_SYSTEM_PROMPT, user_content, cfg)
    if env is None:
        return [], f"batch of {len(batch)} pair(s): {err}"

    proposals = []
    for item in env.get("proposals", []):
        if not isinstance(item, dict):
            continue
        pair_id = item.get("pair_id")
        if pair_id not in lookup or not item.get("is_duplicate"):
            continue
        keep, retire, sim = lookup[pair_id]
        merged_content = str(item.get("merged_content", "")).strip()
        why = str(item.get("why", "")).strip()
        if not merged_content or not why:
            continue  # malformed confirmation — treat as not-confirmed rather than guess
        new_quality = max(float(keep.get("quality_score") or 0.0), float(retire.get("quality_score") or 0.0))
        proposals.append({
            "type": "dedup",
            "role": "keep",
            "pair_id": pair_id,
            "call": "mentor_correct",
            "args": {
                "doc_id": keep["_id"],
                "correction": merged_content,
                "new_quality": new_quality,
            },
            "why": f"merge with {retire['_id']} ({retire.get('title', '')!r}), "
                   f"cosine={sim:.4f}: {why}",
        })
        proposals.append({
            "type": "dedup",
            "role": "retire",
            "pair_id": pair_id,
            "call": "record_outcome",
            "args": {
                "doc_id": retire["_id"],
                "success": False,
                "evidence": (
                    f"Superseded by merge into doc_id={keep['_id']} "
                    f"({keep.get('title', '')!r}): {why}"
                )[:500],
                "notes": f"dedup pass merge, cosine={sim:.4f}, pair_id={pair_id}",
            },
            "why": f"redundant with kept doc {keep['_id']}: {why}",
        })
    return proposals, None


# --- null-result records (Prompt 3.8 — PH3-2 formalized) --------------------
#
# Every run_pass_*() below has, since Prompt 2.2, narrated a null result in
# PROSE when it finds nothing ("Null result (PH3-2)" strings scattered
# through this file). Prompt 3.8 formalizes that prose into a structured,
# machine-readable record alongside it, so a later reader — a human
# skimming report.md, dream_digest.py, or a future dream pass mining dream
# history itself — can tell the two null shapes apart WITHOUT parsing
# prose:
#   - "nothing there": the pass actually inspected `corpus_size`-worth of
#     data and applied `thresholds`, and still found nothing worth
#     proposing (`looked=True`).
#   - "didn't look": some upstream gate — an empty index, an unreachable
#     dependency, a missing/empty log window — stopped the pass before it
#     could examine anything at all (`looked=False`). corpus_size is still
#     reported in this case (usually all zeros) so the distinction is
#     visible in the data itself, not just in `looked`.
#
# Every run_pass_*() now returns a 3-tuple (proposals, narrative,
# null_record); null_record is None whenever the pass produced >=1
# proposal, or otherwise has something non-null to show (the patterns pass
# never emits proposals at all — see run_pass_patterns — but still counts
# as non-null when its mined analytics aren't all empty).

def _null_record(pass_name: str, reason: str, *, looked: bool,
                  corpus_size: dict, thresholds: dict) -> dict:
    """One structured null-result record for `pass_name`. `looked` is the
    single field a reader should check first (see module note above);
    `reason` is a short, greppable code, not a sentence — the
    already-returned narrative string carries the human-readable prose.
    `corpus_size`/`thresholds` are pass-specific dicts of plain counts and
    config values (never doc content) so a null record is always safe to
    log, print, or feed to a later pass without redaction concerns."""
    return {
        "pass": pass_name,
        "result": "null",
        "reason": reason,
        "looked": looked,
        "corpus_size": corpus_size,
        "thresholds": thresholds,
    }


def run_pass_dedup(cfg: DreamConfig, sessions, episodes_by_session, kb_docs, error_docs) -> tuple:
    """Prompt 2.2 — near-duplicate lse-kb entries -> "dedup" proposal pairs.

    Pipeline: embed every doc (Ollama nomic-embed-text, same call shape as
    search_kb) -> pairwise cosine -> candidate pairs above dedup_floor ->
    accept pairs at/above dedup_threshold (set by the --sample-labels
    labeling exercise, default 0.92) -> confirm each pair with the local
    model (defense-in-depth against same-topic-not-same-claim false
    merges) -> one mentor_correct + one record_outcome proposal per
    confirmed pair.

    A null result at any stage (empty lse-kb, no embeddable docs, no
    candidate pairs, no pairs past threshold, model confirms nothing) is
    returned as an explicit narrative, not silently swallowed — PH3-2 —
    AND (Prompt 3.8) as a structured null_record, the function's 3rd
    return value (None when this call produced >=1 proposal).
    """
    thresholds = {"dedup_floor": cfg.dedup_floor, "dedup_threshold": cfg.dedup_threshold}

    if not kb_docs:
        narrative = "dedup pass: lse-kb returned zero docs (empty index or ES unreachable this run) — nothing to dedup. Null result (PH3-2)."
        return [], narrative, _null_record(
            "dedup", "empty_kb", looked=False,
            corpus_size={"kb_docs": 0, "embedded_docs": 0, "candidate_pairs": 0, "pairs_above_threshold": 0},
            thresholds=thresholds,
        )

    docs_by_id = {d["_id"]: d for d in kb_docs if d.get("_id")}

    embeddings = embed_kb_docs(cfg, kb_docs)
    if not embeddings:
        narrative = (
            f"dedup pass: embedding failed for all {len(docs_by_id)} doc(s) "
            f"(Ollama unreachable at {cfg.ollama_url}?) — cannot compute "
            "similarity this run."
        )
        return [], narrative, _null_record(
            "dedup", "embedding_unavailable", looked=False,
            corpus_size={"kb_docs": len(kb_docs), "embedded_docs": 0, "candidate_pairs": 0, "pairs_above_threshold": 0},
            thresholds=thresholds,
        )

    pairs = find_candidate_pairs(embeddings, cfg.dedup_floor)
    pairs = filter_same_document_chunks(pairs, docs_by_id)
    if not pairs:
        narrative = (
            f"dedup pass: zero candidate pairs at/above the floor "
            f"{cfg.dedup_floor} across {len(embeddings)} embedded doc(s) "
            "(after excluding same-document chunk pairs). Null result "
            "(PH3-2) — no near-duplicates in the corpus at this floor "
            "right now."
        )
        return [], narrative, _null_record(
            "dedup", "no_candidate_pairs", looked=True,
            corpus_size={"kb_docs": len(kb_docs), "embedded_docs": len(embeddings),
                         "candidate_pairs": 0, "pairs_above_threshold": 0},
            thresholds=thresholds,
        )

    accepted = [p for p in pairs if p[2] >= cfg.dedup_threshold]
    if not accepted:
        narrative = (
            f"dedup pass: {len(pairs)} candidate pair(s) found above the floor "
            f"{cfg.dedup_floor}, but none reached the merge threshold "
            f"{cfg.dedup_threshold}. Null result (PH3-2) — nothing proposed "
            "this run."
        )
        return [], narrative, _null_record(
            "dedup", "no_pairs_above_threshold", looked=True,
            corpus_size={"kb_docs": len(kb_docs), "embedded_docs": len(embeddings),
                         "candidate_pairs": len(pairs), "pairs_above_threshold": 0},
            thresholds=thresholds,
        )

    narrative_lines = [
        f"dedup pass: {len(accepted)} candidate pair(s) at/above threshold "
        f"{cfg.dedup_threshold}, out of {len(pairs)} pair(s) above the floor "
        f"{cfg.dedup_floor}, out of {len(embeddings)} embedded doc(s)."
    ]
    proposals = []
    for start in range(0, len(accepted), DEDUP_LLM_BATCH_SIZE):
        if _budget_checkpoint(cfg):  # Prompt 4.2
            break
        batch = accepted[start:start + DEDUP_LLM_BATCH_SIZE]
        batch_proposals, batch_note = _dedup_batch_to_proposals(cfg, batch, docs_by_id)
        proposals.extend(batch_proposals)
        if batch_note:
            narrative_lines.append(batch_note)

    null_record = None
    if not proposals:
        narrative_lines.append(
            "Model confirmed zero true duplicates among the candidates — "
            "null result (PH3-2): cosine similarity alone was not enough "
            "evidence for any pair this run."
        )
        null_record = _null_record(
            "dedup", "model_confirmed_zero", looked=True,
            corpus_size={"kb_docs": len(kb_docs), "embedded_docs": len(embeddings),
                         "candidate_pairs": len(pairs), "pairs_above_threshold": len(accepted)},
            thresholds=thresholds,
        )
    return proposals, "\n".join(narrative_lines), null_record


def run_pass_stale_contradiction(cfg: DreamConfig, sessions, episodes_by_session, kb_docs, error_docs) -> tuple:
    """Prompt 2.3 — two independent sub-passes over the same lse-kb pull:

    (a) reverify: deterministic CHRONOS TTL check, no LLM call. See
        find_reverify_candidates/build_reverify_proposals.
    (b) demote: for every undreamed session, cross-check whatever
        high-quality KB docs it surfaced via search_kb against that
        session's OTHER tool results, looking for a model-judged, verbatim-
        quoted contradiction. See find_contradiction_candidates/
        _demote_proposals_for_doc.

    Both sub-passes report an explicit null result when they find nothing
    (PH3-2) rather than staying silent about it — and (Prompt 3.8) the
    whole pass's structured null_record (3rd return value) is set only
    when BOTH sub-passes are null this run; either sub-pass alone
    producing a proposal makes the pass non-null overall.
    """
    thresholds = {
        "contradiction_min_quality": CONTRADICTION_MIN_QUALITY,
        "chronos_ttl_days": dict(_CHRONOS_TTL_DAYS),
    }
    if not kb_docs:
        narrative = "stale-contradiction pass: lse-kb returned zero docs (empty index or ES unreachable this run) — nothing to check. Null result (PH3-2)."
        return [], narrative, _null_record(
            "stale-contradiction", "empty_kb", looked=False,
            corpus_size={"kb_docs": 0, "sessions_considered": len(sessions),
                         "sessions_with_candidates": 0, "reverify_candidates": 0,
                         "demote_confirmed": 0},
            thresholds=thresholds,
        )

    docs_by_id = {d["_id"]: d for d in kb_docs if d.get("_id")}

    reverify_proposals, reverify_note = build_reverify_proposals(kb_docs)
    narrative_lines = [reverify_note]

    demote_proposals = []
    demoted_doc_ids = set()  # one demote per doc_id per run -- see note below
    sessions_with_candidates = 0
    for row in sessions:
        if _budget_checkpoint(cfg):  # Prompt 4.2
            break
        session_id = row["session_id"]
        if cfg.budget is not None:
            # "consumed" = looked at, regardless of whether it turns out
            # to have a candidate -- counted here, before the (potentially
            # non-trivial) contradiction scan below, not after.
            cfg.budget.record_session()
        session_episodes = episodes_by_session.get(session_id) or []
        candidates = find_contradiction_candidates(session_episodes, docs_by_id)
        if not candidates:
            continue
        sessions_with_candidates += 1
        for doc, evidence_lines in candidates:
            if doc["_id"] in demoted_doc_ids:
                # record_outcome(success=False) demotes -0.15 PER CALL — a
                # doc found contradicted by 3 separate evidence lines (real,
                # observed live: 3 evidence lines in one session all pointing
                # at the same stale container-inventory doc) would otherwise
                # get triple-demoted for what is really one finding. First
                # confirmed contradiction per doc_id wins per run; re-confirm
                # on a later run if it's still wrong.
                narrative_lines.append(
                    f"doc_id={doc['_id']}: additional contradiction found "
                    f"(session={session_id}) but already demoted once this "
                    "run — skipped to avoid over-penalizing a single finding."
                )
                continue
            batch_proposals, note = _demote_proposals_for_doc(cfg, session_id, doc, evidence_lines)
            if batch_proposals:
                demoted_doc_ids.add(doc["_id"])
            demote_proposals.extend(batch_proposals)
            if note:
                narrative_lines.append(note)

    narrative_lines.append(
        f"contradiction: {sessions_with_candidates} session(s) had both a "
        f"high-quality surfaced doc and other tool evidence to check it "
        f"against, out of {len(sessions)} session(s) considered; "
        f"{len(demote_proposals)} contradiction(s) confirmed."
    )
    if not demote_proposals and sessions_with_candidates == 0:
        narrative_lines.append(
            "Null result (PH3-2): no session both surfaced a high-quality "
            "KB doc and had other tool evidence to check it against this run."
        )

    null_record = None
    if not reverify_proposals and not demote_proposals:
        null_record = _null_record(
            "stale-contradiction", "no_reverify_and_no_contradictions", looked=True,
            corpus_size={"kb_docs": len(kb_docs), "sessions_considered": len(sessions),
                         "sessions_with_candidates": sessions_with_candidates,
                         "reverify_candidates": len(reverify_proposals),
                         "demote_confirmed": len(demote_proposals)},
            thresholds=thresholds,
        )

    return reverify_proposals + demote_proposals, "\n".join(narrative_lines), null_record


def run_pass_error_cluster(cfg: DreamConfig, sessions, episodes_by_session, kb_docs, error_docs) -> tuple:
    """Prompt 2.4 — group lse-errors docs + episode error/timeout occurrences
    by embedding similarity; clusters with >=ERROR_CLUSTER_MIN_OCCURRENCES
    episode occurrences spanning >=ERROR_CLUSTER_MIN_SESSIONS sessions get a
    drafted "skill-candidate" proposal. A matching lse-errors doc supplies
    prior-art context (its resolution text, if any) but never counts toward
    the occurrence/session bar itself — see collect_lse_errors_items.
    """
    thresholds = {
        "error_cluster_threshold": cfg.error_cluster_threshold,
        "min_occurrences": ERROR_CLUSTER_MIN_OCCURRENCES,
        "min_sessions": ERROR_CLUSTER_MIN_SESSIONS,
    }
    episode_items = collect_episode_error_occurrences(sessions, episodes_by_session)
    error_doc_items = collect_lse_errors_items(error_docs)
    all_items = episode_items + error_doc_items
    if not all_items:
        narrative = (
            "error-cluster pass: no episode error/timeout occurrences and no "
            "lse-errors docs to cluster this run. Null result (PH3-2)."
        )
        return [], narrative, _null_record(
            "error-cluster", "no_items", looked=False,
            corpus_size={"episode_items": 0, "error_doc_items": 0, "embedded_items": 0,
                         "clusters_found": 0, "clusters_qualifying": 0},
            thresholds=thresholds,
        )

    items_by_key = {item["key"]: item for item in all_items}
    embeddings = embed_items(cfg, all_items)
    if not embeddings:
        narrative = (
            f"error-cluster pass: embedding failed for all {len(all_items)} "
            f"item(s) (Ollama unreachable at {cfg.ollama_url}?)."
        )
        return [], narrative, _null_record(
            "error-cluster", "embedding_unavailable", looked=False,
            corpus_size={"episode_items": len(episode_items), "error_doc_items": len(error_doc_items),
                         "embedded_items": 0, "clusters_found": 0, "clusters_qualifying": 0},
            thresholds=thresholds,
        )

    clusters = cluster_by_similarity(embeddings, cfg.error_cluster_threshold)
    narrative_lines = [
        f"error-cluster: {len(clusters)} cluster(s) found among {len(embeddings)} "
        f"embedded item(s) ({len(episode_items)} episode occurrence(s), "
        f"{len(error_doc_items)} lse-errors doc(s)) at threshold "
        f"{cfg.error_cluster_threshold}."
    ]

    proposals = []
    qualifying = 0
    for cluster_keys in clusters:
        if _budget_checkpoint(cfg):  # Prompt 4.2
            break
        episode_members = [items_by_key[k] for k in cluster_keys if items_by_key[k]["source"] == "episode"]
        errors_context = [items_by_key[k] for k in cluster_keys if items_by_key[k]["source"] == "lse-errors"]
        distinct_sessions = {m["session_id"] for m in episode_members}
        if len(episode_members) < ERROR_CLUSTER_MIN_OCCURRENCES or len(distinct_sessions) < ERROR_CLUSTER_MIN_SESSIONS:
            continue
        qualifying += 1
        batch_proposals, note = _draft_skill_candidate(cfg, episode_members, errors_context)
        proposals.extend(batch_proposals)
        if note:
            narrative_lines.append(
                f"cluster ({len(episode_members)} occ, {len(distinct_sessions)} sessions): {note}"
            )

    narrative_lines.append(
        f"{qualifying} cluster(s) met the >={ERROR_CLUSTER_MIN_OCCURRENCES} occurrences / "
        f">={ERROR_CLUSTER_MIN_SESSIONS} sessions bar; {len(proposals)} skill-candidate(s) drafted."
    )
    null_record = None
    if qualifying == 0:
        narrative_lines.append(
            "Null result (PH3-2): no error/timeout pattern repeated enough "
            "this run to clear the occurrence/session bar for a skill-candidate."
        )
        null_record = _null_record(
            "error-cluster", "no_cluster_cleared_bar", looked=True,
            corpus_size={"episode_items": len(episode_items), "error_doc_items": len(error_doc_items),
                         "embedded_items": len(embeddings), "clusters_found": len(clusters),
                         "clusters_qualifying": 0},
            thresholds=thresholds,
        )
    return proposals, "\n".join(narrative_lines), null_record


# --- patterns pass (Prompt 3.1, TRAUM-INSIGHT — mechanical, NO LLM) ---------
#
# Everything below parses agent_commands.log's compact tag-line format
# (corpus-audit.md (a): '[YYYY-MM-DD HH:MM:SS] TAG: detail', CMD paired with
# a following 'DONE rc=<n> len=<n>' line, 99.998% of the corpus) into a flat
# list of event dicts, then mines that list four different ways. Every
# function from _LOG_LINE_RE down to mine_patterns() is a pure function of
# its arguments — no file I/O, no network, no randomness, no LLM call — so
# each is independently unit-testable against synthetic log lines/events.

# --- agent-log secret redaction (Thread 4 prerequisite, 2026-07-12) --------
# The Thread 3 close's live run surfaced a plaintext password inside a repeated
# `sshpass -p` command in agent_commands.log. The log is written verbatim by
# goethe.py's audit path (it has no redaction of its own), so the dreamer must
# scrub at READ time, before anything reaches patterns.json, report files, or
# an off-host LLM prompt. Rules 1 and 3 are goethe_mcp.py's episode-journaling
# regexes (_BEARER_RE / _PATTERN_SECRET_RE) verbatim -- same shapes, same
# replacement-tag convention; rule 2 adds the credential-as-CLI-flag shape
# (`sshpass -p`, `--password`) that the assignment-style rule 3 structurally
# cannot catch. (curl's bare `-u` is NOT matched: a single-letter flag shared
# by `sort -u`/`python -u` would redact innocent arguments and corrupt the
# frequency table; curl credentials still hit rule 2 via --user or rule 3 via
# token-shaped values.)
_REDACT_RULES = [
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+"),
     "[REDACTED:bearer-token]"),
    (re.compile(r"(?i)((?:sshpass\s+(?:-p|--password)|--password|--user|--token|--api-key|--secret)"
                r"[=\s]+)(\"[^\"]+\"|'[^']+'|\S+)"),
     r"\1[REDACTED:cli-credential]"),
    (re.compile(r"(?i)([\w]*(?:key|token|secret|password)[\w]*)"
                r"([\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9\-_./+]{12,}"),
     r"\1\2[REDACTED:pattern-match]"),
]


def redact_log_text(text: str) -> str:
    """Scrub high-confidence secret shapes from one agent-log detail string.
    Applied inside parse_agent_log_lines() so EVERY downstream consumer
    (command_frequency, find_failure_retries, repeated-sequence mining,
    patterns.json, the insights LLM prompt) only ever sees redacted text --
    one choke point, not per-consumer discipline."""
    if not text:
        return text
    for pattern, replacement in _REDACT_RULES:
        text = pattern.sub(replacement, text)
    try:
        from redact import redact_sensitive_text  # shared module supersedes the 3-rule local set (P1, 2026-07-17)
        text = redact_sensitive_text(text)
    except Exception:
        pass
    return text


_LOG_LINE_RE = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (?P<tag>[A-Z][A-Z0-9]*): (?P<detail>.*)$"
)
_CWD_SUFFIX_RE = re.compile(r"\s*\(cwd=(?P<cwd>[^)]*)\)\s*$")
_DONE_RC_RE = re.compile(r"^rc=(?P<rc>-?\d+)\s+len=(?P<len>\d+)")


def parse_agent_log_lines(lines: list) -> list[dict]:
    """Parse compact tag-line events: '[ts] TAG: detail'.

    corpus-audit.md (a): 99.998% of agent_commands.log is this one-line-per-
    event format; the 2-line 'bootstrap era' block (2026-05-23 22:12:51-57,
    exactly 2 lines, ever) is '[ts] ▶ COMMAND' / '  cmd : ...' / '  cwd : ...'
    / a divider line — none of which match `_LOG_LINE_RE` (no bare-word tag
    followed by ': ') — so it is silently, structurally skipped, exactly as
    corpus-audit.md calls out is safe ("trivially skippable").

    Returns one dict per matched line, in file order:
      {"line_no": <1-indexed position within `lines`>, "ts": "...",
       "tag": "CMD"/"DONE"/..., "detail": <cwd suffix stripped>,
       "cwd": <str or None>, "rc": <int or None, DONE lines only>}

    `line_no` is 1-indexed within the `lines` list passed in, NOT
    necessarily the on-disk line number — callers doing a windowed
    (tail -N) read are responsible for that offset if they need it; the
    patterns pass itself only ever uses line_no for *relative* (gap)
    distances, so this is deliberately not disk-absolute.
    """
    events = []
    for i, raw in enumerate(lines, start=1):
        m = _LOG_LINE_RE.match(raw.rstrip("\n"))
        if not m:
            continue
        tag = m.group("tag")
        detail = redact_log_text(m.group("detail"))
        cwd = None
        cwd_m = _CWD_SUFFIX_RE.search(detail)
        if cwd_m:
            cwd = cwd_m.group("cwd")
            detail = detail[:cwd_m.start()].rstrip()
        event = {"line_no": i, "ts": m.group("ts"), "tag": tag, "detail": detail, "cwd": cwd}
        if tag == "DONE":
            rc_m = _DONE_RC_RE.match(detail)
            event["rc"] = int(rc_m.group("rc")) if rc_m else None
        events.append(event)
    return events


def command_frequency(events: list, top_n: int) -> list[dict]:
    """Prompt 3.1 (a) — frequency table over CMD-tag detail strings (the
    literal shell command run; cwd is stripped by parse_agent_log_lines so
    the same command from two different working directories still counts
    as one entry). Ties broken by first-seen order (stable), so output is
    reproducible run-to-run, not dependent on dict/hash ordering."""
    counts = Counter()
    first_seen = {}
    for idx, e in enumerate(events):
        if e["tag"] != "CMD":
            continue
        cmd = e["detail"]
        counts[cmd] += 1
        first_seen.setdefault(cmd, idx)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
    return [{"command": cmd, "count": n} for cmd, n in ordered[:top_n]]


def _find_next_matching_cmd(events: list, start_idx: int, detail: str, max_line_no: int):
    for e in events[start_idx:]:
        if e["line_no"] > max_line_no:
            break
        if e["tag"] == "CMD" and e["detail"] == detail:
            return e
    return None


def find_failure_retries(events: list, window_lines: int) -> list[dict]:
    """Prompt 3.1 (b) — failure->retry adjacency: a CMD whose paired DONE
    reports rc!=0, followed by the SAME command re-issued as a later CMD
    within `window_lines` (raw log lines, not event count) after the
    failing DONE. Single forward pass, bounded lookahead per failure —
    deterministic, no LLM.

    'Paired' follows corpus-audit.md (a) literally: the DONE immediately
    following a CMD is that CMD's own completion marker, so `last_cmd` is
    reset to None on every DONE (consumed) rather than carried forward —
    an untagged/unmatched DONE (no preceding CMD in this window) is simply
    not attributable to a command and is skipped, not guessed at.
    """
    results = []
    last_cmd = None  # (detail, line_no) of the most recent CMD, awaiting its DONE
    for idx, e in enumerate(events):
        if e["tag"] == "CMD":
            last_cmd = (e["detail"], e["line_no"])
            continue
        if e["tag"] == "DONE":
            if last_cmd is not None:
                rc = e.get("rc")
                if rc is not None and rc != 0:
                    cmd_detail, _cmd_line = last_cmd
                    fail_line = e["line_no"]
                    retry = _find_next_matching_cmd(
                        events, idx + 1, cmd_detail, fail_line + window_lines
                    )
                    if retry is not None:
                        results.append({
                            "command": cmd_detail,
                            "rc": rc,
                            "fail_line": fail_line,
                            "retry_line": retry["line_no"],
                            "gap_lines": retry["line_no"] - fail_line,
                        })
            last_cmd = None
    return results


def _iso_week(ts: str) -> str:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def tool_usage_by_week(events: list) -> tuple:
    """Prompt 3.1 (c) — per-tag ('tool') event counts bucketed by ISO week.
    Every tag x week combination in the observed range is present in the
    output (zero-filled), not just weeks where a tag actually fired — this
    is what makes a 'this tool went quiet' finding (the RFC-KB
    zero-usage class corpus-audit.md flags) directly readable straight out
    of patterns.json, no second pass needed. DONE is excluded (it is CMD's
    own completion marker, not a distinct tool). Deterministic, no LLM.

    Returns (usage: {tag: {week: count}}, weeks_sorted: [week, ...]).
    """
    weeks_seen = set()
    tags_seen = set()
    raw_counts = Counter()
    for e in events:
        if e["tag"] == "DONE":
            continue
        wk = _iso_week(e["ts"])
        weeks_seen.add(wk)
        tags_seen.add(e["tag"])
        raw_counts[(e["tag"], wk)] += 1
    weeks_sorted = sorted(weeks_seen)
    usage = {
        tag: {wk: raw_counts.get((tag, wk), 0) for wk in weeks_sorted}
        for tag in sorted(tags_seen)
    }
    return usage, weeks_sorted


def infer_sessions(events: list, gap_minutes: int) -> list:
    """agent_commands.log carries no session_id (corpus-audit.md (a) —
    only tasks.db/episode files do). Sessions are inferred by inactivity
    gap: a new session starts whenever the time between one event and the
    next exceeds `gap_minutes`. Single forward pass over already
    time-ordered events — deterministic, no LLM.

    Returns a list of event-lists (one per inferred session), in order.
    """
    sessions = []
    current = []
    prev_dt = None
    for e in events:
        dt = datetime.strptime(e["ts"], "%Y-%m-%d %H:%M:%S")
        if prev_dt is not None and (dt - prev_dt).total_seconds() > gap_minutes * 60:
            if current:
                sessions.append(current)
            current = []
        current.append(e)
        prev_dt = dt
    if current:
        sessions.append(current)
    return sessions


def session_command_lists(sessions: list) -> list:
    """Per inferred session, the ordered list of CMD detail strings only
    (DONE/other tags dropped) — the sequence-mining unit for
    find_automation_candidates."""
    return [[e["detail"] for e in sess if e["tag"] == "CMD"] for sess in sessions]


def find_automation_candidates(command_lists: list, min_len: int, max_len: int,
                                min_sessions: int) -> list:
    """Prompt 3.1 (d) — longest contiguous command sequences (>=min_len)
    that recur across >=min_sessions distinct inferred sessions.
    Longest-first: lengths are scanned from max_len down to min_len, and
    once a sequence at some length L clears the session bar, every
    (session_idx, position) it occupies is 'claimed' so a shorter sequence
    nested inside it is not ALSO reported as a separate, redundant finding
    at a shorter length. Claims from length L are only applied to filter
    length L-1 and shorter — two different qualifying windows of the SAME
    length are each reported independently even if they overlap (they are
    literally different sequences; only cross-length nesting is
    de-duplicated). Plain contiguous-window counting, no LLM; bounded by
    max_len so a pathological run of one repeated command can't blow up
    compute.
    """
    claimed = set()  # (session_idx, position) already covered by a longer match
    candidates = []
    for length in range(max_len, min_len - 1, -1):
        window_to_sessions: dict = {}
        for s_idx, cmds in enumerate(command_lists):
            n = len(cmds)
            for start in range(0, n - length + 1):
                if any((s_idx, start + k) in claimed for k in range(length)):
                    continue
                window = tuple(cmds[start:start + length])
                window_to_sessions.setdefault(window, {}).setdefault(s_idx, []).append(start)

        accepted_this_length = [
            (window, by_session) for window, by_session in window_to_sessions.items()
            if len(by_session) >= min_sessions
        ]

        for window, by_session in accepted_this_length:
            for s_idx, starts in by_session.items():
                for start in starts:
                    for k in range(length):
                        claimed.add((s_idx, start + k))
            candidates.append({
                "sequence": list(window),
                "length": length,
                "session_count": len(by_session),
                "sessions": sorted(by_session.keys()),
                "occurrence_count": sum(len(v) for v in by_session.values()),
            })

    candidates.sort(key=lambda c: (-c["length"], -c["session_count"], c["sequence"]))
    return candidates


def mine_patterns(events: list, cfg: DreamConfig) -> dict:
    """Prompt 3.1 orchestrator — runs all four mechanical mining sub-passes
    over one already-parsed event stream and assembles patterns.json's
    shape. Pure function of `events` + config knobs (no file I/O, no
    network, no LLM) so tests can feed synthetic events straight in and
    assert on the returned dict."""
    freq = command_frequency(events, cfg.patterns_top_commands)
    retries = find_failure_retries(events, cfg.patterns_retry_window)
    usage_by_week, weeks = tool_usage_by_week(events)
    sessions = infer_sessions(events, cfg.patterns_session_gap_minutes)
    command_lists = session_command_lists(sessions)
    automation = find_automation_candidates(
        command_lists,
        cfg.patterns_min_sequence_len,
        max(cfg.patterns_max_sequence_len, cfg.patterns_min_sequence_len),
        cfg.patterns_min_sessions,
    )
    n_failures = sum(1 for e in events if e["tag"] == "DONE" and e.get("rc") not in (None, 0))

    return {
        "lines_scanned": len(events),
        "first_ts": events[0]["ts"] if events else None,
        "last_ts": events[-1]["ts"] if events else None,
        "command_frequency": freq,
        "failure_retry": retries,
        "failure_retry_summary": {
            "total_failures": n_failures,
            "total_retries_within_window": len(retries),
            "retry_window_lines": cfg.patterns_retry_window,
        },
        "tool_usage_by_week": usage_by_week,
        "weeks_observed": weeks,
        "sessions_inferred": len(sessions),
        "automation_candidates": automation,
        "params": {
            "session_gap_minutes": cfg.patterns_session_gap_minutes,
            "min_sequence_len": cfg.patterns_min_sequence_len,
            "max_sequence_len": cfg.patterns_max_sequence_len,
            "min_sessions": cfg.patterns_min_sessions,
            "top_commands": cfg.patterns_top_commands,
            "max_lines_windowed": cfg.patterns_max_lines,
        },
    }


def read_agent_log_window(cfg: DreamConfig) -> list:
    """Bounded read for the patterns pass — corpus-audit.md (a)'s explicit
    caveat ('a dream pass should windowed-read... rather than load
    whole-file'; the log is unrotated and growing, 9.4MB/134k+ lines and
    climbing). Same tail-deque strategy as tail_agent_log, but with its own,
    much larger default (--patterns-max-lines, 50,000 vs tail_agent_log's
    fixed 5,000) since Prompt 3.1 explicitly asks to mine the log's
    ~44k-line working history, not just a short recent tail."""
    if not os.path.exists(cfg.agent_log):
        return []
    with open(cfg.agent_log, "rt", encoding="utf-8", errors="replace") as f:
        return list(deque(f, maxlen=cfg.patterns_max_lines))


def write_patterns_json(cfg: DreamConfig, patterns: dict) -> str:
    """dry-run/write split mirrors write_report(): --dry-run (default)
    prints the payload and touches no files; --no-dry-run creates the
    dream-dir day directory and writes patterns.json (or --patterns-out)."""
    today = date.today().isoformat()
    out_dir = os.path.join(cfg.dream_dir, today)
    out_path = cfg.patterns_out or os.path.join(out_dir, "patterns.json")
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), **patterns}

    if cfg.dry_run:
        print(f"[dream_runner] [dry-run] would write patterns to: {out_path}", file=sys.stderr)
        print(json.dumps(payload, indent=2))
        return out_path

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out_path


def run_pass_patterns(cfg: DreamConfig, sessions, episodes_by_session, kb_docs, error_docs) -> tuple:
    """Prompt 3.1 — TRAUM-INSIGHT audit-log miner. Purely mechanical: NO LLM
    call anywhere in this function or anything it calls. Four sub-passes —
    command frequency, failure->retry adjacency, per-tag-per-week usage
    counters, and cross-session repeated-command-sequence ('automation
    candidate') mining — over agent_commands.log.

    Generates ZERO mentor_correct/record_outcome proposals. Unlike the
    other three passes, this one writes a raw analytics artifact
    (patterns.json) rather than proposing KB writes — a later prompt is
    expected to consume patterns.json for any KB-writing follow-up.

    Ignores `sessions`/`episodes_by_session`/`kb_docs`/`error_docs` (kept
    in the signature only for PASS_FUNCS uniformity with the other three
    passes): agent_commands.log has no session_id of its own
    (corpus-audit.md (a)), so this pass infers its own sessions by
    inactivity gap rather than reusing manifest.db's episode-derived ones.
    """
    thresholds = {
        "patterns_min_sequence_len": cfg.patterns_min_sequence_len,
        "patterns_min_sessions": cfg.patterns_min_sessions,
        "patterns_retry_window": cfg.patterns_retry_window,
        "patterns_max_lines": cfg.patterns_max_lines,
    }
    raw_lines = read_agent_log_window(cfg)
    if not raw_lines:
        narrative = (
            f"patterns pass: agent_commands.log not found or empty at "
            f"{cfg.agent_log} — nothing to mine. Null result (PH3-2)."
        )
        return [], narrative, _null_record(
            "patterns", "log_missing_or_empty", looked=False,
            corpus_size={"raw_lines": 0, "events": 0, "sessions_inferred": 0,
                         "command_frequency_rows": 0, "automation_candidates": 0,
                         "failure_retry": 0},
            thresholds=thresholds,
        )

    events = parse_agent_log_lines(raw_lines)
    if not events:
        narrative = (
            f"patterns pass: read {len(raw_lines)} raw line(s) from "
            f"{cfg.agent_log} but matched zero compact-tag-line events "
            "(bootstrap-era-only window, or unrecognized format). Null "
            "result (PH3-2)."
        )
        return [], narrative, _null_record(
            "patterns", "no_matching_events", looked=False,
            corpus_size={"raw_lines": len(raw_lines), "events": 0, "sessions_inferred": 0,
                         "command_frequency_rows": 0, "automation_candidates": 0,
                         "failure_retry": 0},
            thresholds=thresholds,
        )

    patterns = mine_patterns(events, cfg)
    out_path = write_patterns_json(cfg, patterns)

    fr_summary = patterns["failure_retry_summary"]
    narrative = (
        f"patterns pass: mined {len(events)} event(s) from {len(raw_lines)} "
        f"windowed raw line(s) of {cfg.agent_log} "
        f"({patterns['first_ts']} .. {patterns['last_ts']}). "
        f"{len(patterns['command_frequency'])} distinct command(s) in the "
        f"frequency table (top {cfg.patterns_top_commands}); "
        f"{fr_summary['total_failures']} failure(s) found, "
        f"{fr_summary['total_retries_within_window']} retried within "
        f"{cfg.patterns_retry_window} line(s); "
        f"{len(patterns['weeks_observed'])} week(s) x "
        f"{len(patterns['tool_usage_by_week'])} tag(s) in the usage matrix; "
        f"{patterns['sessions_inferred']} session(s) inferred "
        f"(gap={cfg.patterns_session_gap_minutes}m), "
        f"{len(patterns['automation_candidates'])} automation candidate "
        f"sequence(s) found (>={cfg.patterns_min_sequence_len} commands, "
        f">={cfg.patterns_min_sessions} sessions). Written to {out_path}. "
        "Mechanical only — no LLM call in this pass (Prompt 3.1)."
    )

    corpus_size = {
        "raw_lines": len(raw_lines), "events": len(events),
        "sessions_inferred": patterns["sessions_inferred"],
        "command_frequency_rows": len(patterns["command_frequency"]),
        "automation_candidates": len(patterns["automation_candidates"]),
        "failure_retry": len(patterns["failure_retry"]),
    }
    null_record = None
    all_domains_empty = not (
        patterns["command_frequency"] or patterns["failure_retry"]
        or patterns["tool_usage_by_week"] or patterns["automation_candidates"]
    )
    if all_domains_empty:
        # Prompt 3.8: this is the pass's real "nothing there" verdict — it
        # looked (raw_lines/events both non-empty, corpus_size says so),
        # and every one of the four mechanical sub-passes still came back
        # empty. Distinct from the partial case below, which the pre-3.8
        # narrative already covered but did NOT distinguish structurally.
        narrative += (
            " Null result (PH3-2): the entire windowed read mined zero "
            "findings across all four sub-passes (command frequency, "
            "failure->retry, tool usage, automation candidates)."
        )
        null_record = _null_record(
            "patterns", "all_domains_empty", looked=True,
            corpus_size=corpus_size, thresholds=thresholds,
        )
    elif not patterns["automation_candidates"] and not patterns["failure_retry"]:
        narrative += (
            " Null sub-result (PH3-2): no repeated-sequence automation "
            "candidates and no failure->retry adjacencies found in this window."
        )
    return [], narrative, null_record




# --- insights pass (Prompt 3.2, TRAUM-INSIGHT — one LLM call per domain) ---
#
# Feeds patterns.json's four mined domains (re-derived in-memory via
# mine_patterns/read_agent_log_window -- the SAME code Prompt 3.1's
# `patterns` pass itself calls, so this pass has no on-disk patterns.json
# dependency and no ordering requirement against a prior `--pass patterns`
# run) plus recent session summaries to the local model. "Tight scope per
# call" (Qwen3.6's profile) means one insight DOMAIN per LLM call, never one
# diffuse prompt covering all four at once -- see INSIGHT_DOMAINS and
# _INSIGHT_DOMAIN_BUILDERS below, one pair per patterns.json section.

INSIGHT_DOMAINS = ("command-frequency", "failure-retry", "tool-usage", "automation-candidates")
INSIGHT_PROPOSED_CHANGES = {"kb-fact", "skill", "prompt-rule", "tool-change"}
INSIGHT_OBSERVATION_MIN_LEN = 20  # no one-word "findings" -- same discipline as elsewhere in this file
INSIGHT_MAX_ITEMS_PER_DOMAIN_PROMPT = 30  # cap raw data rows shown per call


def build_session_summaries(sessions: list, max_sessions: int) -> list:
    """Prompt 3.2's "last N session summaries" -- built straight from
    manifest.db's own `sessions` row (session_id/start_ts/end_ts/n_calls/
    n_errors/tools_used), no episode re-read needed. `sessions` is already
    the --sessions/--since-bounded undreamed-session list every other pass
    uses (select_undreamed_sessions) -- "last N" reuses that existing
    selection rather than adding a second, redundant session-count knob;
    `max_sessions` (--insights-max-sessions-in-prompt) only caps how many
    of those get inlined into an LLM prompt, independent of how many were
    read from manifest.db in the first place."""
    summaries = []
    for row in sessions[:max_sessions]:
        try:
            tools_used = json.loads(row["tools_used"] or "[]")
        except (json.JSONDecodeError, TypeError):
            tools_used = []
        summaries.append({
            "session_id": row["session_id"],
            "start_ts": row["start_ts"],
            "end_ts": row["end_ts"],
            "n_calls": row["n_calls"],
            "n_errors": row["n_errors"],
            "tools_used": tools_used,
        })
    return summaries


def _render_session_summaries(summaries: list) -> str:
    if not summaries:
        return "(no undreamed session summaries available this run)"
    lines = []
    for s in summaries:
        tools = ", ".join(s["tools_used"][:12])
        lines.append(
            f"- session_id={s['session_id']} start={s['start_ts']} end={s['end_ts']} "
            f"n_calls={s['n_calls']} n_errors={s['n_errors']} tools=[{tools}]"
        )
    return "\n".join(lines)


def _domain_command_frequency(patterns: dict):
    rows = patterns.get("command_frequency") or []
    if not rows:
        return None
    rows = rows[:INSIGHT_MAX_ITEMS_PER_DOMAIN_PROMPT]
    lines = [f'- "{r["command"]}" (count={r["count"]})' for r in rows]
    refs = {r["command"] for r in rows}
    return "\n".join(lines), refs


def _domain_failure_retry(patterns: dict):
    rows = patterns.get("failure_retry") or []
    if not rows:
        return None
    rows = rows[:INSIGHT_MAX_ITEMS_PER_DOMAIN_PROMPT]
    lines = [
        f'- "{r["command"]}" failed rc={r["rc"]} at line {r["fail_line"]}, '
        f'retried {r["gap_lines"]} line(s) later at line {r["retry_line"]}'
        for r in rows
    ]
    refs = {r["command"] for r in rows}
    return "\n".join(lines), refs


def _domain_tool_usage(patterns: dict):
    usage = patterns.get("tool_usage_by_week") or {}
    weeks = patterns.get("weeks_observed") or []
    if not usage or not weeks:
        return None
    lines = []
    refs = set()
    for tag in sorted(usage):
        per_week = ", ".join(f"{wk}={usage[tag].get(wk, 0)}" for wk in weeks)
        lines.append(f"- {tag}: {per_week}")
        refs.add(tag)
        refs.update(weeks)
    return "\n".join(lines), refs


def _domain_automation_candidates(patterns: dict):
    rows = patterns.get("automation_candidates") or []
    if not rows:
        return None
    rows = rows[:INSIGHT_MAX_ITEMS_PER_DOMAIN_PROMPT]
    lines = []
    refs = set()
    for r in rows:
        seq_str = " -> ".join(r["sequence"])
        lines.append(
            f'- [{seq_str}] recurs across {r["session_count"]} session(s), '
            f'{r["occurrence_count"]} occurrence(s) total'
        )
        refs.add(seq_str)
        refs.update(r["sequence"])
    return "\n".join(lines), refs


_INSIGHT_DOMAIN_BUILDERS = {
    "command-frequency": _domain_command_frequency,
    "failure-retry": _domain_failure_retry,
    "tool-usage": _domain_tool_usage,
    "automation-candidates": _domain_automation_candidates,
}


_INSIGHT_SCHEMA_BLOCK = """Return ONLY this JSON object -- no prose, no thinking, no code fences:
{"insights": [
  {"observation": "one or two sentences: the specific pattern you found and why it matters",
   "evidence_refs": ["<copy EXACTLY from the DATA block above -- a command string, tag name, week label, or sequence step, character-for-character>", "..."],
   "cost_estimate": "rough wasted-calls/wasted-time estimate grounded in the counts you were given (e.g. '12 wasted CMD retries, ~2 min agent time')",
   "proposed_change": "one of: kb-fact | skill | prompt-rule | tool-change",
   "confidence": <float 0.0-1.0>,
   "kb_fact": {"title": "...", "content": "...", "topic": "...", "volatility": "static|fast|slow"},
   "skill": {"task": "...", "procedure": "...", "verification": "...", "preconditions": "", "failure_modes": "", "occupation": "..."},
   "prompt_rule": {"rule": "one short, imperative sentence -- exactly as it should read inside the system prompt", "rationale": "one sentence: what recurring problem this rule prevents", "section_hint": "which existing prompt section this would slot under, e.g. 'ground-truth-before-action' or 'time discipline' -- best guess, not binding"}
  }
]}
Include "kb_fact" ONLY when proposed_change is "kb-fact"; include "skill" ONLY when
proposed_change is "skill"; include "prompt_rule" ONLY when proposed_change is
"prompt-rule"; omit all three otherwise. A "prompt_rule" is NOT a new fact or a new
procedure -- it is a standing behavioral instruction worth adding to every future
session's system prompt, proposed only when the SAME avoidable mistake or omission
recurs across multiple sessions (never from one occurrence). evidence_refs that are not
an EXACT copy from the DATA block will be discarded by the validator, and an insight
with zero surviving evidence_refs will be discarded entirely -- ground every insight in
the real data you were given, do not invent counts or commands. Zero insights is a valid,
expected outcome for this domain if nothing here clears the bar."""


_INSIGHT_SYSTEM_PROMPTS = {
    "command-frequency": """You are the TRAUM dreamer's cross-session insight pass (Thread 3, Prompt 3.2), COMMAND-FREQUENCY domain ONLY.

You will be given the most-frequently-issued shell commands mined mechanically
from agent_commands.log (already counted -- do not recount, do not second-guess
the numbers) plus a list of recent session summaries for context.

Look for exactly ONE kind of finding in THIS call: a command (or tight family of
commands) run often enough, or repetitively enough for a narrow fixed purpose,
that it represents a real recurring workflow worth systematizing -- via a new
lse-kb fact documenting it, a reusable skill procedure, a prompt-rule change, or
an actual tool/automation change. Do NOT analyze failures, retries, or
week-over-week usage trends here -- those are separate domains with their own
calls.

""" + _INSIGHT_SCHEMA_BLOCK,

    "failure-retry": """You are the TRAUM dreamer's cross-session insight pass (Thread 3, Prompt 3.2), FAILURE-RETRY domain ONLY.

You will be given commands that failed (nonzero exit) and were re-issued
verbatim shortly afterward, mined mechanically from agent_commands.log
(already matched -- do not re-derive which pairs count) plus recent session
summaries for context.

Look for exactly ONE kind of finding in THIS call: a recurring failure pattern
worth fixing at the root -- a missing precondition, a config issue, a tool bug
-- rather than being silently worked around by a manual retry every time it
happens. Do NOT analyze raw command frequency, tool-usage cadence, or
multi-command sequences here -- those are separate domains with their own
calls.

""" + _INSIGHT_SCHEMA_BLOCK,

    "tool-usage": """You are the TRAUM dreamer's cross-session insight pass (Thread 3, Prompt 3.2), TOOL-USAGE domain ONLY.

You will be given per-tool (per-tag) event counts bucketed by ISO week, already
zero-filled across every week in range (already computed -- do not recompute),
plus recent session summaries for context.

Look for exactly ONE kind of finding in THIS call: a tool whose usage pattern
across weeks is itself the story -- went from active to silent (possible
abandonment or a broken workflow worth documenting), spiked sharply, or shows
some other week-over-week shift worth a human's attention. Do NOT analyze
individual command text, failure/retry pairs, or multi-command sequences here
-- those are separate domains with their own calls.

""" + _INSIGHT_SCHEMA_BLOCK,

    "automation-candidates": """You are the TRAUM dreamer's cross-session insight pass (Thread 3, Prompt 3.2), AUTOMATION-CANDIDATES domain ONLY.

You will be given command sequences that recur, in the same order, across
multiple distinct sessions (already confirmed to meet the session-count bar --
do not re-verify that count), plus recent session summaries for context.

Look for exactly ONE kind of finding in THIS call: a sequence worth turning
into a documented skill procedure, or an actual tool/script (proposed_change =
"tool-change") that replaces N manual steps with one call. Do NOT analyze raw
command frequency, failure/retry pairs, or week-over-week tool usage here --
those are separate domains with their own calls.

""" + _INSIGHT_SCHEMA_BLOCK,
}


def _validate_insight_item(item: dict, valid_refs: set) -> tuple:
    """Structural + code-enforced-evidence validation for one insight
    envelope item. Returns (cleaned_item, None) on success, (None, reason)
    on rejection. Returns a NEW dict with evidence_refs filtered down to
    only the refs that are a real, exact match against `valid_refs` (the
    domain data + session_ids actually shown to the model this call) --
    Prompt 3.2's verbatim-evidence rule, code-enforced here rather than
    only prompted for, same discipline as the stale-contradiction pass's
    substring check (_demote_proposals_for_doc)."""
    if not isinstance(item, dict):
        return None, "not an object"
    observation = str(item.get("observation", "")).strip()
    if len(observation) < INSIGHT_OBSERVATION_MIN_LEN:
        return None, f"observation missing or under {INSIGHT_OBSERVATION_MIN_LEN} chars"
    proposed_change = item.get("proposed_change")
    if proposed_change not in INSIGHT_PROPOSED_CHANGES:
        return None, f"unknown proposed_change: {proposed_change!r}"
    cost_estimate = str(item.get("cost_estimate", "")).strip()
    if not cost_estimate:
        return None, "cost_estimate missing or empty"
    confidence = item.get("confidence")
    if (not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
            or not (0.0 <= float(confidence) <= 1.0)):
        return None, f"confidence must be a number in [0.0, 1.0], got {confidence!r}"
    raw_refs = item.get("evidence_refs")
    if not isinstance(raw_refs, list):
        return None, "evidence_refs must be a list"
    verified_refs = [r for r in raw_refs if isinstance(r, str) and r in valid_refs]
    if not verified_refs:
        return None, "no evidence_refs verified as an exact match against the data shown this call"

    cleaned = {
        "observation": observation,
        "evidence_refs": verified_refs,
        "cost_estimate": cost_estimate,
        "proposed_change": proposed_change,
        "confidence": float(confidence),
    }
    if proposed_change == "kb-fact":
        kb_fact = item.get("kb_fact")
        if (isinstance(kb_fact, dict) and str(kb_fact.get("title", "")).strip()
                and str(kb_fact.get("content", "")).strip()):
            volatility = kb_fact.get("volatility")
            cleaned["kb_fact"] = {
                "title": str(kb_fact.get("title", "")).strip(),
                "content": str(kb_fact.get("content", "")).strip(),
                "topic": str(kb_fact.get("topic", "")).strip() or "general",
                "volatility": volatility if volatility in ("static", "fast", "slow") else "slow",
            }
    elif proposed_change == "skill":
        skill = item.get("skill")
        if (isinstance(skill, dict) and str(skill.get("task", "")).strip()
                and str(skill.get("procedure", "")).strip()
                and str(skill.get("verification", "")).strip()):
            cleaned["skill"] = {
                "task": str(skill.get("task", "")).strip(),
                "procedure": str(skill.get("procedure", "")).strip(),
                "verification": str(skill.get("verification", "")).strip(),
                "preconditions": str(skill.get("preconditions", "")).strip(),
                "failure_modes": str(skill.get("failure_modes", "")).strip(),
                "occupation": str(skill.get("occupation", "")).strip() or "Local System Engineer",
            }
    elif proposed_change == "prompt-rule":
        # Prompt 3.6. Note there is deliberately no "target_file" key read
        # from the model here -- the file a prompt-rule proposal writes to
        # is fixed in code (_insight_to_proposal -> LEARNED_RULES_TARGET),
        # never something the model chooses, so there is no field here for
        # a prompt-injected episode to steer.
        prompt_rule = item.get("prompt_rule")
        if (isinstance(prompt_rule, dict) and str(prompt_rule.get("rule", "")).strip()
                and str(prompt_rule.get("rationale", "")).strip()):
            cleaned["prompt_rule"] = {
                "rule": str(prompt_rule.get("rule", "")).strip(),
                "rationale": str(prompt_rule.get("rationale", "")).strip(),
                "section_hint": str(prompt_rule.get("section_hint", "")).strip() or "(unspecified)",
            }
    return cleaned, None


def _insight_to_proposal(insight: dict, domain: str, today: str):
    """kb-fact/skill/prompt-rule-shaped insights become a real proposal;
    tool-change still has no write path of any kind (no tool/script exists
    to dispatch a tool-change through) and stays report.md-only. Returns
    None if proposed_change isn't proposal-shaped, or its detail sub-object
    didn't validate (see _validate_insight_item).

    prompt-rule (Prompt 3.6) is the one case that does NOT dispatch through
    an existing goethe.py Tools method the way kb-fact/skill do -- there is
    no Tools method for "add a standing prompt instruction," and there must
    never be one that edits prompts/node4090* directly (plan §3.6: "NEVER
    direct edits to the canonical node4090 prompt"). Instead it targets the
    generated include file prompts/learned-rules.md via a new
    append_learned_rule call that dream_apply.py handles as its one
    documented exception to "writes go through Tools" (see that file's
    module docstring and check_prompt_rule_target()). target_file is a
    fixed constant here, never read from `insight` -- the model never
    chooses the path a prompt-rule proposal writes to."""
    evidence_str = (
        f"TRAUM-INSIGHT {domain} domain, dream-{today}: " + "; ".join(insight["evidence_refs"])
    )[:900]
    if insight["proposed_change"] == "kb-fact" and "kb_fact" in insight:
        kb = insight["kb_fact"]
        return {
            "type": "kb-fact",
            "call": "index_to_kb",
            "args": {
                "content": kb["content"],
                "title": kb["title"],
                "topic": kb["topic"],
                "source_tier": "inferred",  # dream-origin can never self-grant ground_truth
                "quality_score": 0.5,
                "evidence": evidence_str,
                "verified_against": "",
                "volatility": kb["volatility"],
            },
            "insight_domain": domain,
            "confidence": insight["confidence"],
            "why": insight["observation"][:300],
        }
    if insight["proposed_change"] == "skill" and "skill" in insight:
        sk = insight["skill"]
        return {
            "type": "skill-candidate",
            "call": "skill_record",
            "args": {
                "task": sk["task"],
                "occupation": sk["occupation"],
                "procedure": sk["procedure"],
                "verification": sk["verification"],
                "preconditions": sk["preconditions"],
                "failure_modes": sk["failure_modes"],
                "provenance": f"dream-{today}",
                "source_tier": "inferred",
                "quality": 0.45,
            },
            "evidence": insight["evidence_refs"],
            "insight_domain": domain,
            "confidence": insight["confidence"],
            "why": insight["observation"][:300],
        }
    if insight["proposed_change"] == "prompt-rule" and "prompt_rule" in insight:
        pr = insight["prompt_rule"]
        return {
            "type": "prompt-rule",
            "call": "append_learned_rule",
            "args": {
                "target_file": LEARNED_RULES_TARGET,  # hard-coded, see docstring above
                "rule": pr["rule"],
                "rationale": pr["rationale"],
                "section_hint": pr["section_hint"],
                "provenance": f"dream-{today}",
                "source_tier": "inferred",
            },
            "evidence": insight["evidence_refs"],
            "insight_domain": domain,
            "confidence": insight["confidence"],
            "why": insight["observation"][:300],
        }
    return None


def _run_insight_domain(cfg: DreamConfig, domain: str, patterns: dict, session_text: str,
                         session_refs: set, today: str) -> tuple:
    """One request_dream_envelope() call for one insight domain. Returns
    (insights, proposals, note). A domain with no underlying data (e.g.
    zero automation candidates this run) makes NO LLM call at all -- there
    is nothing to ask about, same null-result-without-a-call discipline
    the dedup/error-cluster passes already follow when their own
    prerequisite data is empty."""
    built = _INSIGHT_DOMAIN_BUILDERS[domain](patterns)
    if built is None:
        return [], [], f"{domain}: no data this run — skipped, no LLM call."
    data_text, domain_refs = built
    valid_refs = domain_refs | session_refs

    user_content = (
        f"DATA ({domain}):\n{data_text}\n\n"
        f"RECENT SESSION SUMMARIES:\n{session_text}"
    )
    env, err = request_dream_envelope(
        _INSIGHT_SYSTEM_PROMPTS[domain], user_content, cfg, key="insights"
    )
    if env is None:
        return [], [], f"{domain}: {err}"

    insights = []
    proposals = []
    rejected = 0
    for item in env.get("insights", []):
        cleaned, _reason = _validate_insight_item(item, valid_refs)
        if cleaned is None:
            rejected += 1
            continue
        cleaned["domain"] = domain
        insights.append(cleaned)
        proposal = _insight_to_proposal(cleaned, domain, today)
        if proposal is not None:
            proposals.append(proposal)

    note = f"{domain}: {len(insights)} insight(s) accepted"
    if rejected:
        note += f", {rejected} rejected (malformed or unverifiable evidence_refs)"
    note += "."
    return insights, proposals, note


def run_pass_insights(cfg: DreamConfig, sessions, episodes_by_session, kb_docs, error_docs) -> tuple:
    """Prompt 3.2 — TRAUM-INSIGHT cross-session insight pass. Feeds
    patterns.json's four mined domains (re-derived in-memory via
    mine_patterns/read_agent_log_window, same code Prompt 3.1's `patterns`
    pass itself uses -- no on-disk patterns.json dependency, no ordering
    requirement against a prior `--pass patterns` run) plus recent session
    summaries to the local model, ONE insight domain per LLM call (tight
    scope per call, matching Qwen3.6's profile) rather than one diffuse
    prompt covering everything at once.

    Insights ALWAYS land in report.md's "## Cross-session insights" section
    (folded into this pass's own narrative string -- write_report emits
    narrative verbatim, so a "## Cross-session insights" heading inside it
    renders as its own top-level report section). proposed_change in
    {"kb-fact", "skill", "prompt-rule"} is proposal-shaped: kb-fact/skill
    dispatch through dream_apply.py's existing Tools calls
    (index_to_kb/skill_record); prompt-rule (Prompt 3.6) dispatches through
    append_learned_rule, which dream_apply.py applies by appending to
    prompts/learned-rules.md instead of calling a Tools method -- see
    _insight_to_proposal. "tool-change" still maps to no write path at all
    and is never converted to a proposals.jsonl entry. All three
    proposal-shaped kinds flow into the SAME `proposals` list every other
    pass returns, validated by the SAME validate_proposal_shape() gate in
    main().
    """
    thresholds = {
        "insights_max_sessions_in_prompt": cfg.insights_max_sessions_in_prompt,
        "insight_observation_min_len": INSIGHT_OBSERVATION_MIN_LEN,
    }
    raw_lines = read_agent_log_window(cfg)
    events = parse_agent_log_lines(raw_lines) if raw_lines else []
    patterns = mine_patterns(events, cfg)

    session_summaries = build_session_summaries(sessions, cfg.insights_max_sessions_in_prompt)
    session_text = _render_session_summaries(session_summaries)
    session_refs = {s["session_id"] for s in session_summaries}

    domains_with_data = [d for d in INSIGHT_DOMAINS if _INSIGHT_DOMAIN_BUILDERS[d](patterns) is not None]
    if not domains_with_data and not session_summaries:
        narrative = (
            "insights pass: no patterns.json domain data (empty agent_commands.log "
            "window) and no session summaries this run — nothing to feed the model. "
            "Null result (PH3-2)."
        )
        return [], narrative, _null_record(
            "insights", "no_data_to_feed", looked=False,
            corpus_size={"session_summaries": 0, "domains_with_data": 0,
                         "insights_accepted": 0, "proposals": 0},
            thresholds=thresholds,
        )

    today = date.today().isoformat()
    all_insights = []
    all_proposals = []
    notes = []
    for domain in INSIGHT_DOMAINS:
        if _budget_checkpoint(cfg):  # Prompt 4.2
            notes.append(f"{domain}: skipped -- {cfg.budget.truncation_reason}.")
            break
        insights, proposals, note = _run_insight_domain(
            cfg, domain, patterns, session_text, session_refs, today
        )
        all_insights.extend(insights)
        all_proposals.extend(proposals)
        if note:
            notes.append(note)

    narrative_lines = [
        f"insights pass: {len(session_summaries)} session summary(ies) considered "
        f"across {len(INSIGHT_DOMAINS)} domain(s); {len(all_insights)} insight(s) "
        f"accepted total, {len(all_proposals)} converted to a proposal "
        "(kb-fact/skill/prompt-rule — tool-change stays report.md-only).",
        "",
    ] + notes + [""]

    narrative_lines.append("## Cross-session insights")
    narrative_lines.append("")
    null_record = None
    if not all_insights:
        narrative_lines.append(
            "Null result (PH3-2): no domain produced an insight that cleared the "
            "evidence-verification bar this run."
        )
        null_record = _null_record(
            "insights", "no_insight_cleared_bar", looked=True,
            corpus_size={"session_summaries": len(session_summaries),
                         "domains_with_data": len(domains_with_data),
                         "insights_accepted": 0, "proposals": 0},
            thresholds=thresholds,
        )
    else:
        for i, ins in enumerate(all_insights, 1):
            became_proposal = ins["proposed_change"] in ("kb-fact", "skill") and (
                "kb_fact" in ins or "skill" in ins
            )
            narrative_lines.append(
                f"{i}. **[{ins['domain']}/{ins['proposed_change']}]** "
                f"(confidence={ins['confidence']:.2f}) — {ins['observation']}"
            )
            narrative_lines.append(f"   - evidence: {', '.join(ins['evidence_refs'])}")
            narrative_lines.append(f"   - cost estimate: {ins['cost_estimate']}")
            if became_proposal:
                narrative_lines.append("   - flowed into proposals.jsonl")
            narrative_lines.append("")

    return all_proposals, "\n".join(narrative_lines), null_record


PASS_FUNCS = {
    "dedup": run_pass_dedup,
    "stale-contradiction": run_pass_stale_contradiction,
    "error-cluster": run_pass_error_cluster,
    "patterns": run_pass_patterns,
    "insights": run_pass_insights,
}

# --- output: report.md + proposals.jsonl ------------------------------------

def write_report(cfg: DreamConfig, sessions, proposals: list[dict], narrative: str,
                  null_record: dict | None = None) -> tuple[str, str]:
    """Prompt 3.8 adds `null_record` (optional, default None — every
    pre-3.8 call site with 2 positional args still works). When set,
    report.md gets a plain, dedicated "## Null result" section — not
    buried inside the narrative prose above it — stating the looked/
    didn't-look verdict, the corpus size examined, and the thresholds
    applied. The record is ALSO appended (never overwritten) to
    <dream-dir>/<date>/null-results.jsonl, the same "at" convention
    dream_apply.py already uses for applied.jsonl/rejected.jsonl.

    PASS-SCOPED FILENAMES (Thread 4 prerequisite, 2026-07-12): output is
    report-<pass>.md / proposals-<pass>.jsonl, NOT the shared report.md /
    proposals.jsonl of Threads 2-3. The Thread 3 close found the shared
    names silently discarded earlier passes' REAL pending proposals when a
    full cycle ran multiple passes against the same day-dir (recovered by
    hand that close; Prompt 3.8's append-mode null-results.jsonl fixed it
    for null verdicts only). Per-pass names make a later pass structurally
    unable to clobber an earlier one, while re-running the SAME pass still
    overwrites only its own snapshot (correct: latest run of a pass wins).
    Readers glob: dream_digest.py and dream_apply --queue scan
    proposals*.jsonl / report*.md, so legacy day-dirs stay readable."""
    today = date.today().isoformat()
    out_dir = os.path.join(cfg.dream_dir, today)
    report_path = os.path.join(out_dir, f"report-{cfg.pass_name}.md")
    proposals_path = os.path.join(out_dir, f"proposals-{cfg.pass_name}.jsonl")
    null_results_path = os.path.join(out_dir, "null-results.jsonl")

    lines = [
        f"# TRAUM dream report — {today} — pass: {cfg.pass_name}",
        "",
        f"Sessions considered: {len(sessions)}",
        f"Proposals generated: {len(proposals)}",
        "",
        "## Narrative",
        "",
        narrative,
        "",
    ]
    if proposals:
        lines.append("## Proposals")
        lines.append("")
        for i, p in enumerate(proposals, 1):
            lines.append(f"{i}. **{p.get('type')}** via `{p.get('call')}` — {p.get('why', '')}")
        lines.append("")

    if null_record is not None:
        # Prompt 3.8: "report.md says so plainly" — a dedicated section,
        # not just prose the reader has to notice inside ## Narrative.
        verdict = "nothing there" if null_record["looked"] else "didn't look"
        lines.append("## Null result")
        lines.append("")
        lines.append(f"**{verdict}** (`looked={null_record['looked']}`) — reason: `{null_record['reason']}`")
        lines.append("")
        lines.append(f"- corpus size examined: `{json.dumps(null_record['corpus_size'], sort_keys=True)}`")
        lines.append(f"- thresholds used: `{json.dumps(null_record['thresholds'], sort_keys=True)}`")
        lines.append("")
    report_text = "\n".join(lines)

    if cfg.dry_run:
        would_write = f"  {report_path}\n  {proposals_path}"
        if null_record is not None:
            would_write += f"\n  {null_results_path} (append)"
        print(f"[dream_runner] [dry-run] would write:\n{would_write}", file=sys.stderr)
        print(report_text)
        return report_path, proposals_path

    os.makedirs(out_dir, exist_ok=True)
    with open(report_path, "wt", encoding="utf-8") as f:
        f.write(report_text)
    with open(proposals_path, "wt", encoding="utf-8") as f:
        for p in proposals:
            f.write(json.dumps(p) + "\n")
    if null_record is not None:
        record = {**null_record, "date": today,
                  "generated_at": datetime.now().astimezone().isoformat()}
        with open(null_results_path, "at", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    return report_path, proposals_path


def write_failure_report(cfg: DreamConfig, exc: Exception, sessions_count: int = 0) -> tuple[str, str]:
    """Prompt 4.3 (TRAUM-AUTO) crash discipline: a PARTIAL report.md with a
    prominent FAILED banner, written from whatever context main() still
    has at crash time. sessions_count defaults to 0 so a crash before
    select_undreamed_sessions() even runs (e.g. during the episode
    snapshot) still gets a usable report instead of no report at all.

    Pass-scoped <dream-dir>/<date>/report-<pass>.md path (Thread 4
    prerequisite, 2026-07-12 -- same fix as write_report(): the Thread 3
    close found shared per-day filenames let a later pass silently clobber
    an earlier pass's output, so a crashed pass now only ever replaces its
    OWN pass's report, never another pass's, and never a successful
    pass's report either).

    ALSO appends one line to <dream-dir>/<date>/crashes.jsonl -- the same
    "at"-mode append convention null-results.jsonl already uses, so unlike
    report.md this survives the whole night's multi-pass sequence intact.
    This is what dream_digest.py's 3-consecutive-failed-nights escalation
    (same prompt) scans across recent day-dirs; see gather_crash_streak.

    Honors cfg.dry_run like every other write in this file (prints instead
    of writing). Returns (report_path, crashes_path) either way.
    """
    import traceback as _tb  # noqa: PLC0415

    today = date.today().isoformat()
    out_dir = os.path.join(cfg.dream_dir, today)
    report_path = os.path.join(out_dir, f"report-{cfg.pass_name}.md")
    crashes_path = os.path.join(out_dir, "crashes.jsonl")

    tb_text = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    lines = [
        f"# TRAUM dream report — {today} — pass: {cfg.pass_name}",
        "",
        "## FAILED",
        "",
        f"This pass crashed with an unhandled exception at {now} and did NOT "
        "complete. Everything below is PARTIAL/best-effort context from "
        "whatever main() had gotten to, not a normal report.",
        "",
        f"Sessions considered before the crash: {sessions_count}",
        "",
        f"**Error:** `{type(exc).__name__}: {exc}`",
        "",
        "```",
        tb_text.rstrip(),
        "```",
        "",
        "manifest.db's `dreamed_at` is untouched for every session this run "
        "would have looked at — only dream_apply.py ever sets it, and this "
        "pass never reached a point where it would have called that — so a "
        "re-dream on the next successful run will naturally retry everything "
        "this crash interrupted. Safe to re-dream.",
        "",
        f"See lse-errors-1024 (context=dream-runner, provenance=dream-infra) for "
        "the same failure recorded as a searchable error-KB entry, and "
        f"`{crashes_path}` for this night's full crash log.",
        "",
    ]
    report_text = "\n".join(lines)

    if cfg.dry_run:
        print(f"[dream_runner] [dry-run] would write FAILED report to:\n  {report_path}\n  {crashes_path}",
              file=sys.stderr)
        print(report_text)
        return report_path, crashes_path

    os.makedirs(out_dir, exist_ok=True)
    with open(report_path, "wt", encoding="utf-8") as f:
        f.write(report_text)
    crash_record = {
        "date": today,
        "pass": cfg.pass_name,
        "failed_at": now,
        "error_type": type(exc).__name__,
        "error_text": str(exc)[:2000],
        "sessions_considered": sessions_count,
    }
    with open(crashes_path, "at", encoding="utf-8") as f:
        f.write(json.dumps(crash_record) + "\n")
    return report_path, crashes_path


# --- CLI ----------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="dream_runner.py",
        description="TRAUM-ENGINE offline dream runner — READ-ONLY, proposes but never "
        "applies (Thread 2, Prompt 2.1 skeleton). See docs/dreaming/DESIGN.md.",
    )
    ap.add_argument("--pass", dest="pass_name", choices=sorted(PASS_FUNCS), required=True,
                    help="which dream pass to run: " + ", ".join(sorted(PASS_FUNCS)))
    ap.add_argument("--sessions", type=int, default=50,
                    help="max undreamed sessions to consider this run (default: 50)")
    ap.add_argument("--since", default=None,
                    help="only consider sessions with start_ts >= this ISO date "
                    "(default: no lower bound)")
    ap.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True,
                    help="report.md/proposals.jsonl are printed, not written to disk "
                    "(default: true). NOTE: Elasticsearch is NEVER written by this "
                    "script regardless of this flag — that is dream_apply.py's job "
                    "alone (Prompt 2.5), always confirm-gated. Pass --no-dry-run to "
                    "actually write the report/proposals files.")
    ap.add_argument("--episode-dir", default=_episode_dir_default(),
                    help="episode corpus root (default: $GOETHE_EPISODE_DIR or "
                    "/opt/local-se/episodes)")
    ap.add_argument("--dream-dir", default=_dream_dir_default(),
                    help="dream output root (default: $GOETHE_DREAM_DIR or /opt/local-se/dreams)")
    ap.add_argument("--manifest-db", default=None,
                    help="path to manifest.db (default: <episode-dir>/manifest.db)")
    ap.add_argument("--es-url", default=_es_url_default())
    ap.add_argument("--tasks-db", default=_tasks_db_default())
    ap.add_argument("--agent-log", default=_agent_log_default())
    ap.add_argument("--dream-llm-url", default=_dream_llm_url_default(),
                    help="forced dreamer endpoint, PLANNER_FORCE_URL-style (health-probed, "
                    "cascades to NODE3090_LLM_URL/NODE3090_OLLAMA_URL on failure or when unset)")
    ap.add_argument("--node3090-llm-url", default=_node3090_llm_url_default())
    ap.add_argument("--node3090-ollama-url", default=_node3090_ollama_url_default())
    ap.add_argument("--node3090-fallback-model", default=_node3090_fallback_model_default())
    ap.add_argument("--node3090-ssh-host", default=_node3090_ssh_host_default(),
                    help="node3090 SSH host for the remote VRAM gate probe "
                    "(default: $GOETHE_NODE3090_SSH_HOST or node3090.home.arpa)")
    ap.add_argument("--node3090-ssh-user", default=_node3090_ssh_user_default())
    ap.add_argument("--node3090-ssh-port", type=int, default=_node3090_ssh_port_default())
    ap.add_argument("--node3090-vram-gate-mb", type=int, default=_node3090_vram_gate_mb_default(),
                    help="skip the llama-server leg and go straight to Ollama when "
                    "node3090's free VRAM (nvidia-smi, via SSH) is below this many MiB "
                    "(default: 2000) -- same gate pattern as goethe.py's "
                    "_planner_free_vram_mb, applied to the remote box")
    ap.add_argument("--runner-session-prefix", default=_dream_runner_prefix_default(),
                    help="exclude sessions whose session_id starts with this (no "
                    "dream-of-dreams, DESIGN.md §2 invariant 3(e)); default: unset/none")

    dedup_group = ap.add_argument_group("dedup pass (Prompt 2.2)")
    dedup_group.add_argument("--ollama-url", default=_ollama_url_default(),
                    help="Ollama base URL for the configured embedding model (default: $GOETHE_OLLAMA_URL "
                    "or http://127.0.0.1:11434 — same valve as goethe.py's OLLAMA_URL)")
    dedup_group.add_argument("--embed-model", default=_embed_model_default(),
                    help="Ollama embedding model (default: qwen3-embedding:0.6b, 1024-dim)")
    dedup_group.add_argument("--dedup-floor", type=float, default=_dedup_floor_default(),
                    help="candidate-pair cosine floor (default: 0.85) — below the merge "
                    "threshold, wide enough to feed the labeling exercise")
    dedup_group.add_argument("--dedup-threshold", type=float, default=_dedup_threshold_default(),
                    help="merge cosine threshold for real runs (default: 0.92, matching "
                    "index_to_kb's live dedup threshold — earn changing this via "
                    "--sample-labels, not by editing the default)")
    dedup_group.add_argument("--sample-labels", action="store_true",
                    help="emit a threshold-labeling worksheet instead of running the pass: "
                    "samples borderline candidate pairs at each --label-thresholds value "
                    "for human in-thread labeling. No LLM calls, no proposals.jsonl.")
    dedup_group.add_argument("--label-thresholds", type=float, nargs="+",
                    default=list(DEFAULT_LABEL_THRESHOLDS),
                    help=f"candidate thresholds to sample for labeling (default: "
                    f"{list(DEFAULT_LABEL_THRESHOLDS)})")
    dedup_group.add_argument("--label-band", type=float, default=DEFAULT_LABEL_BAND,
                    help=f"band width above each threshold to sample from (default: {DEFAULT_LABEL_BAND})")
    dedup_group.add_argument("--label-sample-n", type=int, default=DEFAULT_LABEL_SAMPLE_N,
                    help=f"max pairs sampled per threshold band (default: {DEFAULT_LABEL_SAMPLE_N})")
    dedup_group.add_argument("--labels-out", default=None,
                    help="write the labeling worksheet to this path in addition to stdout "
                    "(e.g. eval/dedup-threshold-labels.md, adjacent to retrieval-gold-v1.jsonl)")

    error_group = ap.add_argument_group("error-cluster pass (Prompt 2.4)")
    error_group.add_argument("--error-cluster-threshold", type=float,
                    default=_error_cluster_threshold_default(),
                    help="cosine floor for grouping error/timeout occurrences as the same "
                    "underlying failure (default: 0.80)")

    patterns_group = ap.add_argument_group("patterns pass (Prompt 3.1, TRAUM-INSIGHT)")
    patterns_group.add_argument("--patterns-max-lines", type=int,
                    default=_patterns_max_lines_default(),
                    help="windowed tail-read size for agent_commands.log, in raw lines "
                    "(default: 50000 -- corpus-audit.md (a)'s windowed-read caveat, the "
                    "log is unrotated and growing)")
    patterns_group.add_argument("--patterns-retry-window", type=int,
                    default=_patterns_retry_window_default(),
                    help="failure->retry adjacency lookahead, in raw log lines (default: 20)")
    patterns_group.add_argument("--patterns-session-gap-minutes", type=int,
                    default=_patterns_session_gap_minutes_default(),
                    help="inactivity gap (minutes) used to infer session boundaries in "
                    "agent_commands.log, which carries no session_id of its own (default: 30)")
    patterns_group.add_argument("--patterns-min-sequence-len", type=int,
                    default=_patterns_min_sequence_len_default(),
                    help="shortest command sequence considered an automation candidate "
                    "(default: 3)")
    patterns_group.add_argument("--patterns-max-sequence-len", type=int,
                    default=_patterns_max_sequence_len_default(),
                    help="longest command sequence window mined, bounds worst-case compute "
                    "(default: 8)")
    patterns_group.add_argument("--patterns-min-sessions", type=int,
                    default=_patterns_min_sessions_default(),
                    help="minimum distinct inferred sessions a repeated command sequence "
                    "must span to qualify as an automation candidate (default: 3)")
    patterns_group.add_argument("--patterns-top-commands", type=int,
                    default=_patterns_top_commands_default(),
                    help="command-frequency table size cap (default: 50)")
    patterns_group.add_argument("--patterns-out", default=None,
                    help="override patterns.json output path (default: "
                    "<dream-dir>/<date>/patterns.json)")

    insights_group = ap.add_argument_group("insights pass (Prompt 3.2, TRAUM-INSIGHT)")
    insights_group.add_argument("--insights-max-sessions-in-prompt", type=int,
                    default=_insights_max_sessions_in_prompt_default(),
                    help="cap on how many session summaries are inlined into each "
                    "insight LLM prompt, independent of --sessions' manifest.db "
                    "selection size (default: 20)")

    guard_group = ap.add_argument_group("run guards + budgets (Prompt 4.2, TRAUM-AUTO)")
    guard_group.add_argument("--lockfile", default=_lockfile_default(),
                    help="path to the cross-invocation run lock (default: "
                    "<dream-dir>/.dream.lock) -- guards against two dream_runner.py "
                    "processes (scheduled or manual) running concurrently")
    guard_group.add_argument("--lock-max-age-s", type=float, default=_lock_max_age_s_default(),
                    help="a held lock older than this many seconds is treated as stale "
                    "and reclaimed even if its PID still looks alive (PID-reuse edge "
                    "case) (default: 14400 = 4h)")
    guard_group.add_argument("--session-active-window-min", type=int,
                    default=_session_active_window_min_default(),
                    help="skip the run if any LSE session (per manifest.db, refreshed "
                    "right before this check) was active within this many minutes "
                    "(default: 30) -- courtesy to a live operator, not a hard invariant")
    guard_group.add_argument("--budget-max-sessions", type=int, default=None,
                    help="hard per-run cap on sessions actually processed by a pass "
                    "with a per-session LLM loop (default: same value as --sessions)")
    guard_group.add_argument("--budget-max-llm-calls", type=int,
                    default=_budget_max_llm_calls_default(),
                    help="hard per-run cap on LLM chat-completion calls made through "
                    "call_dream_llm, across the whole cascade (default: 100)")
    guard_group.add_argument("--budget-max-wall-clock-min", type=float,
                    default=_budget_max_wall_clock_min_default(),
                    help="hard per-run wall-clock budget in minutes (default: 45)")
    guard_group.add_argument("--ignore-guards", action="store_true",
                    help="bypass the lock + recent-session-activity checks entirely "
                    "(manual/debug runs only -- NEVER set this on the scheduled "
                    "nightly cycle; per-run budgets still apply even with this set)")

    ap.add_argument("-v", "--verbose", action="store_true")
    return ap.parse_args(argv)


KB_SOURCE_FIELDS = [
    "title", "content", "doc_id", "topic", "tags", "quality_score",
    "source_tier", "source_url", "source_path", "volatility", "stale",
    "refinement_count", "consecutive_failures", "success_count",
    "created_at", "updated_at", "verified_against", "version",
]  # deliberately excludes "embedding" (1024 floats/doc) — dedup re-embeds
   # fresh via Ollama rather than trusting a possibly-stale stored vector.


def _run_sample_labels(cfg: DreamConfig) -> None:
    """--sample-labels mode: emit the threshold-labeling worksheet and exit.
    No LLM calls, no report.md/proposals.jsonl, no session scan needed —
    this is pure lse-kb hygiene tooling for the human-in-the-loop exercise
    Prompt 2.2 describes ("sample 20 candidate pairs at 3 thresholds... we
    label them together in-thread")."""
    try:
        kb_docs = search_index(cfg, "lse-kb", {"query": {"match_all": {}}, "size": 500,
                                                "_source": KB_SOURCE_FIELDS})
    except Exception as exc:
        print(f"[dream_runner] ES read failed ({exc}) — cannot sample for labeling.", file=sys.stderr)
        return
    if not kb_docs:
        print("[dream_runner] lse-kb returned zero docs — nothing to sample.", file=sys.stderr)
        return

    docs_by_id = {d["_id"]: d for d in kb_docs if d.get("_id")}
    embeddings = embed_kb_docs(cfg, kb_docs)
    if not embeddings:
        print(f"[dream_runner] embedding failed for all {len(docs_by_id)} doc(s) "
              f"(Ollama unreachable at {cfg.ollama_url}?).", file=sys.stderr)
        return

    pairs = find_candidate_pairs(embeddings, cfg.dedup_floor)
    before_chunk_filter = len(pairs)
    pairs = filter_same_document_chunks(pairs, docs_by_id)
    print(f"[dream_runner] {len(pairs)} candidate pair(s) at/above floor {cfg.dedup_floor} "
          f"across {len(embeddings)} embedded doc(s) ({before_chunk_filter - len(pairs)} "
          "dropped as same-document chunks).", file=sys.stderr)

    sample = sample_pairs_for_labeling(pairs, cfg)
    worksheet = render_labeling_worksheet(sample, docs_by_id, cfg)
    print(worksheet)
    if cfg.labels_out:
        os.makedirs(os.path.dirname(cfg.labels_out) or ".", exist_ok=True)
        with open(cfg.labels_out, "wt", encoding="utf-8") as f:
            f.write(worksheet)
        print(f"[dream_runner] worksheet also written to {cfg.labels_out}", file=sys.stderr)


# --- run guards (Prompt 4.2, TRAUM-AUTO): lockfile, session-activity, ------
# --- and the dreamer-episode-exclusion assert -------------------------------

def _pid_alive(pid: int) -> bool:
    """True if a process with this PID currently exists (any owner).
    os.kill(pid, 0) sends no actual signal, just probes existence/
    permission. ESRCH (no such process) -> dead, the lock is stale.
    EPERM (exists, owned by someone else) -> still counts as alive; this
    is a liveness probe, never an attempt to signal/kill anything."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock(lockfile: str) -> dict | None:
    try:
        with open(lockfile, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def acquire_lock(cfg: DreamConfig) -> bool:
    """Best-effort single-writer lock across ALL dream_runner.py
    invocations on this box, not just same-pass ones -- covers both the
    scheduled 5-ExecStart nightly cycle somehow still running when the
    NEXT night's timer fires (each pass is its own process, so this is
    what actually prevents two full cycles overlapping) and an operator's
    manual CLI run overlapping the scheduled one.

    Atomic create (O_CREAT|O_EXCL) avoids the classic check-then-create
    race. A held lock is reclaimed once (one retry) when it looks stale:
    its PID is dead (a crashed prior run -- Prompt 4.3's real crash
    discipline isn't built yet, so this is the only cleanup a crash gets
    today), OR the file itself is older than cfg.lock_max_age_s (PID-reuse
    edge case, or a run stuck well past its own wall-clock budget).

    Returns True if acquired (caller now owns the lock and MUST call
    release_lock when done, normally via try/finally), False if genuinely
    held by a live, fresh lock -- callers should treat False as "skip this
    run", never as an error.
    """
    os.makedirs(os.path.dirname(cfg.lockfile) or ".", exist_ok=True)
    payload = json.dumps({
        "pid": os.getpid(),
        "pass": cfg.pass_name,
        "acquired_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }).encode()

    for _attempt in (1, 2):  # 2nd attempt only fires right after reclaiming a stale lock
        try:
            fd = os.open(cfg.lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
            return True
        except FileExistsError:
            pass

        held = _read_lock(cfg.lockfile)
        try:
            age_s = time.time() - os.path.getmtime(cfg.lockfile)
        except OSError:
            age_s = float("inf")  # file vanished between the exists-check and stat -- treat as gone
        held_pid = held.get("pid") if held else None
        stale = (
            held is None
            or held_pid is None
            or not _pid_alive(held_pid)
            or age_s >= cfg.lock_max_age_s
        )
        if not stale:
            return False
        print(f"[dream_runner] reclaiming stale lock at {cfg.lockfile} "
              f"(held={held}, age={age_s:.0f}s)", file=sys.stderr)
        try:
            os.remove(cfg.lockfile)
        except OSError:
            pass
        # Loop back for exactly one more O_EXCL attempt now that the stale
        # file is gone -- if another process beat us to reclaiming it, the
        # 2nd attempt legitimately fails again and we correctly report
        # "held", rather than looping forever.
    return False


def release_lock(cfg: DreamConfig) -> None:
    """Best-effort -- never raises. Only removes the lock if it still
    looks like OUR lock (PID match), so a lock some OTHER process already
    reclaimed as stale (we somehow ran past lock_max_age_s ourselves) is
    never yanked out from under it."""
    held = _read_lock(cfg.lockfile)
    if held and held.get("pid") == os.getpid():
        try:
            os.remove(cfg.lockfile)
        except OSError:
            pass


def _recent_session_active(cfg: DreamConfig) -> str:
    """Empty string if no LSE session was recently active; otherwise a
    human-readable reason for the skip.

    Refreshes manifest.db first (episode_index.build_manifest) so "per
    manifest" -- Prompt 4.2's own phrasing -- reflects near-real-time
    state rather than however stale the last independent manifest rebuild
    happened to be; nothing else on this box currently rebuilds
    manifest.db on a schedule of its own, so without this refresh the
    check could easily miss a session that started minutes ago.
    """
    try:
        _epidx.build_manifest(cfg.episode_dir, cfg.manifest_db)
    except Exception as exc:
        print(f"[dream_runner] WARNING: manifest refresh before session-activity "
              f"check failed ({exc}) -- checking against possibly-stale manifest.db",
              file=sys.stderr)

    if not os.path.exists(cfg.manifest_db):
        return ""

    conn = sqlite3.connect(cfg.manifest_db, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT session_id, end_ts FROM sessions ORDER BY end_ts DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["end_ts"]:
        return ""

    try:
        end_dt = datetime.fromisoformat(row["end_ts"])
    except ValueError:
        return ""
    now = datetime.now().astimezone()
    age_min = (now - end_dt).total_seconds() / 60.0
    # age_min < 0 means the session's own end_ts is in our "future" (clock
    # skew) -- don't false-positive-block a nightly run on a clock glitch.
    if 0 <= age_min < cfg.session_active_window_min:
        return (f"session {row['session_id']!r} was active {age_min:.1f} min ago "
                f"(< {cfg.session_active_window_min}min window)")
    return ""


def _snapshot_episode_session_files(episode_dir: str) -> dict[str, float]:
    """{relative_path: mtime} for every SESSION file (day-dir/*.jsonl[.gz])
    under episode_dir -- deliberately excludes manifest.db itself, which is
    a legitimate, expected write target (episode_index.build_manifest() --
    including the call inside _recent_session_active() above -- and
    dream_apply.py's dreamed_at column both write there by design). Reuses
    episode_index.py's own iter_day_dirs/iter_session_files so "what counts
    as a session file" has exactly one definition anywhere in this
    codebase, rather than a second regex guess living here too."""
    snap: dict[str, float] = {}
    if not os.path.isdir(episode_dir):
        return snap
    for _day, day_dir in _epidx.iter_day_dirs(episode_dir):
        for path in _epidx.iter_session_files(day_dir):
            try:
                snap[os.path.relpath(path, episode_dir)] = os.path.getmtime(path)
            except OSError:
                continue
    return snap


def assert_no_episode_writes(episode_dir: str, before: dict[str, float]) -> None:
    """Prompt 4.2 (TRAUM-AUTO) makes DESIGN.md §2 invariant 3(e) --
    "no dream-of-dreams" -- structural, not just conventional.

    It is currently true BY CONSTRUCTION that dream_runner.py never writes
    a session file into EPISODE_DIR: the dreamer does not run through
    goethe_mcp.py's register() journaling wrapper, so nothing in this file
    even HAS a write path into EPISODE_DIR today. But "currently true by
    construction" is an ASSUMPTION a future edit could break quietly (a
    new pass that shells out to something that happens to write there,
    or a copy-paste of gateway-adjacent code) -- the prompt's own words are
    "assert, don't assume". So: assert it. Compare a full before/after
    listing (path -> mtime) of every session file under episode_dir and
    fail LOUDLY if anything was added, removed, or modified.

    Raises AssertionError -- deliberately uncaught anywhere in main(); a
    violation here is exactly the corpus-poisoning failure mode
    docs/threat-model-kb.md's dreaming section (Prompt 4.7, not yet
    written) will need to reason about, so it must be as loud as a real
    bug, never silently swallowed.
    """
    after = _snapshot_episode_session_files(episode_dir)
    if after != before:
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        changed = sorted(p for p in (set(after) & set(before)) if after[p] != before[p])
        raise AssertionError(
            "INVARIANT VIOLATION (Prompt 4.2, no-dream-of-dreams): EPISODE_DIR "
            f"session files changed during this run -- added={added} "
            f"removed={removed} changed={changed}. dream_runner must NEVER "
            "write into GOETHE_EPISODE_DIR; this indicates a new code path "
            "broke that invariant."
        )


def _handle_crash(cfg: DreamConfig, exc: Exception, sessions_count: int = 0) -> None:
    """Prompt 4.3 (TRAUM-AUTO) crash discipline -- called from main()'s
    `except Exception` handler for ANY unhandled exception during a real
    run (post-guards, post-lock-acquisition; see main()'s own comment for
    why the guard-check phase itself is out of scope). Best-effort does:
      1. record_crash_error() -- lse-errors-1024, context="dream-runner",
         provenance="dream-infra".
      2. write_failure_report() -- partial report.md with a FAILED banner
         + crashes.jsonl append (what the 3-consecutive-failed-nights
         escalation in dream_digest.py scans for).
      3. refresh the morning digest, so an escalation banner (if this
         crash makes 3 in a row) shows up immediately, not just after
         tomorrow's first successful/unsuccessful run.
      3. dreamed_at is left untouched -- already true by construction
         (only dream_apply.py ever sets it), nothing here needs to
         actively enforce that, it's just restated in the report text.

    NEVER raises itself -- each step is independently try/excepted so one
    broken reporting path (e.g. ES down, which might be WHY the original
    crash happened) cannot mask or replace the exception main() is about
    to re-raise after this returns. Logs its own failures to stderr.
    """
    print(f"[dream_runner] CRASH in pass={cfg.pass_name}: {type(exc).__name__}: {exc}",
          file=sys.stderr)

    try:
        write_failure_report(cfg, exc, sessions_count=sessions_count)
    except Exception as report_exc:
        print(f"[dream_runner] WARNING: failed to write the FAILED report itself "
              f"({report_exc}) -- continuing crash handling anyway", file=sys.stderr)

    try:
        result = record_crash_error(cfg, error_text=f"{type(exc).__name__}: {exc}",
                                     context="dream-runner")
        print(f"[dream_runner] {result}", file=sys.stderr)
    except Exception as record_exc:
        print(f"[dream_runner] WARNING: record_crash_error itself failed ({record_exc})",
              file=sys.stderr)

    try:
        dream_digest.refresh_digest(
            dream_dir=cfg.dream_dir, episode_dir=cfg.episode_dir, manifest_db=cfg.manifest_db,
            es_url=cfg.es_url, dry_run=cfg.dry_run,
        )
    except Exception as digest_exc:
        print(f"[dream_runner] WARNING: post-crash digest refresh failed ({digest_exc})",
              file=sys.stderr)


def main(argv=None) -> None:
    args = parse_args(argv)
    cfg = build_config(args)

    if args.sample_labels:
        _run_sample_labels(cfg)
        return

    # Prompt 4.2: lock + recent-session-activity guards. --ignore-guards is
    # a manual/debug escape hatch ONLY -- goethe-dream.service.tmpl never
    # sets it. Per-run budgets (below) always apply regardless. NOTE
    # (Prompt 4.3): the guard-check phase itself is deliberately OUTSIDE
    # the try/except crash handler below -- it runs before the lock is
    # even acquired (nothing to release yet), and both guard functions
    # already have their own internal exception handling that degrades to
    # "don't block" rather than raising (see _recent_session_active's own
    # docstring) -- an exception escaping THAT would itself be a bug in
    # the guard code, a different failure class than a pass crashing.
    if not cfg.ignore_guards:
        block_reason = _recent_session_active(cfg)
        if block_reason:
            print(f"[dream_runner] SKIPPING run (pass={cfg.pass_name}): {block_reason}",
                  file=sys.stderr)
            return
        if not acquire_lock(cfg):
            print(f"[dream_runner] SKIPPING run (pass={cfg.pass_name}): another dream "
                  f"run holds the lock at {cfg.lockfile}", file=sys.stderr)
            return
    else:
        print("[dream_runner] --ignore-guards set: bypassing the lock + recent-session "
              "checks (manual/debug run only -- never use this on the scheduled "
              "nightly cycle)", file=sys.stderr)

    cfg.budget = DreamBudget(
        max_sessions=cfg.budget_max_sessions,
        max_llm_calls=cfg.budget_max_llm_calls,
        max_wall_clock_s=cfg.budget_max_wall_clock_min * 60,
    )

    sessions: list = []
    try:
        episode_snapshot = _snapshot_episode_session_files(cfg.episode_dir)

        sessions = select_undreamed_sessions(cfg)
        mode = "[dry-run] " if cfg.dry_run else ""
        print(f"[dream_runner] {mode}pass={cfg.pass_name} undreamed-sessions-selected={len(sessions)} "
              f"(limit={cfg.sessions_limit}, since={cfg.since or '(none)'})", file=sys.stderr)

        if not sessions:
            print("[dream_runner] no undreamed sessions — episode-history context will be empty, "
                  "but ES-only passes (dedup, error-cluster) still run against the live indices.",
                  file=sys.stderr)

        episodes_by_session = {row["session_id"]: read_session_episodes(cfg, row) for row in sessions}

        kb_docs: list = []
        error_docs: list = []
        try:
            if cfg.pass_name in ("dedup", "stale-contradiction"):
                kb_docs = search_index(cfg, "lse-kb", {"query": {"match_all": {}}, "size": 500,
                                                        "_source": KB_SOURCE_FIELDS})
            if cfg.pass_name == "error-cluster":
                error_docs = search_index(cfg, "lse-errors-1024", {"query": {"match_all": {}}, "size": 500,
                                                                "_source": ERROR_SOURCE_FIELDS})
        except Exception as exc:
            print(f"[dream_runner] WARNING: ES read failed ({exc}) — proceeding with empty index view",
                  file=sys.stderr)

        pass_func = PASS_FUNCS[cfg.pass_name]
        raw_proposals, narrative, null_record = pass_func(cfg, sessions, episodes_by_session, kb_docs, error_docs)

        if cfg.budget.truncated:
            narrative = (
                f"{narrative}\n\n**BUDGET TRUNCATION (Prompt 4.2):** this pass stopped early — "
                f"{cfg.budget.truncation_reason}. Results above are PARTIAL, not a complete pass "
                "over the selected corpus — this is a normal, expected exit, not an error. Budget "
                f"usage: sessions {cfg.budget.sessions_consumed}/{cfg.budget.max_sessions}, LLM "
                f"calls {cfg.budget.llm_calls_made}/{cfg.budget.max_llm_calls}, wall-clock "
                f"{cfg.budget.elapsed_s():.0f}s/{cfg.budget.max_wall_clock_s:.0f}s. manifest.db's "
                "dreamed_at is untouched either way (only dream_apply.py sets it), so a re-dream "
                "will naturally pick up whatever this run didn't reach."
            )
            print(f"[dream_runner] BUDGET TRUNCATED: {cfg.budget.truncation_reason}", file=sys.stderr)

        proposals = []
        for p in raw_proposals:
            err = validate_proposal_shape(p)
            if err:
                print(f"[dream_runner] WARNING: dropping malformed proposal ({err}): {p!r}",
                      file=sys.stderr)
                continue
            proposals.append(p)

        report_path, proposals_path = write_report(cfg, sessions, proposals, narrative, null_record)
        null_suffix = f" null_result={null_record['reason']} (looked={null_record['looked']})" if null_record else ""
        print(f"[dream_runner] {mode}done. report={report_path} proposals={proposals_path} "
              f"n_proposals={len(proposals)}{null_suffix}", file=sys.stderr)

        # Prompt 3.4 (TRAUM-INSIGHT): refresh the morning digest "at the end of
        # every dream run". Never allowed to turn a successful pass into a
        # reported failure -- refresh_digest() swallows its own exceptions.
        dream_digest.refresh_digest(
            dream_dir=cfg.dream_dir, episode_dir=cfg.episode_dir, manifest_db=cfg.manifest_db,
            es_url=cfg.es_url, dry_run=cfg.dry_run,
        )

        # Prompt 4.2: assert, don't assume -- see assert_no_episode_writes's
        # own docstring. Deliberately the LAST statement in the try block,
        # inside it (not after) so it still runs via `finally` -> release_lock
        # even if this specific check is what fails.
        try:
            assert_no_episode_writes(cfg.episode_dir, episode_snapshot)
        except AssertionError as _aerr:
            if cfg.ignore_guards:
                print(
                    "[dream_runner] WARNING (downgraded by --ignore-guards): "
                    "EPISODE_DIR changed during this manual run -- expected when "
                    "the live gateway is serving sessions concurrently; the "
                    "nightly quiet-hours run keeps the hard invariant. "
                    f"Details: {_aerr}",
                    file=sys.stderr,
                )
            else:
                raise
    except Exception as exc:
        # Prompt 4.3: crash discipline. Handle (record_error, partial
        # FAILED report, digest refresh), THEN re-raise the ORIGINAL
        # exception unchanged -- this process still exits non-zero (so
        # `systemctl status`/journalctl correctly show this pass failed),
        # but goethe-dream.service.tmpl has Restart=no (Type=oneshot's own
        # default, made explicit -- see that file) so there is no
        # systemd-level restart spiral, and each of its 5 ExecStart lines
        # is "-"-prefixed so one crashed pass doesn't block the remaining
        # four that same night. The .timer fires again tomorrow regardless
        # of tonight's exit code -- that's the actual retry mechanism.
        _handle_crash(cfg, exc, sessions_count=len(sessions))
        raise
    finally:
        if not cfg.ignore_guards:
            release_lock(cfg)


if __name__ == "__main__":
    main()
