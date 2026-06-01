"""
LSE RAG Stack — Step 4: New tool functions for the LSE OpenWebUI tool.

Add these functions to tools/openwebui-tool-v1.5.8.py (or the next version).
They slot in alongside the existing execute_command / write_file / read_file functions.

Dependencies (add to requirements at top of tool file):
    pip install elasticsearch requests --break-system-packages
"""

# ─────────────────────────────────────────────────────────────────────────────
# PASTE THESE INTO THE LSE TOOL CLASS
# ─────────────────────────────────────────────────────────────────────────────

import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

# Config — adjust if ports differ
_ES_URL      = "http://localhost:9200"
_OLLAMA_URL  = "http://127.0.0.1:11434"
_EMBED_MODEL = "nomic-embed-text"
_KB_INDEX    = "lse-kb"
_CACHE_INDEX = "lse-search-cache"
_ERR_INDEX   = "lse-errors"


def _embed(text: str) -> list:
    """Get embedding vector from Ollama nomic-embed-text (CPU, no GPU pressure)."""
    import requests
    r = requests.post(
        f"{_OLLAMA_URL}/api/embed",
        json={"model": _EMBED_MODEL, "input": "search_query: " + text[:5000]},
        timeout=15
    )
    r.raise_for_status()
    return r.json()["embeddings"][0]


def _es() -> object:
    """Lazy ES client."""
    from elasticsearch import Elasticsearch
    return Elasticsearch(_ES_URL, request_timeout=10)


def search_kb(
    query: str,
    min_score: float = 0.72,
    max_results: int = 5,
    topic_filter: Optional[str] = None
) -> dict:
    """
    Search the LSE knowledge base using semantic (vector) + keyword (BM25) hybrid search.

    Checks the curated KB first. If no results meet min_score, automatically
    falls through to web_search_enhanced() and indexes good results back.

    Args:
        query:        Natural language search query.
        min_score:    Minimum cosine similarity threshold (0–1). Default 0.72.
        max_results:  Maximum number of KB results to return. Default 5.
        topic_filter: Optionally restrict to a topic tag (e.g. 'comfyui', 'wan2.1').

    Returns:
        dict with 'source' ('kb' or 'web'), 'results' list, and 'refined' bool.
    """
    try:
        embedding = _embed(query)
        es = _es()

        knn = {
            "field": "embedding",
            "query_vector": embedding,
            "k": max_results,
            "num_candidates": 50,
            "boost": 0.7
        }

        bm25 = {
            "multi_match": {
                "query": query,
                "fields": ["title^2", "content"],
                "boost": 0.3
            }
        }

        # Optional topic filter
        filter_clause = []
        if topic_filter:
            filter_clause = [{"term": {"topic": topic_filter}}]

        body = {
            "knn": knn,
            "query": {
                "bool": {
                    "must": [bm25],
                    "filter": filter_clause
                }
            },
            "_source": ["doc_id", "title", "content", "source_path", "source_url",
                        "topic", "quality_score", "updated_at"],
            "size": max_results
        }

        resp = es.search(index=_KB_INDEX, body=body)
        hits = resp["hits"]["hits"]

        # Filter by min_score
        good_hits = [h for h in hits if h.get("_score", 0) >= min_score]

        if good_hits:
            results = [{
                "title":         h["_source"]["title"],
                "content":       h["_source"]["content"],
                "source":        h["_source"].get("source_path") or h["_source"].get("source_url", ""),
                "topic":         h["_source"]["topic"],
                "quality_score": h["_source"]["quality_score"],
                "score":         round(h["_score"], 4),
                "updated_at":    h["_source"]["updated_at"]
            } for h in good_hits]

            return {
                "source": "kb",
                "hit_count": len(results),
                "results": results,
                "refined": False,
                "message": f"Found {len(results)} KB result(s) — quality scores: " +
                           ", ".join(f"{r['quality_score']:.2f}" for r in results)
            }

        # KB miss — fall through to web search and auto-index
        return {
            "source": "kb_miss",
            "hit_count": 0,
            "results": [],
            "refined": False,
            "message": f"No KB results above threshold {min_score} for '{query}'. "
                       "Use web_search_enhanced() to search the web and auto-index results."
        }

    except Exception as e:
        return {"error": str(e), "source": "kb_error", "results": []}


