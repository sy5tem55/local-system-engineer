#!/usr/bin/env python3
"""
goethe_kb.py — LSE knowledge-base trust lifecycle, extracted from goethe.py
============================================================================
PH5-1 (TrustPolicy — single source of truth for source-tier quality ceilings,
replacing three inline _TIER_CEILING dicts) and PH5-2 (KB surface extraction)
of the 2026-07 roadmap. `Tools` in goethe.py inherits `KBMixin`; goethe_mcp
discovers tools via dir(instance), so the exposed MCP tool list is unchanged.

Methods moved verbatim (2026-07-18, from goethe.py v0.4.0-a lines 4663-6067):
  _embed, _es, search_kb, index_to_kb, record_error, check_error_kb,
  _resolve_kb_id, record_outcome, mentor_correct, kb_verify, mentor_demote,
  skill_search, skill_record, skill_outcome
Contract suite: tests/test_kb_contracts.py pins all behavior; run before and
after any change here (run_tests scope=harness).
"""

import json
import os
from datetime import datetime
from typing import Optional


class TrustPolicy:
    """Single source of truth for source-tier quality ceilings (PH5-1).

    Kills the 3x duplicated _TIER_CEILING dicts (index_to_kb / skill_record /
    skill_outcome). Semantics preserved exactly:
      - index_to_kb + skill_record fall back to "inferred" on unknown tier;
      - skill_outcome falls back to "secondary" (its historical default).
    Ceiling values are pinned by tests/test_kb_contracts.py.
    """

    TIER_CEILING = {
        "ground_truth": 1.0,
        "primary": 0.8,
        "secondary": 0.6,
        "inferred": 0.4,
    }

    @classmethod
    def ceiling(cls, source_tier: str, default: str = "inferred") -> tuple:
        """Return (resolved_tier, ceiling) for a claimed source tier."""
        tier = source_tier if source_tier in cls.TIER_CEILING else default
        return tier, cls.TIER_CEILING[tier]

    # REFACTOR-4 origin tags (PH5-3, 2026-07-18). "dream" is stamped by the
    # dream apply path, never claimed via index_to_kb.
    ORIGINS = ("web", "human", "local-probe", "dream")

    @classmethod
    def apply_origin(cls, origin: str, tier: str, ceiling: float) -> tuple:
        """Normalize an origin tag and enforce the ASYMMETRIC TRUST RULE:
        web-origin content can never carry source_tier=ground_truth — a fetched
        page is at best a primary source; ground truth is reserved for output
        of commands/probes run against the live system (origin=local-probe) or
        operator statements (origin=human). Returns (origin, tier, ceiling, warn).
        """
        origin = origin if origin in cls.ORIGINS else "unspecified"
        warn = ""
        if origin == "web" and tier == "ground_truth":
            tier = "primary"
            ceiling = min(ceiling, cls.TIER_CEILING["primary"])
            warn = (
                " | ORIGIN DOWNGRADE: origin=web cannot carry "
                "source_tier=ground_truth (asymmetric trust rule) — stored as "
                "primary, ceiling 0.8. Ground truth requires origin=local-probe "
                "(live command output) or origin=human."
            )
        return origin, tier, ceiling, warn


