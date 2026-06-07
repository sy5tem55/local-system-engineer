#!/usr/bin/env python3
"""
Fetches the pfSense REST API v2 OpenAPI spec and indexes it into lse-kb.
Run directly on LUCIFER WSL2 — do NOT run via LSE/OWUI.

Usage:
    PFSENSE_API_KEY=<key> python3 index_pfsense_api.py
"""

import os, json, hashlib, requests, sys
from datetime import datetime, timezone
from elasticsearch import Elasticsearch

PFSENSE_URL = "https://pfsense.home.arpa/api/v2/schema/openapi"
API_KEY     = os.environ.get("PFSENSE_API_KEY", "")
ES_URL      = "http://localhost:9200"
KB_INDEX    = "lse-kb"
EMBED_URL   = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"

if not API_KEY:
    sys.exit("Set PFSENSE_API_KEY env var first")

def embed(text: str) -> list:
    r = requests.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text[:8000]}, timeout=30)
    r.raise_for_status()
    return r.json()["embedding"]

def index_doc(es, title, content, topic, source_url, quality=0.9):
    content = content[:4000]
    vec = embed(content)
    doc_hash = hashlib.sha256(content[:500].encode()).hexdigest()[:16]
    now = datetime.now(timezone.utc).isoformat()
    # dedup check
    resp = es.search(index=KB_INDEX, body={
        "knn": {"field": "embedding", "query_vector": vec, "k": 1, "num_candidates": 10},
        "_source": ["quality_score"], "size": 1,
    })
    hits = resp["hits"]["hits"]
    if hits and hits[0]["_score"] >= 0.92:
        es.update(index=KB_INDEX, id=hits[0]["_id"], body={"doc": {
            "content": content, "embedding": vec,
            "quality_score": max(hits[0]["_source"]["quality_score"], quality),
            "updated_at": now,
        }})
        print(f"  UPDATED  {title[:60]}")
        return
    es.index(index=KB_INDEX, id=doc_hash, document={
        "doc_id": doc_hash, "title": title, "content": content,
        "source_url": source_url, "source_path": None,
        "topic": topic, "tags": [topic, "pfsense", "api"],
        "quality_score": quality, "refinement_count": 0,
        "embedding": vec, "created_at": now, "updated_at": now, "version": 1,
    })
    print(f"  INDEXED  {title[:60]}")

def main():
    print(f"Fetching {PFSENSE_URL} ...")
    r = requests.get(PFSENSE_URL,
        headers={"x-api-key": API_KEY, "Accept": "application/json"},
        verify=False, timeout=30)
    r.raise_for_status()
    spec = r.json()
    print(f"Got spec: {len(spec.get('paths', {}))} paths")

    es = Elasticsearch(ES_URL, request_timeout=10)
    paths = spec.get("paths", {})

    # Group by tag (pfSense groups endpoints by resource)
    from collections import defaultdict
    by_tag = defaultdict(list)
    for path, methods in paths.items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            tags = op.get("tags", ["general"])
            summary = op.get("summary", "")
            desc = op.get("description", "")
            params = op.get("parameters", [])
            param_str = ", ".join(p.get("name","") for p in params) if params else "none"
            chunk = (
                f"Endpoint: {method.upper()} {path}\n"
                f"Summary: {summary}\n"
                f"Description: {desc}\n"
                f"Parameters: {param_str}\n"
            )
            for tag in tags:
                by_tag[tag].append(chunk)

    # Index one doc per tag group
    base_url = "https://pfrest.org/api-docs/"
    for tag, chunks in sorted(by_tag.items()):
        content = f"pfSense REST API v2 — {tag} endpoints\n\n" + "\n---\n".join(chunks)
        topic = "pfsense"
        title = f"pfSense API v2: {tag}"
        index_doc(es, title, content, topic, base_url + tag)

    print(f"\nDone. Indexed {len(by_tag)} tag groups.")

if __name__ == "__main__":
    import urllib3; urllib3.disable_warnings()
    main()