def index_to_kb(
    content: str,
    title: str,
    topic: str,
    source_url: str = "",
    quality_score: float = 0.8,
    tags: list = None
) -> dict:
    """
    Index a document into the LSE knowledge base.

    Call this after finding high-quality information from a web search.
    If a similar document already exists (cosine > 0.92), it updates the existing
    entry and increments quality_score rather than creating a duplicate.

    Args:
        content:       Full text of the document.
        title:         Human-readable title.
        topic:         Topic tag (e.g. 'comfyui', 'wan2.1', 'llama-cpp').
        source_url:    URL where this was found (empty string if from local file).
        quality_score: 0.0–1.0. Web-sourced fresh content → 0.8. Verified → 1.0.
        tags:          Additional tags list.

    Returns:
        dict with 'action' ('created' or 'updated') and 'doc_id'.
    """
    try:
        embedding = _embed(content)
        es = _es()
        now = datetime.now(timezone.utc).isoformat()
        doc_hash = hashlib.sha256(content[:500].encode()).hexdigest()[:16]

        # Check for near-duplicate
        dup_resp = es.search(index=_KB_INDEX, body={
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": 1,
                "num_candidates": 10
            },
            "_source": ["doc_id", "quality_score", "refinement_count", "version"],
            "size": 1
        })

        dup_hits = dup_resp["hits"]["hits"]
        if dup_hits and dup_hits[0]["_score"] >= 0.92:
            # Update existing doc — refine it
            existing = dup_hits[0]
            new_quality = min(1.0, max(existing["_source"]["quality_score"], quality_score))
            es.update(index=_KB_INDEX, id=existing["_id"], body={
                "doc": {
                    "content":          content,
                    "embedding":        embedding,
                    "quality_score":    new_quality,
                    "refinement_count": existing["_source"]["refinement_count"] + 1,
                    "updated_at":       now,
                    "version":          existing["_source"]["version"] + 1,
                    "source_url":       source_url or None,
                    "tags":             list(set((tags or []) + ["refined"]))
                }
            })
            return {
                "action": "updated",
                "doc_id": existing["_id"],
                "new_quality_score": new_quality,
                "message": f"Refined existing doc (quality {existing['_source']['quality_score']:.2f} → {new_quality:.2f})"
            }

        # New document — create it
        doc = {
            "doc_id":           doc_hash,
            "title":            title,
            "content":          content,
            "source_path":      None,
            "source_url":       source_url or None,
            "topic":            topic,
            "tags":             list(set((tags or []) + [topic])),
            "quality_score":    quality_score,
            "refinement_count": 0,
            "embedding":        embedding,
            "created_at":       now,
            "updated_at":       now,
            "version":          1
        }
        es.index(index=_KB_INDEX, id=doc_hash, document=doc)
        return {
            "action": "created",
            "doc_id": doc_hash,
            "quality_score": quality_score,
            "message": f"New KB entry created — topic: {topic}, quality: {quality_score:.2f}"
        }

    except Exception as e:
        return {"error": str(e)}


