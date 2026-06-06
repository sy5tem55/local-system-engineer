#!/usr/bin/env python3
"""
rfc_kb.py — RFC corpus ingestion and authority-weighted search for the LSE KB.

Architecture (§3.5 Authority Model):
  quality_score = min(authority_ceiling,
                      raw_score × confirmation_weight × recency_weight)

  authority_ceiling  — derived from RFC status (Internet Std: 0.95, obsoleted: 0.30)
  recency_weight     — 1.0 if not obsoleted · 0.30 if obsoleted_by is set
  confirmation_weight— empirical: fraction of past resolutions that cited this
                       section successfully. Starts at 1.0, updated by bump_confirmation().

Three-layer retrieval:
  Layer 1 — Protocol taxonomy filter (deterministic, fast)
  Layer 2 — Dense kNN on symptom description within filtered corpus
  Layer 3 — Confirmation weight re-ranking

Index: lse-rfc-kb (Elasticsearch, separate from lse-kb)
Embeddings: Ollama nomic-embed-text (same as main KB)
Symptom tagging: Ollama llama3.2:3b (one-time, at index time)

Usage:
  python3 scripts/rfc_kb.py --index-all        # fetch + chunk + tag + embed + index all RFCs
  python3 scripts/rfc_kb.py --index 2131        # index single RFC
  python3 scripts/rfc_kb.py --tag-only          # (re)generate symptom_tags without re-indexing
  python3 scripts/rfc_kb.py --search "DHCP client keeps sending DISCOVER after ACK"
  python3 scripts/rfc_kb.py --status            # show index stats per RFC
  python3 scripts/rfc_kb.py --dry-run 2131      # chunk + print, no ES write
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ── Configuration ─────────────────────────────────────────────────────────────

ES_URL        = os.getenv("ES_URL",     "http://localhost:9200")
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://localhost:11434")
RFC_INDEX     = "lse-rfc-kb"
EMBED_MODEL   = "nomic-embed-text"
EMBED_PREFIX  = "search_query: "
TAG_MODEL     = "llama3.2:3b"
RFC_BASE_URL  = "https://www.rfc-editor.org/rfc/rfc{}.txt"
CACHE_DIR     = Path("/opt/local-se/rfc-cache")
MAX_CHUNK_CHARS = 2500
KB_THRESHOLD  = 0.72

# ── RFC Registry ──────────────────────────────────────────────────────────────
# authority_ceiling values:
#   Internet Standard   → 0.95
#   Draft Standard      → 0.90
#   Proposed Standard   → 0.85
#   Best Current Practice → 0.85
#   Informational       → 0.70
#   Experimental        → 0.65
#   Historic/Obsoleted  → 0.30 (recency_weight also set to 0.30)

RFC_REGISTRY = {
    # ── DHCP ─────────────────────────────────────────────────────────────────
    2131: {
        "title":             "Dynamic Host Configuration Protocol",
        "status":            "Internet Standard",
        "authority_ceiling": 0.95,
        "protocols":         ["dhcp", "bootp"],
        "obsoletes":         [1541],
        "obsoleted_by":      None,
        "notes":             "Core DHCPv4. §4.4.5 covers client reacquisition — Samsung TV DHCP hammer.",
    },
    2132: {
        "title":             "DHCP Options and BOOTP Vendor Extensions",
        "status":            "Internet Standard",
        "authority_ceiling": 0.95,
        "protocols":         ["dhcp", "bootp"],
        "obsoletes":         [1533],
        "obsoleted_by":      None,
        "notes":             "DHCP option codes. Useful for diagnosing client option requests.",
    },
    # ── DNS ──────────────────────────────────────────────────────────────────
    1034: {
        "title":             "Domain Names — Concepts and Facilities",
        "status":            "Internet Standard",
        "authority_ceiling": 0.95,
        "protocols":         ["dns"],
        "obsoletes":         [882, 883],
        "obsoleted_by":      None,
        "notes":             "DNS fundamentals. Zone, delegation, resolver concepts.",
    },
    1035: {
        "title":             "Domain Names — Implementation and Specification",
        "status":            "Internet Standard",
        "authority_ceiling": 0.95,
        "protocols":         ["dns"],
        "obsoletes":         [882, 883, 973],
        "obsoleted_by":      None,
        "notes":             "DNS wire format, resource records, resolver algorithm.",
    },
    2308: {
        "title":             "Negative Caching of DNS Queries (DNS NCACHE)",
        "status":            "Proposed Standard",
        "authority_ceiling": 0.85,
        "protocols":         ["dns"],
        "obsoletes":         [1034],
        "obsoleted_by":      None,
        "notes":             "NXDOMAIN, NODATA caching. TTL semantics for negative answers.",
    },
    2782: {
        "title":             "A DNS RR for specifying the location of services (DNS SRV)",
        "status":            "Proposed Standard",
        "authority_ceiling": 0.85,
        "protocols":         ["dns"],
        "obsoletes":         [2052],
        "obsoleted_by":      None,
        "notes":             "SRV records. Used by HA, mDNS, and service discovery.",
    },
    # ── TLS / PKI ─────────────────────────────────────────────────────────────
    8446: {
        "title":             "The Transport Layer Security (TLS) Protocol Version 1.3",
        "status":            "Proposed Standard",
        "authority_ceiling": 0.85,
        "protocols":         ["tls", "ssl", "https"],
        "obsoletes":         [5246],
        "obsoleted_by":      None,
        "notes":             "TLS 1.3 handshake, cipher suites, certificate verification.",
    },
    5280: {
        "title":             "Internet X.509 Public Key Infrastructure Certificate and CRL Profile",
        "status":            "Proposed Standard",
        "authority_ceiling": 0.85,
        "protocols":         ["tls", "x509", "pki", "https"],
        "obsoletes":         [3280],
        "obsoleted_by":      None,
        "notes":             "X.509 cert structure, validity, chain validation. pfSense WebGUI CA.",
    },
    # ── TCP / IP ──────────────────────────────────────────────────────────────
    9293: {
        "title":             "Transmission Control Protocol (TCP)",
        "status":            "Internet Standard",
        "authority_ceiling": 0.95,
        "protocols":         ["tcp"],
        "obsoletes":         [793],
        "obsoleted_by":      None,
        "notes":             "Current TCP spec. RST handling, TIME-WAIT, connection state machine.",
    },
    792: {
        "title":             "Internet Control Message Protocol",
        "status":            "Internet Standard",
        "authority_ceiling": 0.95,
        "protocols":         ["icmp", "ping"],
        "obsoletes":         [],
        "obsoleted_by":      None,
        "notes":             "ICMP message types, unreachable, redirect, echo.",
    },
    1122: {
        "title":             "Requirements for Internet Hosts — Communication Layers",
        "status":            "Internet Standard",
        "authority_ceiling": 0.95,
        "protocols":         ["tcp", "udp", "icmp", "ip"],
        "obsoletes":         [],
        "obsoleted_by":      None,
        "notes":             "Host requirements: ARP, IP, TCP, UDP, ICMP behaviour. Canonical reference.",
    },
    4632: {
        "title":             "Classless Inter-domain Routing (CIDR): The Internet Address Assignment and Aggregation Plan",
        "status":            "Best Current Practice",
        "authority_ceiling": 0.85,
        "protocols":         ["ip", "routing", "cidr"],
        "obsoletes":         [1519],
        "obsoleted_by":      None,
        "notes":             "CIDR notation, prefix aggregation, subnet calculation.",
    },
    # ── HTTP ─────────────────────────────────────────────────────────────────
    9110: {
        "title":             "HTTP Semantics",
        "status":            "Internet Standard",
        "authority_ceiling": 0.95,
        "protocols":         ["http", "https", "api"],
        "obsoletes":         [7231, 7232, 7233, 7235],
        "obsoleted_by":      None,
        "notes":             "HTTP methods, status codes, headers. REST API behaviour.",
    },
    9112: {
        "title":             "HTTP/1.1",
        "status":            "Internet Standard",
        "authority_ceiling": 0.95,
        "protocols":         ["http", "https"],
        "obsoletes":         [7230],
        "obsoleted_by":      None,
        "notes":             "HTTP/1.1 framing, connection management, pipelining.",
    },
    # ── Syslog ────────────────────────────────────────────────────────────────
    5424: {
        "title":             "The Syslog Protocol",
        "status":            "Proposed Standard",
        "authority_ceiling": 0.85,
        "protocols":         ["syslog"],
        "obsoletes":         [3164],
        "obsoleted_by":      None,
        "notes":             "Syslog message format, severity, facility, structured data.",
    },
    5426: {
        "title":             "Transmission of Syslog Messages over UDP",
        "status":            "Proposed Standard",
        "authority_ceiling": 0.85,
        "protocols":         ["syslog", "udp"],
        "obsoletes":         [],
        "obsoleted_by":      None,
        "notes":             "Syslog over UDP:514. pfSense → LUCIFER syslog pipeline.",
    },
    # ── NTP ──────────────────────────────────────────────────────────────────
    5905: {
        "title":             "Network Time Protocol Version 4: Protocol and Algorithms Specification",
        "status":            "Proposed Standard",
        "authority_ceiling": 0.85,
        "protocols":         ["ntp", "time"],
        "obsoletes":         [1305],
        "obsoleted_by":      None,
        "notes":             "NTPv4 stratum, clock discipline, time synchronisation.",
    },
    # ── NAT / Firewall ────────────────────────────────────────────────────────
    3022: {
        "title":             "Traditional IP Network Address Translator (Traditional NAT)",
        "status":            "Informational",
        "authority_ceiling": 0.70,
        "protocols":         ["nat", "firewall", "ip"],
        "obsoletes":         [1631],
        "obsoleted_by":      None,
        "notes":             "NAT basics, port mapping, ALG requirements. pfSense NAT rules.",
    },
    # ── NFS ──────────────────────────────────────────────────────────────────
    7530: {
        "title":             "Network File System (NFS) Version 4 Protocol",
        "status":            "Proposed Standard",
        "authority_ceiling": 0.85,
        "protocols":         ["nfs", "nfsv4"],
        "obsoletes":         [3530],
        "obsoleted_by":      None,
        "notes":             "NFSv4 operations, locking, ACLs. QNAP NAS exports.",
    },
    1813: {
        "title":             "NFS Version 3 Protocol Specification",
        "status":            "Informational",
        "authority_ceiling": 0.70,
        "protocols":         ["nfs", "nfsv3"],
        "obsoletes":         [],
        "obsoleted_by":      None,
        "notes":             "NFSv3 procedures, error codes, mount protocol.",
    },
}

# Recency weight: obsoleted RFCs are still informative but not authoritative
def _recency_weight(rfc_num: int) -> float:
    meta = RFC_REGISTRY.get(rfc_num, {})
    if meta.get("obsoleted_by"):
        return 0.30
    return 1.0


def _authority_ceiling(rfc_num: int) -> float:
    meta = RFC_REGISTRY.get(rfc_num, {})
    if meta.get("obsoleted_by"):
        return 0.30
    return meta.get("authority_ceiling", 0.70)


# ── ES Index Schema ───────────────────────────────────────────────────────────

RFC_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "rfc_number":         {"type": "integer"},
            "rfc_title":          {"type": "text"},
            "section_id":         {"type": "keyword"},
            "section_title":      {"type": "text"},
            "content":            {"type": "text"},
            "symptom_tags":       {"type": "text"},
            "protocols":          {"type": "keyword"},
            "rfc_status":         {"type": "keyword"},
            "authority_ceiling":  {"type": "float"},
            "recency_weight":     {"type": "float"},
            "confirmation_weight":{"type": "float"},
            "quality_score":      {"type": "float"},
            "obsoleted_by":       {"type": "integer"},
            "char_count":         {"type": "integer"},
            "indexed_at":         {"type": "date"},
            "embedding": {
                "type":       "dense_vector",
                "dims":       768,
                "index":      True,
                "similarity": "cosine",
            },
        }
    }
}


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_rfc(rfc_num: int, force: bool = False) -> str:
    """Download RFC plain text, cache to disk. Returns raw text."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"rfc{rfc_num}.txt"
    if cache_path.exists() and not force:
        return cache_path.read_text(encoding="utf-8", errors="replace")

    url = RFC_BASE_URL.format(rfc_num)
    print(f"  Fetching RFC {rfc_num} from {url} ...", flush=True)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        text = resp.text
        cache_path.write_text(text, encoding="utf-8")
        print(f"  Cached: {cache_path} ({len(text):,} chars)")
        return text
    except Exception as e:
        print(f"  ERROR fetching RFC {rfc_num}: {e}")
        return ""


