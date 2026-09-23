"""Phase 5 — graph layer over the KB (task 9d4b23ca).

Storage: new ES index ``lse-graph`` with two doc kinds in one index
(ES 8.x has no multi-type): ``entity`` (id, type, name, attrs) and
``edge`` (src, rel, dst, evidence_doc_id).

Design (docs/ROADMAP-mechanisms-2026-09.md, Phase 5):
  - Fixed, small vocabulary: 6 entity types, 8 relations. Free-form
    types are how a graph becomes soup — validation rejects anything
    outside the vocabulary.
  - The graph NEVER self-writes. Extraction produces PROPOSALS that go
    through the existing TRAUM Human Gate (traum-state.db); only
    APPLIED proposals are materialized into lse-graph (see
    materialize_accepted_graph, added in a later step).
  - Recall is additive and valve-gated: GRAPH_RECALL=0 (default) leaves
    search_kb behaviour byte-identical; a bad extraction degrades to
    today's behaviour.

This module is deliberately dependency-light: plain functions taking an
Elasticsearch client (or None) and a state db path, so tests can run
against mocks without a live ES.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

# --- fixed vocabulary (roadmap: start small, 6 / 8) ------------------------

ENTITY_TYPES = ["node", "service", "model", "port", "credential", "procedure"]
RELATIONS = [
    "runs_on",
    "serves",
    "documented_by",
    "caused",
    "fixed_by",
    "supersedes",
    "uses_credential",
    "part_of",
]

ENTITY_TYPES_SET = frozenset(ENTITY_TYPES)
RELATIONS_SET = frozenset(RELATIONS)

GRAPH_INDEX = "lse-graph"


# --- id helpers ------------------------------------------------------------

def entity_id(etype: str, name: str) -> str:
    """Deterministic ES id for an entity: sha256(type|name)[:16]."""
    return hashlib.sha256(f"{etype}|{name}".encode("utf-8")).hexdigest()[:16]


def edge_id(src: str, rel: str, dst: str, evidence_doc_id: str = "") -> str:
    """Deterministic ES id for an edge: sha256(src|rel|dst|evidence)[:16]."""
    return hashlib.sha256(
        f"{src}|{rel}|{dst}|{evidence_doc_id}".encode("utf-8")
    ).hexdigest()[:16]


# --- validation ------------------------------------------------------------

def _clean_str(v) -> str:
    return str(v or "").strip()


def validate_entity(raw: dict) -> dict:
    """Validate one raw entity against the fixed vocabulary.

    Returns a normalized entity doc (no ES id — caller assigns via
    entity_id()). Raises ValueError on anything outside the vocabulary:
    unknown type, empty name, non-dict input.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"entity must be a dict, got {type(raw).__name__}")
    etype = _clean_str(raw.get("type")).lower()
    name = _clean_str(raw.get("name"))
    if etype not in ENTITY_TYPES_SET:
        raise ValueError(
            f"entity type {etype!r} not in fixed vocabulary {ENTITY_TYPES}"
        )
    if not name:
        raise ValueError("entity name must be a non-empty string")
    attrs = raw.get("attrs")
    if attrs is not None and not isinstance(attrs, dict):
        raise ValueError("entity attrs must be a dict when present")
    return {
        "kind": "entity",
        "type": etype,
        "name": name,
        "attrs": attrs or {},
    }


def validate_edge(raw: dict) -> dict:
    """Validate one raw edge against the fixed relation vocabulary.

    src/dst must be entity ids or entity names (the materializer resolves
    names to ids). Raises ValueError on unknown relation or missing
    endpoints. evidence_doc_id is REQUIRED — every edge must carry a
    backlink to the lse-kb doc that evidences it (roadmap design §1).
    """
    if not isinstance(raw, dict):
        raise ValueError(f"edge must be a dict, got {type(raw).__name__}")
    src = _clean_str(raw.get("src"))
    rel = _clean_str(raw.get("rel")).lower()
    dst = _clean_str(raw.get("dst"))
    evidence = _clean_str(raw.get("evidence_doc_id"))
    if rel not in RELATIONS_SET:
        raise ValueError(
            f"relation {rel!r} not in fixed vocabulary {RELATIONS}"
        )
    if not src or not dst:
        raise ValueError("edge src and dst must be non-empty strings")
    if not evidence:
        raise ValueError(
            "edge evidence_doc_id is required (backlink to lse-kb)"
        )
    return {
        "kind": "edge",
        "src": src,
        "rel": rel,
        "dst": dst,
        "evidence_doc_id": evidence,
    }


