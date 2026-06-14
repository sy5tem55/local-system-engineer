"""
rag_tools_v2.py
---------------
Updated RAG tool functions for OpenWebUI / LSE.
Adds:  index_to_kb (v2)  —  authority-aware indexing
       mentor_correct     —  human / Opus mentor override
       record_outcome     —  increment empirical_runs or empirical_failures

Drop these into the OpenWebUI Tool Functions editor, replacing the v1 versions.
All three share the same ES client config; adjust ES_URL if needed.
"""

import json
from datetime import datetime, timezone
from typing import Optional

# ── shared config (edit these) ───────────────────────────────────────────────

ES_URL    = "http://localhost:9200"
KB_INDEX  = "lse-kb"          # alias always points to the live index

# ── authority ceiling map (must stay in sync with migrate_kb_index.py) ───────

_AUTHORITY_CEILINGS = {
    "official_vendor": 1.00,
    "mentor":          1.00,
    "empirical":       0.95,
    "community":       0.75,
    "inferred":        0.60,
}

# ── lazy ES client ────────────────────────────────────────────────────────────

_es = None

def _get_es():
    global _es
    if _es is None:
        try:
            from elasticsearch import Elasticsearch
            _es = Elasticsearch(ES_URL)
        except ImportError:
            raise RuntimeError("pip install elasticsearch --break-system-packages")
    return _es


# ── composite quality_score calculator ───────────────────────────────────────

def _compute_quality(
    raw_score:        float,
    source_authority: str,
    empirical_runs:   int,
    empirical_failures: int,
    mentor_verified:  bool,
    updated_at:       Optional[str],
) -> float:
    ceiling = _AUTHORITY_CEILINGS.get(source_authority, 0.60)

    # confirmation weight
    total = empirical_runs + empirical_failures
    if total == 0:
        conf_w = 1.0
    else:
        success_rate = empirical_runs / total
        confidence   = min(total / 10.0, 1.0)
        conf_w       = 0.5 + confidence * (success_rate - 0.5)

    # recency weight
    rec_w = 1.0
    if updated_at:
        try:
            ts       = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - ts).days
            rec_w    = max(0.70, 1.0 - (age_days / 365) * 0.15)
        except (ValueError, TypeError):
            pass

    # mentor bypass: skip degradation, just clamp to ceiling
    if mentor_verified:
        return min(ceiling, raw_score)

    return min(ceiling, raw_score * conf_w * rec_w)


# ── tool 1: index_to_kb (v2) ─────────────────────────────────────────────────

def index_to_kb(
    title:            str,
    content:          str,
    topic:            str,
    tags:             list[str]         = None,
    source_url:       str               = "",
    source_authority: str               = "",   # auto-classified if empty and source_url given
    quality_score:    float             = 0.7,
    empirical_runs:   int               = 0,
    empirical_failures: int             = 0,
    doc_id:           Optional[str]     = None,
) -> str:
    """
    Index a knowledge entry into the LSE KB with full authority metadata.

    Args:
        title:              Short descriptive title.
        content:            Full text to index (can be multi-paragraph).
        topic:              Broad topic keyword (e.g. 'PowerShell', 'Docker').
        tags:               Optional list of keyword tags for filtering.
        source_url:         URL of the source document (enables auto-classification).
        source_authority:   Override authority tier. If omitted, auto-classified from
                            source_url via OFFICIAL_DOCS_MAP. Falls back to 'inferred'.
                            Allowed: official_vendor | empirical | mentor | community | inferred
        quality_score:      Base score before composite formula is applied (0.0–1.0).
        empirical_runs:     Known successful executions confirming this entry.
        empirical_failures: Known executions that contradict this entry.
        doc_id:             Optional stable ID (enables upsert / idempotent indexing).

    Returns:
        JSON string with the indexed document's ID and computed quality_score.
    """
    # lazy import — only needed inside the function for OpenWebUI sandboxing
    from official_docs_map import classify_url

    now = datetime.now(timezone.utc).isoformat()

    # auto-classify authority from URL if caller didn't specify
    if not source_authority:
        classified_auth, _ = classify_url(source_url)
        source_authority = classified_auth

    source_authority = source_authority if source_authority in _AUTHORITY_CEILINGS else "inferred"
    authority_score  = _AUTHORITY_CEILINGS[source_authority]

    computed_quality = _compute_quality(
        raw_score          = quality_score,
        source_authority   = source_authority,
        empirical_runs     = empirical_runs,
        empirical_failures = empirical_failures,
        mentor_verified    = False,
        updated_at         = now,
    )

    doc = {
        "title":              title,
        "content":            content,
        "topic":              topic,
        "tags":               tags or [],
        "source_url":         source_url,
        "source_authority":   source_authority,
        "authority_score":    authority_score,
        "quality_score":      round(computed_quality, 4),
        "empirical_runs":     empirical_runs,
        "empirical_failures": empirical_failures,
        "mentor_verified":    False,
        "mentor_note":        "",
        "conflicting":        False,
        "created_at":         now,
        "updated_at":         now,
    }

    es   = _get_es()
    kwargs = {"index": KB_INDEX, "document": doc}
    if doc_id:
        kwargs["id"] = doc_id

    resp = es.index(**kwargs)
    es.indices.refresh(index=KB_INDEX)

    return json.dumps({
        "status":        "indexed",
        "doc_id":        resp["_id"],
        "quality_score": doc["quality_score"],
        "authority":     source_authority,
    })


