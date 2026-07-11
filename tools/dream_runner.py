#!/usr/bin/env python3
"""
dream_runner.py — TRAUM-ENGINE offline dream runner (v0.4.0)
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
a two-attempt envelope-parse loop with one corrective retry. Nothing here
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
  GOETHE_DREAM_RUNNER_SESSION_PREFIX  if set, sessions whose session_id starts with
                                    this are excluded from selection — DESIGN.md §2
                                    invariant 3(e), "no dream-of-dreams". Empty (default)
                                    = no filter; the dreamer does not currently run
                                    through the MCP gateway, so it has no session_id
                                    of its own to exclude yet.

INVARIANTS enforced structurally in this file, not just by convention
(DESIGN.md §2 row 1 and row 3(e)):
  - Zero Elasticsearch write calls anywhere below — only `search_index()`
    (es.search) exists; there is no es.index/update/delete call site.
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
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime

import episode_index as _epidx

__version__ = "0.4.0"


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


def _dream_runner_prefix_default() -> str:
    return os.environ.get("GOETHE_DREAM_RUNNER_SESSION_PREFIX", "")


def _ollama_url_default() -> str:
    # Same valve/default as goethe.py's Tools.Valves.OLLAMA_URL (tools/goethe.py:934).
    return os.environ.get("GOETHE_OLLAMA_URL", "http://127.0.0.1:11434")


def _embed_model_default() -> str:
    # Same as goethe.py's Tools.Valves.EMBED_MODEL (tools/goethe.py:938).
    return os.environ.get("GOETHE_EMBED_MODEL", "nomic-embed-text")


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


def build_config(args: argparse.Namespace) -> DreamConfig:
    episode_dir = args.episode_dir
    manifest_db = args.manifest_db or os.path.join(episode_dir, "manifest.db")
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
    """The ONLY ES call shape this file is allowed to use. Do not add an
    es.index/update/delete call anywhere in this module — proposing a
    change is this file's entire job; applying one is dream_apply.py's
    (Prompt 2.5), and only past a human confirm-gate."""
    es = es_client(cfg)
    resp = es.search(index=index, body=body)
    return [dict(h["_source"], _id=h["_id"]) for h in resp["hits"]["hits"]]


# --- embeddings / cosine dedup (Prompt 2.2) ---------------------------------

def embed_text(cfg: DreamConfig, text: str) -> list:
    """768-dim embedding from Ollama nomic-embed-text — the SAME call shape
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
    Returns the model's raw reply string, or 'ERROR: <reason>' if every
    step fails.
    """
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
    if _health_probe(llm_url):
        print(f"[dream_runner] llama-server probe OK -> {llm_url}", file=sys.stderr)
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


def parse_dream_envelope(reply: str) -> tuple[dict | None, str]:
    """Parse a dream-pass reply into its JSON envelope. Same strip +
    raw_decode approach as goethe.py's _parse_planner_envelope
    (tools/goethe.py:6751), adapted to this envelope's required key —
    'proposals' (a list; may be EMPTY, that's a valid outcome per
    DESIGN.md §6.1 "zero proposals is a valid, expected outcome") instead
    of the planner's 'steps'.
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
    if "proposals" not in env or not isinstance(env["proposals"], list):
        return None, "envelope has no 'proposals' array"
    return env, ""


def request_dream_envelope(system_prompt: str, user_content: str, cfg: DreamConfig) -> tuple[dict | None, str | None]:
    """Two-attempt retry loop, same shape as goethe.py's
    _request_plan_envelope (tools/goethe.py:6860): call the LLM, parse the
    envelope; on failure, append a corrective note describing exactly what
    was wrong and retry exactly once.
    Returns (envelope_dict, None) on success, (None, error_message) on
    failure (both attempts exhausted, or the LLM cascade itself errored).
    """
    env = None
    fail_reason = ""
    content = user_content
    for attempt in (1, 2):
        reply = call_dream_llm(system_prompt, content, cfg, no_think=True)
        if not reply or reply.startswith("ERROR:"):
            return None, f"DREAMER UNAVAILABLE — ({(reply or 'no reply')[:160]})"
        env, fail_reason = parse_dream_envelope(reply)
        if env is not None:
            break
        print(f"[dream_runner] attempt {attempt} rejected — {fail_reason[:120]}", file=sys.stderr)
        content = (
            user_content
            + "\n\nPREVIOUS REPLY REJECTED: " + fail_reason[:200]
            + "\nReturn ONLY the JSON envelope object {\"proposals\": [...]} — "
            "no thinking, no prose, no code fences."
        )
    if env is None:
        return None, f"DREAMER UNAVAILABLE — {fail_reason} (after retry)."
    return env, None


