#!/usr/bin/env python3
"""PROVE-2 — Contract tests for every KB-mutating tool function in goethe.py.

Pins the CURRENT (v0.2.9) tier/evidence/dedup behavior so the Phase-1 KB-DECAY
changes and Phase-5 refactors (TrustPolicy extraction, goethe_kb.py split) land
against a green safety net (Fowler: refactor only under tests).

Covered contracts:
  index_to_kb    — tier ceilings, ground_truth evidence gate (>=40 chars),
                   waterfall provenance cap (<=0.3), dedup-updates-not-duplicates,
                   monotonic max(existing, new) quality.
  record_outcome — counts increment; quality_score is NEVER touched (the
                   monotonic-upward behavior KB-DECAY-1 will change — update
                   these tests when it lands); id/title resolution.
  mentor_correct — REJECTS lowering quality; raise path updates content.
  skill_record   — quality clamp min(q, 0.7, tier ceiling) floor 0.2;
                   <2-step and no-verification rejection; dedup; provenance flag.
  skill_outcome  — evidence gates (>=20 / >=50 ground_truth); +0.10 capped at
                   tier ceiling; -0.15 demotion with auto-archive below 0.2;
                   pinned skills never archived.

SAFETY: every ES call from the code under test is routed through an index-
rewriting proxy: lse-kb -> lse-kb-test, lse-skills -> lse-skills-test,
lse-errors -> lse-errors-test. Any other index name raises. Production
indices are never touched. Embeddings are deterministic fakes (no Ollama
dependency; identical text -> cosine 1.0, distinct text -> ~0.0), so the
0.92 dedup threshold is exercised exactly.

Run on LUCIFER (ES on localhost:9200):
    python3 -m pytest tests/test_kb_contracts.py -v
"""

import hashlib
import math
import random
import sys
from pathlib import Path

import pytest

# ── import goethe.py from tools/ ─────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe  # noqa: E402

# ── test-index safety layer ──────────────────────────────────────────────────

INDEX_MAP = {
    "lse-kb": "lse-kb-test",
    "lse-skills": "lse-skills-test",
    "lse-errors": "lse-errors-test",
}
TEST_INDICES = set(INDEX_MAP.values())


def _rewrite(index: str) -> str:
    if index in TEST_INDICES:  # already rewritten (direct test access)
        return index
    if index not in INDEX_MAP:
        raise RuntimeError(
            f"PROVE-2 safety guard: code under test touched unexpected index "
            f"'{index}' — refusing (production protection)."
        )
    return INDEX_MAP[index]


class ESIndexRewriteProxy:
    """Wraps an Elasticsearch client. Rewrites every `index=` kwarg to the
    throwaway -test index and force-refreshes after writes so contract tests
    are deterministic (ES is near-real-time by default)."""

    def __init__(self, raw):
        self._raw = raw

    # reads
    def search(self, *, index, **kw):
        return self._raw.search(index=_rewrite(index), **kw)

    def get(self, *, index, id, **kw):
        return self._raw.get(index=_rewrite(index), id=id, **kw)

    def exists(self, *, index, id, **kw):
        return self._raw.exists(index=_rewrite(index), id=id, **kw)

    def count(self, *, index, **kw):
        return self._raw.count(index=_rewrite(index), **kw)

    # writes (auto-refresh)
    def index(self, *, index, **kw):
        idx = _rewrite(index)
        r = self._raw.index(index=idx, **kw)
        self._raw.indices.refresh(index=idx)
        return r

    def update(self, *, index, id, **kw):
        idx = _rewrite(index)
        r = self._raw.update(index=idx, id=id, **kw)
        self._raw.indices.refresh(index=idx)
        return r


def _hash_vec(seed: str) -> list:
    rnd = random.Random(hashlib.sha256(seed.encode()).digest())
    v = [rnd.uniform(-1.0, 1.0) for _ in range(768)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def fake_embed(text: str) -> list:
    """Deterministic 768-dim unit vector keyed on text. No Ollama needed.

    - identical text        → cosine 1.0            (dedup fires, score 1.0)
    - distinct text         → |cos| ~ 1/sqrt(768)   (dedup never fires, ~0.5)
    - shared @@anchor:X@@   → cosine ≈ 0.64         (score ≈ 0.82: retrievable
      by an anchored query at low min_score, but safely below the 0.92 dedup
      threshold — used by the search_kb rerank tests)
    """
    import re

    m = re.search(r"@@anchor:(\w+)@@", text)
    noise = _hash_vec("NOISE::" + text)
    if not m:
        return noise
    base = _hash_vec("ANCHOR::" + m.group(1))
    v = [0.8 * b + 0.6 * n for b, n in zip(base, noise)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


# ── mappings (mirrors rag/02-es-setup.py + rag/06-skills-index-setup.py) ─────

KB_TEST_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "doc_id": {"type": "keyword"},
            "title": {"type": "text"},
            "content": {"type": "text"},
            "source_path": {"type": "keyword"},
            "source_url": {"type": "keyword"},
            "topic": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "quality_score": {"type": "float"},
            "refinement_count": {"type": "integer"},
            "embedding": {
                "type": "dense_vector", "dims": 768,
                "index": True, "similarity": "cosine",
            },
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "version": {"type": "integer"},
            "source_tier": {"type": "keyword"},
            "evidence": {"type": "text"},
            "verified_against": {"type": "keyword"},
            "empirical_runs": {"type": "integer"},
            "success_count": {"type": "integer"},
            "failure_count": {"type": "integer"},
            "last_outcome_at": {"type": "date"},
            "last_outcome_notes": {"type": "text"},
            "mentor_corrected_at": {"type": "date"},
        }
    },
}