# ── Chunker ───────────────────────────────────────────────────────────────────

# Matches section headers like "1.", "2.3.", "4.1.2." at start of line
_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*\.?)\s{2,}(.+)$", re.MULTILINE)


def chunk_rfc(rfc_num: int, text: str) -> list[dict]:
    """
    Split RFC plain text into section-level chunks.
    Returns list of dicts with section_id, section_title, content.
    Merges short sections with the next one to avoid micro-chunks.
    """
    meta = RFC_REGISTRY.get(rfc_num, {})
    matches = list(_SECTION_RE.finditer(text))

    if not matches:
        # Fallback: split into fixed-size windows
        chunks = []
        for i, start in enumerate(range(0, len(text), MAX_CHUNK_CHARS)):
            chunk_text = text[start:start + MAX_CHUNK_CHARS].strip()
            if len(chunk_text) < 100:
                continue
            chunks.append({
                "section_id":    f"{rfc_num}-chunk-{i}",
                "section_title": f"RFC {rfc_num} (part {i+1})",
                "content":       chunk_text,
            })
        return chunks

    chunks = []
    for i, match in enumerate(matches):
        start = match.start()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        # Skip very short sections (boilerplate, ToC entries)
        if len(content) < 150:
            continue

        # Truncate oversized sections
        if len(content) > MAX_CHUNK_CHARS:
            content = content[:MAX_CHUNK_CHARS] + "\n[... truncated ...]"

        chunks.append({
            "section_id":    f"{rfc_num}-{match.group(1).rstrip('.')}",
            "section_title": match.group(2).strip(),
            "content":       content,
        })

    # Always include an abstract chunk if present
    abstract_match = re.search(r"Abstract\s*\n+(.*?)(?=\n\s*\n\s*(?:\d+\.|Table of Contents))",
                                text, re.DOTALL | re.IGNORECASE)
    if abstract_match:
        abstract_text = abstract_match.group(1).strip()
        if abstract_text and len(abstract_text) > 50:
            chunks.insert(0, {
                "section_id":    f"{rfc_num}-abstract",
                "section_title": "Abstract",
                "content":       abstract_text[:MAX_CHUNK_CHARS],
            })

    print(f"  RFC {rfc_num}: {len(chunks)} chunks")
    return chunks


