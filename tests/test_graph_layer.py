#!/usr/bin/env python3
"""Phase 5 graph-layer contract tests (task 9d4b23ca, step 14).

Pins the Phase 5 contracts (tools/goethe_graph.py + the graph surface in
tools/goethe_kb.py):

  1. Extraction uses ONLY the fixed vocabulary (6 entity types / 8
     relations); unknown tokens are ignored; empty text yields [].
  2. Inline extraction NEVER blocks the index write: extraction or
     proposal-persistence failures are swallowed and index_to_kb still
     succeeds (roadmap Phase 5: best-effort by contract).
  3. materialize_accepted_graph writes ONLY operator-APPLIED proposals;
     STAGED proposals are never materialized; the state db is opened
     read-only and never mutated by the materializer.
  4. search_kb with GRAPH_RECALL=0 (default) is unchanged (the graph
     expansion is never even invoked); GRAPH_RECALL=1 is additive only
     (base result + 'related via:' lines), capped at +5, deduped, and a
     graph-side failure degrades silently to the base result.
  5. graph_query is read-only (the tests give it an ES client that has NO
     write methods) and validates its inputs.

SAFETY: the one live-ES path (index_to_kb / search_kb seeding) routes
through an index-rewriting proxy: lse-kb -> lse-kb-test-<pid>-<uuid>.
Any other index name raises. All graph-index access in these tests goes
through fakes, so lse-graph (live or not) is never touched.

Run on LUCIFER (ES on localhost:9200):
    /home/sy5/owui/bin/python3 -m pytest tests/test_graph_layer.py -q
"""

import hashlib
import json
import math
import os
import random
import re
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

# ── import the modules under test from tools/ ────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe  # noqa: E402  (Tools + KBMixin)
import goethe_graph  # noqa: E402

# ── test-index safety layer (pattern: tests/test_kb_contracts.py) ────────────

_RUN_TAG = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
KB_TEST_INDEX = f"lse-kb-test-{_RUN_TAG}"
INDEX_MAP = {"lse-kb": KB_TEST_INDEX}
_TEST_INDEX_RE = re.compile(r"^lse-kb-test-(\d+)-[0-9a-f]{8}$")


def _rewrite(index: str) -> str:
    if index in INDEX_MAP.values():
        return index
    if index not in INDEX_MAP:
        raise RuntimeError(
            f"safety guard: code under test touched unexpected index '{index}'"
        )
    return INDEX_MAP[index]


class ESIndexRewriteProxy:
    """Rewrites lse-kb -> throwaway test index; force-refresh after writes."""

    def __init__(self, raw):
        self._raw = raw

    def search(self, *, index, **kw):
        return self._raw.search(index=_rewrite(index), **kw)

    def get(self, *, index, id, **kw):
        return self._raw.get(index=_rewrite(index), id=id, **kw)

    def count(self, *, index, **kw):
        return self._raw.count(index=_rewrite(index), **kw)

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

    # NOTE: deliberately NO `indices` property (same as test_kb_contracts):
    # the best-effort `es.indices.refresh(index="lse-kb")` inside index_to_kb
    # hits AttributeError on the proxy and is swallowed by design — this
    # keeps the production index name out of every raw client call.


def _sweep_orphaned_indices(es):
    try:
        resp = es.indices.get(index="lse-kb-test-*")
    except Exception:
        return
    for name in resp:
        m = _TEST_INDEX_RE.match(name)
        if m and int(m.group(1)) != os.getpid():
            try:
                es.indices.delete(index=name)
            except Exception:
                pass


# ── deterministic fake embeddings (pattern: test_kb_contracts.py) ───────────

