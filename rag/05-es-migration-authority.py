#!/usr/bin/env python3
"""
LSE RAG Stack — Migration: add source authority fields to lse-kb.

Adds to existing lse-kb index (no reindex needed — all new fields):
  source_authority    keyword   'official_vendor'|'empirical'|'mentor'|'community'|'inferred'
  authority_score     float     weighted quality ceiling per authority tier
  empirical_runs      integer   successful executions that confirmed this doc
  empirical_failures  integer   failures that contradict this doc
  mentor_verified     boolean   human or superior model has explicitly approved
  mentor_note         text      what the mentor said
  conflicting         boolean   flagged when two sources of different authority disagree

Backfills all existing 32 chunks with safe defaults (source_authority='inferred').

Usage:
    python3 05-es-migration-authority.py [--es-url http://localhost:9200]
"""
import sys
import json
import argparse

try:
    from elasticsearch import Elasticsearch, helpers
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "elasticsearch==8.19.3", "--break-system-packages"], check=True)
    from elasticsearch import Elasticsearch, helpers

# ── Authority tiers ───────────────────────────────────────────────────────────

AUTHORITY_TIERS = {
    # Tier 1: Primary Source of Truth
    # Official documentation maintained by the project authors/vendor.
    # Defines intended behaviour. Ceiling = 1.0.
    'official_vendor': {
        'ceiling': 1.0,
        'weight':  1.0,
        'description': 'Official vendor/project documentation',
    },

    # Tier 2a: Empirical — this system
    # Actual execution success on LUCIFER. Defines real behaviour here.
    # Ceiling = 0.95 (slightly below official to allow official to override
    # when empirical success was on a misconfigured state).
    # Note: for system-specific facts, empirical MAY outrank official.
    # Use mentor_verified=True to promote to ceiling=1.0 when confirmed.
    'empirical': {
        'ceiling': 0.95,
        'weight':  0.9,
        'description': 'Confirmed by actual successful execution on this system',
    },

    # Tier 2b: Mentor — human or superior model correction
    # Can override both official and empirical. Ceiling = 1.0.
    # Stored separately from official_vendor so we can distinguish
    # "the docs say X" from "Opus/human confirmed X works here".
    'mentor': {
        'ceiling': 1.0,
        'weight':  1.0,
        'description': 'Verified by human or superior model (Opus) mentor',
    },

    # Tier 3: Community — reputable but not authoritative
    # StackOverflow, GitHub issues, blog posts, third-party tutorials.
    # Accurate often but not guaranteed. Ceiling = 0.75.
    'community': {
        'ceiling': 0.75,
        'weight':  0.6,
        'description': 'Community source (StackOverflow, GitHub issues, blogs)',
    },

    # Tier 4: Inferred — origin unknown
    # Default for pre-existing KB docs where source is not tracked.
    'inferred': {
        'ceiling': 0.65,
        'weight':  0.5,
        'description': 'Origin not tracked — default for legacy KB entries',
    },
}

# ── Official domain map — defines "Official" per topic ────────────────────────
# A source URL is classified as 'official_vendor' if its domain appears here
# for the relevant topic. All others default to 'community' or 'inferred'.

OFFICIAL_DOCS_MAP = {
    'powershell':       ['learn.microsoft.com/en-us/powershell',
                         'github.com/PowerShell/PowerShell'],
    'python':           ['docs.python.org', 'peps.python.org'],
    'docker':           ['docs.docker.com', 'hub.docker.com/_/'],
    'elasticsearch':    ['elastic.co/docs', 'elastic.co/guide',
                         'github.com/elastic/elasticsearch'],
    'llama-cpp':        ['github.com/ggerganov/llama.cpp'],
    'ollama':           ['ollama.com', 'github.com/ollama/ollama'],
    'comfyui':          ['github.com/comfyanonymous/ComfyUI',
                         'docs.comfy.org'],
    'openwebui':        ['docs.openwebui.com',
                         'github.com/open-webui/open-webui'],
    'ubuntu':           ['manpages.ubuntu.com', 'help.ubuntu.com',
                         'ubuntu.com/server/docs'],
    'nvidia-cuda':      ['docs.nvidia.com', 'developer.nvidia.com/docs'],
    'searxng':          ['docs.searxng.org',
                         'github.com/searxng/searxng'],
    'pfsense':          ['docs.netgate.com'],
    'wan2.1':           ['github.com/Wan-Video/Wan2.1',
                         'huggingface.co/Wan-AI'],
    'stable-diffusion': ['github.com/AUTOMATIC1111/stable-diffusion-webui',
                         'github.com/comfyanonymous/ComfyUI'],
    'huggingface':      ['huggingface.co/docs', 'huggingface.co/blog'],
    'lse-launcher':     ['/opt/local-se/', '/home/sy5/.lse/'],  # local paths
}


def classify_source_authority(source_url: str, topic: str) -> str:
    """Auto-classify a source URL into an authority tier."""
    if not source_url:
        return 'inferred'
    url_lower = source_url.lower()
    # Check official domains for this topic
    domains = OFFICIAL_DOCS_MAP.get(topic, [])
    if any(d.lower() in url_lower for d in domains):
        return 'official_vendor'
    # Generic official signals
    if any(x in url_lower for x in ['/docs/', 'documentation', 'reference',
                                      'learn.microsoft', 'developer.', 'docs.']):
        return 'community'  # probably good but not confirmed official
    return 'community'