# ── tool 2: record_outcome ────────────────────────────────────────────────────

def record_outcome(
    doc_id:  str,
    success: bool,
    note:    str = "",
) -> str:
    """
    Record a real-world execution result against a KB entry.

    Increments empirical_runs (success=True) or empirical_failures (success=False),
    then recomputes quality_score under the composite formula.

    Args:
        doc_id:  Elasticsearch document ID of the KB entry to update.
        success: True if the procedure described in the entry worked; False if it failed.
        note:    Optional free-text context (e.g. error message on failure).

    Returns:
        JSON string with updated quality_score and run counts.
    """
    es  = _get_es()
    now = datetime.now(timezone.utc).isoformat()

    # fetch current doc
    try:
        hit = es.get(index=KB_INDEX, id=doc_id)
    except Exception as exc:
        return json.dumps({"error": f"Doc {doc_id} not found: {exc}"})

    src = hit["_source"]
    runs     = src.get("empirical_runs", 0)
    failures = src.get("empirical_failures", 0)

    if success:
        runs += 1
    else:
        failures += 1

    new_quality = _compute_quality(
        raw_score          = src.get("quality_score", 0.7),
        source_authority   = src.get("source_authority", "inferred"),
        empirical_runs     = runs,
        empirical_failures = failures,
        mentor_verified    = src.get("mentor_verified", False),
        updated_at         = now,
    )

    update_body = {
        "doc": {
            "empirical_runs":     runs,
            "empirical_failures": failures,
            "quality_score":      round(new_quality, 4),
            "updated_at":         now,
        }
    }
    if note:
        # append note to mentor_note field as a running log
        existing_note = src.get("mentor_note", "")
        tag = "[success]" if success else "[failure]"
        update_body["doc"]["mentor_note"] = (
            f"{existing_note}\n{now} {tag}: {note}".strip()
        )

    es.update(index=KB_INDEX, id=doc_id, body=update_body)
    es.indices.refresh(index=KB_INDEX)

    return json.dumps({
        "doc_id":             doc_id,
        "success":            success,
        "empirical_runs":     runs,
        "empirical_failures": failures,
        "quality_score":      round(new_quality, 4),
    })


# ── tool 3: mentor_correct ────────────────────────────────────────────────────

