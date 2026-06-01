#!/usr/bin/env python3
"""
migrate_kb_index.py
-------------------
Migrates the lse-kb Elasticsearch index to the authority-aware schema.

New fields added:
  source_authority   keyword   'official_vendor' | 'empirical' | 'mentor' | 'community' | 'inferred'
  authority_score    float     ceiling weight for quality_score computation
  empirical_runs     integer   confirmed successful executions
  empirical_failures integer   executions that contradicted this entry
  mentor_verified    boolean   human or superior-model explicitly approved
  mentor_note        text      what the mentor said
  conflicting        boolean   two authoritative sources disagree on this topic

Strategy: create lse-kb-v2 with the new mapping, reindex all docs with
safe defaults for new fields, then atomically swap the alias.

Usage:
    python migrate_kb_index.py [--es-url http://localhost:9200] [--dry-run]
"""

import argparse
import json
import sys
from datetime import datetime, timezone

try:
    from elasticsearch import Elasticsearch, NotFoundError
    from elasticsearch.helpers import reindex, scan
except ImportError:
    sys.exit("pip install elasticsearch --break-system-packages")

# ── configuration ────────────────────────────────────────────────────────────

OLD_INDEX  = "lse-kb"
NEW_INDEX  = "lse-kb-v2"
ALIAS      = "lse-kb"          # alias will point to whichever index is live

# ── new mapping (full) ────────────────────────────────────────────────────────

