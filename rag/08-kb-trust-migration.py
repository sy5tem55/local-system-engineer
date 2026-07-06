#!/usr/bin/env python3
"""LSE RAG Stack — Step 8: KB trust-lifecycle field migration (KB-DECAY-5).

Adds the Goethe v0.3.0 trust fields to the lse-kb mapping:

    stale                 boolean  — quality floored at 0.2 → quarantined
                                     (NEVER silently deleted; kept for forensics)
    consecutive_failures  integer  — evidence-backed failure streak (KB-DECAY-1)
    volatility            keyword  — static | slow | fast (CHRONOS-3, mapped now
                                     so the CHRONOS phase needs no second migration)

Idempotent (same pattern as 02-es-setup.py): PUT mapping only adds missing
fields; existing fields and documents are untouched. Docs without the new
fields simply lack them — Goethe code treats absent as stale=False /
consecutive_failures=0 / volatility="slow".

Run on LUCIFER:  /home/sy5/owui/bin/python3 rag/08-kb-trust-migration.py
Options:         --es-url http://localhost:9200   --index lse-kb
"""
import argparse
import sys

from elasticsearch import Elasticsearch

TRUST_FIELDS = {
    "stale": {"type": "boolean"},
    "consecutive_failures": {"type": "integer"},
    "volatility": {"type": "keyword"},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--es-url", default="http://localhost:9200")
    ap.add_argument("--index", default="lse-kb")
    args = ap.parse_args()

    es = Elasticsearch(args.es_url, request_timeout=10)
    if not es.ping():
        print(f"ERROR: Elasticsearch not reachable at {args.es_url}")
        return 1
    if not es.indices.exists(index=args.index):
        print(f"ERROR: index '{args.index}' does not exist — run 02-es-setup.py first.")
        return 1

    current = es.indices.get_mapping(index=args.index)[args.index]["mappings"].get(
        "properties", {}
    )
    missing = {k: v for k, v in TRUST_FIELDS.items() if k not in current}
    if not missing:
        print(f"{args.index}: all trust fields already mapped — nothing to do.")
        return 0

    es.indices.put_mapping(index=args.index, properties=missing)
    print(f"{args.index}: added trust fields: {', '.join(sorted(missing))}")
    print(
        "Verify:  curl -s localhost:9200/"
        + args.index
        + "/_mapping | python3 -m json.tool | grep -A2 -E 'stale|consecutive|volatility'"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
