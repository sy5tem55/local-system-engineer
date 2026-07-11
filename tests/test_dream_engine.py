"""
Unit tests for the TRAUM-ENGINE apply gate (Thread 2, Prompt 2.9 — invariant
tests for tools/dream_apply.py and its use of tools/dream_runner.py).

Covers:
  - validate_proposal_for_apply() fail-closed rejection of the three DESIGN.md
    §2 row 3 hard invariants: (a) never raise quality, (b) never mint
    source_tier=ground_truth, (c) never touch a quarantined doc except the
    (unused-in-practice) quarantine-delete-request exception — synthetic
    proposal/doc fixtures, one per invariant.
  - origin/provenance stamping (_stamp_dream_fields, the ONE EXCEPTION to
    pure Tools-passthrough documented in dream_apply.py's module docstring)
    verified end-to-end through apply_group() against a disposable in-memory
    ES doc.
  - the dedup pair path (group_proposals + apply_group) preserving the union
    of empirical_runs/success_count/failure_count across keep+retire onto
    the keep-doc only, per dream_runner.py's dedup pass docstring and
    dream_apply.py's ONE EXCEPTION note.
  - dream_runner.py's ES client is read-only (search_index never calls
    anything but es.search) and nothing escapes dream_apply's dry-run guard
    (--dry-run calls no Tools method and touches no ES verb at all); across
    every call type dream_apply.py can dispatch, es.delete() is never
    called (no hard-delete path exists in this codebase — KB-DECAY
    quarantine is the only retirement mechanism).
  - the fifth (DESIGN.md §6.2) proposal type, "kb-fact" / index_to_kb —
    reused verbatim from Thread 1's SCRIBE-1 debrief format — applies a
    brand-new fact and gets the same full origin+provenance stamp as
    mentor_correct/record_outcome (index_to_kb has neither parameter
    either), located via the doc_id parsed out of its own return string.

No live Elasticsearch, no live Ollama, no goethe.py Tools class is loaded —
everything is driven through small in-memory FakeES/FakeTools doubles
(mock-based, per Prompt 2.9's ask) so this file has zero external
dependencies and is safe to run anywhere, including alongside
test_kb_contracts.py's own (live-ES) contract tests:

    python3 -m pytest tests/test_dream_engine.py tests/test_kb_contracts.py -q
"""

import hashlib
import re
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_apply as da  # noqa: E402
import dream_runner as dr  # noqa: E402

TODAY = date.today().isoformat()


# --- test doubles -------------------------------------------------------

class FakeES:
    """In-memory Elasticsearch double.

    Records every call as (verb, index, id) in self.calls so tests can
    assert exactly which write verbs occurred. .get/.search are pure reads;
    .update merges into the in-memory store (mirrors goethe.py's Tools
    methods' own es.update(body={"doc": ...}) partial-update shape). .index
    creates/replaces a doc (mirrors the real Tools.skill_record/index_to_kb
    "brand-new doc" path, tools/goethe.py's own es.index(document=...) call
    shape) — legitimate, not blocked. .delete raises AssertionError
    unconditionally: no hard-delete tool exists anywhere in this codebase
    (KB-DECAY quarantine — stale=true at the 0.2 quality floor — is the
    only retirement mechanism), so any code path that reaches es.delete()
    is a bug this double is built to catch loudly rather than silently
    permit.
    """

    def __init__(self, docs=None):
        self.store = {}  # (index, id) -> dict
        for (index, doc_id), src in (docs or {}).items():
            self.store[(index, doc_id)] = dict(src)
        self.calls = []

    def get(self, *, index, id, _source=None, **kw):
        self.calls.append(("get", index, id))
        if (index, id) not in self.store:
            raise KeyError(f"no such doc {index}/{id}")
        src = self.store[(index, id)]
        if _source:
            src = {k: src.get(k) for k in _source}
        return {"_source": dict(src)}

    def search(self, *, index, body=None, **kw):
        self.calls.append(("search", index, None))
        hits = [
            {"_id": doc_id, "_source": src}
            for (idx, doc_id), src in self.store.items()
            if idx == index
        ]
        return {"hits": {"hits": hits}}

    def update(self, *, index, id, body, **kw):
        self.calls.append(("update", index, id))
        self.store.setdefault((index, id), {}).update(body.get("doc", {}))
        return {"result": "updated"}

    def index(self, *, index, id=None, document=None, body=None, **kw):
        self.calls.append(("index", index, id))
        self.store[(index, id)] = dict(document or body or {})
        return {"result": "created"}

    def delete(self, *, index, id, **kw):
        self.calls.append(("delete", index, id))
        raise AssertionError(
            "es.delete() must never be called -- no hard-delete tool exists "
            "in this codebase (KB-DECAY quarantine is the retirement path)"
        )