class KBMixin:
    """KB/skill tool methods mixed into goethe.Tools. Uses self.valves,
    self._log, self._strip_years, self._budget_gate from the host class."""

    # ── RAG private helpers ──────────────────────────────────────────────────

    def _embed(self, text: str) -> list:
        """Embedding from the configured Ollama model (1024-dim in production)."""
        import requests  # noqa: PLC0415

        r = requests.post(
            f"{self.valves.OLLAMA_URL}/api/embed",
            json={
                "model": self.valves.EMBED_MODEL,
                "input": text[:5000],  # qwen3-embedding: no task prefix (nomic-only convention, removed 2026-07-19)
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["embeddings"][0]

    def _es(self):
        """Lazy Elasticsearch 8.x client."""
        from elasticsearch import Elasticsearch  # noqa: PLC0415

        return Elasticsearch(self.valves.ES_URL, request_timeout=10)

    # ── RAG tool functions ───────────────────────────────────────────────────

    def search_kb(
        self,
        query: str,
        min_score: float = 3.5,
        max_results: int = 5,
        topic_filter: str = "",
    ) -> str:
        """
        Search the LSE knowledge base using semantic + keyword hybrid search.

        KB-FIRST RULE — mandatory:
          ALWAYS call this before search_web or any SearxNG query.
          The KB contains curated, locally-verified technical knowledge about this system.
          Searching the web for something already in the KB is a protocol violation.

        RESULT QUALITY:
          Each result includes a quality_score (0.0–1.0):
            0.3 = stub / single fact — verify before using
            0.5 = rough first draft — usable but may be incomplete
            0.6 = reasonable coverage — good starting point
            0.8 = web-verified — cross-referenced with live source
            1.0 = authoritative — manually verified or official docs
          Each result also shows its age (updated Xd ago). STALENESS RULE:
          for tokens, paths, ports, and config values, a KB hit is a POINTER,
          not ground truth — verify against the live system (read_file /
          docker inspect) before using or quoting the value. Acting on a
          stale config value without a live read is a protocol violation.

        ON MISS:
          If this returns "KB miss", fall through to search_web(). Then call
          index_to_kb() with the best result to grow the KB for next time.

        Args:
            query:        Natural language search query.
            min_score:    HYBRID-score threshold (0.7·knn + 0.3·BM25 — BM25 is
                          unbounded, so real scores run ~3.5–16, NOT 0–1).
                          Default 3.5, calibrated for 1024-dim qwen3-embedding (2026-07-15): keeps 98% top-3, 75% total.
                          keeps 38/38 correct top-1 hits, rejects 3/11 wrong
                          ones, loses zero correct. (The old 0.72 default was
                          calibrated for cosine and filtered nothing.) Do not
                          hand-tune — re-run rag/eval_retrieval.py
                          --threshold-report after major KB growth instead.
            max_results:  Max results to return. Default 5.
            topic_filter: Optional topic tag: 'comfyui', 'wan2.1', 'searxng',
                          'llama-cpp', 'pfsense', 'infrastructure', 'openwebui'.
        """
        self._log(f"SEARCH-KB: {query}")
        _tb = self._consume_time_banner()  # CHRONOS-2 (v0.3.1)
        try:
            embedding = self._embed(query)
            es = self._es()
            filter_clause = [{"term": {"topic": topic_filter}}] if topic_filter else []
            body = {
                "knn": {
                    "field": "embedding",
                    "query_vector": embedding,
                    "k": max_results,
                    "num_candidates": 50,
                    "boost": 0.7,
                },
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["title^2", "content"],
                                    "boost": 0.3,
                                }
                            }
                        ],
                        "filter": filter_clause,
                    }
                },
                "_source": [
                    "title",
                    "content",
                    "source_path",
                    "source_url",
                    "topic",
                    "quality_score",
                    "updated_at",
                    "empirical_runs",
                    "success_count",
                    "failure_count",
                    "consecutive_failures",
                    "stale",
                    "volatility",
                ],
                "size": max_results,
            }
            resp = es.search(index="lse-kb", body=body)
            hits = [h for h in resp["hits"]["hits"] if h.get("_score", 0) >= min_score]
            if not hits:
                return _tb + (
                    f"KB miss — no results above threshold {min_score} for '{query}'.\n"
                    "Fall through to search_web(), then call index_to_kb() with quality results."
                )

            # CHRONOS-3 (v0.3.1): volatility TTLs — static=∞, slow=90d (default),
            # fast=7d. Age beyond TTL → [EXPIRED] tag + rerank demotion. This
            # replaces the retired 30d/7d docstring table with enforced metadata.
            _TTL_DAYS = {"static": None, "slow": 90, "fast": 7}

            def _age_days(s):
                try:
                    return max(
                        0,
                        (
                            datetime.now().astimezone()
                            - datetime.fromisoformat(s.get("updated_at") or "")
                        ).days,
                    )
                except Exception:
                    return None

            def _is_expired(s):
                ttl = _TTL_DAYS.get(s.get("volatility") or "slow", 90)
                age = _age_days(s)
                return ttl is not None and age is not None and age > ttl

            # KB-DECAY-2 (v0.3.0): client-side trust rerank. Penalize by verified
            # failure ratio (multiplier 1 − 0.3·fail/runs); halve stale (quarantined)
            # and expired docs so they always rank below fresh ones. Deliberately NOT
            # an ES function_score — measure with the gold set before moving server-side.
            def _trust_rank(h):
                s = h["_source"]
                runs = s.get("empirical_runs", 0) or 0
                fails = s.get("failure_count", 0) or 0
                mult = 1.0 - 0.3 * (fails / runs) if runs else 1.0
                # quality-weighted rank (2026-07-19): 0.35-quality design-doc
                # chunks stop outranking 0.7-quality specific ops docs
                mult *= 0.5 + (s.get("quality_score") or 0.5)
                if s.get("stale"):
                    mult *= 0.5
                if _is_expired(s):
                    mult *= 0.5
                return h.get("_score", 0) * mult

            hits.sort(key=_trust_rank, reverse=True)

            def _body(c, rank):
                c = (c or "").strip()
                cap = 3500 if rank == 1 else 900
                if len(c) <= cap:
                    return c
                return (
                    c[:cap].rstrip()
                    + f"\n    …[truncated {len(c) - cap} chars — "
                    "use read_file on source above for full text]"
                )
            lines = [f"KB results for '{query}' ({len(hits)} found):\n"]
            for i, h in enumerate(hits, 1):
                s = h["_source"]
                src = s.get("source_path") or s.get("source_url") or "unknown"
                _age_d = _age_days(s)
                _age = f"updated {_age_d}d ago" if _age_d is not None else "age unknown"
                _vol = s.get("volatility") or "slow"
                _runs = s.get("empirical_runs", 0) or 0
                _ok = s.get("success_count", 0) or 0
                _fail = s.get("failure_count", 0) or 0
                _trust = (
                    f"runs={_runs} ({_ok} ok/{_fail} fail)" if _runs else "untested"
                )
                _flags = ""
                if s.get("stale"):
                    _flags += "    [STALE — quarantined, verify live before use]\n"
                if _is_expired(s):
                    _flags += (
                        f"    [EXPIRED — {_vol} TTL exceeded; pointer only, "
                        "re-verify live before use]\n"
                    )
                lines.append(
                    f"[{i}] doc_id={h['_id']} | {s['title']} | topic={s['topic']} | "
                    f"quality={s['quality_score']:.2f} | score={h['_score']:.3f} | "
                    f"{_trust} | {_age} | volatility={_vol}\n"
                    f"{_flags}"
                    f"    source: {src}\n"
                    f"    (pass doc_id above to record_outcome/mentor_correct)\n"
                    f"    {_body(s['content'], i)}\n"
                )
            return _tb + "\n".join(lines)
        except Exception as e:
            self._log(f"SEARCH-KB ERROR: {e}")
            return f"KB search error: {e}\nFall through to search_web()."

    def _wf_version_claim(self, text: str) -> bool:
        """WATERFALL (v1.7.18): True if text makes an external-software
        version/behavior claim, e.g. 'removed in v9577', 'deprecated since 2.8.0',
        'changed in version 9'. Used to gate KB writes that lack provenance."""
        import re as _re  # noqa: PLC0415

        if not text:
            return False
        verb = (
            r"removed|added|introduced|deprecated|renamed|dropped|replaced|"
            r"disabled|enabled|broke|broken|changed|merged|landed|backported|"
            r"no longer (?:available|supported|present)|now (?:requires|defaults)"
        )
        ver = (
            r"v\d|version\s+\d|\d+\.\d+\.\d+|"
            r"\d+\.\d+(?!\s?(?:gb|mb|kb|tb|g\b|m\b|k\b|ghz|mhz|hz|sec|s\b|ms|%|x\b|hour|hr|min|day|am|pm))|"
            r"build\s+\d|release\s+\d|b\d{3,}"
        )
        pat = (
            r"(?i)(?:(?:" + verb + r")[^.\n]{0,40}?(?:" + ver + r")"
            r"|(?:since|as of|starting (?:in|with)|prior to|before|after)\s+(?:"
            + ver + r"))"
        )
        return bool(_re.search(pat, text))

    def _wf_has_provenance(
        self,
        text: str,
        source_url: str = "",
        evidence: str = "",
        verified_against: str = "",
    ) -> bool:
        """WATERFALL (v1.7.18): True if waterfall provenance is attached — a fetched
        URL, >=40 chars of ground-truth evidence, a version snapshot, or an inline
        URL / RFC / doc_id in the text itself."""
        import re as _re  # noqa: PLC0415

        if (source_url or "").strip().lower().startswith(("http://", "https://")):
            return True
        if len((evidence or "").strip()) >= 40:
            return True
        if (verified_against or "").strip():
            return True
        t = text or ""
        if _re.search(r"https?://", t):
            return True
        if _re.search(r"(?i)\bRFC\s*\d{3,5}", t):
            return True
        if _re.search(r"(?i)\bdoc_id[=:\s]", t):
            return True
        return False

    def index_to_kb(
        self,
        content: str,
        title: str,
        topic: str,
        source_url: str = "",
        quality_score: float = 0.5,
        source_tier: str = "inferred",
        evidence: str = "",
        verified_against: str = "",
        volatility: str = "slow",
        origin: str = "",
    ) -> str:
        """
        Index a document into the LSE knowledge base (lse-kb index).

        ORIGIN TAG (REFACTOR-4, mandatory for new docs):
          origin= declares WHERE the content came from:
            "web"         — fetched page / search result
            "human"       — operator told you
            "local-probe" — output of a command run against the live system
          Anything else is stored as "unspecified". ASYMMETRIC TRUST RULE:
          origin="web" can NEVER carry source_tier=ground_truth — it is
          auto-downgraded to primary (ceiling 0.8). origin="dream" is stamped
          by the dream apply path only; do not claim it here.

        WHEN TO CALL:
          After finding high-quality information from search_web() or Playwright
          that is not already in the KB, or that is better than what's there.
          Call AT MOST ONCE per user request, for the single best finding.
          Do NOT call search_kb() afterwards to verify — trust the return value.
          Do NOT call this if search_kb() already returned a hit with quality >= 0.6.

        DEDUPLICATION:
          If a nearly identical document already exists (cosine > 0.92), this
          UPDATES the existing entry rather than duplicating it. quality_score
          is raised to max(existing, new). The KB improves over time.

        WATERFALL PROVENANCE RULE (v1.7.18):
          Claims about external-software version/behavior ("X removed in v9577",
          "deprecated since 2.8.0") MUST carry waterfall provenance — set source_url=
          (fetched URL), evidence= (ground-truth tool output), or include an inline
          RFC / doc_id. Before such a claim, run the waterfall: search_kb -> vendor
          docs/README -> github -> search_web. An unprovenanced version/behavior claim
          is stored tagged [UNVERIFIED] at quality <=0.3 so it cannot pose as fact.

        Args:
            content:       Full text to index.
            title:         Human-readable title.
            topic:         Use existing tags: 'wan2.1', 'comfyui', 'stable-diffusion',
                           'llama-cpp', 'searxng', 'pfsense', 'openwebui',
                           'lse-operations', 'infrastructure', 'general'.
            source_url:    URL where found (empty string for local content).
            quality_score: 0.0–1.0. Hard-capped to source_tier ceiling
                           (see source_tier). Default 0.5.
            source_tier:   Tier of evidence. Sets quality ceiling:
                           ground_truth=1.0 (live system test, tool-result evidence
                           required); primary=0.8 (vendor docs, official README, RFC);
                           secondary=0.6 (community forums, SO, Reddit, blog posts);
                           inferred=0.4 (untested hypothesis, model inference).
                           Default=inferred. Omitting source_tier caps quality at 0.4.
            evidence:      Required for source_tier=ground_truth — paste the actual
                           tool-result output (HTTP response, command output, >=40
                           chars). Empty or thin evidence downgrades ceiling to 0.7.
            verified_against: Optional version/config snapshot this entry was
                           verified against, e.g. "pfSense Plus 26.03" or
                           "RUTX50 fw 07.23.4". Stored for staleness tracking.
            volatility:    CHRONOS-3 (v0.3.1) freshness class — how fast this fact
                           decays. 'static' (never expires: topology, hardware,
                           protocols), 'slow' (90d TTL: procedures, configs —
                           DEFAULT), 'fast' (7d TTL: versions, CVEs, firmware,
                           prices). Past its TTL a doc is tagged [EXPIRED] in
                           search_kb and demoted below fresh hits. Re-verifying
                           via record_outcome(success=True) resets the clock.
        """
        import hashlib  # noqa: PLC0415
        from datetime import timezone  # noqa: PLC0415

        tier, ceiling = TrustPolicy.ceiling(source_tier)
        origin, tier, ceiling, origin_warn = TrustPolicy.apply_origin(origin, tier, ceiling)
        volatility = volatility if volatility in ("static", "slow", "fast") else "slow"
        tier_warn = origin_warn
        if tier == "ground_truth" and len((evidence or "").strip()) < 40:
            ceiling = 0.7
            tier_warn = (
                " | TIER DOWNGRADE: source_tier=ground_truth requires evidence "
                ">=40 chars from a real tool result (HTTP response/command output). "
                "Ceiling capped at 0.7 — re-index with evidence= to unlock 1.0."
            )
        wf_warn = ""
        if self._wf_version_claim(content) and not self._wf_has_provenance(
            content, source_url, evidence, verified_against
        ):
            ceiling = min(ceiling, 0.3)
            tier = "inferred"
            content = (
                "[UNVERIFIED: external version/behavior claim, no waterfall provenance] "
                + content
            )
            wf_warn = (
                " | WATERFALL: version/behavior claim about external software with no "
                "provenance (KB doc_id / fetched URL / RFC). Stored UNVERIFIED, quality "
                "capped <=0.3. Run search_kb -> vendor docs/README -> github -> "
                "search_web, then re-index with source_url= or evidence=."
            )
        quality_score = min(float(quality_score), ceiling)
        self._log(
            f"INDEX-KB: title={title} topic={topic} tier={tier} quality={quality_score}"
        )
        # Store full content (up to 50000 chars); embed only first 8000 (nomic-embed-text token limit)
        content = content[:50000]
        embed_content = content[:8000]
        try:
            embedding = self._embed(embed_content)
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            doc_hash = hashlib.sha256(content[:500].encode()).hexdigest()[:16]
            dup_resp = es.search(
                index="lse-kb",
                body={
                    "knn": {
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": 1,
                        "num_candidates": 10,
                    },
                    "_source": ["quality_score", "refinement_count", "version"],
                    "size": 1,
                },
            )
            dup_hits = dup_resp["hits"]["hits"]
            if dup_hits and dup_hits[0]["_score"] >= 0.92:
                existing = dup_hits[0]
                new_q = min(
                    1.0, max(existing["_source"]["quality_score"], quality_score)
                )
                _dup_doc = {
                    "content": content,
                    "embedding": embedding,
                    "quality_score": new_q,
                    "refinement_count": existing["_source"]["refinement_count"] + 1,
                    "updated_at": now,
                    "version": existing["_source"]["version"] + 1,
                    "source_url": source_url or None,
                    "volatility": volatility,
                    **({"origin": origin} if origin != "unspecified" else {}),
                }
                # KB-DECAY recovery: re-indexing with tier-gated evidence above
                # the quarantine floor clears stale + the failure streak.
                if new_q > 0.2:
                    _dup_doc["stale"] = False
                    _dup_doc["consecutive_failures"] = 0
                es.update(
                    index="lse-kb",
                    id=existing["_id"],
                    body={"doc": _dup_doc},
                )
                es.update(
                    index="lse-kb",
                    id=existing["_id"],
                    body={
                        "doc": {
                            "source_tier": tier,
                            "evidence": (evidence or "").strip()[:1000] or None,
                            "verified_against": (verified_against or "").strip()
                            or None,
                        }
                    },
                )
                return (
                    f"KB updated (refined): doc_id={existing['_id']} | "
                    f"quality {existing['_source']['quality_score']:.2f} → {new_q:.2f} | "
                    f"refinements={existing['_source']['refinement_count'] + 1} | "
                    f"tier={tier}{tier_warn}{wf_warn}"
                )
            doc = {
                "doc_id": doc_hash,
                "title": title,
                "content": content,
                "source_path": None,
                "source_url": source_url or None,
                "topic": topic,
                "tags": [topic],
                "quality_score": quality_score,
                "refinement_count": 0,
                "embedding": embedding,
                "created_at": now,
                "updated_at": now,
                "version": 1,
                "source_tier": tier,
                "evidence": (evidence or "").strip()[:1000] or None,
                "verified_against": (verified_against or "").strip() or None,
                "volatility": volatility,
                "origin": origin,
            }
            es.index(index="lse-kb", id=doc_hash, document=doc)
            return (
                f"KB created: doc_id={doc_hash} | title='{title}' | "
                f"topic={topic} | tier={tier} | quality={quality_score:.2f}{tier_warn}{wf_warn}"
            )
        except Exception as e:
            self._log(f"INDEX-KB ERROR: {e}")
            return f"KB index error: {e}"

    def record_error(self, error_text: str, context: str, resolution: str) -> str:
        """
        Record an error and its resolution to the LSE error knowledge base.

        MANDATORY — call this after recovering from ANY mistake:
          After fixing any error (command failure, wrong path, permission denied,
          wrong flag, broken pipe, etc.), call this so the same mistake is never
          made again in any future session.

        Args:
            error_text:  The exact error message or clear description of the failure.
            context:     What you were trying to do when the error occurred.
            resolution:  Exactly what fixed it.
        """
        import hashlib, re  # noqa: PLC0415
        from datetime import timezone  # noqa: PLC0415

        self._log(f"RECORD-ERROR: {error_text[:80]}")
        wf_note = ""
        if self._wf_version_claim(resolution) and not self._wf_has_provenance(resolution):
            resolution = "[UNVERIFIED CLAIM] " + resolution
            wf_note = (
                " | WATERFALL: resolution makes an external version/behavior claim with "
                "no provenance — tagged UNVERIFIED. Attach a fetched URL or RFC ref."
            )
        try:
            embedding = self._embed(error_text + " " + context)
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            normalised = re.sub(r"\s+", " ", error_text.lower().strip())
            error_hash = hashlib.sha256(normalised.encode()).hexdigest()[:16]
            dup_resp = es.search(
                index="lse-errors-1024",
                body={
                    "knn": {
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": 1,
                        "num_candidates": 10,
                    },
                    "_source": ["occurrence_count"],
                    "size": 1,
                },
            )
            dup_hits = dup_resp["hits"]["hits"]
            if dup_hits and dup_hits[0]["_score"] >= 0.90:
                existing = dup_hits[0]
                new_count = existing["_source"]["occurrence_count"] + 1
                es.update(
                    index="lse-errors-1024",
                    id=existing["_id"],
                    body={
                        "doc": {
                            "last_seen": now,
                            "occurrence_count": new_count,
                            "resolution": resolution,
                        }
                    },
                )
                return f"Error KB updated: known error now seen {new_count}x. Resolution updated.{wf_note}"
            doc = {
                "error_hash": error_hash,
                "error_text": error_text,
                "context": context,
                "resolution": resolution,
                "embedding": embedding,
                "occurrence_count": 1,
                "first_seen": now,
                "last_seen": now,
            }
            es.index(index="lse-errors-1024", id=error_hash, document=doc)
            return f"Error KB created: new error pattern recorded (hash={error_hash}).{wf_note}"
        except Exception as e:
            self._log(f"RECORD-ERROR ERROR: {e}")
            return f"Error KB record failed: {e}"

    def check_error_kb(self, error_text: str) -> str:
        """
        Check if an error has been seen before and retrieve its known resolution.

        KB-FIRST RULE — call this BEFORE any operation that might fail in a known way.
          Surface the resolution immediately rather than hitting the same failure again.

        Args:
            error_text: The error message or description to look up.
        """
        self._log(f"CHECK-ERROR-KB: {error_text[:80]}")
        try:
            embedding = self._embed(error_text)
            es = self._es()
            resp = es.search(
                index="lse-errors-1024",
                body={
                    "knn": {
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": 1,
                        "num_candidates": 10,
                    },
                    "_source": [
                        "error_text",
                        "resolution",
                        "occurrence_count",
                        "last_seen",
                    ],
                    "size": 1,
                },
            )
            hits = resp["hits"]["hits"]
            if hits and hits[0]["_score"] >= 0.88:
                h = hits[0]["_source"]
                return (
                    f"⚠️ KNOWN ERROR (seen {h['occurrence_count']}x, "
                    f"last: {h['last_seen'][:10]})\n"
                    f"Error: {h['error_text'][:200]}\n"
                    f"Resolution: {h['resolution']}\n"
                    f"Apply the known resolution — do not repeat the failed approach."
                )
            return (
                "Not seen before — proceed carefully. "
                "Call record_error() after resolving to prevent recurrence."
            )
        except Exception as e:
            self._log(f"CHECK-ERROR-KB ERROR: {e}")
            return f"Error KB check failed: {e}. Proceed with caution."

    def _resolve_kb_id(self, es, ref: str):
        """Resolve a KB reference to the real Elasticsearch _id (v0.2.1).

        Accepts either the 16-char doc hash (_id) OR a human title — the model
        frequently passes the title, which es.get(id=...) 404s on (the
        mentor_correct/record_outcome failure mode). Returns (doc_id, note) on
        success or (None, message) with actionable guidance on failure."""
        ref = (ref or "").strip()
        if not ref:
            return None, "empty doc_id"
        # 1) exact _id hit
        try:
            if es.exists(index="lse-kb", id=ref):
                return ref, "matched by id"
        except Exception:
            pass
        # 2) fall back to an exact-title lookup
        try:
            r = es.search(
                index="lse-kb",
                body={
                    "query": {"match_phrase": {"title": ref}},
                    "_source": ["title"],
                    "size": 5,
                },
            )
            hits = r["hits"]["hits"]
        except Exception as e:
            return None, f"KB lookup error: {e}"
        if len(hits) == 1:
            return hits[0]["_id"], f"resolved title -> doc_id {hits[0]['_id']}"
        if not hits:
            return None, (
                f"no KB doc with id or title '{ref}'. Run search_kb() to get the "
                "exact doc_id (now shown as 'doc_id=...' in results), or use "
                "index_to_kb() to create the entry if it does not exist yet."
            )
        cands = ", ".join(h["_id"] for h in hits[:5])
        return None, (
            f"{len(hits)} KB docs match the title '{ref}' — pass the exact doc_id "
            f"from search_kb. Candidates: {cands}"
        )

    def record_outcome(
        self,
        doc_id: str,
        success: bool,
        notes: str = "",
        evidence: str = "",
    ) -> str:
        """
        Record an operational outcome against an existing KB document.

        WHEN TO CALL:
          After applying a procedure documented in the KB:
            success=True  — the documented approach worked as described.
            success=False — it failed or needed modification. Also call record_error().

          Increments empirical_runs, success_count, and failure_count on the KB doc
          so the LSE can track how many times a procedure has been tested in production
          and whether it reliably works.

        DEMOTION (v0.3.0, KB-DECAY-1 — applied server-side, do not compute yourself):
          success=False WITH evidence (>=20 chars of real tool output) demotes the doc:
            quality_score = max(0.2, quality − 0.15) and consecutive_failures += 1.
          At the 0.2 floor the doc is QUARANTINED: stale=true. It is never deleted —
          search_kb shows it with a [STALE] banner and ranks it below fresh docs.
          Quality is regained ONLY via the tier-gated paths (index_to_kb with better
          evidence, or a human mentor_correct) — a later success does NOT re-elevate.
          success=False WITHOUT evidence still counts the failure but does NOT demote —
          unverified failure claims must not erode the KB (same gate as skill_outcome).
          success=True resets consecutive_failures to 0. quality_score is untouched.

        EVIDENCE:
          GOOD: evidence="curl :8080/health → 404; systemctl is-active llama → inactive"
          BAD:  evidence="didn't work"   ← thin self-report, no demotion applied

        Args:
            doc_id:   The doc_id field from a search_kb or index_to_kb result.
            success:  True if the procedure succeeded, False if it failed.
            notes:    Optional context: variant used, environment, what differed, etc.
            evidence: For failures: the actual tool/command output proving the doc is
                      wrong (>=20 chars). Required to trigger demotion.
        """
        from datetime import timezone  # noqa: PLC0415

        self._log(f"RECORD-OUTCOME: doc_id={doc_id} success={success}")
        evidence = (evidence or "").strip()[:500]
        try:
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            resolved, note = self._resolve_kb_id(es, doc_id)
            if not resolved:
                return f"record_outcome: {note}"
            doc_id = resolved
            resp = es.get(
                index="lse-kb",
                id=doc_id,
                _source=[
                    "empirical_runs",
                    "success_count",
                    "failure_count",
                    "title",
                    "quality_score",
                    "consecutive_failures",
                    "stale",
                ],
            )
            src = resp["_source"]
            runs = src.get("empirical_runs", 0) + 1
            success_count = src.get("success_count", 0) + (1 if success else 0)
            failure_count = src.get("failure_count", 0) + (0 if success else 1)
            old_q = src.get("quality_score", 0.0)
            update: dict = {
                "empirical_runs": runs,
                "success_count": success_count,
                "failure_count": failure_count,
                "last_outcome_at": now,
            }
            if notes:
                update["last_outcome_notes"] = notes
            decay_note = ""
            if success:
                # KB-DECAY-1: verified success ends the failure streak but does
                # NOT re-elevate quality — that stays tier-gated (index_to_kb /
                # mentor_correct). stale stays until a tier-gated raise clears it.
                # CHRONOS-3 (v0.3.1): a verified success IS a re-verification —
                # bump updated_at so the volatility TTL clock resets and an
                # [EXPIRED] tag clears.
                update["updated_at"] = now
                if src.get("consecutive_failures", 0):
                    update["consecutive_failures"] = 0
                    decay_note = " | failure streak reset"
            elif len(evidence) >= 20:
                new_q = max(0.2, old_q - 0.15)
                streak = src.get("consecutive_failures", 0) + 1
                update["quality_score"] = new_q
                update["consecutive_failures"] = streak
                update["last_failure_evidence"] = evidence
                if new_q <= 0.2:
                    update["stale"] = True
                    decay_note = (
                        f" | DEMOTED {old_q:.2f} → {new_q:.2f} (streak={streak}) | "
                        f"STALE — quarantined at the 0.2 floor; kept for forensics, "
                        f"re-verify live before ever using this entry"
                    )
                else:
                    decay_note = f" | DEMOTED {old_q:.2f} → {new_q:.2f} (streak={streak})"
            else:
                decay_note = (
                    " | failure counted but NOT demoted — no evidence supplied. "
                    "Pass evidence= (>=20 chars of real tool output) to demote a "
                    "wrong KB entry."
                )
            es.update(index="lse-kb", id=doc_id, body={"doc": update})
            outcome_str = "✅ success" if success else "❌ failure"
            return (
                f"Outcome recorded: {outcome_str} | "
                f"doc='{src.get('title', doc_id)}' | "
                f"runs={runs} ({success_count} success / {failure_count} failure)"
                f"{decay_note}"
            )
        except Exception as e:
            self._log(f"RECORD-OUTCOME ERROR: {e}")
            return f"record_outcome failed: {e}"

    def mentor_correct(
        self,
        doc_id: str,
        correction: str,
        new_quality: float,
    ) -> str:
        """
        Apply a human-authored correction to an existing KB document.

        WHEN TO CALL:
          When the user identifies an error, outdated information, or an important
          improvement in a KB entry. Replaces the document content with the corrected
          version, re-embeds it, and raises the quality score.

        QUALITY RULE:
          This function never lowers the quality score. If new_quality is lower than
          the existing score, the call is rejected. Use index_to_kb to add a competing
          entry at a lower quality instead.

        Args:
            doc_id:       The doc_id of the KB entry to correct — the 'doc_id=...'
                          value shown in search_kb results (NOT the title). A title
                          is accepted as a fallback and resolved automatically; if
                          it matches no entry you get a clear message (use
                          index_to_kb to create a new entry instead).
            correction:   The full corrected content to replace the existing entry.
            new_quality:  New quality score (0.0–1.0).
                          Use 0.95–1.0 for human-verified corrections.
        """
        from datetime import timezone  # noqa: PLC0415

        self._log(f"MENTOR-CORRECT: doc_id={doc_id} new_quality={new_quality}")
        try:
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            resolved, note = self._resolve_kb_id(es, doc_id)
            if not resolved:
                return f"mentor_correct: {note}"
            doc_id = resolved
            resp = es.get(
                index="lse-kb",
                id=doc_id,
                _source=["quality_score", "refinement_count", "title"],
            )
            src = resp["_source"]
            old_quality = src.get("quality_score", 0.0)
            if new_quality < old_quality:
                return (
                    f"REJECTED: new_quality ({new_quality:.2f}) is lower than existing "
                    f"({old_quality:.2f}). mentor_correct must not lower quality. "
                    f"Use index_to_kb to add a competing entry instead."
                )
            embedding = self._embed(correction)
            _mc_doc = {
                "content": correction,
                "embedding": embedding,
                "quality_score": new_quality,
                "refinement_count": src.get("refinement_count", 0) + 1,
                "updated_at": now,
                "mentor_corrected_at": now,
            }
            # KB-DECAY recovery: a human correction above the quarantine floor
            # is THE tier-gated re-elevation path — clear stale + failure streak.
            if new_quality > 0.2:
                _mc_doc["stale"] = False
                _mc_doc["consecutive_failures"] = 0
            es.update(index="lse-kb", id=doc_id, body={"doc": _mc_doc})
            return (
                f"Mentor correction applied: doc='{src.get('title', doc_id)}' | "
                f"quality {old_quality:.2f} → {new_quality:.2f} | "
                f"refinements={src.get('refinement_count', 0) + 1}"
            )
        except Exception as e:
            self._log(f"MENTOR-CORRECT ERROR: {e}")
            return f"mentor_correct failed: {e}"

    def kb_verify(self, doc_id: str, observed: str = "") -> str:
        """
        Verify a KB document's recorded version/config snapshot against the live
        system — the "application updated → KB silently wrong" regression detector
        (v0.3.0, KB-DECAY-3).

        TWO-PHASE PROTOCOL:
          Phase 1 — kb_verify(doc_id):
            Returns the stored verified_against snapshot plus probe instructions.
            YOU then run the live probe with existing tools (get_github_release,
            read_file, execute_command 'cat /etc/os-release', service --version, …).
          Phase 2 — kb_verify(doc_id, observed=<probe output>):
            Compares the snapshot against your probe output.
            MATCH    → auto record_outcome(success=True) — updated_at refreshed,
                       failure streak reset.
            MISMATCH → auto record_outcome(success=False, evidence=<probe output>)
                       — the KB-DECAY-1 demotion fires; the doc is on its way to
                       the 0.2 stale quarantine if it keeps failing verification.

        GATE:
          observed must be REAL probe output (>=20 chars), pasted verbatim.
          Passing a summary or a claim instead of tool output is a protocol
          violation — the comparison and the demotion evidence are only as
          trustworthy as the probe text.
          GOOD: observed="pfSense Plus 26.03-RELEASE (amd64) built on Thu Jun 12"
                ← verbatim tool output, comparable token by token
          BAD:  observed="the version matches what the KB says"
                ← a claim, not output. Do NOT paraphrase probe results.
          Do NOT call phase 2 with output from memory or an earlier session —
          the probe must have run THIS session.

        WHEN TO CALL:
          - Before acting on any KB doc whose verified_against names a version,
            firmware, or config snapshot ("pfSense Plus 26.03", "RUTX50 fw 07.23.4").
          - After any known upgrade of a system the KB documents.
          - When search_kb shows a doc as untested or with failures.

        Args:
            doc_id:   The doc_id from search_kb/index_to_kb results (title accepted).
            observed: Phase 2 only — verbatim live-probe output to compare against
                      the stored snapshot.
        """
        self._log(f"KB-VERIFY: doc_id={doc_id} phase={'2' if observed else '1'}")
        observed = (observed or "").strip()
        try:
            es = self._es()
            resolved, note = self._resolve_kb_id(es, doc_id)
            if not resolved:
                return f"kb_verify: {note}"
            doc_id = resolved
            resp = es.get(
                index="lse-kb",
                id=doc_id,
                _source=["title", "verified_against", "source_url", "updated_at",
                         "quality_score", "stale"],
            )
            src = resp["_source"]
            va = (src.get("verified_against") or "").strip()
            title = src.get("title", doc_id)
            if not va:
                return (
                    f"kb_verify: doc '{title}' has NO verified_against snapshot — "
                    "nothing to regression-check. If you verify it against the live "
                    "system now, re-index with verified_against= set (index_to_kb "
                    "dedup will update the existing entry)."
                )
            if not observed:
                return (
                    f"kb_verify phase 1 — doc '{title}' (doc_id={doc_id})\n"
                    f"  verified_against: {va}\n"
                    f"  quality={src.get('quality_score', 0):.2f}"
                    f"{' | STALE' if src.get('stale') else ''} | "
                    f"last updated: {str(src.get('updated_at', ''))[:10]}\n"
                    "NEXT: probe the live system for this exact version/config "
                    "(get_github_release / read_file / execute_command), then call "
                    f"kb_verify('{doc_id}', observed=<verbatim probe output>)."
                )
            if len(observed) < 20:
                return (
                    "kb_verify rejected: observed is too thin (<20 chars) to be real "
                    "probe output. Paste the verbatim tool result, not a claim."
                )
            # Normalized containment check: every token of the snapshot should
            # appear in the probe output for a match (case-insensitive).
            import re as _re  # noqa: PLC0415

            va_tokens = [t for t in _re.split(r"[\s,;/]+", va.lower()) if t]
            obs_l = observed.lower()
            missing = [t for t in va_tokens if t not in obs_l]
            if not missing:
                outcome = self.record_outcome(
                    doc_id, success=True,
                    notes=f"kb_verify: snapshot '{va}' confirmed against live probe",
                )
                return (
                    f"kb_verify MATCH ✅ — '{title}': live system still matches "
                    f"verified_against '{va}'.\n{outcome}"
                )
            outcome = self.record_outcome(
                doc_id, success=False,
                notes="kb_verify regression",
                evidence=(
                    f"verified_against regression: recorded '{va}' but live probe "
                    f"shows: {observed[:300]}"
                ),
            )
            return (
                f"kb_verify MISMATCH ❌ — '{title}': recorded '{va}' but the live "
                f"probe does not contain: {', '.join(missing[:5])}.\n"
                f"The entry has been demoted with the probe as evidence.\n{outcome}\n"
                "If the doc is still conceptually right, re-verify its content and "
                "re-index with the NEW verified_against snapshot."
            )
        except Exception as e:
            self._log(f"KB-VERIFY ERROR: {e}")
            return f"kb_verify failed: {e}"

    def mentor_demote(self, doc_id: str, new_quality: float, reason: str) -> str:
        """
        HUMAN-AUTHORIZED demotion of a KB document's quality score
        (v0.3.0, KB-DECAY-4).

        AUTHORIZATION GATE — mandatory, no exceptions:
          Call this ONLY when the human user has explicitly said this specific KB
          entry is wrong or overrated IN THIS SESSION. Never call it on your own
          judgment — model-initiated demotion is a protocol violation (the pfSense
          trust-metadata incident, P26). Evidence-based demotion you may perform
          yourself goes through record_outcome(success=False, evidence=...) instead.
          GOOD: user says "that RUTX50 wake-procedure doc is wrong, knock it
                down" → mentor_demote with their words as reason
          BAD:  kb_verify MISMATCH, a failed probe, or your own reasoning says
                a doc is outdated → record_outcome(success=False, evidence=…),
                NOT mentor_demote. Human words authorize; evidence demotes.

        WHY THIS EXISTS:
          mentor_correct is raise-only by design. Before v0.3.0 the only way to
          neutralise a wrong high-quality doc was a competing entry — which the
          wrong doc kept outranking. This is the direct human kill-switch.

        EFFECT:
          quality_score set to new_quality (must be LOWER than current — use
          mentor_correct to raise). new_quality <= 0.2 → stale=true quarantine
          (never deleted; search_kb shows the [STALE] banner). reason is stored
          on the doc as demote_reason for forensics.

        Args:
            doc_id:      The doc_id from search_kb results (title accepted).
            new_quality: New score, 0.0–1.0, strictly below the current one.
            reason:      Why the human demoted it (>=10 chars, stored on the doc).

        Trust the return value — do NOT call search_kb afterwards to confirm
        the new score.
        """
        from datetime import timezone  # noqa: PLC0415

        self._log(f"MENTOR-DEMOTE: doc_id={doc_id} new_quality={new_quality}")
        reason = (reason or "").strip()
        try:
            if len(reason) < 10:
                return (
                    "mentor_demote rejected: reason is required (>=10 chars) — it is "
                    "the forensic record of why a human pulled this entry down."
                )
            new_quality = max(0.0, min(float(new_quality), 1.0))
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            resolved, note = self._resolve_kb_id(es, doc_id)
            if not resolved:
                return f"mentor_demote: {note}"
            doc_id = resolved
            resp = es.get(
                index="lse-kb", id=doc_id, _source=["quality_score", "title"]
            )
            src = resp["_source"]
            old_quality = src.get("quality_score", 0.0)
            if new_quality >= old_quality:
                return (
                    f"REJECTED: new_quality ({new_quality:.2f}) is not lower than "
                    f"existing ({old_quality:.2f}). mentor_demote only lowers — "
                    "use mentor_correct to raise."
                )
            update = {
                "quality_score": new_quality,
                "mentor_demoted_at": now,
                "demote_reason": reason[:500],
                "updated_at": now,
            }
            stale_note = ""
            if new_quality <= 0.2:
                update["stale"] = True
                stale_note = " | STALE — quarantined (kept for forensics)"
            es.update(index="lse-kb", id=doc_id, body={"doc": update})
            return (
                f"Mentor demotion applied: doc='{src.get('title', doc_id)}' | "
                f"quality {old_quality:.2f} → {new_quality:.2f}{stale_note} | "
                f"reason: {reason[:120]}"
            )
        except Exception as e:
            self._log(f"MENTOR-DEMOTE ERROR: {e}")
            return f"mentor_demote failed: {e}"

    # ── v1.5.17: Log / scan summarisers ──────────────────────────────────────

    # ── Skills layer (v1.7.0 — lse-skills index) ────────────────────────────

    def skill_search(
        self, task: str, occupation: str = "", max_results: int = 2
    ) -> str:
        """
        Search the LSE skills index (lse-skills) for a PROCEDURE matching the task.

        SKILLS-FIRST RULE — mandatory:
          Before starting any multi-step or procedural operation (cleanup, restart,
          migration, hardening, recovery), call this BEFORE search_kb. Skills are
          runbook-shaped: preconditions → procedure → verification → failure modes.
          Skipping skill_search before a multi-step operation is a protocol violation.

        SKILLS vs FACTS:
          GOOD: skill_search("safely delete duplicate model files")
                ← procedural task: needs steps, safety gates, verification
          BAD:  skill_search("what port does llama-server use")
                ← single fact: use search_kb instead
          If this returns no skill, fall back to search_kb, then proceed carefully.

        GATE: never call more than once per task; max_results is capped at 2 to
        protect the context budget — do NOT request more.

        Args:
            task:        What you are about to do, in plain language.
            occupation:  Optional filter: 'linux-sysadmin', 'network-engineer',
                         'sre', 'dba', 'security-analyst'.
            max_results: Max skills returned (1-2). Default 2.
        """
        self._log(f"SKILL-SEARCH: {task} occupation={occupation}")
        max_results = max(1, min(int(max_results), 2))
        try:
            embedding = self._embed(task)
            es = self._es()
            filters = [{"term": {"archived": False}}]
            if occupation:
                filters.append({"term": {"occupation": occupation}})
            body = {
                "knn": {
                    "field": "embedding",
                    "query_vector": embedding,
                    "k": max_results,
                    "num_candidates": 50,
                    "boost": 0.7,
                },
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": task,
                                    "fields": ["task^2", "procedure"],
                                    "boost": 0.3,
                                }
                            }
                        ],
                        "filter": filters,
                    }
                },
                "_source": [
                    "skill_id",
                    "occupation",
                    "task",
                    "preconditions",
                    "procedure",
                    "verification",
                    "failure_modes",
                    "provenance",
                    "quality",
                    "stats",
                    "pinned",
                ],
                "size": max_results,
            }
            resp = es.search(index="lse-skills", body=body)
            hits = [h for h in resp["hits"]["hits"] if h.get("_score", 0) >= 0.72]
            if not hits:
                return (
                    f"SKILL miss — no procedure above threshold for '{task}'.\n"
                    "Fall back to search_kb. If you then complete the task with a "
                    "ground-truth-verified outcome, record the procedure with skill_record()."
                )
            # Update usage stats (best-effort; retrieval must not fail on stats)
            lines = [f"SKILLS for '{task}' ({len(hits)} found):\n"]
            for i, h in enumerate(hits, 1):
                s = h["_source"]
                try:
                    es.update(
                        index="lse-skills",
                        id=h["_id"],
                        body={
                            "script": {
                                "source": (
                                    "ctx._source.stats.uses += 1; "
                                    "ctx._source.stats.last_used = params.now"
                                ),
                                "params": {
                                    "now": datetime.now().astimezone().isoformat()
                                },
                            }
                        },
                    )
                except Exception:
                    pass
                st = s.get("stats", {})
                lines.append(
                    f"[{i}] {s['skill_id']} | quality={s['quality']:.2f} | "
                    f"uses={st.get('uses', 0)} "
                    f"(ok={st.get('episode_successes', 0)}/fail={st.get('episode_failures', 0)})"
                    f"{' | PINNED' if s.get('pinned') else ''}\n"
                    f"    TASK: {s['task']}\n"
                    f"    PRECONDITIONS: {'; '.join(s.get('preconditions') or []) or '(none)'}\n"
                    f"    PROCEDURE: {' -> '.join(s.get('procedure') or [])}\n"
                    f"    VERIFY: {s.get('verification', '')}\n"
                    f"    FAILURE MODES: {'; '.join(s.get('failure_modes') or []) or '(none)'}\n"
                    f"    (report the outcome with skill_outcome('{s['skill_id']}', ...) "
                    f"after ground-truth verification)\n"
                )
            return "\n".join(lines)
        except Exception as e:
            self._log(f"SKILL-SEARCH ERROR: {e}")
            return f"SKILL search error: {e}\nFall back to search_kb()."

    def skill_record(
        self,
        task: str,
        occupation: str,
        procedure: str,
        verification: str,
        preconditions: str = "",
        failure_modes: str = "",
        provenance: str = "",
        quality: float = 0.5,
        source_tier: str = "inferred",
    ) -> str:
        """
        Record a PROVEN procedure as a skill in the lse-skills index.

        EVIDENCE GATE — mandatory:
          Only call after the procedure was executed AND its outcome verified by a
          ground-truth check (verify_ssh, file/state probe, service health).
          Recording an unverified or self-reported procedure is a protocol violation.

        WHAT IS A SKILL:
          GOOD: task="free disk space by removing duplicates",
                procedure="enumerate; readlink -f + stat %i BOTH paths; verify
                survivor sha256; delete; df delta"  ← steps with safety gates
          BAD:  task="llama-server port", procedure="8080"
                ← that is a fact: use index_to_kb instead

        DEDUPLICATION:
          Near-identical skills (cosine > 0.92) are UPDATED, not duplicated;
          quality rises to max(existing, new). Trust the return value — do NOT
          call skill_search afterwards to verify the write.

        Args:
            task:          One-line description of what the skill accomplishes.
            occupation:    'linux-sysadmin', 'network-engineer', 'sre', 'dba',
                           'security-analyst'.
            procedure:     Ordered steps, separated by ';' or newlines.
            verification:  How success is confirmed (ground-truth command/check).
            preconditions: Required access/state, ';'-separated. Optional.
            failure_modes: Known ways this goes wrong, ';'-separated. Optional.
            provenance:    Episode id, URL, or incident doc reference. Optional
                           but strongly expected — unattributed skills are flagged.
            quality:       0.0-1.0. Episode-verified=0.5, cross-referenced=0.7.
                           Never start above 0.7.
            source_tier:   Evidence tier for this skill (same scale as index_to_kb).
                           ground_truth=1.0 ceiling (live test); primary=0.8;
                           secondary=0.6; inferred=0.4. Stored in document.
        """
        if (provenance or "").lower().startswith("dream") and os.environ.get(
            "GOETHE_DREAM_APPLY"
        ) != "1":
            return (
                f"SKILL rejected: provenance '{provenance}' is dream-cycle output. "
                "Dream proposals must pass the human gate via dream_apply.py -- "
                "direct skill_record is not permitted for them. "
                "Run: python3 tools/dream_apply.py --queue"
            )
        import hashlib  # noqa: PLC0415
        import re  # noqa: PLC0415

        self._log(f"SKILL-RECORD: occupation={occupation} task={task[:80]}")
        sk_tier, _sk_ceiling = TrustPolicy.ceiling(source_tier)
        quality = max(0.2, min(float(quality), 0.7, _sk_ceiling))
        _split = lambda s: [p.strip() for p in re.split(r"[;\n]+", s) if p.strip()]
        steps = _split(procedure)
        if len(steps) < 2:
            return (
                "SKILL rejected: procedure has fewer than 2 steps — that is a "
                "fact, not a skill. Use index_to_kb() instead."
            )
        if not verification.strip():
            return "SKILL rejected: verification is required (P2 — evidence-gated)."
        try:
            embed_text = f"{occupation}: {task}\n" + "\n".join(steps)
            embedding = self._embed(embed_text[:8000])
            es = self._es()
            now = datetime.now().astimezone().isoformat()
            dup = es.search(
                index="lse-skills",
                body={
                    "knn": {
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": 1,
                        "num_candidates": 10,
                    },
                    "_source": ["skill_id", "quality", "version"],
                    "size": 1,
                },
            )["hits"]["hits"]
            if dup and dup[0]["_score"] >= 0.92:
                ex = dup[0]
                new_q = min(0.7, max(ex["_source"]["quality"], quality))
                es.update(
                    index="lse-skills",
                    id=ex["_id"],
                    body={
                        "doc": {
                            "task": task,
                            "procedure": steps,
                            "preconditions": _split(preconditions),
                            "failure_modes": _split(failure_modes),
                            "verification": verification,
                            "provenance": _split(provenance),
                            "embedding": embedding,
                            "quality": new_q,
                            "updated_at": now,
                            "version": ex["_source"].get("version", 1) + 1,
                            "archived": False,
                            "source_tier": sk_tier,
                        }
                    },
                )
                return (
                    f"SKILL updated: {ex['_source']['skill_id']} | "
                    f"quality {ex['_source']['quality']:.2f} -> {new_q:.2f}"
                )
            slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:60]
            skill_id = f"{occupation}/{slug}"
            doc_id = hashlib.sha256(skill_id.encode()).hexdigest()[:16]
            es.index(
                index="lse-skills",
                id=doc_id,
                document={
                    "skill_id": skill_id,
                    "occupation": occupation,
                    "task": task,
                    "preconditions": _split(preconditions),
                    "procedure": steps,
                    "verification": verification,
                    "failure_modes": _split(failure_modes),
                    "provenance": _split(provenance) or ["UNATTRIBUTED"],
                    "embedding": embedding,
                    "quality": quality,
                    "stats": {
                        "uses": 0,
                        "episode_successes": 0,
                        "episode_failures": 0,
                        "last_used": None,
                    },
                    "pinned": False,
                    "archived": False,
                    "created_at": now,
                    "updated_at": now,
                    "version": 1,
                    "source_tier": sk_tier,
                },
            )
            flag = "" if provenance.strip() else " | FLAGGED: no provenance"
            return f"SKILL created: {skill_id} | quality={quality:.2f}{flag}"
        except Exception as e:
            self._log(f"SKILL-RECORD ERROR: {e}")
            return f"SKILL record error: {e}"

    def skill_outcome(
        self,
        skill_id: str,
        success: bool,
        evidence: str,
        source_tier: str = "secondary",
    ) -> str:
        """
        Report a VERIFIED outcome for a skill that was injected/used this task.

        EVIDENCE GATE — mandatory:
          success=True requires ground-truth verification output in evidence
          (verify_ssh result, health check, state probe). The model's own claim
          of success is NOT evidence — passing self-reported success is a
          protocol violation (node-t3-002 lesson).
          GOOD: evidence="verify_ssh: all 4 assertions pass; df shows +17GB"
          BAD:  evidence="the procedure appeared to work"  ← self-report, rejected
          source_tier=ground_truth requires evidence >=50 chars and unlocks quality
          up to 1.0. Other tiers cap at their ceiling (primary=0.8, secondary=0.6).
          Pushing quality to 1.0 requires source_tier=ground_truth — this prevents
          self-granted max scores (pfSense read-only incident, P26).

        QUALITY RULES (applied server-side, do not compute yourself):
          verified success: +0.10 · verified failure: −0.15 · cap 1.0 ·
          floor 0.2 → skill auto-archived.

        GATE: only call when a skill from skill_search was actually followed
        during the task. Do NOT call for skills that were retrieved but ignored.
        Trust the returned new quality — do NOT re-query to verify.

        Args:
            skill_id: The skill_id returned by skill_search/skill_record.
            success:  True only with ground-truth evidence; False on verified failure.
            evidence: The verification output (command + result), max 500 chars.
        """
        self._log(f"SKILL-OUTCOME: {skill_id} success={success}")
        evidence = (evidence or "").strip()[:500]
        so_tier, so_ceiling = TrustPolicy.ceiling(source_tier, default="secondary")
        ev_min = 50 if so_tier == "ground_truth" else 20
        if len(evidence) < ev_min:
            return (
                f"SKILL outcome rejected: evidence too thin (need >={ev_min} chars "
                f"for source_tier={so_tier}). Paste the actual verification output "
                "(command + result), not a claim."
            )
        try:
            es = self._es()
            resp = es.search(
                index="lse-skills",
                body={
                    "query": {"term": {"skill_id": skill_id}},
                    "_source": ["quality", "stats", "pinned"],
                    "size": 1,
                },
            )
            hits = resp["hits"]["hits"]
            if not hits:
                return f"SKILL outcome error: skill_id '{skill_id}' not found."
            h = hits[0]
            old_q = h["_source"]["quality"]
            # v0.3.0: floor aligned to the documented 0.2 (was max(0.0, …) — code/
            # docstring drift found by PROVE-2). Same demotion math as record_outcome.
            new_q = min(so_ceiling, old_q + 0.10) if success else max(0.2, old_q - 0.15)
            archived = (
                (not success)
                and (new_q <= 0.2)
                and not h["_source"].get("pinned", False)
            )
            stats_field = "episode_successes" if success else "episode_failures"
            now = datetime.now().astimezone().isoformat()
            es.update(
                index="lse-skills",
                id=h["_id"],
                body={
                    "script": {
                        "source": (
                            "ctx._source.quality = params.q; "
                            f"ctx._source.stats.{stats_field} += 1; "
                            "ctx._source.archived = params.arch; "
                            "ctx._source.updated_at = params.now; "
                            "if (ctx._source.evidence_log == null) "
                            "{ ctx._source.evidence_log = []; } "
                            "ctx._source.evidence_log.add(params.ev)"
                        ),
                        "params": {
                            "q": new_q,
                            "arch": archived,
                            "now": now,
                            "ev": {"ts": now, "success": success, "evidence": evidence},
                        },
                    }
                },
            )
            tail = " | ARCHIVED (quality floor)" if archived else ""
            return (
                f"SKILL outcome recorded: {skill_id} | "
                f"quality {old_q:.2f} -> {new_q:.2f}{tail}"
            )
        except Exception as e:
            self._log(f"SKILL-OUTCOME ERROR: {e}")
            return f"SKILL outcome error: {e}"

    # pfsense_log_summary -- EXTRACTED to lse/skills/pfsense/tools.py
    # (Phase 2 skill extraction, 2026-07-06). See the pointer comment near
    # where pfsense_graphql used to live, above, for the loading mechanism.