NEW_MAPPING = {
    "mappings": {
        "properties": {
            # ── existing core fields ──────────────────────────────────────────
            "topic":           {"type": "keyword"},
            "title":           {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "content":         {"type": "text", "analyzer": "english"},
            "tags":            {"type": "keyword"},
            "quality_score":   {"type": "float"},
            "source_url":      {"type": "keyword"},
            "created_at":      {"type": "date"},
            "updated_at":      {"type": "date"},

            # ── new authority fields ──────────────────────────────────────────
            "source_authority": {
                "type": "keyword"
                # allowed values: official_vendor | empirical | mentor | community | inferred
            },
            "authority_score": {
                "type": "float"
                # ceiling: official_vendor=1.0, mentor=1.0, empirical=0.95,
                #          community=0.75,       inferred=0.60
            },
            "empirical_runs": {
                "type": "integer"
                # incremented by record_success() calls that reference this doc
            },
            "empirical_failures": {
                "type": "integer"
                # incremented by record_failure() calls
            },
            "mentor_verified": {
                "type": "boolean"
            },
            "mentor_note": {
                "type": "text"
                # free-text explanation from human or Opus mentor
            },
            "conflicting": {
                "type": "boolean"
                # true when a higher-authority source disagrees with this entry
            },
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,
        "refresh_interval":   "1s"
    }
}

# ── authority ceiling map ─────────────────────────────────────────────────────

AUTHORITY_CEILINGS = {
    "official_vendor": 1.00,
    "mentor":          1.00,
    "empirical":       0.95,
    "community":       0.75,
    "inferred":        0.60,
}

DEFAULT_AUTHORITY    = "inferred"
DEFAULT_AUTH_CEILING = AUTHORITY_CEILINGS[DEFAULT_AUTHORITY]

# ── helpers ───────────────────────────────────────────────────────────────────

def compute_quality_score(doc: dict) -> float:
    """
    Recompute quality_score as a composite using the authority ceiling.

    quality_score = min(authority_ceiling,
                        raw_score * confirmation_weight * recency_weight)

    confirmation_weight: rises with empirical_runs, collapses on failures.
    recency_weight:      decays linearly over 365 days from updated_at.
    """
    authority   = doc.get("source_authority", DEFAULT_AUTHORITY)
    ceiling     = AUTHORITY_CEILINGS.get(authority, DEFAULT_AUTH_CEILING)
    raw_score   = doc.get("quality_score", 0.5)

    runs     = doc.get("empirical_runs", 0)
    failures = doc.get("empirical_failures", 0)
    total    = runs + failures

    if total == 0:
        confirmation_weight = 1.0
    else:
        success_rate        = runs / total
        # shrink toward 0.5 when evidence is thin; approach success_rate as n grows
        confidence          = min(total / 10.0, 1.0)
        confirmation_weight = 0.5 + confidence * (success_rate - 0.5)

    # recency: full weight if updated within 365 days, down to 0.70 at 2 years
    recency_weight = 1.0
    updated_at_str = doc.get("updated_at")
    if updated_at_str:
        try:
            updated = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - updated).days
            recency_weight = max(0.70, 1.0 - (age_days / 365) * 0.15)
        except (ValueError, TypeError):
            pass

    # mentor override: skip ceiling reduction entirely
    if doc.get("mentor_verified", False):
        return min(ceiling, raw_score)

    return min(ceiling, raw_score * confirmation_weight * recency_weight)


def transform(hit: dict) -> dict:
    """Add new fields with safe defaults to an existing document."""
    src = hit["_source"].copy()
    src.setdefault("source_authority",  DEFAULT_AUTHORITY)
    src.setdefault("authority_score",   DEFAULT_AUTH_CEILING)
    src.setdefault("empirical_runs",    0)
    src.setdefault("empirical_failures",0)
    src.setdefault("mentor_verified",   False)
    src.setdefault("mentor_note",       "")
    src.setdefault("conflicting",       False)
    # recompute quality_score under new formula
    src["quality_score"] = compute_quality_score(src)
    return src


# ── main migration ────────────────────────────────────────────────────────────

def migrate(es_url: str, dry_run: bool) -> None:
    es = Elasticsearch(es_url)

    # 1. Verify source index exists
    try:
        info = es.indices.get(index=OLD_INDEX)
        # OLD_INDEX may itself be an alias — resolve to the concrete name
        concrete_old = list(info.keys())[0]
        print(f"[✓] Source: {concrete_old}")
    except NotFoundError:
        sys.exit(f"[✗] Index '{OLD_INDEX}' not found — nothing to migrate.")

    # 2. Create new index
    if es.indices.exists(index=NEW_INDEX):
        if not dry_run:
            print(f"[!] {NEW_INDEX} already exists — deleting for clean migration.")
            es.indices.delete(index=NEW_INDEX)
        else:
            print(f"[dry-run] Would delete existing {NEW_INDEX}")

    if dry_run:
        print(f"[dry-run] Would create {NEW_INDEX} with new mapping.")
        print(json.dumps(NEW_MAPPING, indent=2))
    else:
        es.indices.create(index=NEW_INDEX, body=NEW_MAPPING)
        print(f"[✓] Created {NEW_INDEX}")

    # 3. Iterate & transform documents
    migrated = 0
    errors   = 0

    for hit in scan(es, index=concrete_old, query={"query": {"match_all": {}}}):
        doc_id  = hit["_id"]
        new_doc = transform(hit)
        if dry_run:
            print(f"[dry-run] Would index doc {doc_id}: authority={new_doc['source_authority']}, "
                  f"quality={new_doc['quality_score']:.3f}")
        else:
            try:
                es.index(index=NEW_INDEX, id=doc_id, document=new_doc)
                migrated += 1
            except Exception as exc:
                print(f"[✗] Failed to index {doc_id}: {exc}")
                errors += 1

    if dry_run:
        print("[dry-run] Migration preview complete — no changes made.")
        return

    print(f"[✓] Migrated {migrated} docs, {errors} errors.")
    if errors:
        sys.exit(f"[✗] {errors} documents failed — fix before swapping alias.")

    # 4. Atomically swap alias
    actions = []
    # remove alias from old concrete index if it exists there
    alias_info = es.indices.get_alias(name=ALIAS, ignore_unavailable=True)
    for idx in alias_info:
        if idx != NEW_INDEX:
            actions.append({"remove": {"index": idx, "alias": ALIAS}})
    actions.append({"add": {"index": NEW_INDEX, "alias": ALIAS}})

    es.indices.update_aliases(body={"actions": actions})
    print(f"[✓] Alias '{ALIAS}' now points to {NEW_INDEX}")

    # 5. Refresh
    es.indices.refresh(index=NEW_INDEX)
    print("[✓] Migration complete.")
    print(f"    Old index '{concrete_old}' is still present — delete manually once verified:")
    print(f"    curl -X DELETE {es_url}/{concrete_old}")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate lse-kb to authority-aware schema")
    parser.add_argument("--es-url",  default="http://localhost:9200", help="Elasticsearch base URL")
    parser.add_argument("--dry-run", action="store_true",             help="Preview only, no writes")
    args = parser.parse_args()
    migrate(args.es_url, args.dry_run)
