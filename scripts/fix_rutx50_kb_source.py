#!/usr/bin/env python3
"""
Fix the wrong source URL on the 'Teltonika RUTX50 SSH Access Guide' KB entry.
Run from WSL2: python3 scripts/fix_rutx50_kb_source.py
"""
import json
from elasticsearch import Elasticsearch

ES_URL = "http://localhost:9200"
INDEX = "lse-kb"

es = Elasticsearch(ES_URL)

# Find the document
resp = es.search(
    index=INDEX,
    body={
        "query": {"match": {"title": "Teltonika RUTX50 SSH Access Guide"}},
        "size": 5,
    },
)

hits = resp["hits"]["hits"]
if not hits:
    print("No document found matching 'Teltonika RUTX50 SSH Access Guide'")
    print("Trying broader search...")
    resp = es.search(
        index=INDEX,
        body={"query": {"match": {"content": "RUTX50 SSH Access"}}, "size": 5},
    )
    hits = resp["hits"]["hits"]

if not hits:
    print("ERROR: document not found in lse-kb index")
    exit(1)

for hit in hits:
    doc_id = hit["_id"]
    src = hit["_source"]
    current_source = src.get("source", "(none)")
    title = src.get("title", "(no title)")
    print(f"\nFound: id={doc_id}")
    print(f"  title:   {title}")
    print(f"  source:  {current_source}")
    print(f"  quality: {src.get('quality_score', '?')}")
    print(f"  topic:   {src.get('topic', '?')}")

    if "teltonika-networks.com" in current_source:
        print(f"\n  -> Fixing wrong source URL...")
        es.update(
            index=INDEX,
            id=doc_id,
            body={
                "doc": {
                    "source": "verified via live SSH sessions (LSE P24-P27); key in Vaultwarden 'Teltonika RUTX50 SSH'",
                    "verified_against": "live SSH test 2026-06-13 — platform=OpenWrt 21.02.0 confirmed",
                    "source_tier": "ground_truth",
                }
            },
        )
        print(f"  -> Updated source to: verified via live SSH sessions (LSE P24-P27)")
        print(f"  -> source_tier: ground_truth")
    else:
        print(f"  -> Source looks OK, no fix needed")

print("\nDone.")