def mentor_correct(
    doc_id:         str,
    correction:     str,
    authority:      str   = "human",        # 'human' | 'opus-4' | 'opus-4-5'
    new_score:      Optional[float] = None, # explicit override, else auto-ceiling
    mark_correct:   bool  = True,           # True = doc is now authoritative; False = flag as wrong
    flag_conflict:  bool  = False,          # True = other docs on same topic may conflict
) -> str:
    """
    Apply a mentor correction to a KB entry.

    This is the highest-authority write operation. It:
      - Sets source_authority = 'mentor'
      - Sets mentor_verified  = True  (if mark_correct=True)
      - Records correction text in mentor_note
      - Recomputes quality_score (ceiling 1.0, bypasses degradation)
      - Optionally flags conflicting=True on this entry

    If mark_correct=False (the mentor is saying "this entry is WRONG"):
      - Sets quality_score to 0.1 (effectively deprecated)
      - Sets conflicting = True
      - Does NOT set mentor_verified = True

    Args:
        doc_id:        ES document ID of the entry being corrected.
        correction:    The mentor's note / correction text.
        authority:     Who is correcting: 'human' | 'opus-4' | 'opus-4-5' etc.
        new_score:     Explicit quality_score override (0.0–1.0). If omitted,
                       mark_correct=True sets 0.95, mark_correct=False sets 0.10.
        mark_correct:  True = entry is now endorsed; False = entry is deprecated.
        flag_conflict: True = set conflicting=True as a signal to the retrieval layer.

    Returns:
        JSON string confirming the update.
    """
    es  = _get_es()
    now = datetime.now(timezone.utc).isoformat()

    try:
        hit = es.get(index=KB_INDEX, id=doc_id)
    except Exception as exc:
        return json.dumps({"error": f"Doc {doc_id} not found: {exc}"})

    src = hit["_source"]

    if mark_correct:
        quality      = new_score if new_score is not None else 0.95
        verified     = True
        conflicting  = flag_conflict
    else:
        quality      = new_score if new_score is not None else 0.10
        verified     = False
        conflicting  = True   # a mentor saying "wrong" always flags conflict

    # append mentor note with attribution
    existing = src.get("mentor_note", "")
    tag      = f"[{authority}] {'✓ CORRECT' if mark_correct else '✗ INCORRECT'}"
    new_note = f"{existing}\n{now} {tag}: {correction}".strip()

    update_body = {
        "doc": {
            "source_authority": "mentor",
            "authority_score":  1.00,
            "quality_score":    round(quality, 4),
            "mentor_verified":  verified,
            "mentor_note":      new_note,
            "conflicting":      conflicting,
            "updated_at":       now,
        }
    }

    es.update(index=KB_INDEX, id=doc_id, body=update_body)
    es.indices.refresh(index=KB_INDEX)

    return json.dumps({
        "doc_id":         doc_id,
        "mentor":         authority,
        "mark_correct":   mark_correct,
        "quality_score":  round(quality, 4),
        "mentor_verified":verified,
        "conflicting":    conflicting,
        "note_preview":   new_note[:200],
    })


# ── tool 4: search_kb (hybrid BM25 + kNN via RRF) — trajectory S2.3 ───────────
#
# SHIP GATE: this is the REFERENCE implementation, staged here for porting into
# the Cogitator tool. Do NOT replace the deployed search_kb until
# `python3 rag/eval_retrieval.py --compare` shows rrf beats `linear` on the gold
# set (recall@3 then MRR). If linear wins or ties, keep linear and record the
# result (S2.3 is explicitly "ship only if metrics improve").
#
# WHY RRF over the current linear combination: the deployed search_kb sums a
# kNN score (boost 0.7) and a BM25 score (boost 0.3) in one query and thresholds
# the SUM at 0.72. BM25 scores are unbounded, so that threshold has no stable
# meaning (S2.4). RRF fuses RANK positions, not raw scores, so it is immune to
# the score-scale mismatch; and the miss decision is moved onto the raw kNN
# COSINE (bounded 0..1), where a floor IS meaningful.

OLLAMA_URL  = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
RRF_K       = 60
COSINE_FLOOR_DEFAULT = 0.60   # semantic relevance gate (replaces the 0.72-on-sum)


