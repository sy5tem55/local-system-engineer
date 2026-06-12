#!/usr/bin/env python3
"""Create the lse-skills ES index (Cogitator v1.7.0 skills layer).

Schema: docs/lse-1.7.0-design.md §3.2 + pinned/archived/evidence_log
(adopted from the Hermes curator analysis, docs/hermes-skill-learning-analysis.md).

Run on LUCIFER (ES localhost:9200):  python3 rag/06-skills-index-setup.py
Idempotent — exits cleanly if the index exists.
"""
import sys

from elasticsearch import Elasticsearch

ES_URL = "http://localhost:9200"
INDEX = "lse-skills"

MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "skill_id":      {"type": "keyword"},
            "occupation":    {"type": "keyword"},
            "task":          {"type": "text"},
            "preconditions": {"type": "text"},
            "procedure":     {"type": "text"},
            "verification":  {"type": "text"},
            "failure_modes": {"type": "text"},
            "provenance":    {"type": "keyword"},
            "embedding":     {"type": "dense_vector", "dims": 768,
                              "index": True, "similarity": "cosine"},
            "quality":       {"type": "float"},
            "stats": {
                "properties": {
                    "uses":              {"type": "integer"},
                    "episode_successes": {"type": "integer"},
                    "episode_failures":  {"type": "integer"},
                    "last_used":         {"type": "date"},
                }
            },
            "evidence_log": {
                "type": "object", "enabled": True,
            },
            "pinned":     {"type": "boolean"},
            "archived":   {"type": "boolean"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "version":    {"type": "integer"},
        }
    },
}


def main() -> int:
    es = Elasticsearch(ES_URL, request_timeout=10)
    if es.indices.exists(index=INDEX):
        count = es.count(index=INDEX)["count"]
        print(f"{INDEX} already exists ({count} docs) — nothing to do.")
        return 0
    es.indices.create(index=INDEX, body=MAPPING)
    print(f"{INDEX} created.")
    print("Verify:  curl -s localhost:9200/lse-skills/_count")
    return 0


if __name__ == "__main__":
    sys.exit(main())