# ── Symptom Tagger ────────────────────────────────────────────────────────────

_TAG_PROMPT = """\
You are a network engineer. Given an RFC section below, list 8-12 SPECIFIC \
operational symptoms, error conditions, or observable behaviours that would \
cause an engineer to look up this exact section. Be concrete:
- Use protocol keywords (e.g. DHCP DISCOVER, DNS NXDOMAIN, TCP RST)
- Include log message fragments where applicable
- Include tool outputs (nmap, tcpdump, dig, openssl s_client)
- One symptom per line, no numbering, no bullets

RFC section:
{content}

Symptoms:"""


def tag_section(content: str, verbose: bool = False) -> str:
    """
    Call Ollama to generate symptom tags for an RFC section.
    Returns newline-separated symptom strings, or "" on failure.
    Prints a one-line error on first failure per run.
    """
    prompt = _TAG_PROMPT.format(content=content[:1500])
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":   TAG_MODEL,
                "prompt":  prompt,
                "stream":  False,
                "options": {"num_predict": 300, "temperature": 0.3},
            },
            timeout=60,
        )
        if resp.status_code == 200:
            tags = resp.json().get("response", "").strip()
            if verbose:
                print(f"    Tags: {tags[:120]}...")
            return tags
        else:
            print(f"  [tag_section] HTTP {resp.status_code}: {resp.text[:200]}")
            return ""
    except Exception as e:
        print(f"  [tag_section] {type(e).__name__}: {e}")
        return ""