def _embed_query(text: str) -> list:
    """768-dim nomic-embed-text query embedding (matches Cogitator._embed)."""
    import requests
    r = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": "search_query: " + text[:5000]},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["embeddings"][0]


def _rrf_fuse_ids(list_a: list, list_b: list, k: int = RRF_K) -> list:
    """Reciprocal Rank Fusion of two ranked id lists -> fused ids (desc score)."""
    score, order = {}, []
    for lst in (list_a, list_b):
        for rank, _id in enumerate(lst, 1):
            if _id not in score:
                score[_id] = 0.0
                order.append(_id)
            score[_id] += 1.0 / (k + rank)
    return sorted(order, key=lambda i: (-score[i], order.index(i)))


def search_kb(
    query: str,
    cosine_floor: float = COSINE_FLOOR_DEFAULT,
    max_results: int = 5,
    topic_filter: str = "",
) -> str:
    """
    Search the LSE knowledge base — hybrid BM25 + kNN fused with RRF.

    Ranking: the semantic (kNN cosine) and lexical (BM25 multi_match) result
    lists are fused with Reciprocal Rank Fusion, so a doc that ranks well on
    EITHER signal surfaces, and neither score scale dominates the other.

    Miss decision: a result set is a "KB miss" only if the best kNN COSINE is
    below `cosine_floor` (default 0.60) — i.e. nothing is semantically close.
    This replaces the old min_score=0.72 applied to an unbounded summed score.

    Args:
        query:        Natural-language search query.
        cosine_floor: Semantic relevance gate on raw kNN cosine (0–1). Default 0.60.
        max_results:  Max fused results to return. Default 5.
        topic_filter: Optional topic tag (e.g. 'pfsense', 'searxng', 'llama-cpp').
    """
    pool = max(max_results * 3, 10)  # fuse over a slightly wider pool
    flt = [{"term": {"topic": topic_filter}}] if topic_filter else []
    src = ["title", "content", "source_path", "source_url", "topic",
           "quality_score", "updated_at"]
    es = _get_es()

    vec = _embed_query(query)
    knn_body = {
        "knn": {"field": "embedding", "query_vector": vec, "k": pool,
                "num_candidates": 50, "filter": flt or None},
        "_source": src, "size": pool,
    }
    if not flt:
        knn_body["knn"].pop("filter")
    bm_body = {
        "query": {"bool": {"must": [{"multi_match": {"query": query,
                  "fields": ["title^2", "content"]}}], "filter": flt}},
        "_source": src, "size": pool,
    }

    knn_resp = es.search(index=KB_INDEX, body=knn_body)
    bm_resp = es.search(index=KB_INDEX, body=bm_body)

    knn_hits = knn_resp["hits"]["hits"]
    by_id = {h["_id"]: h for h in knn_hits}
    for h in bm_resp["hits"]["hits"]:
        by_id.setdefault(h["_id"], h)

    # semantic floor on the best RAW kNN cosine (kNN-only query => _score is cosine)
    best_cosine = max((h.get("_score", 0.0) for h in knn_hits), default=0.0)
    if best_cosine < cosine_floor:
        return (
            f"KB miss — nothing semantically close (best cosine {best_cosine:.2f} "
            f"< floor {cosine_floor}) for '{query}'.\n"
            "Fall through to search_web(), then index_to_kb() with quality results."
        )

    fused_ids = _rrf_fuse_ids([h["_id"] for h in knn_hits],
                              [h["_id"] for h in bm_resp["hits"]["hits"]])[:max_results]

    lines = [f"KB results for '{query}' ({len(fused_ids)} found, hybrid RRF):\n"]
    for i, _id in enumerate(fused_ids, 1):
        s = by_id[_id]["_source"]
        srcp = s.get("source_path") or s.get("source_url") or "unknown"
        q = s.get("quality_score", "?")
        title = s.get("title", "untitled")
        snippet = (s.get("content", "") or "")[:280].replace("\n", " ")
        lines.append(f"{i}. {title}  [quality {q}]  ({srcp})\n   {snippet}")
    return "\n".join(lines)