SKILLS_TEST_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "skill_id": {"type": "keyword"},
            "occupation": {"type": "keyword"},
            "task": {"type": "text"},
            "preconditions": {"type": "text"},
            "procedure": {"type": "text"},
            "verification": {"type": "text"},
            "failure_modes": {"type": "text"},
            "provenance": {"type": "keyword"},
            "embedding": {
                "type": "dense_vector", "dims": 768,
                "index": True, "similarity": "cosine",
            },
            "quality": {"type": "float"},
            "stats": {
                "properties": {
                    "uses": {"type": "integer"},
                    "episode_successes": {"type": "integer"},
                    "episode_failures": {"type": "integer"},
                    "last_used": {"type": "date"},
                }
            },
            "evidence_log": {"type": "object", "enabled": True},
            "pinned": {"type": "boolean"},
            "archived": {"type": "boolean"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "version": {"type": "integer"},
            "source_tier": {"type": "keyword"},
        }
    },
}

# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def raw_es():
    from elasticsearch import Elasticsearch

    es = Elasticsearch("http://127.0.0.1:9200", request_timeout=10)
    if not es.ping():
        pytest.skip("Elasticsearch not reachable on 127.0.0.1:9200")
    return es


@pytest.fixture()
def es(raw_es):
    """Fresh throwaway test indices per test; deleted afterwards."""
    for name, mapping in (
        ("lse-kb-test", KB_TEST_MAPPING),
        ("lse-skills-test", SKILLS_TEST_MAPPING),
    ):
        if raw_es.indices.exists(index=name):
            raw_es.indices.delete(index=name)
        raw_es.indices.create(index=name, **mapping)
    yield ESIndexRewriteProxy(raw_es)
    for name in TEST_INDICES:
        if raw_es.indices.exists(index=name):
            raw_es.indices.delete(index=name)


@pytest.fixture()
def tools(es, monkeypatch, tmp_path):
    t = goethe.Tools()
    t.valves.LOG_FILE = str(tmp_path / "test-audit.log")
    monkeypatch.setattr(t, "_es", lambda: es)
    monkeypatch.setattr(t, "_embed", lambda text: fake_embed(text))
    return t


def kb_doc(es, doc_id):
    return es.get(index="lse-kb-test", id=doc_id)["_source"]


def kb_count(es):
    return es.count(index="lse-kb-test")["count"]


def skill_doc(es, skill_id):
    r = es.search(
        index="lse-skills-test",
        body={"query": {"term": {"skill_id": skill_id}}, "size": 1},
    )
    hits = r["hits"]["hits"]
    assert hits, f"skill {skill_id} not found in test index"
    return hits[0]["_source"]


def extract_doc_id(result: str) -> str:
    import re

    m = re.search(r"doc_id=([0-9a-f]{16})", result)
    assert m, f"no doc_id in result: {result}"
    return m.group(1)


# Content long enough to be a real KB entry, with NO version/behavior claim
# (so the waterfall gate stays out of tier-ceiling tests).
PLAIN = (
    "The pfSense box answers DNS for the home.arpa zone via Unbound. "
    "Host overrides live under Services / DNS Resolver. The resolver "
    "listens on the LAN and OPT1 interfaces only."
)
EVIDENCE_40 = "curl -s localhost:9200/_cluster/health -> " + "x" * 20  # >=40 chars


# ══ index_to_kb — tier ceilings ═══════════════════════════════════════════════


class TestIndexToKbTierCeilings:
    @pytest.mark.parametrize(
        "tier,requested,expected",
        [
            ("inferred", 0.9, 0.4),
            ("secondary", 0.9, 0.6),
            ("primary", 0.9, 0.8),
            ("ground_truth", 1.0, 1.0),  # with valid evidence
        ],
    )
    def test_quality_capped_at_tier_ceiling(self, tools, es, tier, requested, expected):
        r = tools.index_to_kb(
            content=PLAIN, title=f"tier {tier}", topic="general",
            quality_score=requested, source_tier=tier,
            evidence=EVIDENCE_40 if tier == "ground_truth" else "",
        )
        assert "KB created" in r
        doc = kb_doc(es, extract_doc_id(r))
        assert doc["quality_score"] == pytest.approx(expected)
        assert doc["source_tier"] == tier

    def test_unknown_tier_treated_as_inferred(self, tools, es):
        r = tools.index_to_kb(
            content=PLAIN, title="bogus tier", topic="general",
            quality_score=0.9, source_tier="totally-made-up",
        )
        doc = kb_doc(es, extract_doc_id(r))
        assert doc["source_tier"] == "inferred"
        assert doc["quality_score"] == pytest.approx(0.4)

    def test_quality_below_ceiling_not_raised(self, tools, es):
        r = tools.index_to_kb(
            content=PLAIN, title="modest quality", topic="general",
            quality_score=0.3, source_tier="primary",
        )
        doc = kb_doc(es, extract_doc_id(r))
        assert doc["quality_score"] == pytest.approx(0.3)