# ── Embedder ──────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """Embed text via Ollama nomic-embed-text. Returns empty list on failure."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": EMBED_PREFIX + text[:2000]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("embedding", [])
    except Exception as e:
        print(f"  Embedding failed: {e}")
        return []


# ── ES helpers ────────────────────────────────────────────────────────────────

def ensure_index():
    """Create lse-rfc-kb index with mapping if it doesn't exist."""
    resp = requests.head(f"{ES_URL}/{RFC_INDEX}", timeout=5)
    if resp.status_code == 404:
        r = requests.put(
            f"{ES_URL}/{RFC_INDEX}",
            json=RFC_INDEX_MAPPING,
            timeout=10,
        )
        r.raise_for_status()
        print(f"  Created index: {RFC_INDEX}")
    else:
        print(f"  Index exists: {RFC_INDEX}")


def index_doc(doc: dict) -> bool:
    """Upsert a document by section_id."""
    doc_id = doc["section_id"].replace("/", "-")
    resp = requests.put(
        f"{ES_URL}/{RFC_INDEX}/_doc/{doc_id}",
        json=doc,
        timeout=15,
    )
    return resp.status_code in (200, 201)


def index_status() -> list[dict]:
    """Return per-RFC chunk counts from the index."""
    try:
        resp = requests.post(
            f"{ES_URL}/{RFC_INDEX}/_search",
            json={
                "size": 0,
                "aggs": {
                    "by_rfc": {
                        "terms": {"field": "rfc_number", "size": 50},
                        "aggs": {
                            "avg_quality": {"avg": {"field": "quality_score"}},
                            "with_tags":   {"filter": {"exists": {"field": "symptom_tags"}}},
                        },
                    }
                },
            },
            timeout=10,
        )
        buckets = resp.json().get("aggregations", {}).get("by_rfc", {}).get("buckets", [])
        return [
            {
                "rfc":         b["key"],
                "chunks":      b["doc_count"],
                "avg_quality": round(b["avg_quality"]["value"] or 0, 3),
                "tagged":      b["with_tags"]["doc_count"],
            }
            for b in buckets
        ]
    except Exception as e:
        print(f"  Status query failed: {e}")
        return []