class FakeTools:
    """Stands in for goethe.py's Tools class. Mirrors just the ES-touching
    shape of mentor_correct/record_outcome/skill_record (one es.update()
    each, tools/goethe.py:5361/5283) closely enough that dream_apply.py's
    apply_group() exercises the exact call shape it would against the real
    Tools class, without needing a live goethe.py/ES/Ollama."""

    def __init__(self, es):
        self._es_instance = es
        self.calls = []

    def _es(self):
        return self._es_instance

    def mentor_correct(self, doc_id, correction, new_quality):
        self.calls.append(("mentor_correct", doc_id, correction, new_quality))
        self._es_instance.update(
            index="lse-kb", id=doc_id,
            body={"doc": {"content": correction, "quality_score": new_quality}},
        )
        return f"Mentor correction applied: doc='{doc_id}' | quality -> {new_quality:.2f}"

    def record_outcome(self, doc_id, success, notes="", evidence=""):
        self.calls.append(("record_outcome", doc_id, success, notes, evidence))
        self._es_instance.update(
            index="lse-kb", id=doc_id,
            body={"doc": {"last_outcome_notes": notes}},
        )
        return f"Outcome recorded: doc='{doc_id}' success={success}"

    def kb_verify(self, doc_id, observed=""):
        self.calls.append(("kb_verify", doc_id))
        return f"VERIFY phase1: doc_id={doc_id}"  # read-only, no ES call

    def skill_record(self, **kwargs):
        self.calls.append(("skill_record", kwargs))
        return "SKILL created: test-skill-slug"

    def index_to_kb(self, content, title, topic="general", source_url="",
                     quality_score=0.5, source_tier="inferred", evidence="",
                     verified_against="", volatility="slow"):
        self.calls.append(("index_to_kb", title, topic, source_tier, quality_score))
        # same doc_id derivation as the real Tools.index_to_kb (tools/goethe.py):
        # sha256 of the first 500 content chars, first 16 hex chars.
        doc_hash = hashlib.sha256(content[:500].encode()).hexdigest()[:16]
        self._es_instance.index(
            index="lse-kb", id=doc_hash,
            document={
                "title": title, "content": content, "topic": topic,
                "quality_score": quality_score, "source_tier": source_tier,
                "evidence": evidence, "verified_against": verified_against,
                "volatility": volatility,
            },
        )
        return (
            f"KB created: doc_id={doc_hash} | title='{title}' | "
            f"topic={topic} | tier={source_tier} | quality={quality_score:.2f}"
        )


def _make_cfg(es_url="http://fake-es.invalid:9200"):
    """Minimal DreamConfig -- only es_url matters for the read-only tests
    below; every other field just needs a legal value."""
    return dr.DreamConfig(
        episode_dir="/tmp/episodes",
        dream_dir="/tmp/dreams",
        manifest_db="/tmp/manifest.db",
        es_url=es_url,
        tasks_db="/tmp/tasks.db",
        agent_log="/tmp/agent_commands.log",
        dream_llm_url="",
        node3090_llm_url="http://node3090.home.arpa:8080",
        node3090_ollama_url="http://node3090.home.arpa:11434",
        node3090_fallback_model="qwen3:4b",
        ollama_url="http://127.0.0.1:11434",
        embed_model="nomic-embed-text",
        dedup_floor=0.75,
        dedup_threshold=0.92,
        error_cluster_threshold=0.80,
        runner_session_prefix="",
        sessions_limit=50,
        since=None,
        pass_name="dedup",
        dry_run=True,
    )


# --- 1. proposal validator invariant tests (synthetic fixtures) ------------

