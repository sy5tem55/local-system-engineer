#!/usr/bin/env python3
"""
LSE RAG Stack — Step 3: Seed Elasticsearch with /opt/local-se/kb/ documents.

Each document starts with quality_score=0.5 (rough — known to need refinement).
As web searches find better information on the same topic, quality_score rises
toward 1.0. The goal is iterative refinement, not a static dump.

Usage:
    python3 03-kb-seed.py [--kb-dir /opt/local-se/kb] [--es-url http://localhost:9200]
    python3 03-kb-seed.py --reindex   # re-embed and update existing docs
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from elasticsearch import Elasticsearch, helpers
    import requests
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "elasticsearch", "requests", "--break-system-packages"], check=True)
    from elasticsearch import Elasticsearch, helpers
    import requests

# ── Config ────────────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://127.0.0.1:11434"
EMBED_MODEL  = "nomic-embed-text"
EMBED_PREFIX = "search_document: "   # nomic-embed-text uses task prefixes
ES_INDEX     = "lse-kb"
CHUNK_SIZE   = 3000    # chars — nomic handles 8192 tokens ≈ ~6000 chars, stay safe
CHUNK_OVERLAP= 300
INITIAL_QUALITY = 0.5  # rough starting quality

TOPIC_MAP = {
    # filename keywords → topic tag (ordered: more specific first)
    "wan2.1":       "wan2.1",
    "wan":          "wan2.1",
    "comfyui":      "comfyui",
    "a1111":        "stable-diffusion",
    "image-gen":    "stable-diffusion",
    "image_gen":    "stable-diffusion",
    "llama-cpp":    "llama-cpp",
    "llama":        "llama-cpp",
    "searxng":      "searxng",
    "pfsense":      "pfsense",
    "launcher":     "lse-launcher",
    "port":         "infrastructure",
    "container":    "infrastructure",
    "session":      "lse-operations",
    "handover":     "lse-operations",
    "prompt":       "lse-prompt",
    "tool":         "lse-tool",
    "openwebui":    "openwebui",
    "eval":         "lse-eval",
    "readme":       "lse-general",
    "kb":           "lse-kb",
}

# Files known to be stubs/rough — flag for priority refinement
ROUGH_FILES = {
    "image-generation-tools.md",
    "llama-cpp-build.md",
    "launcher-script-location.md",
    "searxng-docker-port-fact.md",
    "port-and-container-audit.md",
}

def get_initial_quality(filepath: Path) -> float:
    """Assign starting quality: stubs get 0.3, known-good docs get 0.6."""
    if filepath.name in ROUGH_FILES:
        return 0.3   # priority for refinement
    if filepath.stat().st_size > 10000:
        return 0.6   # larger docs assumed more complete
    return 0.5       # standard rough starting point


def get_embedding(text: str) -> list[float]:
    """Get embedding from Ollama nomic-embed-text."""
    payload = {
        "model": EMBED_MODEL,
        "input": EMBED_PREFIX + text[:6000]   # stay within token budget
    }
    r = requests.post(f"{OLLAMA_URL}/api/embed", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["embeddings"][0]


def infer_topic(filepath: Path) -> str:
    name = filepath.stem.lower()
    for keyword, topic in TOPIC_MAP.items():
        if keyword in name:
            return topic
    return "general"


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, respecting paragraph boundaries where possible."""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # Try to break at a paragraph boundary
            para_break = text.rfind('\n\n', start, end)
            if para_break > start + chunk_size // 2:
                end = para_break
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c.strip()]


def doc_id(filepath: Path, chunk_idx: int) -> str:
    return hashlib.sha256(f"{filepath}:{chunk_idx}".encode()).hexdigest()[:16]