# ── Pipeline ──────────────────────────────────────────────────────────────────

def process_rfc(
    rfc_num: int,
    tag: bool = True,
    dry_run: bool = False,
    verbose: bool = True,
) -> int:
    """
    Full pipeline for one RFC: fetch → chunk → tag → embed → index.
    Returns number of chunks indexed.
    """
    meta = RFC_REGISTRY.get(rfc_num)
    if not meta:
        print(f"  RFC {rfc_num} not in registry — skipping")
        return 0

    if verbose:
        print(f"\n{'─'*60}")
        print(f"  RFC {rfc_num} — {meta['title']}")
        print(f"  Status: {meta['status']} · Ceiling: {meta['authority_ceiling']}")
        print(f"{'─'*60}")

    text = fetch_rfc(rfc_num)
    if not text:
        return 0

    chunks = chunk_rfc(rfc_num, text)
    if not chunks:
        print(f"  No chunks extracted from RFC {rfc_num}")
        return 0

    if dry_run:
        for c in chunks[:3]:
            print(f"\n  [{c['section_id']}] {c['section_title']}")
            print(f"  {c['content'][:300]}...")
        return len(chunks)

    a_ceil   = _authority_ceiling(rfc_num)
    r_weight = _recency_weight(rfc_num)
    protocols = meta.get("protocols", [])
    indexed = 0

    for i, chunk in enumerate(chunks):
        if verbose:
            print(f"  [{i+1}/{len(chunks)}] {chunk['section_id']} — {chunk['section_title'][:50]}", end="", flush=True)

        # Symptom tagging (Ollama)
        symptom_tags = ""
        if tag:
            symptom_tags = tag_section(chunk["content"])
            if verbose:
                print(f" → {len(symptom_tags.splitlines())} tags", end="", flush=True)

        # Embedding — combine content + symptom_tags for richer vector
        embed_text = chunk["content"]
        if symptom_tags:
            embed_text = symptom_tags + "\n\n" + embed_text
        embedding = embed(embed_text)

        # Quality score (confirmation_weight starts at 1.0)
        quality = min(a_ceil, 1.0 * 1.0 * r_weight)

        doc = {
            "rfc_number":          rfc_num,
            "rfc_title":           meta["title"],
            "section_id":          chunk["section_id"],
            "section_title":       chunk["section_title"],
            "content":             chunk["content"],
            "symptom_tags":        symptom_tags,
            "protocols":           protocols,
            "rfc_status":          meta["status"],
            "authority_ceiling":   a_ceil,
            "recency_weight":      r_weight,
            "confirmation_weight": 1.0,
            "quality_score":       quality,
            "obsoleted_by":        meta.get("obsoleted_by"),
            "char_count":          len(chunk["content"]),
            "indexed_at":          datetime.now(timezone.utc).isoformat(),
            "embedding":           embedding,
        }

        if index_doc(doc):
            indexed += 1
            if verbose:
                print(" ✓")
        else:
            if verbose:
                print(" ✗")

        time.sleep(0.1)  # avoid hammering Ollama

    print(f"  Indexed {indexed}/{len(chunks)} chunks for RFC {rfc_num}")
    return indexed