class TestProposalValidatorInvariants:
    """DESIGN.md §2 row 3 -- validate_proposal_for_apply() must reject each
    of the three hard invariants dream_apply.py enforces fail-closed, even
    though nothing about the proposal's *shape* is wrong."""

    def test_rejects_quality_raising_proposal(self):
        es = FakeES(docs={("lse-kb", "doc-1"): {"quality_score": 0.5, "stale": False}})
        proposal = {
            "type": "dedup",
            "call": "mentor_correct",
            "args": {
                "doc_id": "doc-1",
                "correction": "merged content replacing the old text",
                "new_quality": 0.9,  # > live 0.5 -- must never be allowed to raise
                "provenance": f"dream-{TODAY}",
            },
            "why": "dedup merge",
        }
        reason = da.validate_proposal_for_apply(proposal, es)
        assert reason is not None
        assert "raise quality" in reason
        assert "0.50" in reason and "0.90" in reason

    def test_accepts_quality_holding_steady_proposal(self):
        """Sanity control: new_quality == current is a hold, not a raise --
        the normal shape of a dedup 'keep' proposal whose live doc already
        reflects the generation-time merge max -- and must pass this check
        (though it may still be rejected by other, unrelated invariants)."""
        es = FakeES(docs={("lse-kb", "doc-1"): {"quality_score": 0.5, "stale": False}})
        current_doc = es.get(index="lse-kb", id="doc-1")["_source"]
        assert da.check_quality_raise({"new_quality": 0.5}, current_doc) is None

    def test_rejects_ground_truth_self_grant(self):
        es = FakeES()  # unreached -- ground_truth check runs before any doc fetch
        proposal = {
            "type": "skill-candidate",
            "call": "skill_record",
            "args": {
                "task": "restart a stuck service",
                "occupation": "sre",
                "procedure": "check status; restart via systemctl",
                "verification": "systemctl is-active reports running",
                "provenance": f"dream-{TODAY}",
                "source_tier": "ground_truth",  # dream-origin may never self-grant this
                "quality": 0.6,
            },
            "why": "recurring failure cluster",
        }
        reason = da.validate_proposal_for_apply(proposal, es)
        assert reason is not None
        assert "ground_truth" in reason

    def test_rejects_quarantined_doc_touch(self):
        es = FakeES(docs={("lse-kb", "doc-q"): {"quality_score": 0.2, "stale": True}})
        proposal = {
            "type": "demote",
            "call": "record_outcome",
            "args": {
                "doc_id": "doc-q",
                "success": False,
                "evidence": "curl :8080/health -> 404, service confirmed down",
                "provenance": f"dream-{TODAY}",
            },
            "why": "contradicted by live evidence this session",
        }
        reason = da.validate_proposal_for_apply(proposal, es)
        assert reason is not None
        assert "quarantined" in reason

    def test_quarantine_check_allows_only_the_named_exception_type(self):
        """check_quarantine() in isolation: the quarantine-delete-request
        exception clause DESIGN.md §2 row 3(c) carves out (not emitted by
        any pass today, per dream_apply.py's own module docstring, but the
        code path must still exist and behave correctly)."""
        quarantined_doc = {"stale": True, "quality_score": 0.1}
        assert da.check_quarantine(quarantined_doc, da.QUARANTINE_DELETE_TYPE) is None
        assert da.check_quarantine(quarantined_doc, "demote") is not None
        # a non-quarantined doc is untouched by this check regardless of type
        assert da.check_quarantine({"stale": False, "quality_score": 0.8}, "demote") is None


# --- 2. origin/provenance stamping against a disposable ES doc -------------