def validate_extraction(entities: list, edges: list) -> tuple[list, list]:
    """Validate a full extraction result.

    Returns (clean_entities, clean_edges). Raises ValueError on the first
    invalid item — the caller is expected to catch and drop the whole
    extraction (best-effort, never block the index write).
    """
    if not isinstance(entities, list) or not isinstance(edges, list):
        raise ValueError("extraction must be (list of entities, list of edges)")
    return [validate_entity(e) for e in entities], [validate_edge(e) for e in edges]


# --- index management ------------------------------------------------------

# Mapping for lse-graph. One index, two kinds, discriminated by ``kind``.
# Entity fields: type/name/attrs. Edge fields: src/rel/dst/evidence_doc_id.
# All ids/names are keyword so term queries (one-hop expansion) are exact.
_LSE_GRAPH_MAPPING = {
    "mappings": {
        "properties": {
            "kind": {"type": "keyword"},
            # entity
            "type": {"type": "keyword"},
            "name": {"type": "keyword"},
            "attrs": {"type": "object", "enabled": False},
            # edge
            "src": {"type": "keyword"},
            "rel": {"type": "keyword"},
            "dst": {"type": "keyword"},
            "evidence_doc_id": {"type": "keyword"},
            # shared
            "updated_at": {"type": "date"},
        }
    },
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    },
}


def ensure_lse_graph_index(es=None, url: str | None = None) -> bool:
    """Create the lse-graph index if missing. Returns True if it now exists.

    ``es`` is an existing Elasticsearch client (injected by goethe_kb /
    dream_runner); when None, a client is built from ``url`` (default
    $GOETHE_ES_URL or http://localhost:9200). Idempotent — safe to call
    on every startup path. Raises on real ES errors (callers that want
    best-effort wrap in try/except themselves).
    """
    if es is None:
        from elasticsearch import Elasticsearch  # noqa: PLC0415

        es = Elasticsearch(url or os.environ.get("GOETHE_ES_URL", "http://localhost:9200"),
                           request_timeout=10)
    if es.indices.exists(index=GRAPH_INDEX):
        return True
    es.indices.create(index=GRAPH_INDEX, body=_LSE_GRAPH_MAPPING)
    return True


# --- proposal payload helpers ----------------------------------------------

def graph_proposal(evidence_doc_id: str, entities: list, edges: list,
                   doc_title: str = "") -> dict:
    """Build a TRAUM proposal dict for a graph extraction.

    Shape matches the existing proposal convention ({"type", "args", ...});
    it persists through the SAME state.record_proposals path and the Human
    Gate — the graph never self-writes. ``type`` is the new "graph" type;
    materialization (a later step) only reads APPLIED proposals of this type.
    """
    clean_e, clean_g = validate_extraction(entities, edges)
    if not clean_e and not clean_g:
        raise ValueError("graph proposal must carry at least one entity or edge")
    return {
        "type": "graph",
        "call": "none",
        "args": {
            "evidence_doc_id": evidence_doc_id,
            "doc_title": doc_title,
            "entities": clean_e,
            "edges": clean_g,
        },
        "why": (
            f"graph extraction for {evidence_doc_id}: "
            f"{len(clean_e)} entities, {len(clean_g)} edges"
        ),
    }