# ── Search ────────────────────────────────────────────────────────────────────

def search_rfc(
    symptom: str,
    protocol: str = "",
    top_k: int = 3,
    min_quality: float = 0.60,
) -> list[dict]:
    """
    Three-layer RFC search:
      1. Protocol filter (if provided)
      2. kNN dense search on symptom embedding
      3. Re-rank by quality_score (authority_ceiling × confirmation_weight × recency_weight)

    Returns top_k results as list of dicts:
      rfc_number, section_id, section_title, quality_score, snippet, citation
    """
    embedding = embed(symptom)
    if not embedding:
        return []

    query: dict = {
        "size": top_k * 3,   # over-fetch for re-ranking
        "min_score": min_quality,
        "knn": {
            "field":         "embedding",
            "query_vector":  embedding,
            "k":             top_k * 3,
            "num_candidates": 50,
        },
    }

    # Layer 1: protocol filter
    if protocol:
        query["post_filter"] = {
            "term": {"protocols": protocol.lower()}
        }

    try:
        resp = requests.post(
            f"{ES_URL}/{RFC_INDEX}/_search",
            json=query,
            timeout=10,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
    except Exception as e:
        print(f"  RFC search failed: {e}")
        return []

    # Layer 3: re-rank by quality_score × ES relevance score
    results = []
    for h in hits:
        src = h["_source"]
        es_score = h["_score"]
        quality  = src.get("quality_score", 0.0)
        combined = es_score * quality

        results.append({
            "rfc_number":    src["rfc_number"],
            "rfc_title":     src.get("rfc_title", ""),
            "section_id":    src["section_id"],
            "section_title": src.get("section_title", ""),
            "quality_score": quality,
            "es_score":      round(es_score, 4),
            "combined_score":round(combined, 4),
            "snippet":       src.get("content", "")[:400],
            "citation":      f"RFC {src['rfc_number']} §{src['section_id'].split('-', 1)[-1]} — {src.get('section_title', '')}",
        })

    # Sort by combined score, return top_k
    results.sort(key=lambda r: r["combined_score"], reverse=True)
    return results[:top_k]


def bump_confirmation(section_id: str, success: bool):
    """
    Update confirmation_weight for a section after a resolution attempt.
    success=True: weight × 1.1 (capped at 1.0)
    success=False: weight × 0.95 (floor at 0.5)
    Recomputes quality_score after update.
    """
    doc_id = section_id.replace("/", "-")
    try:
        get_resp = requests.get(f"{ES_URL}/{RFC_INDEX}/_doc/{doc_id}", timeout=5)
        if get_resp.status_code != 200:
            return
        src = get_resp.json()["_source"]
        old_cw = src.get("confirmation_weight", 1.0)
        new_cw = min(1.0, old_cw * 1.1) if success else max(0.5, old_cw * 0.95)
        new_qs = min(
            src.get("authority_ceiling", 0.70),
            new_cw * src.get("recency_weight", 1.0),
        )
        requests.post(
            f"{ES_URL}/{RFC_INDEX}/_update/{doc_id}",
            json={"doc": {"confirmation_weight": new_cw, "quality_score": new_qs}},
            timeout=5,
        )
    except Exception:
        pass


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="RFC KB — corpus ingestion and authority-weighted search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/rfc_kb.py --index-all
  python3 scripts/rfc_kb.py --index 2131
  python3 scripts/rfc_kb.py --dry-run 2131
  python3 scripts/rfc_kb.py --search "DHCP client retransmits after receiving ACK"
  python3 scripts/rfc_kb.py --search "TLS certificate verify failed" --protocol tls
  python3 scripts/rfc_kb.py --status
""",
    )
    p.add_argument("--index-all",  action="store_true", help="Index all registered RFCs")
    p.add_argument("--index",      type=int,            help="Index single RFC number")
    p.add_argument("--dry-run",    type=int,            help="Chunk + print RFC, no ES write")
    p.add_argument("--tag-only",   action="store_true", help="Regenerate symptom_tags only")
    p.add_argument("--no-tag",     action="store_true", help="Skip Ollama tagging (faster)")
    p.add_argument("--search",     type=str,            help="Symptom to search for")
    p.add_argument("--protocol",   type=str, default="", help="Protocol filter for search")
    p.add_argument("--status",     action="store_true", help="Show index stats")
    p.add_argument("--list",       action="store_true", help="List registered RFCs")
    args = p.parse_args()

    if args.list:
        print(f"\n  {'RFC':>6}  {'Ceil':>5}  {'Status':<22}  {'Protocols':<20}  Title")
        print(f"  {'─'*6}  {'─'*5}  {'─'*22}  {'─'*20}  {'─'*40}")
        for num, meta in sorted(RFC_REGISTRY.items()):
            protos = ",".join(meta["protocols"][:3])
            obs = f" → obsoleted by {meta['obsoleted_by']}" if meta.get("obsoleted_by") else ""
            print(f"  {num:>6}  {meta['authority_ceiling']:>5.2f}  "
                  f"{meta['status']:<22}  {protos:<20}  {meta['title'][:40]}{obs}")
        print()
        return

    if args.status:
        rows = index_status()
        if not rows:
            print("  Index is empty or unreachable.")
            return
        print(f"\n  {'RFC':>6}  {'Chunks':>6}  {'Tagged':>6}  {'Avg Quality':>11}")
        print(f"  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*11}")
        for r in sorted(rows, key=lambda x: x["rfc"]):
            meta = RFC_REGISTRY.get(r["rfc"], {})
            title = meta.get("title", "")[:35]
            print(f"  {r['rfc']:>6}  {r['chunks']:>6}  {r['tagged']:>6}  "
                  f"{r['avg_quality']:>11.3f}  {title}")
        print()
        return

    if args.search:
        print(f"\n  Searching: {args.search!r}"
              + (f"  [protocol={args.protocol}]" if args.protocol else ""))
        results = search_rfc(args.search, protocol=args.protocol)
        if not results:
            print("  No results (index empty or Ollama unavailable).")
            return
        for i, r in enumerate(results, 1):
            print(f"\n  [{i}] {r['citation']}")
            print(f"       Quality: {r['quality_score']:.3f}  ES: {r['es_score']:.4f}  Combined: {r['combined_score']:.4f}")
            print(f"       {r['snippet'][:200]}...")
        print()
        return

    if args.dry_run:
        text = fetch_rfc(args.dry_run)
        chunks = chunk_rfc(args.dry_run, text)
        for c in chunks[:5]:
            print(f"\n[{c['section_id']}] {c['section_title']}")
            print(c["content"][:400])
        print(f"\n  Total chunks: {len(chunks)}")
        return

    if args.tag_only:
        # Re-tag all indexed chunks that have empty symptom_tags.
        # Fetches chunks from ES in pages, calls Ollama for each untagged chunk,
        # updates the doc (new tags + re-embedded vector + updated quality_score).
        print(f"\n  Starting --tag-only pass on {RFC_INDEX} ...")
        tagged = 0
        skipped = 0
        errors = 0
        page_size = 50
        search_from = 0
        while True:
            try:
                resp = requests.post(
                    f"{ES_URL}/{RFC_INDEX}/_search",
                    json={
                        "from": search_from, "size": page_size,
                        "query": {"match_all": {}},
                        "_source": ["section_id", "content", "symptom_tags",
                                    "authority_ceiling", "recency_weight"],
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                hits = resp.json().get("hits", {}).get("hits", [])
            except Exception as e:
                print(f"  ES fetch error: {e}")
                break
            if not hits:
                break
            for h in hits:
                src_doc = h["_source"]
                sid     = src_doc.get("section_id", h["_id"])
                content = src_doc.get("content", "")
                existing_tags = src_doc.get("symptom_tags", "").strip()
                if existing_tags:
                    skipped += 1
                    continue
                tags = tag_section(content)
                if not tags:
                    errors += 1
                    continue
                # Re-embed with tags prepended for richer vector
                embedding = embed(tags + "\n\n" + content)
                a_ceil  = src_doc.get("authority_ceiling", 0.70)
                r_wt    = src_doc.get("recency_weight", 1.0)
                new_qs  = min(a_ceil, 1.0 * r_wt)
                doc_id  = sid.replace("/", "-")
                try:
                    requests.post(
                        f"{ES_URL}/{RFC_INDEX}/_update/{doc_id}",
                        json={"doc": {
                            "symptom_tags": tags,
                            "embedding":    embedding,
                            "quality_score": new_qs,
                        }},
                        timeout=15,
                    ).raise_for_status()
                    tagged += 1
                    print(f"  [{tagged}] {sid[:50]} → {len(tags.splitlines())} tags")
                except Exception as e:
                    print(f"  Update failed for {sid}: {e}")
                    errors += 1
                time.sleep(0.1)
            search_from += page_size
        print(f"\n  Tag-only complete: tagged={tagged} skipped={skipped} errors={errors}")
        return

    if args.index or args.index_all:
        ensure_index()
        tag = not args.no_tag
        rfcs_to_index = list(RFC_REGISTRY.keys()) if args.index_all else [args.index]
        total = 0
        for num in rfcs_to_index:
            total += process_rfc(num, tag=tag)
        print(f"\n  Total chunks indexed: {total}")
        return

    p.print_help()


if __name__ == "__main__":
    main()