def _hash_vec(seed: str) -> list:
    rnd = random.Random(hashlib.sha256(seed.encode()).digest())
    v = [rnd.uniform(-1.0, 1.0) for _ in range(768)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def fake_embed(text: str) -> list:
    """768-dim unit vector; identical/@@anchor@@-shared text -> high cosine."""
    m = re.search(r"@@anchor:(\w+)@@", text)
    noise = _hash_vec("NOISE::" + text)
    if not m:
        return noise
    base = _hash_vec("ANCHOR::" + m.group(1))
    v = [0.8 * b + 0.6 * n for b, n in zip(base, noise)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


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


@pytest.fixture(scope="session")
def raw_es():
    from elasticsearch import Elasticsearch

    es = Elasticsearch("http://127.0.0.1:9200", request_timeout=10)
    if not es.ping():
        pytest.skip("Elasticsearch not reachable on 127.0.0.1:9200")
    _sweep_orphaned_indices(es)
    yield es
    try:
        if es.indices.exists(index=KB_TEST_INDEX):
            es.indices.delete(index=KB_TEST_INDEX)
    except Exception:
        pass


@pytest.fixture()
def es(raw_es):
    if raw_es.indices.exists(index=KB_TEST_INDEX):
        raw_es.indices.delete(index=KB_TEST_INDEX)
    raw_es.indices.create(index=KB_TEST_INDEX, **KB_TEST_MAPPING)
    yield ESIndexRewriteProxy(raw_es)
    if raw_es.indices.exists(index=KB_TEST_INDEX):
        raw_es.indices.delete(index=KB_TEST_INDEX)


@pytest.fixture()
def tools(es, monkeypatch, tmp_path):
    t = goethe.Tools()
    t.valves.LOG_FILE = str(tmp_path / "test-audit.log")
    # Keep the inline graph path away from the LIVE traum-state.db.
    monkeypatch.setenv("GOETHE_DREAM_DIR", str(tmp_path))
    monkeypatch.setattr(t, "_es", lambda: es)
    monkeypatch.setattr(t, "_embed", lambda text: fake_embed(text))
    return t


# Text that yields real entities (node + service + port) so the inline path
# actually has work to do — and so a failure injected mid-path is meaningful.
GRAPH_TEXT = "node3090 runs goethe_mcp on port 9700."


# ══ 1. extraction — fixed vocabulary only ═══════════════════════════════════


class TestExtractionVocabulary:
    def test_entities_and_edges_within_vocabulary(self):
        props = goethe_graph.extract_graph_proposals(
            "node3090 runs goethe_mcp on port 9700; RUTX50 is the edge device.",
            "docX",
        )
        assert len(props) == 1
        p = props[0]
        assert p["type"] == "graph"
        ents = p["args"]["entities"]
        edges = p["args"]["edges"]
        assert ents, "expected entities from known tokens"
        assert all(e["type"] in goethe_graph.ENTITY_TYPES_SET for e in ents)
        assert all(e["rel"] in goethe_graph.RELATIONS_SET for e in edges)
        assert all(e["evidence_doc_id"] == "docX" for e in edges)
        names = {e["name"] for e in ents}
        assert {"node3090", "goethe_mcp", "9700", "rutx50"} <= names

    def test_port_filter_drops_ephemeral_keeps_stable(self):
        # 2026-09-23 operator decision "A + D + port filter": the Studio
        # engine port is kernel-ephemeral per session (KB 3dfcafb1ddb99f4e);
        # docs quote session ports verbatim. Only environment-stable ports
        # are graph material - ephemeral ones must not become entities, and
        # their documented_by edges must not be minted either.
        props = goethe_graph.extract_graph_proposals(
            "llama-server bound 127.0.0.1 on port 8083 this session; "
            "the gateway is port:9700; a forwarder tried port 33703; "
            "Studio UI listens on port 8080.",
            "docPorts",
        )
        assert len(props) == 1
        ents = props[0]["args"]["entities"]
        port_names = {e["name"] for e in ents if e["type"] == "port"}
        assert port_names == {"9700", "8080"}  # stable ports kept
        assert not ({"8083", "33703"} & port_names)  # ephemeral dropped
        edge_srcs = {e["src"] for e in props[0]["args"]["edges"]}
        assert "8083" not in edge_srcs
        assert "33703" not in edge_srcs

    def test_model_token_extracted_as_model_type(self):
        props = goethe_graph.extract_graph_proposals(
            "serving Qwen3-27B on the box", "docM")
        names = {(e["type"], e["name"])
                 for p in props for e in p["args"]["entities"]}
        assert ("model", "Qwen3-27B") in names

    def test_unknown_tokens_ignored(self):
        assert goethe_graph.extract_graph_proposals(
            "The zyxwv quux apparatus performs frobnication.", "docY") == []

    def test_empty_or_missing_input_yields_empty(self):
        assert goethe_graph.extract_graph_proposals("", "docZ") == []
        assert goethe_graph.extract_graph_proposals(None, "docZ") == []
        assert goethe_graph.extract_graph_proposals(GRAPH_TEXT, "") == []

    def test_validate_entity_rejects_unknown_type(self):
        with pytest.raises(ValueError):
            goethe_graph.validate_entity({"type": "appliance", "name": "x"})

    def test_validate_entity_rejects_empty_name(self):
        with pytest.raises(ValueError):
            goethe_graph.validate_entity({"type": "node", "name": "  "})

    def test_validate_edge_rejects_unknown_relation(self):
        with pytest.raises(ValueError):
            goethe_graph.validate_edge(
                {"src": "a", "rel": "bananas", "dst": "b",
                 "evidence_doc_id": "d"})

    def test_validate_edge_requires_evidence(self):
        with pytest.raises(ValueError):
            goethe_graph.validate_edge(
                {"src": "a", "rel": "runs_on", "dst": "b"})

    def test_ids_are_deterministic(self):
        a = goethe_graph.entity_id("node", "node3090")
        b = goethe_graph.entity_id("node", "node3090")
        assert a == b and len(a) == 16
        e1 = goethe_graph.edge_id(a, "runs_on", "svc", "doc1")
        e2 = goethe_graph.edge_id(a, "runs_on", "svc", "doc1")
        e3 = goethe_graph.edge_id(a, "runs_on", "svc", "doc2")
        assert e1 == e2 and e1 != e3


# ══ 2. inline extraction never blocks the index write ═══════════════════════


class TestInlineNeverBlocks:
    def test_extraction_failure_does_not_block_index(self, tools, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("extraction blew up")

        monkeypatch.setattr(goethe_graph, "extract_graph_proposals", boom)
        r = tools.index_to_kb(content=GRAPH_TEXT, title="graph test",
                              topic="general")
        assert r.startswith("KB created: doc_id=")

    def test_persistence_failure_does_not_block_index(self, tools, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("state db on fire")

        monkeypatch.setattr(goethe_graph, "insert_graph_proposals", boom)
        r = tools.index_to_kb(content=GRAPH_TEXT, title="graph test 2",
                              topic="general")
        assert r.startswith("KB created: doc_id=")

    def test_inline_stages_proposal_on_success(self, tools, tmp_path):
        r = tools.index_to_kb(content=GRAPH_TEXT, title="graph test 3",
                              topic="general")
        assert r.startswith("KB created: doc_id=")
        db = tmp_path / "traum-state.db"
        assert db.exists(), "inline path should have created a state db"
        conn = sqlite3.connect(db)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM proposals "
                "WHERE proposal_type='graph' AND state IN ('STAGED','PENDING')"
            ).fetchone()[0]
            applied = conn.execute(
                "SELECT COUNT(*) FROM proposals WHERE state='APPLIED'"
            ).fetchone()[0]
        finally:
            conn.close()
        # PENDING is the canonical end state: record_proposals stores
        # STAGED, then finish_attempt(SUCCEEDED) promotes it to PENDING
        # ('parent_attempt_completed') — queued for the Human Gate, never
        # auto-accepted.
        assert n >= 1, "expected a STAGED/PENDING graph proposal"
        assert applied == 0, "inline path must never auto-accept"


# ══ 3. materializer — only APPLIED proposals ════════════════════════════════


class FakeGraphIndex:
    """Capturing fake of the lse-graph ES client (has write methods)."""

    def __init__(self, existing_entities=None):
        self.written = []
        self._existing = existing_entities or []
        self.refreshed = 0

        class _Indices:
            def __init__(self, outer):
                self._o = outer

            def exists(self, *, index):
                return True

            def create(self, *, index, body=None):
                self._o.written.append(("create", index))

            def refresh(self, *, index):
                self._o.refreshed += 1

        self.indices = _Indices(self)

    def search(self, *, index, body=None, **kw):
        return {"hits": {"hits": [
            {"_id": goethe_graph.entity_id(e["type"], e["name"]),
             "_source": {"type": e["type"], "name": e["name"]}}
            for e in self._existing
        ]}}

    def index(self, *, index, id=None, document=None, **kw):
        self.written.append((index, id, document))
        return {"result": "created"}


def _stage(tmp_path, text, doc_id):
    """Stage one real extraction through the canonical TRAUM path."""
    props = goethe_graph.extract_graph_proposals(text, doc_id)
    assert props, "test text must yield a proposal"
    stored = goethe_graph.insert_graph_proposals(
        props, state_db=str(tmp_path / "traum-state.db"), source="graph-test")
    assert stored and all(r["state"] in {"STAGED", "PENDING"} for r in stored)
    return stored


def _apply(state_db, proposal_id):
    conn = sqlite3.connect(state_db)
    try:
        conn.execute("UPDATE proposals SET state='APPLIED' WHERE proposal_id=?",
                     (proposal_id,))
        conn.commit()
    finally:
        conn.close()


class TestMaterializerOnlyAccepted:
    def test_staged_never_materialized(self, tmp_path):
        stored = _stage(tmp_path, GRAPH_TEXT, "docA")
        db = str(tmp_path / "traum-state.db")
        fake = FakeGraphIndex()
        out = goethe_graph.materialize_accepted_graph(es=fake, state_db=db)
        assert out["applied"] == 0
        assert out["entities_written"] == 0
        assert out["edges_written"] == 0
        assert fake.written == []

    def test_only_applied_written(self, tmp_path):
        stored = _stage(tmp_path, GRAPH_TEXT, "docA")
        db = str(tmp_path / "traum-state.db")
        _apply(db, stored[0]["proposal_id"])
        fake = FakeGraphIndex()
        out = goethe_graph.materialize_accepted_graph(es=fake, state_db=db)
        assert out["applied"] == 1
        assert out["entities_written"] > 0
        assert out["edges_written"] > 0
        assert out["errors"] == []
        kinds = {doc["kind"] for _, _, doc in fake.written}
        assert kinds <= {"entity", "edge"}
        # materializer is read-only on the state db: row still APPLIED,
        # nothing added.
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT state FROM proposals WHERE proposal_id=?",
                (stored[0]["proposal_id"],)).fetchone()
            n = conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
        finally:
            conn.close()
        assert row[0] == "APPLIED"
        assert n == 1

    def test_mixed_states_write_only_the_accepted_payload(self, tmp_path):
        a = _stage(tmp_path, GRAPH_TEXT, "docA")          # node3090 etc.
        b = _stage(tmp_path, "RUTX50 pfsense on port 53", "docB")
        db = str(tmp_path / "traum-state.db")
        _apply(db, b[0]["proposal_id"])  # apply ONLY the second
        fake = FakeGraphIndex()
        out = goethe_graph.materialize_accepted_graph(es=fake, state_db=db)
        assert out["applied"] == 1
        written_names = {doc.get("name") for _, _, doc in fake.written
                         if doc.get("kind") == "entity"}
        assert "rutx50" in written_names and "pfsense" in written_names
        assert "node3090" not in written_names  # docA stayed STAGED

    def test_missing_state_db_reports_error(self, tmp_path):
        out = goethe_graph.materialize_accepted_graph(
            es=FakeGraphIndex(), state_db=str(tmp_path / "nope.db"))
        assert out["applied"] == 0
        assert out["errors"]


# ══ 4. search_kb — GRAPH_RECALL valve ═══════════════════════════════════════


class FakeRecallES:
    """Scripted fake of the lse-graph client for _graph_recall_lines."""

    def __init__(self, hop1_edges, entity_names, hop2_edges, kb_docs,
                 index_exists=True):
        self.hop1 = hop1_edges
        self.entity_names = entity_names
        self.hop2 = hop2_edges
        self.kb_docs = kb_docs
        self.index_exists = index_exists

        class _Indices:
            def __init__(self, outer):
                self._o = outer

            def exists(self, *, index):
                return self._o.index_exists

        self.indices = _Indices(self)

    def search(self, *, index, body=None, **kw):
        for f in body["query"]["bool"]["filter"]:
            if "terms" in f and "evidence_doc_id" in f["terms"]:
                return {"hits": {"hits": [
                    {"_id": f"edge{i}", "_source": e}
                    for i, e in enumerate(self.hop1)]}}
            if "terms" in f and "src" in f["terms"]:
                return {"hits": {"hits": [
                    {"_id": f"edge{i}", "_source": e}
                    for i, e in enumerate(self.hop2)]}}
        raise AssertionError(f"unexpected query: {json.dumps(body)}")

    def get(self, *, index, id, **kw):
        if index == goethe_graph.GRAPH_INDEX:
            if id not in self.entity_names:
                raise KeyError(id)  # missing entity doc: label falls back
            return {"_source": {"kind": "entity", "name": self.entity_names[id]}}
        if index == "lse-kb":
            return {"_source": self.kb_docs[id]}
        raise AssertionError(f"unexpected index {index}")


class TestSearchKbGraphRecall:
    DOC = "@@anchor:graph@@ node3090 runs goethe_mcp on port 9700."
    QUERY = "@@anchor:graph@@ node3090 goethe_mcp port 9700"

    def _seed(self, tools):
        tools.search_kb("warmup no hits", min_score=99.0)  # consume [TIME]
        r = tools.index_to_kb(content=self.DOC, title="graph seed",
                              topic="general")
        assert r.startswith("KB created: doc_id=")

    def test_valve_off_unchanged_and_never_invoked(self, tools, monkeypatch):
        self._seed(tools)

        def spy(hits):
            raise AssertionError("graph recall must not run with valve off")

        monkeypatch.setattr(tools, "_graph_recall_lines", spy)
        tools.valves.GRAPH_RECALL = 0
        r = tools.search_kb(self.QUERY, min_score=0.1)
        assert "[graph]" not in r

    def test_valve_on_is_additive(self, tools, monkeypatch):
        self._seed(tools)
        base = tools.search_kb(self.QUERY, min_score=0.1)
        marker = (
            "[graph] doc_id=zzz | T | topic=general | quality=0.50 | "
            "related via: node3090\n    (Phase 5 graph recall — additive, "
            "outside the ranked results above)\n"
        )
        monkeypatch.setattr(tools, "_graph_recall_lines",
                            lambda hits: [marker])
        tools.valves.GRAPH_RECALL = 1
        r = tools.search_kb(self.QUERY, min_score=0.1)
        assert r.startswith(base)
        assert marker in r

    def test_valve_on_degrades_silently(self, tools, monkeypatch):
        self._seed(tools)
        base = tools.search_kb(self.QUERY, min_score=0.1)

        def boom(hits):
            raise RuntimeError("graph index on fire")

        monkeypatch.setattr(tools, "_graph_recall_lines", boom)
        tools.valves.GRAPH_RECALL = 1
        r = tools.search_kb(self.QUERY, min_score=0.1)
        assert r == base  # additive by design: failure = old behaviour

    def test_recall_lines_cap_five_and_deduped(self, tools, monkeypatch):
        hits = [{"_id": "docA",
                 "_source": {"title": "A", "content": "x", "topic": "general",
                             "quality_score": 0.5}}]
        hop1 = [
            {"src": "EA", "rel": "documented_by", "dst": "docA",
             "evidence_doc_id": "docA"},
            {"src": "EB", "rel": "runs_on", "dst": "docA",
             "evidence_doc_id": "docA"},
        ]
        # 8 edges, 7 UNIQUE linked docs (docB twice) -> dedup to 7, cap to 5.
        hop2 = [
            {"src": "EA", "rel": "documented_by", "dst": f"doc{c}",
             "evidence_doc_id": f"doc{c}"}
            for c in "BCDEFGH"
        ] + [
            {"src": "EA", "rel": "documented_by", "dst": "docB",
             "evidence_doc_id": "docB"},  # duplicate of first edge
        ]
        kb_docs = {f"doc{c}": {"title": f"T{c}", "topic": "general",
                              "quality_score": 0.5}
                   for c in "BCDEFGH"}
        fake = FakeRecallES(hop1, {"EA": "node3090"}, hop2, kb_docs)
        monkeypatch.setattr(tools, "_es", lambda: fake)
        lines = tools._graph_recall_lines(hits)
        assert len(lines) == 5  # cap
        assert all("related via: " in ln for ln in lines)
        assert "node3090" in lines[0]  # EA's name resolved
        assert "docH" not in "".join(lines)  # beyond the cap
        assert "docB" in "".join(lines)  # deduped once, not twice

    def test_recall_lines_dedup_only(self, tools, monkeypatch):
        hits = [{"_id": "docA", "_source": {"title": "A"}}]
        hop1 = [{"src": "EA", "rel": "documented_by", "dst": "docA",
                 "evidence_doc_id": "docA"}]
        hop2 = [
            {"src": "EA", "rel": "documented_by", "dst": f"doc{c}",
             "evidence_doc_id": f"doc{c}"}
            for c in "BC"
        ] + [
            {"src": "EA", "rel": "runs_on", "dst": "docB",
             "evidence_doc_id": "docB"},  # second edge, same doc
        ]
        kb_docs = {f"doc{c}": {"title": f"T{c}", "topic": "general",
                              "quality_score": 0.5}
                   for c in "BC"}
        fake = FakeRecallES(hop1, {"EA": "node3090"}, hop2, kb_docs)
        monkeypatch.setattr(tools, "_es", lambda: fake)
        lines = tools._graph_recall_lines(hits)
        assert len(lines) == 2  # 3 edges -> 2 unique docs

    def test_recall_lines_missing_index_returns_empty(self, tools, monkeypatch):
        fake = FakeRecallES([], {}, {}, {}, index_exists=False)
        monkeypatch.setattr(tools, "_es", lambda: fake)
        assert tools._graph_recall_lines([{"_id": "docA"}]) == []


# ══ 5. graph_query — read-only ══════════════════════════════════════════════


class ReadOnlyGraphES:
    """ES client with NO write methods — any write attempt is an
    AttributeError that graph_query would surface as 'graph_query error:'."""

    def __init__(self, hits, index_exists=True):
        self.hits = hits
        self.index_exists = index_exists
        self.search_calls = []

        class _Indices:
            def __init__(self, outer):
                self._o = outer

            def exists(self, *, index):
                return self._o.index_exists

        self.indices = _Indices(self)

    def search(self, *, index, body=None, **kw):
        self.search_calls.append(body)
        return {"hits": {"hits": self.hits}}


class TestGraphQueryReadOnly:
    HITS = [
        {"_id": "e1", "_source": {"kind": "entity", "type": "node",
                                  "name": "node3090", "attrs": {}}},
        {"_id": "g1", "_source": {"kind": "edge", "src": "e1",
                                  "rel": "runs_on", "dst": "e2",
                                  "evidence_doc_id": "docA"}},
        {"_id": "g2", "_source": {"kind": "edge", "src": "e2",
                                  "rel": "documented_by", "dst": "docB",
                                  "evidence_doc_id": "docB"}},
    ]

    def test_returns_entity_and_edges(self, tools, monkeypatch):
        fake = ReadOnlyGraphES(self.HITS)
        monkeypatch.setattr(tools, "_es", lambda: fake)
        r = tools.graph_query("node3090")
        assert r.startswith("graph_query: 'node3090'")
        assert "ENTITY node 'node3090'" in r
        assert "EDGE e1 -[runs_on]-> e2" in r
        assert "(evidence: docA)" in r
        assert "(evidence: docB)" in r

    def test_rel_filter_constrains_query(self, tools, monkeypatch):
        fake = ReadOnlyGraphES(self.HITS)
        monkeypatch.setattr(tools, "_es", lambda: fake)
        tools.graph_query("node3090", rel="runs_on")
        assert len(fake.search_calls) == 1
        body = json.dumps(fake.search_calls[0])
        assert json.dumps({"term": {"rel": "runs_on"}}) in body

    def test_unknown_relation_rejected_without_es_call(self, tools, monkeypatch):
        fake = ReadOnlyGraphES(self.HITS)
        monkeypatch.setattr(tools, "_es", lambda: fake)
        r = tools.graph_query("node3090", rel="bananas")
        assert r.startswith("graph_query: relation 'bananas' not in fixed")
        assert fake.search_calls == []

    def test_empty_entity_rejected_without_es_call(self, tools, monkeypatch):
        fake = ReadOnlyGraphES(self.HITS)
        monkeypatch.setattr(tools, "_es", lambda: fake)
        r = tools.graph_query("  ")
        assert r.startswith("graph_query: entity must be a non-empty")
        assert fake.search_calls == []

    def test_missing_index_reports_pending_gate(self, tools, monkeypatch):
        fake = ReadOnlyGraphES([], index_exists=False)
        monkeypatch.setattr(tools, "_es", lambda: fake)
        r = tools.graph_query("node3090")
        assert "no graph data" in r and "lse-graph index does not exist" in r

    def test_no_hits(self, tools, monkeypatch):
        fake = ReadOnlyGraphES([])
        monkeypatch.setattr(tools, "_es", lambda: fake)
        r = tools.graph_query("node3090")
        assert r == "graph_query: no graph data for 'node3090'."

# ══ 6. Human Gate wiring — the graph apply path (2026-09-18 fix) ═══════════
#
# The graph class has call='none': NO tool dispatch. The Human Gate is the
# only thing that moves a proposal to APPLIED; materialization is a pure
# idempotent projection (materialize_accepted_graph). This section pins:
#   - apply_group handles the graph class without dispatching any tool;
#   - decide_proposal(approve) on a graph proposal ends APPLIED and projects
#     entities/edges into the (fake) lse-graph index;
#   - an APPLY_FAILED graph proposal can be re-approved (re-claim), while a
#     non-graph APPLY_FAILED proposal still cannot (partial-write discipline);
#   - a projection failure does not roll back the recorded APPLIED decision.


class FakeDecisionES(FakeGraphIndex):
    """FakeGraphIndex (lse-graph side) + lse-kb .get() for the orphan guard."""

    def __init__(self, kb_docs=None):
        super().__init__()
        self.kb = dict(kb_docs or {})

    def get(self, *, index, id, **kw):
        if index == "lse-kb" and id in self.kb:
            return {"_source": dict(self.kb[id])}
        raise KeyError(f"no such doc {index}/{id}")


class FakeDecisionTools:
    """Tools double for decide_proposal: graph apply must dispatch NO
    semantic write method — any call here fails the test."""

    def __init__(self, es):
        self._es_client = es
        self.write_calls = []

    def _es(self):
        return self._es_client

    def mentor_correct(self, *a, **k):
        self.write_calls.append("mentor_correct")
        raise AssertionError("graph apply must not dispatch mentor_correct")

    def record_outcome(self, *a, **k):
        self.write_calls.append("record_outcome")
        raise AssertionError("graph apply must not dispatch record_outcome")

    def index_to_kb(self, *a, **k):
        self.write_calls.append("index_to_kb")
        raise AssertionError("graph apply must not dispatch index_to_kb")

    def record_error(self, *a, **k):
        self.write_calls.append("record_error")
        raise AssertionError("graph apply must not dispatch record_error")


def _kb_doc(doc_id):
    return {"doc_id": doc_id, "title": f"evidence {doc_id}",
            "quality_score": 0.8, "stale": False}


class TestGraphApplyWiring:
    def test_apply_group_graph_dispatches_nothing(self, tmp_path):
        import dream_apply
        stored = _stage(tmp_path, GRAPH_TEXT, "docG")
        p = stored[0]["proposal"]
        es = FakeDecisionES(kb_docs={"docG": _kb_doc("docG")})
        tools = FakeDecisionTools(es)
        results = dream_apply.apply_group(tools, [p], dry_run=False,
                                          repo_root=str(tmp_path))
        assert len(results) == 1
        assert "graph approved" in results[0]["result"]
        assert tools.write_calls == []

    def test_decide_proposal_graph_applies_and_projects(self, tmp_path):
        import dream_apply
        import traum_state
        stored = _stage(tmp_path, GRAPH_TEXT, "docG")
        db = str(tmp_path / "traum-state.db")
        state = traum_state.TraumState(db)
        es = FakeDecisionES(kb_docs={"docG": _kb_doc("docG")})
        tools = FakeDecisionTools(es)
        out = dream_apply.decide_proposal(
            state, stored[0]["proposal_id"], "approve", tools=tools)
        assert out["state"] == "APPLIED" and out["idempotent"] is False
        assert tools.write_calls == []
        # projection ran against the (fake) lse-graph index
        proj = out["graph_projection"]
        assert proj["errors"] == []
        assert proj["entities_written"] > 0
        assert proj["edges_written"] > 0
        kinds = {doc["kind"] for _, _, doc in es.written}
        assert kinds == {"entity", "edge"}
        row = state.get_proposal(stored[0]["proposal_id"])
        assert row["state"] == "APPLIED"

    def test_apply_failed_graph_can_be_reapproved(self, tmp_path):
        import dream_apply
        import traum_state
        stored = _stage(tmp_path, GRAPH_TEXT, "docG")
        db = str(tmp_path / "traum-state.db")
        state = traum_state.TraumState(db)
        pid = stored[0]["proposal_id"]
        # Simulate the pre-fix failure: proposal left APPLY_FAILED.
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "UPDATE proposals SET state='APPLY_FAILED',revision=revision+1,"
                "reason=? WHERE proposal_id=?",
                ("ApplyError: unknown call 'none', not applied", pid))
            conn.commit()
        finally:
            conn.close()
        es = FakeDecisionES(kb_docs={"docG": _kb_doc("docG")})
        tools = FakeDecisionTools(es)
        out = dream_apply.decide_proposal(state, pid, "approve", tools=tools)
        assert out["state"] == "APPLIED"
        assert out["graph_projection"]["entities_written"] > 0
        # idempotent re-approve still re-runs the projection (retry path)
        out2 = dream_apply.decide_proposal(state, pid, "approve", tools=tools)
        assert out2["idempotent"] is True
        assert "graph_projection" in out2

    def test_apply_failed_non_graph_still_blocked(self, tmp_path):
        import dream_apply
        import traum_state
        db = str(tmp_path / "traum-state.db")
        state = traum_state.TraumState(db)
        run = state.create_run(profile="test", requested_passes=["patterns"],
                               config={}, source="test")
        attempt = state.start_attempt(run["run_id"], "patterns")
        stored = state.record_proposals(run["run_id"], attempt["attempt_id"], [{
            "type": "diagnosis", "call": "record_error",
            "args": {"error_text": "boom", "context": "test",
                     "resolution": "fix",
                     "interpretation": "it is not what it looks like",
                     "anti_response": ""},
            "why": "test"},
        ])[0]
        state.finish_attempt(attempt["attempt_id"], "SUCCEEDED", summary={})
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "UPDATE proposals SET state='APPLY_FAILED',revision=revision+1,"
                "reason='boom' WHERE proposal_id=?", (stored["proposal_id"],))
            conn.commit()
        finally:
            conn.close()
        es = FakeDecisionES()
        tools = FakeDecisionTools(es)
        with pytest.raises(traum_state.ConflictError, match="cannot be claimed"):
            dream_apply.decide_proposal(
                state, stored["proposal_id"], "approve", tools=tools)

    def test_projection_failure_does_not_rollback_applied(self, tmp_path, monkeypatch):
        import dream_apply
        import traum_state
        stored = _stage(tmp_path, GRAPH_TEXT, "docG")
        db = str(tmp_path / "traum-state.db")
        state = traum_state.TraumState(db)
        es = FakeDecisionES(kb_docs={"docG": _kb_doc("docG")})
        tools = FakeDecisionTools(es)

        def boom(*a, **k):
            raise RuntimeError("es down")
        monkeypatch.setattr(goethe_graph, "materialize_accepted_graph", boom)
        out = dream_apply.decide_proposal(
            state, stored[0]["proposal_id"], "approve", tools=tools)
        assert out["state"] == "APPLIED"
        assert "error" in out["graph_projection"]
        row = state.get_proposal(stored[0]["proposal_id"])
        assert row["state"] == "APPLIED"