def parse_graph_proposal(payload: dict) -> tuple[list, list]:
    """Re-validate an applied proposal's stored payload.

    Accepts either the full proposal dict or just its args. Returns
    (entities, edges) re-validated against the current vocabulary — a
    proposal recorded under an older vocabulary is rejected here rather
    than materialized with unknown types.
    """
    if not isinstance(payload, dict):
        raise ValueError("proposal payload must be a dict")
    args = payload.get("args", payload)
    if not isinstance(args, dict):
        raise ValueError("proposal args must be a dict")
    evidence = _clean_str(args.get("evidence_doc_id"))
    if not evidence:
        raise ValueError("graph proposal missing evidence_doc_id")
    ents = [validate_entity(e) for e in args.get("entities", [])]
    edges = [validate_edge({**e, "evidence_doc_id": evidence})
             for e in args.get("edges", [])]
    return ents, edges


# --- extraction (best-effort, deterministic) -------------------------------

# Conservative known-name lists for the deterministic path. The LLM dream
# pass (seventh pass) may extract more; this path must stay cheap and
# side-effect-free — it runs inline on every index_to_kb call.
_KNOWN_NODES = ("RUTX50", "pfsense", "node3090", "node4090")
_KNOWN_SERVICES = (
    "goethe_mcp", "llama-server", "llama.cpp", "ollama", "nginx", "docker",
    "elasticsearch", "searxng", "grafana", "vaultwarden", "openwebui",
    "comfyui", "unsloth", "sshd", "systemd",
)


def _extract_entities(text: str) -> list:
    r"""Deterministic entity extraction from one doc body.

    Returns normalized entity dicts (type/name/attrs) in the fixed
    vocabulary. Only high-confidence patterns: node\d{3,4} tokens, the
    known device/service lists, explicit 'port NNNN' mentions, and
    hyphen-B model tokens (e.g. Qwen3-27B). No free-form guessing.
    """
    import re  # noqa: PLC0415

    found = {}  # (type, name) -> attrs
    for m in re.finditer(r"\bnode\d{3,4}\b", text, re.IGNORECASE):
        name = m.group(0).lower()
        found.setdefault(("node", name), {})
    for name in _KNOWN_NODES:
        if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
            found.setdefault(("node", name.lower()), {})
    for name in _KNOWN_SERVICES:
        if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
            found.setdefault(("service", name.lower()), {})
    for m in re.finditer(r"\bport[:\s]+(\d{2,5})\b", text, re.IGNORECASE):
        p = int(m.group(1))
        if 1 <= p <= 65535:
            found.setdefault(("port", str(p)), {})
    for m in re.finditer(r"\b[A-Za-z][A-Za-z0-9._]*?-\d{1,4}B\b", text):
        found.setdefault(("model", m.group(0)), {})
    return [
        {"kind": "entity", "type": t, "name": n, "attrs": a}
        for (t, n), a in sorted(found.items())
    ]


def _extract_edges(entities: list, evidence_doc_id: str) -> list:
    """Conservative edges: documented_by backlink per entity + runs_on
    when a service and a node co-occur in the same doc."""
    edges = []
    nodes = [e["name"] for e in entities if e["type"] == "node"]
    for e in entities:
        edges.append({
            "kind": "edge",
            "src": e["name"],
            "rel": "documented_by",
            "dst": evidence_doc_id,
            "evidence_doc_id": evidence_doc_id,
        })
    for e in entities:
        if e["type"] == "service":
            for n in nodes:
                edges.append({
                    "kind": "edge",
                    "src": e["name"],
                    "rel": "runs_on",
                    "dst": n,
                    "evidence_doc_id": evidence_doc_id,
                })
    return edges


def extract_graph_proposals(text: str, evidence_doc_id: str,
                            doc_title: str = "") -> list:
    """Best-effort extraction of graph proposals from one KB doc body.

    Returns a list of graph proposal dicts (0 or 1 per text). Fixed
    vocabulary only; unknown tokens are ignored. Never raises on odd
    input — empty/None text yields []. The proposal is a PROPOSAL: it
    goes through the Human Gate (see insert_graph_proposals) and is
    never written to lse-graph directly.
    """
    if not text or not evidence_doc_id:
        return []
    try:
        entities = _extract_entities(text)
        if not entities:
            return []
        edges = _extract_edges(entities, evidence_doc_id)
        return [graph_proposal(evidence_doc_id, entities, edges, doc_title)]
    except Exception:
        # Best-effort by contract: extraction problems must never surface
        # as errors to the caller (inline path) — drop the extraction.
        return []