class TestOriginProvenanceStamping:
    """DESIGN.md §2 row 3(d) + dream_apply.py's ONE EXCEPTION note: every
    applied write carries origin=dream + provenance=dream-YYYY-MM-DD, added
    via a single dedicated es.update() immediately after the Tools call --
    never decided by dream_apply.py itself, just tagged on afterward."""

    def test_stamp_dream_fields_sets_origin_and_provenance_directly(self):
        es = FakeES(docs={("lse-kb", "solo-doc"): {"quality_score": 0.5}})
        da._stamp_dream_fields(es, "solo-doc", "2026-07-11")
        doc = es.store[("lse-kb", "solo-doc")]
        assert doc["origin"] == "dream"
        assert doc["provenance"] == "dream-2026-07-11"

    def test_applied_proposal_stamps_a_disposable_doc(self):
        # "disposable" -- created fresh for this test, thrown away after;
        # not a real persisted lse-kb document.
        disposable_doc_id = "disposable-doc-1"
        es = FakeES(docs={
            ("lse-kb", disposable_doc_id): {
                "quality_score": 0.4, "empirical_runs": 2,
                "success_count": 1, "failure_count": 1,
            },
        })
        tools = FakeTools(es)
        group = [{
            "type": "demote",
            "call": "record_outcome",
            "args": {
                "doc_id": disposable_doc_id,
                "success": False,
                "evidence": "systemctl status shows failed, contradicts doc",
                "notes": "contradiction found this session",
            },
            "why": "live evidence disagrees with the doc",
        }]

        results = da.apply_group(tools, group, dry_run=False)

        assert len(results) == 1
        assert tools.calls == [
            ("record_outcome", disposable_doc_id, False,
             "contradiction found this session",
             "systemctl status shows failed, contradicts doc"),
        ]
        doc = es.store[("lse-kb", disposable_doc_id)]
        assert doc["origin"] == "dream"
        assert doc["provenance"] == f"dream-{TODAY}"
        # the record_outcome call itself still landed (FakeTools' own write)
        assert doc["last_outcome_notes"] == "contradiction found this session"


# --- 3. dedup merge preserves the trust-field union -------------------------

class TestDedupTrustFieldUnion:
    """dream_runner.py's dedup pass docstring: a confirmed pair becomes a
    mentor_correct on the keep-doc (merged content, quality raised to the
    max of the two) plus a record_outcome(success=False) on the retire-doc,
    linked by pair_id and applied/confirmed as ONE unit (DESIGN.md §6.5).
    dream_apply.py's ONE EXCEPTION note: since mentor_correct has no
    parameter for empirical_runs/success_count/failure_count, apply_group()
    unions those three fields across keep+retire's PRE-apply state and
    stamps the union onto the keep-doc only -- the retire-doc's own stats
    are left untouched by this merge (it is separately demoted via
    record_outcome, not folded into the keep-doc's numbers twice)."""

    def _build_group(self):
        keep_pre = {"quality_score": 0.6, "empirical_runs": 5, "success_count": 3, "failure_count": 2}
        retire_pre = {"quality_score": 0.4, "empirical_runs": 10, "success_count": 4, "failure_count": 6}
        es = FakeES(docs={
            ("lse-kb", "keep-1"): dict(keep_pre),
            ("lse-kb", "retire-1"): dict(retire_pre),
        })
        proposals = [
            {
                "type": "dedup", "role": "keep", "pair_id": "pair-A", "call": "mentor_correct",
                "args": {"doc_id": "keep-1", "correction": "merged text", "new_quality": 0.6},
                "why": "merge with retire-1",
            },
            {
                "type": "dedup", "role": "retire", "pair_id": "pair-A", "call": "record_outcome",
                "args": {"doc_id": "retire-1", "success": False, "notes": "superseded by keep-1"},
                "why": "redundant with kept doc keep-1",
            },
        ]
        return es, proposals, keep_pre, retire_pre

    def test_group_proposals_pairs_dedup_calls_by_pair_id(self):
        _, proposals, _, _ = self._build_group()
        groups = da.group_proposals(proposals)
        assert len(groups) == 1
        assert groups[0] == proposals

    def test_dedup_apply_unions_trust_fields_onto_keep_doc_only(self):
        es, proposals, keep_pre, retire_pre = self._build_group()
        tools = FakeTools(es)
        groups = da.group_proposals(proposals)
        assert len(groups) == 1

        da.apply_group(tools, groups[0], dry_run=False)

        keep_doc = es.store[("lse-kb", "keep-1")]
        assert keep_doc["empirical_runs"] == keep_pre["empirical_runs"] + retire_pre["empirical_runs"]
        assert keep_doc["success_count"] == keep_pre["success_count"] + retire_pre["success_count"]
        assert keep_doc["failure_count"] == keep_pre["failure_count"] + retire_pre["failure_count"]
        assert keep_doc["origin"] == "dream"
        assert keep_doc["provenance"] == f"dream-{TODAY}"

        # retire-doc is stamped (invariant (d) applies to every applied
        # write) but its OWN trust fields are untouched by the merge --
        # they stay at their pre-apply values, not summed a second time.
        retire_doc = es.store[("lse-kb", "retire-1")]
        assert retire_doc["origin"] == "dream"
        assert retire_doc["provenance"] == f"dream-{TODAY}"
        assert retire_doc["empirical_runs"] == retire_pre["empirical_runs"]
        assert retire_doc["success_count"] == retire_pre["success_count"]
        assert retire_doc["failure_count"] == retire_pre["failure_count"]


