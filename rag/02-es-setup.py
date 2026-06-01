#!/usr/bin/env python3
"""
LSE RAG Stack — Step 2: Elasticsearch index creation
Run after Elasticsearch container is up via Portainer.

Usage:
    python3 02-es-setup.py [--es-url http://localhost:9200]
"""
import argparse
import sys
import json
from datetime import datetime

try:
    from elasticsearch import Elasticsearch
except ImportError:
    print("Installing elasticsearch-py...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "elasticsearch", "--break-system-packages"], check=True)
    from elasticsearch import Elasticsearch

# ── Config ────────────────────────────────────────────────────────────────────
INDICES = {
    "lse-kb": {
        "description": "Curated LSE knowledge base — seeded from /opt/local-se/kb/, refined over time",
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "technical": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "doc_id":       {"type": "keyword"},
                "title":        {"type": "text", "analyzer": "technical"},
                "content":      {"type": "text", "analyzer": "technical"},
                "source_path":  {"type": "keyword"},
                "source_url":   {"type": "keyword"},
                "topic":        {"type": "keyword"},
                "tags":         {"type": "keyword"},
                "quality_score":{"type": "float"},    # 0.0 (rough) → 1.0 (verified)
                "refinement_count": {"type": "integer"},
                "embedding":    {
                    "type": "dense_vector",
                    "dims": 768,
                    "index": True,
                    "similarity": "cosine"
                },
                "created_at":   {"type": "date"},
                "updated_at":   {"type": "date"},
                "version":      {"type": "integer"}
            }
        }
    },
    "lse-search-cache": {
        "description": "Recent web search results — auto-indexed, TTL-expired",
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        },
        "mappings": {
            "properties": {
                "query":        {"type": "text"},
                "url":          {"type": "keyword"},
                "title":        {"type": "text"},
                "content":      {"type": "text"},
                "engine":       {"type": "keyword"},  # searxng, playwright, etc.
                "embedding":    {
                    "type": "dense_vector",
                    "dims": 768,
                    "index": True,
                    "similarity": "cosine"
                },
                "quality_score":{"type": "float"},
                "cached_at":    {"type": "date"},
                "expires_at":   {"type": "date"}      # set to 7 days from cached_at
            }
        }
    },
    "lse-errors": {
        "description": "Error patterns — never repeat the same mistake twice",
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        },
        "mappings": {
            "properties": {
                "error_hash":   {"type": "keyword"},   # sha256 of normalised error
                "error_text":   {"type": "text"},
                "context":      {"type": "text"},      # what the model was trying to do
                "resolution":   {"type": "text"},      # what fixed it
                "embedding":    {
                    "type": "dense_vector",
                    "dims": 768,
                    "index": True,
                    "similarity": "cosine"
                },
                "occurrence_count": {"type": "integer"},
                "first_seen":   {"type": "date"},
                "last_seen":    {"type": "date"}
            }
        }
    }
}


def create_indices(es: Elasticsearch) -> None:
    for index_name, config in INDICES.items():
        if es.indices.exists(index=index_name):
            print(f"  ⚠️  Index '{index_name}' already exists — skipping")
            continue
        body = {
            "settings": config["settings"],
            "mappings": config["mappings"]
        }
        es.indices.create(index=index_name, body=body)
        print(f"  ✅ Created index '{index_name}' — {config['description']}")


def verify_cluster(es: Elasticsearch) -> bool:
    try:
        info = es.info()
        health = es.cluster.health()
        print(f"  Elasticsearch {info['version']['number']} — cluster '{info['cluster_name']}'")
        print(f"  Cluster health: {health['status']}")
        return health['status'] in ('green', 'yellow')
    except Exception as e:
        print(f"  ❌ Cannot reach Elasticsearch: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="LSE RAG — Elasticsearch index setup")
    parser.add_argument("--es-url", default="http://localhost:9200", help="Elasticsearch URL")
    args = parser.parse_args()

    print(f"=== LSE RAG: Elasticsearch index setup ===")
    print(f"Connecting to {args.es_url}...")

    es = Elasticsearch(args.es_url, request_timeout=10)

    if not verify_cluster(es):
        print("\n❌ Elasticsearch not reachable. Deploy the container via Portainer first.")
        print("   Recommended image: elasticsearch:8.17.0")
        print("   Env: discovery.type=single-node, xpack.security.enabled=false")
        print("   Port: 9200:9200")
        sys.exit(1)

    print("\nCreating indices...")
    create_indices(es)

    print(f"\n=== Done. {len(INDICES)} indices ready ===")
    print("\nNext step: run 03-kb-seed.py to index /opt/local-se/kb/ documents")


if __name__ == "__main__":
    main()