# --- proposal shape guard (structural only — NOT the hard-invariant validator) -

REQUIRED_PROPOSAL_KEYS = {"type", "call", "args", "why"}
KNOWN_PROPOSAL_TYPES = {"dedup", "reverify", "demote", "skill-candidate", "kb-fact"}


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
    returned as an explicit narrative, not silently swallowed — PH3-2.
    """
    if not kb_docs:
        return [], "dedup pass: lse-kb returned zero docs (empty index or ES unreachable this run) — nothing to dedup. Null result (PH3-2)."

    docs_by_id = {d["_id"]: d for d in kb_docs if d.get("_id")}

    embeddings = embed_kb_docs(cfg, kb_docs)
    if not embeddings:
        return [], (
            f"dedup pass: embedding failed for all {len(docs_by_id)} doc(s) "
            f"(Ollama unreachable at {cfg.ollama_url}?) — cannot compute "
            "similarity this run."
        )

    pairs = find_candidate_pairs(embeddings, cfg.dedup_floor)
    pairs = filter_same_document_chunks(pairs, docs_by_id)
    if not pairs:
        return [], (
            f"dedup pass: zero candidate pairs at/above the floor "
            f"{cfg.dedup_floor} across {len(embeddings)} embedded doc(s) "
            "(after excluding same-document chunk pairs). Null result "
            "(PH3-2) — no near-duplicates in the corpus at this floor "
            "right now."
        )

    accepted = [p for p in pairs if p[2] >= cfg.dedup_threshold]
    if not accepted:
        return [], (
            f"dedup pass: {len(pairs)} candidate pair(s) found above the floor "
            f"{cfg.dedup_floor}, but none reached the merge threshold "
            f"{cfg.dedup_threshold}. Null result (PH3-2) — nothing proposed "
            "this run."
        )

    narrative_lines = [
        f"dedup pass: {len(accepted)} candidate pair(s) at/above threshold "
        f"{cfg.dedup_threshold}, out of {len(pairs)} pair(s) above the floor "
        f"{cfg.dedup_floor}, out of {len(embeddings)} embedded doc(s)."
    ]
    proposals = []
    for start in range(0, len(accepted), DEDUP_LLM_BATCH_SIZE):
        batch = accepted[start:start + DEDUP_LLM_BATCH_SIZE]
        batch_proposals, batch_note = _dedup_batch_to_proposals(cfg, batch, docs_by_id)
        proposals.extend(batch_proposals)
        if batch_note:
            narrative_lines.append(batch_note)

    if not proposals:
        narrative_lines.append(
            "Model confirmed zero true duplicates among the candidates — "
            "null result (PH3-2): cosine similarity alone was not enough "
            "evidence for any pair this run."
        )
    return proposals, "\n".join(narrative_lines)


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
    (PH3-2) rather than staying silent about it.
    """
    if not kb_docs:
        return [], "stale-contradiction pass: lse-kb returned zero docs (empty index or ES unreachable this run) — nothing to check. Null result (PH3-2)."

    docs_by_id = {d["_id"]: d for d in kb_docs if d.get("_id")}

    reverify_proposals, reverify_note = build_reverify_proposals(kb_docs)
    narrative_lines = [reverify_note]

    demote_proposals = []
    demoted_doc_ids = set()  # one demote per doc_id per run -- see note below
    sessions_with_candidates = 0
    for row in sessions:
        session_id = row["session_id"]
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

    return reverify_proposals + demote_proposals, "\n".join(narrative_lines)