# --- 4. ES read-only boundary (mock-based) ----------------------------------

class TestESReadOnlyBoundary:
    """DESIGN.md §2 row 1 / dream_runner.py's own module docstring: the
    runner touches ES only via search_index(), which is search-only. And
    dream_apply.py's --dry-run must let nothing escape to real ES at all;
    even outside dry-run, no code path here may reach es.index/delete
    (FakeES raises on both, see its docstring)."""

    def test_dream_runner_search_index_never_writes(self, monkeypatch):
        es = FakeES(docs={("lse-kb", "d1"): {"title": "hello", "content": "world"}})
        monkeypatch.setattr(dr, "es_client", lambda cfg: es)
        cfg = _make_cfg()

        hits = dr.search_index(cfg, "lse-kb", {"query": {"match_all": {}}})

        assert es.calls == [("search", "lse-kb", None)]
        assert [h["_id"] for h in hits] == ["d1"]

    def test_dream_apply_dry_run_makes_zero_es_calls(self):
        """Nothing 'escapes' the --dry-run guard: no Tools method is called,
        and no ES verb of any kind (not even a read) fires."""
        es = FakeES(docs={("lse-kb", "doc-1"): {"quality_score": 0.5}})
        tools = FakeTools(es)
        group = [{
            "type": "demote", "call": "record_outcome",
            "args": {"doc_id": "doc-1", "success": False, "evidence": "x" * 25},
            "why": "would-be contradiction",
        }]

        results = da.apply_group(tools, group, dry_run=True)

        assert es.calls == []
        assert tools.calls == []
        assert len(results) == 1
        assert results[0]["result"].startswith("[dry-run] would call")

    def test_dream_apply_never_calls_delete(self):
        """A mixed real-apply batch (dedup pair + reverify + skill-candidate
        + kb-fact) -- es.delete() is never called anywhere in the flow.
        FakeES.delete() raises immediately if reached, so this test failing
        loudly (instead of silently) IS the assertion; the explicit
        verb-set check below is just a second, more legible layer on top.
        (es.index() IS expected here -- skill_record/index_to_kb legitimately
        create brand-new docs that way in the real goethe.py Tools class;
        see FakeES's own docstring.)"""
        es = FakeES(docs={
            ("lse-kb", "keep-2"): {"quality_score": 0.5, "empirical_runs": 1,
                                    "success_count": 1, "failure_count": 0},
            ("lse-kb", "retire-2"): {"quality_score": 0.3, "empirical_runs": 2,
                                      "success_count": 0, "failure_count": 2},
            ("lse-kb", "solo-1"): {"quality_score": 0.4},
        })
        tools = FakeTools(es)

        dedup_group = [
            {"type": "dedup", "pair_id": "p2", "call": "mentor_correct",
             "args": {"doc_id": "keep-2", "correction": "merged", "new_quality": 0.5},
             "why": "merge"},
            {"type": "dedup", "pair_id": "p2", "call": "record_outcome",
             "args": {"doc_id": "retire-2", "success": False, "notes": "dup"},
             "why": "redundant"},
        ]
        reverify_group = [
            {"type": "reverify", "call": "kb_verify", "args": {"doc_id": "solo-1"}, "why": "TTL expired"},
        ]
        skill_group = [
            {"type": "skill-candidate", "call": "skill_record",
             "args": {"task": "t", "occupation": "o", "procedure": "a; b",
                      "verification": "v", "provenance": f"dream-{TODAY}",
                      "quality": 0.45, "source_tier": "inferred"},
             "why": "recurring cluster"},
        ]
        kb_fact_group = [
            {"type": "kb-fact", "call": "index_to_kb",
             "args": {"content": "a fact worth recording, long enough to be real content",
                      "title": "t", "topic": "general", "source_tier": "inferred",
                      "quality_score": 0.4, "evidence": "", "verified_against": "",
                      "volatility": "slow"},
             "why": "standalone fact"},
        ]

        for group in (dedup_group, reverify_group, skill_group, kb_fact_group):
            da.apply_group(tools, group, dry_run=False)

        verbs = {c[0] for c in es.calls}
        assert verbs, "expected at least one ES call across the batch"
        assert verbs <= {"get", "update", "search", "index"}
        assert "delete" not in verbs
        # the skill_record path's own origin-stamp writes to lse-skills,
        # not lse-kb -- confirm it happened via the expected id shape.
        skill_hash = hashlib.sha256(b"test-skill-slug").hexdigest()[:16]
        assert es.store[("lse-skills", skill_hash)]["origin"] == "dream"