def record_error(error_text: str, context: str, resolution: str) -> dict:
    """
    Record an error and its resolution to the LSE error KB.
    The model calls this after recovering from a mistake so it is never repeated.

    Args:
        error_text:  The exact error message or description.
        context:     What the model was trying to do when the error occurred.
        resolution:  What fixed it.

    Returns:
        dict with 'action' ('created' or 'updated') and occurrence count.
    """
    try:
        embedding = _embed(error_text + " " + context)
        es = _es()
        now = datetime.now(timezone.utc).isoformat()

        # Normalise error for deduplication
        normalised = re.sub(r'\s+', ' ', error_text.lower().strip())
        error_hash = hashlib.sha256(normalised.encode()).hexdigest()[:16]

        # Check for similar existing error
        dup_resp = es.search(index=_ERR_INDEX, body={
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": 1,
                "num_candidates": 10
            },
            "_source": ["error_hash", "occurrence_count", "resolution"],
            "size": 1
        })

        dup_hits = dup_resp["hits"]["hits"]
        if dup_hits and dup_hits[0]["_score"] >= 0.90:
            existing = dup_hits[0]
            new_count = existing["_source"]["occurrence_count"] + 1
            es.update(index=_ERR_INDEX, id=existing["_id"], body={
                "doc": {
                    "last_seen":        now,
                    "occurrence_count": new_count,
                    "resolution":       resolution  # update with latest fix
                }
            })
            return {
                "action": "updated",
                "occurrence_count": new_count,
                "message": f"Known error — seen {new_count} time(s). Resolution updated."
            }

        # New error
        doc = {
            "error_hash":       error_hash,
            "error_text":       error_text,
            "context":          context,
            "resolution":       resolution,
            "embedding":        embedding,
            "occurrence_count": 1,
            "first_seen":       now,
            "last_seen":        now
        }
        es.index(index=_ERR_INDEX, id=error_hash, document=doc)
        return {
            "action": "created",
            "occurrence_count": 1,
            "message": "New error pattern recorded to KB."
        }

    except Exception as e:
        return {"error": str(e)}


def check_error_kb(error_text: str) -> dict:
    """
    Check if this error has been seen before and retrieve its known resolution.
    Call this BEFORE attempting any operation that might fail in a known way.

    Args:
        error_text: The error message or description to look up.

    Returns:
        dict with 'known' (bool), 'resolution' (str if known), 'occurrence_count'.
    """
    try:
        embedding = _embed(error_text)
        es = _es()

        resp = es.search(index=_ERR_INDEX, body={
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": 1,
                "num_candidates": 10
            },
            "_source": ["error_text", "resolution", "occurrence_count", "last_seen"],
            "size": 1
        })

        hits = resp["hits"]["hits"]
        if hits and hits[0]["_score"] >= 0.88:
            h = hits[0]["_source"]
            return {
                "known": True,
                "resolution": h["resolution"],
                "occurrence_count": h["occurrence_count"],
                "last_seen": h["last_seen"],
                "message": f"⚠️ Known error (seen {h['occurrence_count']}x). Apply known resolution."
            }
        return {
            "known": False,
            "message": "Error not seen before — proceed carefully and record resolution if fixed."
        }

    except Exception as e:
        return {"error": str(e), "known": False}


# ─────────────────────────────────────────────────────────────────────────────
# DOCSTRINGS FOR OPENWEBUI TOOL REGISTRATION
# These are the descriptions OpenWebUI uses to present tools to the model.
# Replace the function docstrings above with these if the tool framework
# uses a separate description field.
# ─────────────────────────────────────────────────────────────────────────────

TOOL_DESCRIPTIONS = {
    "search_kb": (
        "Search the LSE knowledge base using semantic + keyword hybrid search. "
        "Always call this BEFORE web_search or SearxNG. Returns curated KB results "
        "with quality scores. On a miss, instructs to fall through to web search."
    ),
    "index_to_kb": (
        "Index a document into the LSE knowledge base. Call after finding high-quality "
        "information from a web search. Automatically deduplicates — if a similar doc "
        "exists, it refines and improves it rather than duplicating."
    ),
    "record_error": (
        "Record an error and its resolution to the LSE error knowledge base. "
        "Call this after recovering from any mistake so the same error is never repeated."
    ),
    "check_error_kb": (
        "Check if an error has been seen before and retrieve its known resolution. "
        "Call this BEFORE attempting operations that might fail in known ways."
    )
}