def run_pass_error_cluster(cfg: DreamConfig, sessions, episodes_by_session, kb_docs, error_docs) -> tuple:
    """Prompt 2.4 — group lse-errors docs + episode error/timeout occurrences
    by embedding similarity; clusters with >=ERROR_CLUSTER_MIN_OCCURRENCES
    episode occurrences spanning >=ERROR_CLUSTER_MIN_SESSIONS sessions get a
    drafted "skill-candidate" proposal. A matching lse-errors doc supplies
    prior-art context (its resolution text, if any) but never counts toward
    the occurrence/session bar itself — see collect_lse_errors_items.
    """
    episode_items = collect_episode_error_occurrences(sessions, episodes_by_session)
    error_doc_items = collect_lse_errors_items(error_docs)
    all_items = episode_items + error_doc_items
    if not all_items:
        return [], (
            "error-cluster pass: no episode error/timeout occurrences and no "
            "lse-errors docs to cluster this run. Null result (PH3-2)."
        )

    items_by_key = {item["key"]: item for item in all_items}
    embeddings = embed_items(cfg, all_items)
    if not embeddings:
        return [], (
            f"error-cluster pass: embedding failed for all {len(all_items)} "
            f"item(s) (Ollama unreachable at {cfg.ollama_url}?)."
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
    if qualifying == 0:
        narrative_lines.append(
            "Null result (PH3-2): no error/timeout pattern repeated enough "
            "this run to clear the occurrence/session bar for a skill-candidate."
        )
    return proposals, "\n".join(narrative_lines)


PASS_FUNCS = {
    "dedup": run_pass_dedup,
    "stale-contradiction": run_pass_stale_contradiction,
    "error-cluster": run_pass_error_cluster,
}


# --- output: report.md + proposals.jsonl ------------------------------------

def write_report(cfg: DreamConfig, sessions, proposals: list[dict], narrative: str) -> tuple[str, str]:
    today = date.today().isoformat()
    out_dir = os.path.join(cfg.dream_dir, today)
    report_path = os.path.join(out_dir, "report.md")
    proposals_path = os.path.join(out_dir, "proposals.jsonl")

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
    report_text = "\n".join(lines)

    if cfg.dry_run:
        print(f"[dream_runner] [dry-run] would write:\n  {report_path}\n  {proposals_path}",
              file=sys.stderr)
        print(report_text)
        return report_path, proposals_path

    os.makedirs(out_dir, exist_ok=True)
    with open(report_path, "wt", encoding="utf-8") as f:
        f.write(report_text)
    with open(proposals_path, "wt", encoding="utf-8") as f:
        for p in proposals:
            f.write(json.dumps(p) + "\n")
    return report_path, proposals_path


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
    ap.add_argument("--runner-session-prefix", default=_dream_runner_prefix_default(),
                    help="exclude sessions whose session_id starts with this (no "
                    "dream-of-dreams, DESIGN.md §2 invariant 3(e)); default: unset/none")

    dedup_group = ap.add_argument_group("dedup pass (Prompt 2.2)")
    dedup_group.add_argument("--ollama-url", default=_ollama_url_default(),
                    help="Ollama base URL for nomic-embed-text (default: $GOETHE_OLLAMA_URL "
                    "or http://127.0.0.1:11434 — same valve as goethe.py's OLLAMA_URL)")
    dedup_group.add_argument("--embed-model", default=_embed_model_default(),
                    help="Ollama embedding model (default: nomic-embed-text, 768-dim)")
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

    ap.add_argument("-v", "--verbose", action="store_true")
    return ap.parse_args(argv)


KB_SOURCE_FIELDS = [
    "title", "content", "doc_id", "topic", "tags", "quality_score",
    "source_tier", "source_url", "source_path", "volatility", "stale",
    "refinement_count", "consecutive_failures", "success_count",
    "created_at", "updated_at", "verified_against", "version",
]  # deliberately excludes "embedding" (768 floats/doc) — dedup re-embeds
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


def main(argv=None) -> None:
    args = parse_args(argv)
    cfg = build_config(args)

    if args.sample_labels:
        _run_sample_labels(cfg)
        return

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
            error_docs = search_index(cfg, "lse-errors", {"query": {"match_all": {}}, "size": 500,
                                                            "_source": ERROR_SOURCE_FIELDS})
    except Exception as exc:
        print(f"[dream_runner] WARNING: ES read failed ({exc}) — proceeding with empty index view",
              file=sys.stderr)

    pass_func = PASS_FUNCS[cfg.pass_name]
    raw_proposals, narrative = pass_func(cfg, sessions, episodes_by_session, kb_docs, error_docs)

    proposals = []
    for p in raw_proposals:
        err = validate_proposal_shape(p)
        if err:
            print(f"[dream_runner] WARNING: dropping malformed proposal ({err}): {p!r}",
                  file=sys.stderr)
            continue
        proposals.append(p)

    report_path, proposals_path = write_report(cfg, sessions, proposals, narrative)
    print(f"[dream_runner] {mode}done. report={report_path} proposals={proposals_path} "
          f"n_proposals={len(proposals)}", file=sys.stderr)


if __name__ == "__main__":
    main()