# --- 5. kb-fact / index_to_kb (DESIGN.md §6.2's fifth proposal type) -------

class TestKbFactProposal:
    """kb-fact proposals (call=index_to_kb) propose a NEW doc rather than
    touching an existing one -- reused verbatim from Thread 1 Prompt 1.5's
    SCRIBE-1 debrief format (DESIGN.md §6.2), and completed here for
    dream_apply.py's own apply_group()/render_group() dispatch (Thread 2
    close, Prompt 2.10) so a dream's own kb-fact proposals -- e.g. this
    thread's own calibration-verdict debrief -- have a real apply path,
    not just a validator that accepts the shape."""

    def _kb_fact_proposal(self, **overrides):
        args = {
            "content": "TRAUM Thread 2 calibration verdict: production linear retrieval "
                       "was bit-for-bit identical (recall@1/@3, MRR) before vs after the "
                       "first supervised dream despite ~84% corpus growth (200->368 docs).",
            "title": "TRAUM calibration run 1 verdict",
            "topic": "lse-operations",
            "source_tier": "primary",
            "quality_score": 0.75,
            "evidence": "docs/dreaming/calibration-run-1.md: linear recall@1=0.76 "
                        "recall@3=0.84 MRR=0.800 identical before/after",
            "verified_against": "",
            "volatility": "static",
        }
        args.update(overrides)
        return {
            "type": "kb-fact",
            "call": "index_to_kb",
            "args": args,
            "why": "record the calibration verdict as an independently retrievable fact",
        }

    def test_kb_fact_proposal_validates_with_no_es_doc_needed(self):
        # a NEW-doc proposal has no doc_id -- validate_proposal_for_apply's
        # doc_id-gated checks never fire, so this passes even against an
        # EMPTY FakeES (no live ES doc has to exist for a kb-fact to validate).
        es = FakeES()
        assert da.validate_proposal_for_apply(self._kb_fact_proposal(), es) is None

    def test_kb_fact_proposal_still_rejects_ground_truth(self):
        es = FakeES()
        proposal = self._kb_fact_proposal(source_tier="ground_truth")
        reason = da.validate_proposal_for_apply(proposal, es)
        assert reason is not None
        assert "ground_truth" in reason

    def test_kb_fact_proposal_applies_and_gets_full_stamp(self):
        es = FakeES()
        tools = FakeTools(es)
        proposal = self._kb_fact_proposal()
        group = [proposal]

        results = da.apply_group(tools, group, dry_run=False)

        assert len(results) == 1
        assert tools.calls[0][0] == "index_to_kb"
        doc_hash = hashlib.sha256(proposal["args"]["content"][:500].encode()).hexdigest()[:16]
        doc = es.store[("lse-kb", doc_hash)]
        assert doc["title"] == proposal["args"]["title"]
        # index_to_kb has neither provenance nor origin (DESIGN.md §6.2) --
        # both are added by the SAME full stamp mentor_correct/record_outcome get.
        assert doc["origin"] == "dream"
        assert doc["provenance"] == f"dream-{TODAY}"

    def test_render_group_shows_index_to_kb_fields(self):
        rendered = da.render_group([self._kb_fact_proposal()], dream_dir="/tmp/dreams/2026-07-11")
        assert "index_to_kb" in rendered
        assert "TRAUM calibration run 1 verdict" in rendered
        assert "source_tier:" in rendered and "primary" in rendered
        # no doc_id anywhere in a kb-fact proposal -> REPORT header, not TARGET
        assert "――― REPORT:" in rendered
