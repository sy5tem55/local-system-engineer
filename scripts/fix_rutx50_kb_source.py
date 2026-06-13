#!/usr/bin/env python3
"""
Fix the wrong source URL on the 'Teltonika RUTX50 SSH Access Guide' KB entry.
Run from WSL2: python3 /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/scripts/fix_rutx50_kb_source.py

The field is source_url (not source) in the lse-kb index.
The search_kb display showed https://www.teltonika-networks.com/products/rutx50
which is a fabricated URL — the actual source is live SSH session testing.
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
        "size": 3,
    },
)

hits = resp["hits"]["hits"]
if not hits:
    print("No document found matching title, trying content search...")
    resp = es.search(
        index=INDEX,
        body={"query": {"match": {"content": "RUTX50 SSH Access"}}, "size": 3},
    )
    hits = resp["hits"]["hits"]

if not hits:
    print("ERROR: document not found in lse-kb index")
    exit(1)

for hit in hits:
    doc_id = hit["_id"]
    src = hit["_source"]
    title = src.get("title", "(no title)")

    # Field is source_url in the ES document
    current_source_url = src.get("source_url") or "(none)"
    print(f"\nFound: id={doc_id}")
    print(f"  title:       {title}")
    print(f"  source_url:  {current_source_url}")
    print(f"  quality:     {src.get('quality_score', '?')}")
    print(f"  topic:       {src.get('topic', '?')}")
    print(f"  source_tier: {src.get('source_tier', '(none)')}")
    print(f"  all keys:    {sorted(src.keys())}")

    if title == "Teltonika RUTX50 SSH Access Guide":
        print(f"\n  -> Updating source_url to accurate value...")
        es.update(
            index=INDEX,
            id=doc_id,
            body={
                "doc": {
                    "source_url": "verified via live SSH sessions (LSE P24-P27); key in Vaultwarden 'Teltonika RUTX50 SSH'",
                    "verified_against": "live SSH test 2026-06-13 — platform=OpenWrt 21.02.0 confirmed",
                    "source_tier": "ground_truth",
                }
            },
        )
        print("  -> Done. source_url corrected, source_tier=ground_truth set.")

print("\nAll done.")