def insert_graph_proposals(proposals: list, state_db: str | None = None,
                           source: str = "graph-inline") -> list:
    """Persist graph proposals through the canonical TRAUM state path.

    Creates a lightweight run (source=<source>, pass 'graph-inline') and
    records the proposals via TraumState.record_proposals — the SAME
    fingerprinting, redaction and Human Gate as every other proposal
    type. Proposals land in STAGED and are NEVER auto-accepted; only
    operator adjudication can move them to APPLIED.

    Returns the list of stored proposal rows (STAGED/PENDING only,
    matching the dream_runner convention). Empty input returns [].
    """
    if not proposals:
        return []
    import os as _os  # noqa: PLC0415
    import sys as _sys  # noqa: PLC0415

    if state_db is None:
        state_db = _os.path.join(_os.environ.get(
            "GOETHE_DREAM_DIR", "/opt/local-se/dreams"), "traum-state.db")
    try:
        import traum_state  # noqa: PLC0415  (sibling module in tools/)
    except ImportError:
        _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        import traum_state  # noqa: PLC0415

    state = traum_state.TraumState(state_db)
    run = state.create_run(
        profile="graph",
        requested_passes=["graph-inline"],
        config={"graph": True, "source": source},
        source=source,
    )
    attempt = state.start_attempt(run["run_id"], "graph-inline")
    # R4 (2026-09-18 queue pollution incident): auto-supersede graph
    # proposals whose asserted content (entities + non-provenance edges)
    # already exists in the queue as a PENDING/APPLIED graph proposal —
    # e.g. the same facts re-extracted from a re-indexed doc under a new
    # evidence_doc_id, which the exact-fingerprint dedupe cannot catch.
    # Annotated via the same _initial_state/_initial_reason extension
    # point apply_diagnosis_rules uses: the row lands SUPERSEDED at record
    # time, never PENDING. R4 only supersedes — never approves (Hazard D).
    try:
        import diagnosis_rules  # noqa: PLC0415  (sibling module in tools/)
    except ImportError:
        _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        import diagnosis_rules  # noqa: PLC0415
    r4_superseded = 0
    try:
        priors = [
            row for row in state.list_proposals(state="PENDING,APPLIED")
            if row.get("proposal_type") == "graph"
        ]
        for proposal in proposals:
            if proposal.get("_initial_state"):
                continue  # already adjudicated upstream
            verdict = diagnosis_rules.rule_r4_graph_duplicate(proposal, priors)
            if verdict:
                proposal["_initial_state"], proposal["_initial_reason"] = verdict
                r4_superseded += 1
    except Exception:  # noqa: BLE001 — R4 dedupe is best-effort; on failure record normally
        # R4 is best-effort dedupe: if the prior scan fails, record
        # normally (the proposal stays human-reviewable) rather than
        # dropping it.
        r4_superseded = 0
    stored = state.record_proposals(run["run_id"], attempt["attempt_id"],
                                    [dict(p) for p in proposals])
    surfaced = [row for row in stored if row["state"] in {"STAGED", "PENDING"}]
    try:
        state.finish_attempt(
            attempt["attempt_id"],
            "SUCCEEDED" if surfaced else "NULL",
            summary={"graph_proposals": len(proposals),
                     "surfaced": len(surfaced),
                     "r4_superseded": r4_superseded},
        )
    except Exception:
        # Bookkeeping must not mask a successful persistence.
        pass
    return surfaced


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def materialize_accepted_graph(es=None, state_db: str | None = None,
                               url: str | None = None) -> dict:
    """Write operator-APPLIED graph proposals into lse-graph.

    Reads proposals (proposal_type='graph', state='APPLIED') from
    traum-state.db READ-ONLY (sqlite mode=ro) — this function never
    marks, mutates or re-states a proposal. The Human Gate is the only
    thing that moves a proposal to APPLIED; this is a pure projection
    of the accepted state into the lse-graph index.

    Idempotent: entity/edge docs use deterministic ids (entity_id /
    edge_id), so re-running after further approvals only upserts.
    Edges whose endpoints are not known entities (neither in the
    accepted payload nor already in the index) are skipped and counted.

    Returns {"applied": N, "entities_written": N, "edges_written": N,
             "edges_skipped": N, "errors": [...]}.
    """
    import sqlite3  # noqa: PLC0415

    if state_db is None:
        import os as _os  # noqa: PLC0415
        state_db = _os.path.join(_os.environ.get(
            "GOETHE_DREAM_DIR", "/opt/local-se/dreams"), "traum-state.db")
    if not os.path.exists(state_db):
        return {"applied": 0, "entities_written": 0, "edges_written": 0,
                "edges_skipped": 0, "errors": [f"state db not found: {state_db}"]}

    errors: list = []
    conn = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT payload_json FROM proposals "
            "WHERE proposal_type='graph' AND state='APPLIED'"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return {"applied": 0, "entities_written": 0, "edges_written": 0,
                "edges_skipped": 0, "errors": []}

    if es is None:
        from elasticsearch import Elasticsearch  # noqa: PLC0415
        es = Elasticsearch(url or os.environ.get(
            "GOETHE_ES_URL", "http://localhost:9200"), request_timeout=10)
    ensure_lse_graph_index(es)

    # Known entity names: everything already in the index (name -> id).
    known: dict = {}
    try:
        existing = es.search(
            index=GRAPH_INDEX,
            body={"query": {"term": {"kind": "entity"}},
                  "_source": ["type", "name"], "size": 10000},
        )
        for h in existing["hits"]["hits"]:
            s = h["_source"]
            known[s["name"]] = entity_id(s["type"], s["name"])
    except Exception as exc:  # noqa: BLE001 (first run: index empty)
        pass

    now = utc_now_iso()
    entities_written = 0
    edges_written = 0
    edges_skipped = 0
    for (payload_json,) in rows:
        try:
            payload = json.loads(payload_json)
            ents, edges = parse_graph_proposal(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"payload rejected: {exc}")
            continue
        evidence = payload.get("args", {}).get("evidence_doc_id", "")
        for e in ents:
            eid = entity_id(e["type"], e["name"])
            known[e["name"]] = eid
            try:
                es.index(index=GRAPH_INDEX, id=eid, document={
                    "kind": "entity",
                    "type": e["type"],
                    "name": e["name"],
                    "attrs": e.get("attrs", {}),
                    "updated_at": now,
                })
                entities_written += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"entity write failed: {exc}")
        for g in edges:
            src_id = known.get(g["src"])
            if src_id is None:
                edges_skipped += 1
                continue
            if g["rel"] == "documented_by":
                # dst is the evidence doc id — keyword, not an entity ref.
                dst_id = g["dst"]
            else:
                dst_id = known.get(g["dst"])
                if dst_id is None:
                    edges_skipped += 1
                    continue
            gid = edge_id(src_id, g["rel"], dst_id,
                          g.get("evidence_doc_id", evidence))
            try:
                es.index(index=GRAPH_INDEX, id=gid, document={
                    "kind": "edge",
                    "src": src_id,
                    "rel": g["rel"],
                    "dst": dst_id,
                    "evidence_doc_id": g.get("evidence_doc_id", evidence),
                    "updated_at": now,
                })
                edges_written += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"edge write failed: {exc}")
    try:
        es.indices.refresh(index=GRAPH_INDEX)
    except Exception:  # noqa: BLE001 (best-effort)
        pass
    return {"applied": len(rows), "entities_written": entities_written,
            "edges_written": edges_written, "edges_skipped": edges_skipped,
            "errors": errors}


def render_graph_json(entities: list, edges: list) -> str:
    """Stable JSON rendering (for fingerprints / report lines)."""
    return json.dumps({"entities": entities, "edges": edges},
                      sort_keys=True, separators=(",", ":"))