class TestIndexToKbEvidenceGate:
    def test_ground_truth_thin_evidence_downgrades_to_07(self, tools, es):
        r = tools.index_to_kb(
            content=PLAIN, title="thin evidence", topic="general",
            quality_score=1.0, source_tier="ground_truth",
            evidence="it worked",  # < 40 chars
        )
        assert "TIER DOWNGRADE" in r
        doc = kb_doc(es, extract_doc_id(r))
        assert doc["quality_score"] == pytest.approx(0.7)

    def test_ground_truth_with_real_evidence_unlocks_10(self, tools, es):
        r = tools.index_to_kb(
            content=PLAIN, title="real evidence", topic="general",
            quality_score=1.0, source_tier="ground_truth", evidence=EVIDENCE_40,
        )
        assert "TIER DOWNGRADE" not in r
        doc = kb_doc(es, extract_doc_id(r))
        assert doc["quality_score"] == pytest.approx(1.0)


class TestIndexToKbWaterfall:
    CLAIM = "The --ctx-size flag was removed in v2.8.0 of the server binary."

    def test_version_claim_without_provenance_capped_unverified(self, tools, es):
        r = tools.index_to_kb(
            content=self.CLAIM, title="unprovenanced claim", topic="llama-cpp",
            quality_score=0.8, source_tier="primary",
        )
        assert "WATERFALL" in r
        doc = kb_doc(es, extract_doc_id(r))
        assert doc["quality_score"] <= 0.3
        assert doc["source_tier"] == "inferred"
        assert doc["content"].startswith("[UNVERIFIED")

    def test_version_claim_with_source_url_passes(self, tools, es):
        r = tools.index_to_kb(
            content=self.CLAIM, title="provenanced claim", topic="llama-cpp",
            quality_score=0.8, source_tier="primary",
            source_url="https://github.com/ggml-org/llama.cpp/releases",
        )
        assert "WATERFALL" not in r
        doc = kb_doc(es, extract_doc_id(r))
        assert doc["quality_score"] == pytest.approx(0.8)
        assert not doc["content"].startswith("[UNVERIFIED")


class TestIndexToKbDedup:
    def test_identical_content_updates_not_duplicates(self, tools, es):
        r1 = tools.index_to_kb(
            content=PLAIN, title="original", topic="general",
            quality_score=0.3, source_tier="secondary",
        )
        assert "KB created" in r1
        doc_id = extract_doc_id(r1)

        r2 = tools.index_to_kb(
            content=PLAIN, title="duplicate attempt", topic="general",
            quality_score=0.5, source_tier="secondary",
        )
        assert "KB updated (refined)" in r2
        assert extract_doc_id(r2) == doc_id
        assert kb_count(es) == 1
        doc = kb_doc(es, doc_id)
        assert doc["refinement_count"] == 1
        assert doc["version"] == 2
        assert doc["quality_score"] == pytest.approx(0.5)  # max(existing, new)

    def test_dedup_never_lowers_quality(self, tools, es):
        r1 = tools.index_to_kb(
            content=PLAIN, title="good entry", topic="general",
            quality_score=0.6, source_tier="secondary",
        )
        doc_id = extract_doc_id(r1)
        tools.index_to_kb(
            content=PLAIN, title="worse retry", topic="general",
            quality_score=0.1, source_tier="inferred",
        )
        assert kb_doc(es, doc_id)["quality_score"] == pytest.approx(0.6)

    def test_distinct_content_creates_second_doc(self, tools, es):
        tools.index_to_kb(content=PLAIN, title="doc A", topic="general")
        r2 = tools.index_to_kb(
            content="Grafana provisions the netobs dashboard from the docker "
            "volume mount; panels are keyed on the snapshot age metric.",
            title="doc B", topic="infrastructure",
        )
        assert "KB created" in r2
        assert kb_count(es) == 2


# ══ record_outcome — counts move, quality does NOT (current v0.2.9 contract) ══