def index_file(filepath: Path, es: Elasticsearch, reindex: bool = False) -> int:
    """Embed and index a single KB file. Returns number of chunks indexed."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠️  Cannot read {filepath}: {e}")
        return 0

    if not text.strip():
        return 0

    # Extract title from first heading or filename
    title_match = re.match(r'^#{1,3}\s+(.+)$', text.strip(), re.MULTILINE)
    title = title_match.group(1) if title_match else filepath.stem.replace('-', ' ').replace('_', ' ')

    topic = infer_topic(filepath)
    chunks = chunk_text(text)
    now = datetime.now(timezone.utc).isoformat()
    indexed = 0

    for i, chunk in enumerate(chunks):
        _id = doc_id(filepath, i)

        # Skip if already indexed and not reindexing
        exists = es.exists(index=ES_INDEX, id=_id)
        if not reindex and exists:
            continue

        # DATA-4 (2026-07-18): a reseed must NOT reset earned trust. Snapshot
        # trust metadata from the existing doc and re-apply it below — quality,
        # outcome stats, staleness, volatility, tier, origin all survive.
        trust = {}
        if reindex and exists:
            try:
                _src = es.get(index=ES_INDEX, id=_id)["_source"]
                for fld in ("quality_score", "refinement_count", "success_count",
                            "failure_count", "failure_streak", "stale",
                            "demote_reason", "volatility", "source_tier",
                            "evidence", "verified_against", "origin",
                            "created_at", "version"):
                    if fld in _src and _src[fld] is not None:
                        trust[fld] = _src[fld]
            except Exception as e:
                print(f"  ⚠️  trust snapshot failed for {_id}: {e} — seeding fresh")

        try:
            embedding = get_embedding(chunk)
        except Exception as e:
            print(f"  ❌ Embedding failed for {filepath} chunk {i}: {e}")
            continue

        doc = {
            "doc_id":           _id,
            "title":            title if i == 0 else f"{title} (part {i+1})",
            "content":          chunk,
            "source_path":      str(filepath),
            "source_url":       None,
            "topic":            topic,
            "tags":             [topic, "kb-seed"],
            "quality_score":    get_initial_quality(filepath),
            "refinement_count": 0,
            "embedding":        embedding,
            "created_at":       now,
            "updated_at":       now,
            "version":          1
        }

        doc.update(trust)  # DATA-4: earned trust wins over seed defaults
        if trust.get("version"):
            doc["version"] = trust["version"] + 1
        es.index(index=ES_INDEX, id=_id, document=doc)
        indexed += 1

    return indexed


def main():
    parser = argparse.ArgumentParser(description="LSE RAG — KB seeder")
    parser.add_argument("--kb-dir",   default="/opt/local-se/kb", help="Path to KB directory")
    parser.add_argument("--es-url",   default="http://localhost:9200")
    parser.add_argument("--reindex",  action="store_true", help="Re-embed and overwrite existing docs")
    parser.add_argument("--dry-run",  action="store_true", help="List files without indexing")
    args = parser.parse_args()

    kb_path = Path(args.kb_dir)
    if not kb_path.exists():
        print(f"❌ KB directory not found: {kb_path}")
        sys.exit(1)

    print(f"=== LSE RAG: KB seeder ===")
    print(f"Source : {kb_path}")
    print(f"ES     : {args.es_url}/{ES_INDEX}")
    print(f"Embed  : {OLLAMA_URL} ({EMBED_MODEL})")
    print()

    # Verify Ollama
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        if not any(EMBED_MODEL in m for m in models):
            print(f"❌ Model '{EMBED_MODEL}' not found in Ollama. Run 01-ollama-setup.sh first.")
            sys.exit(1)
        print(f"✅ Ollama OK — {EMBED_MODEL} available")
    except Exception as e:
        print(f"❌ Cannot reach Ollama at {OLLAMA_URL}: {e}")
        sys.exit(1)

    # Collect files
    files = sorted([
        f for f in kb_path.rglob("*")
        if f.is_file() and f.suffix in ('.md', '.txt', '.py', '.yaml', '.yml', '.json', '.sh', '.ps1')
    ])

    print(f"Found {len(files)} files in {kb_path}:")
    for f in files:
        rel = f.relative_to(kb_path)
        size = f.stat().st_size
        print(f"  {str(rel):50s}  {size:>8,} bytes")

    if args.dry_run:
        print("\n[dry-run] No indexing performed.")
        return

    print()
    es = Elasticsearch(args.es_url, request_timeout=10)

    total_chunks = 0
    for f in files:
        rel = f.relative_to(kb_path)
        n = index_file(f, es, reindex=args.reindex)
        if n > 0:
            print(f"  ✅ {rel} → {n} chunk(s) indexed")
        else:
            print(f"  ─  {rel} → already indexed (use --reindex to update)")
        total_chunks += n

    print(f"\n=== Done. {total_chunks} chunks indexed into '{ES_INDEX}' ===")
    print(f"All documents start at quality_score={INITIAL_QUALITY} (rough).")
    print("They will be refined autonomously as the LSE searches and finds better sources.")
    print("\nNext step: run 04-lse-tool-patch.py to add search_kb / index_to_kb to the LSE tool")


if __name__ == "__main__":
    main()