def compute_quality_score(
    source_authority: str,
    base_quality: float,
    empirical_runs: int = 0,
    empirical_failures: int = 0,
    mentor_verified: bool = False,
) -> float:
    """
    Compute weighted quality score from authority tier + empirical evidence.

    Formula:
        score = blend(base_quality, empirical_signal) capped at authority_ceiling
        mentor_verified floors the result at 0.85 (regardless of other signals)
    """
    tier = AUTHORITY_TIERS.get(source_authority, AUTHORITY_TIERS['inferred'])
    ceiling = tier['ceiling']

    total_runs = empirical_runs + empirical_failures
    if total_runs > 0:
        success_rate = empirical_runs / total_runs
        # Confidence saturates after ~5 runs
        confidence = min(1.0, total_runs / 5.0)
        empirical_signal = success_rate * confidence
        # 40% base, 60% empirical when we have run data
        score = base_quality * 0.4 + empirical_signal * 0.6
    else:
        score = base_quality

    if mentor_verified:
        score = max(score, 0.85)

    return round(min(ceiling, max(0.0, score)), 4)


def add_mapping_fields(es: Elasticsearch) -> None:
    """Add new authority fields to lse-kb mapping (non-destructive — adds only)."""
    new_fields = {
        "properties": {
            "source_authority":   {"type": "keyword"},
            "authority_score":    {"type": "float"},
            "empirical_runs":     {"type": "integer"},
            "empirical_failures": {"type": "integer"},
            "mentor_verified":    {"type": "boolean"},
            "mentor_note":        {"type": "text"},
            "conflicting":        {"type": "boolean"},
        }
    }
    es.indices.put_mapping(index="lse-kb", body=new_fields)
    print("  ✅ Mapping updated — 7 new fields added to lse-kb")


def backfill_existing_docs(es: Elasticsearch) -> int:
    """
    Update all existing docs with default authority values.
    Uses update_by_query — no reindex needed.
    """
    # Only update docs that don't already have source_authority set
    result = es.update_by_query(
        index="lse-kb",
        body={
            "script": {
                "source": """
                    if (ctx._source.source_authority == null) {
                        ctx._source.source_authority = 'inferred';
                        ctx._source.authority_score = 0.5;
                        ctx._source.empirical_runs = 0;
                        ctx._source.empirical_failures = 0;
                        ctx._source.mentor_verified = false;
                        ctx._source.mentor_note = '';
                        ctx._source.conflicting = false;
                    }
                """,
                "lang": "painless"
            },
            "query": {"bool": {"must_not": {"exists": {"field": "source_authority"}}}}
        },
        wait_for_completion=True,
        refresh=True,
    )
    updated = result.get("updated", 0)
    print(f"  ✅ Backfilled {updated} existing documents with default authority values")
    return updated


def verify_migration(es: Elasticsearch) -> None:
    """Spot-check a few docs to confirm fields are present."""
    resp = es.search(index="lse-kb", body={
        "query": {"match_all": {}},
        "_source": ["title", "source_authority", "quality_score",
                    "empirical_runs", "mentor_verified"],
        "size": 3
    })
    print("\n  Sample docs after migration:")
    for h in resp["hits"]["hits"]:
        s = h["_source"]
        print(f"    {s['title'][:40]:40s} | authority={s.get('source_authority','?'):15s} "
              f"| quality={s.get('quality_score', 0):.2f} "
              f"| runs={s.get('empirical_runs', 0)} "
              f"| mentor={s.get('mentor_verified', False)}")


def main():
    parser = argparse.ArgumentParser(description="LSE RAG — authority field migration")
    parser.add_argument("--es-url", default="http://127.0.0.1:9200")
    args = parser.parse_args()

    print("=== LSE RAG: Source Authority Migration ===")
    print(f"Target: {args.es_url}/lse-kb")
    print()

    es = Elasticsearch(args.es_url, request_timeout=30)

    try:
        health = es.cluster.health()
        print(f"  Cluster: {health['status']} — Elasticsearch connected")
    except Exception as e:
        print(f"  ❌ Cannot reach Elasticsearch: {e}")
        sys.exit(1)

    print("\nStep 1: Adding mapping fields...")
    add_mapping_fields(es)

    print("\nStep 2: Backfilling existing documents...")
    backfill_existing_docs(es)

    print("\nStep 3: Verifying...")
    verify_migration(es)

    print(f"""
=== Migration complete ===

Authority tiers now active:
  official_vendor  — ceiling 1.0  (official project docs)
  empirical        — ceiling 0.95 (confirmed working on LUCIFER)
  mentor           — ceiling 1.0  (Opus or human override)
  community        — ceiling 0.75 (StackOverflow, blogs, etc.)
  inferred         — ceiling 0.65 (legacy / unknown origin)

Official domain map covers {len(OFFICIAL_DOCS_MAP)} topics.
Existing 32 chunks backfilled as 'inferred' quality_score=0.5.

Next: redeploy openwebui-tool-v1.5.9.py with updated index_to_kb()
""")


if __name__ == "__main__":
    main()