class TestRecordOutcome:
    def _seed(self, tools):
        r = tools.index_to_kb(
            content=PLAIN, title="outcome target", topic="general",
            quality_score=0.5, source_tier="secondary",
        )
        return extract_doc_id(r)

    def test_success_increments_counts_quality_untouched(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.record_outcome(doc_id, success=True, notes="worked as documented")
        assert "✅ success" in r
        doc = kb_doc(es, doc_id)
        assert doc["empirical_runs"] == 1
        assert doc["success_count"] == 1
        assert doc["failure_count"] == 0
        assert doc["quality_score"] == pytest.approx(0.5)

    def test_failure_without_evidence_counts_but_never_demotes(self, tools, es):
        # KB-DECAY-1 evidence gate: unverified failure claims must not erode
        # the KB — counts move, quality does not.
        doc_id = self._seed(tools)
        for _ in range(3):
            r = tools.record_outcome(doc_id, success=False, notes="did not work")
        assert "NOT demoted" in r
        doc = kb_doc(es, doc_id)
        assert doc["failure_count"] == 3
        assert doc["empirical_runs"] == 3
        assert doc["quality_score"] == pytest.approx(0.5)
        assert "consecutive_failures" not in doc or doc["consecutive_failures"] == 0

    def test_unknown_ref_returns_guidance_not_exception(self, tools, es):
        r = tools.record_outcome("no-such-doc-anywhere", success=True)
        assert "record_outcome:" in r
        assert "search_kb" in r

    def test_title_resolves_to_doc_id(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.record_outcome("outcome target", success=True)
        assert "✅ success" in r
        assert kb_doc(es, doc_id)["success_count"] == 1


# ══ KB-DECAY-1 (v0.3.0) — evidence-backed demotion + stale quarantine ═════════

FAIL_EVIDENCE = "curl -s :8080/health → 404; systemctl is-active llama-server → inactive"


class TestRecordOutcomeDemotion:
    def _seed(self, tools, quality=0.5):
        r = tools.index_to_kb(
            content=PLAIN, title="decay target", topic="general",
            quality_score=quality, source_tier="secondary",
        )
        return extract_doc_id(r)

    def test_verified_failure_demotes_015(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.record_outcome(doc_id, success=False, evidence=FAIL_EVIDENCE)
        assert "DEMOTED 0.50 → 0.35" in r
        doc = kb_doc(es, doc_id)
        assert doc["quality_score"] == pytest.approx(0.35)
        assert doc["consecutive_failures"] == 1
        assert doc["last_failure_evidence"] == FAIL_EVIDENCE
        assert not doc.get("stale")

    def test_floor_02_quarantines_stale(self, tools, es):
        doc_id = self._seed(tools)
        tools.record_outcome(doc_id, success=False, evidence=FAIL_EVIDENCE)  # 0.35
        r = tools.record_outcome(doc_id, success=False, evidence=FAIL_EVIDENCE)  # 0.20
        assert "STALE" in r
        doc = kb_doc(es, doc_id)
        assert doc["quality_score"] == pytest.approx(0.2)
        assert doc["stale"] is True
        assert doc["consecutive_failures"] == 2
        # further failures stay at the floor — quarantined, never deleted
        tools.record_outcome(doc_id, success=False, evidence=FAIL_EVIDENCE)
        doc = kb_doc(es, doc_id)
        assert doc["quality_score"] == pytest.approx(0.2)
        assert doc["consecutive_failures"] == 3

    def test_success_resets_streak_but_never_reelevates(self, tools, es):
        doc_id = self._seed(tools)
        tools.record_outcome(doc_id, success=False, evidence=FAIL_EVIDENCE)  # 0.35
        r = tools.record_outcome(doc_id, success=True, notes="worked this time")
        assert "failure streak reset" in r
        doc = kb_doc(es, doc_id)
        assert doc["consecutive_failures"] == 0
        assert doc["quality_score"] == pytest.approx(0.35)  # no free re-elevation

    def test_success_does_not_clear_stale(self, tools, es):
        doc_id = self._seed(tools)
        for _ in range(2):
            tools.record_outcome(doc_id, success=False, evidence=FAIL_EVIDENCE)
        tools.record_outcome(doc_id, success=True)
        doc = kb_doc(es, doc_id)
        assert doc["stale"] is True  # only tier-gated raises clear quarantine
        assert doc["quality_score"] == pytest.approx(0.2)

    def test_tier_gated_reindex_clears_quarantine(self, tools, es):
        doc_id = self._seed(tools)
        for _ in range(2):
            tools.record_outcome(doc_id, success=False, evidence=FAIL_EVIDENCE)
        assert kb_doc(es, doc_id)["stale"] is True
        # re-index the same content with better tier-gated evidence → dedup
        # update raises quality above the floor and clears the quarantine
        r = tools.index_to_kb(
            content=PLAIN, title="decay target (re-verified)", topic="general",
            quality_score=0.6, source_tier="secondary",
        )
        assert "KB updated (refined)" in r
        doc = kb_doc(es, doc_id)
        assert doc["quality_score"] == pytest.approx(0.6)
        assert doc["stale"] is False
        assert doc["consecutive_failures"] == 0

    def test_mentor_correct_clears_quarantine(self, tools, es):
        doc_id = self._seed(tools)
        for _ in range(2):
            tools.record_outcome(doc_id, success=False, evidence=FAIL_EVIDENCE)
        r = tools.mentor_correct(
            doc_id, correction=PLAIN + " Verified again by hand.", new_quality=0.9
        )
        assert "Mentor correction applied" in r
        doc = kb_doc(es, doc_id)
        assert doc["quality_score"] == pytest.approx(0.9)
        assert doc["stale"] is False
        assert doc["consecutive_failures"] == 0


# ══ mentor_correct — never lowers quality ═════════════════════════════════════


class TestMentorCorrect:
    def _seed(self, tools, quality=0.8):
        r = tools.index_to_kb(
            content=PLAIN, title="mentor target", topic="general",
            quality_score=quality, source_tier="primary",
        )
        return extract_doc_id(r)

    def test_lowering_quality_rejected_doc_untouched(self, tools, es):
        doc_id = self._seed(tools, quality=0.8)
        r = tools.mentor_correct(doc_id, correction="totally new text", new_quality=0.5)
        assert "REJECTED" in r
        doc = kb_doc(es, doc_id)
        assert doc["quality_score"] == pytest.approx(0.8)
        assert doc["content"] == PLAIN  # content NOT replaced on rejection

    def test_raising_quality_applies_correction(self, tools, es):
        doc_id = self._seed(tools, quality=0.8)
        corrected = PLAIN + " CORRECTION: the resolver also listens on OPT2."
        r = tools.mentor_correct(doc_id, correction=corrected, new_quality=0.95)
        assert "Mentor correction applied" in r
        doc = kb_doc(es, doc_id)
        assert doc["quality_score"] == pytest.approx(0.95)
        assert doc["content"] == corrected
        assert doc["refinement_count"] == 1
        assert "mentor_corrected_at" in doc

    def test_unknown_ref_returns_guidance(self, tools, es):
        r = tools.mentor_correct("ghost-doc", correction="x", new_quality=0.9)
        assert "mentor_correct:" in r


# ══ skill_record — clamp, gates, dedup ════════════════════════════════════════

PROC = "enumerate candidates; verify sha256 of survivor; delete duplicate; df delta"
VERIF = "df -h shows expected free-space delta; sha256sum survivor matches"


class TestSkillRecord:
    def test_quality_never_starts_above_07_even_ground_truth(self, tools, es):
        r = tools.skill_record(
            task="free disk space by removing duplicate models",
            occupation="linux-sysadmin", procedure=PROC, verification=VERIF,
            provenance="episode node-t3-002", quality=0.95, source_tier="ground_truth",
        )
        assert "SKILL created" in r
        s = skill_doc(es, "linux-sysadmin/free-disk-space-by-removing-duplicate-models")
        assert s["quality"] == pytest.approx(0.7)

    def test_quality_capped_by_tier_ceiling(self, tools, es):
        tools.skill_record(
            task="rotate searxng logs safely", occupation="sre",
            procedure=PROC, verification=VERIF, quality=0.65, source_tier="inferred",
        )
        s = skill_doc(es, "sre/rotate-searxng-logs-safely")
        assert s["quality"] == pytest.approx(0.4)  # inferred ceiling

    def test_quality_floored_at_02(self, tools, es):
        tools.skill_record(
            task="restart the grafana container", occupation="sre",
            procedure=PROC, verification=VERIF, quality=0.05, source_tier="secondary",
        )
        s = skill_doc(es, "sre/restart-the-grafana-container")
        assert s["quality"] == pytest.approx(0.2)

    def test_single_step_procedure_rejected_as_fact(self, tools, es):
        r = tools.skill_record(
            task="llama-server port", occupation="sre",
            procedure="8080", verification=VERIF,
        )
        assert "rejected" in r.lower()
        assert "index_to_kb" in r

    def test_missing_verification_rejected(self, tools, es):
        r = tools.skill_record(
            task="clear the ES cache", occupation="dba",
            procedure=PROC, verification="   ",
        )
        assert "rejected" in r.lower()
        assert "verification" in r.lower()

    def test_duplicate_skill_updates_not_duplicates(self, tools, es):
        task = "resync docker config from repo"
        tools.skill_record(
            task=task, occupation="sre", procedure=PROC, verification=VERIF,
            provenance="incident 2026-06-07", quality=0.4, source_tier="secondary",
        )
        r2 = tools.skill_record(
            task=task, occupation="sre", procedure=PROC, verification=VERIF,
            provenance="incident 2026-06-07", quality=0.6, source_tier="secondary",
        )
        assert "SKILL updated" in r2
        assert es.count(index="lse-skills-test")["count"] == 1
        s = skill_doc(es, "sre/resync-docker-config-from-repo")
        assert s["quality"] == pytest.approx(0.6)  # max(existing, new), cap 0.7
        assert s["version"] == 2

    def test_no_provenance_flagged_unattributed(self, tools, es):
        r = tools.skill_record(
            task="prune old ollama models", occupation="linux-sysadmin",
            procedure=PROC, verification=VERIF,
        )
        assert "FLAGGED: no provenance" in r
        s = skill_doc(es, "linux-sysadmin/prune-old-ollama-models")
        assert s["provenance"] == ["UNATTRIBUTED"]


# ══ skill_outcome — evidence gates, demotion, archive floor ═══════════════════

GT_EVIDENCE = (
    "verify_ssh: all 4 assertions pass; df -h /home shows +17GB free after cleanup"
)


class TestSkillOutcome:
    def _seed(self, tools, es, quality=0.5, pinned=False):
        tools.skill_record(
            task="clean up duplicate gguf files", occupation="linux-sysadmin",
            procedure=PROC, verification=VERIF, provenance="ep-1",
            quality=quality, source_tier="secondary",
        )
        skill_id = "linux-sysadmin/clean-up-duplicate-gguf-files"
        if pinned or quality != 0.5:
            # skill_record clamps starting quality — set the exact test state
            # directly in the throwaway index (fixture-only path).
            r = es.search(
                index="lse-skills-test",
                body={"query": {"term": {"skill_id": skill_id}}, "size": 1},
            )
            es.update(
                index="lse-skills-test", id=r["hits"]["hits"][0]["_id"],
                body={"doc": {"quality": quality, "pinned": pinned}},
            )
        return skill_id

    def test_thin_evidence_rejected(self, tools, es):
        sid = self._seed(tools, es)
        r = tools.skill_outcome(sid, success=True, evidence="it worked")
        assert "rejected" in r.lower()
        assert skill_doc(es, sid)["quality"] == pytest.approx(0.5)  # untouched

    def test_ground_truth_requires_50_chars(self, tools, es):
        sid = self._seed(tools, es)
        r = tools.skill_outcome(
            sid, success=True,
            evidence="short but over twenty chars",  # 28 chars: ok for secondary, not GT
            source_tier="ground_truth",
        )
        assert "rejected" in r.lower()
        assert ">=50" in r

    def test_verified_success_adds_010_capped_at_tier_ceiling(self, tools, es):
        sid = self._seed(tools, es, quality=0.55)
        r = tools.skill_outcome(sid, success=True, evidence=GT_EVIDENCE,
                                source_tier="secondary")
        assert "0.55 -> 0.60" in r  # 0.55 + 0.10 capped at secondary ceiling 0.6
        assert skill_doc(es, sid)["quality"] == pytest.approx(0.6)

    def test_ground_truth_success_can_reach_higher_ceiling(self, tools, es):
        sid = self._seed(tools, es, quality=0.75)
        tools.skill_outcome(sid, success=True, evidence=GT_EVIDENCE,
                            source_tier="ground_truth")
        assert skill_doc(es, sid)["quality"] == pytest.approx(0.85)

    def test_verified_failure_demotes_015_floored_02_and_archives(self, tools, es):
        # v0.3.0: floor aligned to the documented 0.2 (PROVE-2 caught the
        # v0.2.9 code/docstring drift where the code floored at 0.0).
        # Archive fires on failure AT the floor.
        sid = self._seed(tools, es, quality=0.25)
        r = tools.skill_outcome(
            sid, success=False,
            evidence="verify_ssh: assertion a2 failed — inventory count mismatch",
        )
        assert "ARCHIVED" in r
        s = skill_doc(es, sid)
        assert s["quality"] == pytest.approx(0.2)  # max(0.2, 0.25 - 0.15)
        assert s["archived"] is True
        assert s["stats"]["episode_failures"] == 1

    def test_failure_above_floor_demotes_without_archiving(self, tools, es):
        sid = self._seed(tools, es, quality=0.5)
        r = tools.skill_outcome(
            sid, success=False,
            evidence="verify_ssh: assertion a3 failed — config value not applied",
        )
        assert "ARCHIVED" not in r
        s = skill_doc(es, sid)
        assert s["quality"] == pytest.approx(0.35)
        assert s["archived"] is False

    def test_pinned_skill_never_archived_at_floor(self, tools, es):
        sid = self._seed(tools, es, quality=0.25, pinned=True)
        r = tools.skill_outcome(
            sid, success=False,
            evidence="verify_ssh: assertion a1 failed — service inactive after restart",
        )
        assert "ARCHIVED" not in r
        s = skill_doc(es, sid)
        assert s["archived"] is False
        assert s["quality"] == pytest.approx(0.2)

    def test_unknown_skill_id_errors_cleanly(self, tools, es):
        r = tools.skill_outcome("sre/does-not-exist", success=True, evidence=GT_EVIDENCE)
        assert "not found" in r


# ══ KB-DECAY-4 (v0.3.0) — mentor_demote: human kill-switch ════════════════════


class TestMentorDemote:
    def _seed(self, tools, quality=0.8):
        r = tools.index_to_kb(
            content=PLAIN, title="demote target", topic="general",
            quality_score=quality, source_tier="primary",
        )
        return extract_doc_id(r)

    def test_thin_reason_rejected(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.mentor_demote(doc_id, new_quality=0.3, reason="bad")
        assert "rejected" in r.lower()
        assert kb_doc(es, doc_id)["quality_score"] == pytest.approx(0.8)

    def test_raising_or_equal_rejected(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.mentor_demote(
            doc_id, new_quality=0.8, reason="operator says this is fine actually"
        )
        assert "REJECTED" in r
        assert "mentor_correct" in r
        assert kb_doc(es, doc_id)["quality_score"] == pytest.approx(0.8)

    def test_demotion_applies_and_stores_reason(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.mentor_demote(
            doc_id, new_quality=0.4,
            reason="operator: procedure references retired OWUI stack",
        )
        assert "Mentor demotion applied" in r
        doc = kb_doc(es, doc_id)
        assert doc["quality_score"] == pytest.approx(0.4)
        assert "retired OWUI" in doc["demote_reason"]
        assert not doc.get("stale")  # above the quarantine floor

    def test_demotion_to_floor_quarantines(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.mentor_demote(
            doc_id, new_quality=0.15,
            reason="operator: factually wrong, poisoned entry — pull it",
        )
        assert "STALE" in r
        doc = kb_doc(es, doc_id)
        assert doc["quality_score"] == pytest.approx(0.15)
        assert doc["stale"] is True

    def test_unknown_ref_returns_guidance(self, tools, es):
        r = tools.mentor_demote(
            "ghost-doc", new_quality=0.1, reason="operator demotion request"
        )
        assert "mentor_demote:" in r


# ══ KB-DECAY-3 (v0.3.0) — kb_verify: verified_against regression probe ════════


class TestKbVerify:
    def _seed(self, tools, verified_against="pfSense Plus 26.03"):
        r = tools.index_to_kb(
            content=PLAIN, title="verify target", topic="pfsense",
            quality_score=0.8, source_tier="ground_truth",
            evidence=EVIDENCE_40, verified_against=verified_against,
        )
        return extract_doc_id(r)

    def test_phase1_returns_snapshot_and_instructions(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.kb_verify(doc_id)
        assert "phase 1" in r
        assert "pfSense Plus 26.03" in r
        assert f"kb_verify('{doc_id}'" in r

    def test_no_snapshot_says_nothing_to_verify(self, tools, es):
        r0 = tools.index_to_kb(
            content=PLAIN, title="no snapshot", topic="general",
            quality_score=0.5, source_tier="secondary",
        )
        r = tools.kb_verify(extract_doc_id(r0))
        assert "NO verified_against" in r

    def test_thin_observed_rejected(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.kb_verify(doc_id, observed="26.03")
        assert "rejected" in r.lower()

    def test_match_records_success(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.kb_verify(
            doc_id,
            observed="pfSense Plus 26.03-RELEASE (amd64) built on Thu Jun 12; uptime 14 days",
        )
        assert "MATCH ✅" in r
        doc = kb_doc(es, doc_id)
        assert doc["success_count"] == 1
        assert doc["quality_score"] == pytest.approx(0.8)  # untouched (seeded 0.8)

    def test_mismatch_auto_demotes_with_probe_evidence(self, tools, es):
        doc_id = self._seed(tools)
        r = tools.kb_verify(
            doc_id,
            observed="pfSense Plus 26.11-RELEASE (amd64) built on Tue Jun 30; uptime 2 days",
        )
        assert "MISMATCH ❌" in r
        doc = kb_doc(es, doc_id)
        assert doc["failure_count"] == 1
        assert doc["quality_score"] == pytest.approx(0.65)  # 0.8 − 0.15
        assert doc["consecutive_failures"] == 1
        assert "verified_against regression" in doc["last_failure_evidence"]


# ══ KB-DECAY-2 (v0.3.0) — search_kb trust surfacing + rerank ══════════════════


class TestSearchKbTrust:
    A = ("@@anchor:dns@@ The resolver forwards home.arpa queries to Unbound on "
         "the firewall; host overrides are managed in the resolver settings.")
    B = ("@@anchor:dns@@ Unbound on the firewall answers home.arpa lookups; "
         "override entries live in the DNS resolver configuration page.")
    QUERY = "@@anchor:dns@@ resolver home.arpa unbound overrides"

    def _seed_two(self, tools):
        ra = tools.index_to_kb(content=self.A, title="dns doc A", topic="general",
                               quality_score=0.5, source_tier="secondary")
        rb = tools.index_to_kb(content=self.B, title="dns doc B", topic="general",
                               quality_score=0.5, source_tier="secondary")
        assert "KB created" in ra and "KB created" in rb  # anchor stays below dedup
        return extract_doc_id(ra), extract_doc_id(rb)

    def test_trust_counts_and_untested_shown(self, tools, es):
        id_a, _ = self._seed_two(tools)
        tools.record_outcome(id_a, success=True)
        r = tools.search_kb(self.QUERY, min_score=0.1)
        assert "runs=1 (1 ok/0 fail)" in r
        assert "untested" in r  # doc B has no outcomes yet

    def test_stale_doc_gets_banner_and_ranks_below_fresh(self, tools, es):
        id_a, id_b = self._seed_two(tools)
        for _ in range(2):  # 0.5 → 0.35 → 0.2 + stale
            tools.record_outcome(id_a, success=False, evidence=FAIL_EVIDENCE)
        assert kb_doc(es, id_a)["stale"] is True
        r = tools.search_kb(self.QUERY, min_score=0.1)
        assert "[STALE — quarantined, verify live before use]" in r
        # trust rerank: the stale doc must be listed AFTER the fresh one
        assert r.index(f"doc_id={id_b}") < r.index(f"doc_id={id_a}")


# ══ CHRONOS (v0.3.1) — enforced sense of time ═════════════════════════════════


def _backdate(es, doc_id, days):
    from datetime import datetime, timedelta

    old = (datetime.now().astimezone() - timedelta(days=days)).isoformat()
    es.update(index="lse-kb-test", id=doc_id, body={"doc": {"updated_at": old}})


class TestChronosTimeBanner:
    def test_banner_on_first_search_kb_only(self, tools, es):
        tools.index_to_kb(content=PLAIN, title="banner doc", topic="general")
        r1 = tools.search_kb("resolver home.arpa", min_score=0.1)
        assert r1.startswith("[TIME] now=")
        r2 = tools.search_kb("resolver home.arpa", min_score=0.1)
        assert "[TIME]" not in r2

    def test_consume_is_once_per_session(self, tools):
        assert tools._consume_time_banner().startswith("[TIME]")
        assert tools._consume_time_banner() == ""

    def test_gap_computation(self, tools):
        from datetime import datetime

        tools.valves.MODEL_PRETRAIN_CUTOFF = "2025-06"
        now = datetime.now().astimezone()
        expected_gap = (now.year - 2025) * 12 + (now.month - 6)
        b = tools._time_banner()
        assert "model cutoff=2025-06" in b
        assert f"gap≈{expected_gap} months" in b
        assert "presumed stale" in b

    def test_cutoff_unset_warns(self, tools):
        tools.valves.MODEL_PRETRAIN_CUTOFF = ""
        assert "model cutoff UNSET" in tools._time_banner()


class TestChronosYearStrip:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("ASUSWRT-Merlin RT-BE19000 firmware 2025", "ASUSWRT-Merlin RT-BE19000 firmware"),
            ("top laptops 2024 2025", "top laptops"),
            ("CVE-2025-1234 exploit details", "CVE-2025-1234 exploit details"),
            ("ubuntu 24.04 lts release notes", "ubuntu 24.04 lts release notes"),
            ("llama.cpp build b2025 flags", "llama.cpp build b2025 flags"),
            ("pfsense unbound overrides", "pfsense unbound overrides"),
        ],
    )
    def test_standalone_years_stripped_compounds_survive(self, tools, raw, expected):
        assert tools._strip_years(raw) == expected


class TestChronosVolatility:
    def _seed(self, tools, volatility="slow"):
        r = tools.index_to_kb(
            content=PLAIN, title=f"vol {volatility}", topic="general",
            quality_score=0.5, source_tier="secondary", volatility=volatility,
        )
        return extract_doc_id(r)

    def test_volatility_stored_and_default(self, tools, es):
        doc_id = self._seed(tools, volatility="fast")
        assert kb_doc(es, doc_id)["volatility"] == "fast"

    def test_invalid_volatility_falls_back_to_slow(self, tools, es):
        doc_id = self._seed(tools, volatility="hourly")
        assert kb_doc(es, doc_id)["volatility"] == "slow"

    def test_expired_fast_doc_tagged(self, tools, es):
        doc_id = self._seed(tools, volatility="fast")
        _backdate(es, doc_id, days=10)  # fast TTL = 7d
        r = tools.search_kb("resolver home.arpa unbound", min_score=0.1)
        assert "[EXPIRED — fast TTL exceeded" in r
        assert "volatility=fast" in r

    def test_static_never_expires(self, tools, es):
        doc_id = self._seed(tools, volatility="static")
        _backdate(es, doc_id, days=400)
        r = tools.search_kb("resolver home.arpa unbound", min_score=0.1)
        assert "[EXPIRED" not in r

    def test_fresh_slow_doc_not_expired(self, tools, es):
        self._seed(tools, volatility="slow")
        r = tools.search_kb("resolver home.arpa unbound", min_score=0.1)
        assert "[EXPIRED" not in r

    def test_verified_success_resets_ttl_clock(self, tools, es):
        doc_id = self._seed(tools, volatility="fast")
        _backdate(es, doc_id, days=10)
        r = tools.search_kb("resolver home.arpa unbound", min_score=0.1)
        assert "[EXPIRED" in r
        tools.record_outcome(doc_id, success=True, notes="re-verified live")
        r2 = tools.search_kb("resolver home.arpa unbound", min_score=0.1)
        assert "[EXPIRED" not in r2


class TestChronosTimeCheck:
    def _patch_sources(self, monkeypatch, tools, offsets, tls):
        monkeypatch.setattr(
            tools, "_sntp_offset", lambda server, timeout=2.0: offsets.get(server)
        )
        monkeypatch.setattr(tools, "_tls_date_offset", lambda url=None: tls)

    def test_consensus_ok(self, tools, es, monkeypatch):
        self._patch_sources(
            monkeypatch, tools,
            {"pool.ntp.org": 0.10, "time.cloudflare.com": 0.20}, tls=0.15,
        )
        r = tools.time_check()
        assert "✅ clock agrees with NTP consensus" in r
        assert "[TIME] now=" in r and "NTP-verified" in r
        assert "SUGGESTED FIX" not in r

    def test_discrepancy_with_tls_corroboration_suggests_fix(self, tools, es, monkeypatch):
        self._patch_sources(
            monkeypatch, tools,
            {"pool.ntp.org": 5.0, "time.cloudflare.com": 5.2}, tls=5.1,
        )
        r = tools.time_check()
        assert "CLOCK DISCREPANCY" in r
        assert "SUGGESTED FIX (human-run, never automatic)" in r

    def test_discrepancy_without_tls_suggests_nothing(self, tools, es, monkeypatch):
        # Shostack gate: unauthenticated NTP alone must never produce a fix command
        self._patch_sources(
            monkeypatch, tools,
            {"pool.ntp.org": 5.0, "time.cloudflare.com": 5.2}, tls=None,
        )
        r = tools.time_check()
        assert "CLOCK DISCREPANCY" in r
        assert "does NOT corroborate" in r
        assert "SUGGESTED FIX" not in r

    def test_ntp_disagreement_distrusts_ntp(self, tools, es, monkeypatch):
        self._patch_sources(
            monkeypatch, tools,
            {"pool.ntp.org": 0.1, "time.cloudflare.com": 4.0}, tls=0.1,
        )
        r = tools.time_check()
        assert "NTP servers DISAGREE" in r
        assert "system clock — run time_check() to NTP-verify" in r  # unverified banner

    def test_no_ntp_degrades_gracefully(self, tools, es, monkeypatch):
        self._patch_sources(monkeypatch, tools, {}, tls=None)
        r = tools.time_check()
        assert "WARN: no NTP source reachable" in r
        assert "[TIME] now=" in r

    def test_time_check_marks_banner_emitted(self, tools, es, monkeypatch):
        self._patch_sources(
            monkeypatch, tools,
            {"pool.ntp.org": 0.0, "time.cloudflare.com": 0.0}, tls=0.0,
        )
        tools.index_to_kb(content=PLAIN, title="after timecheck", topic="general")
        tools.time_check()
        r = tools.search_kb("resolver home.arpa", min_score=0.1)
        assert "[TIME]" not in r  # banner already delivered by time_check
