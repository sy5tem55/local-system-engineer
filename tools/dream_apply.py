#!/usr/bin/env python3
"""
dream_apply.py — TRAUM-ENGINE apply gate (v0.1.0)
=============================================================================
Companion to docs/dreaming/DESIGN.md (dataflow §1, invariants §2 row 3, SCRIBE-1
confirm-gate format §6) and tools/dream_runner.py (Prompts 2.1-2.4, the
READ-ONLY proposer). TRAUM Thread 2, Prompt 2.5 — the last Thread 2 piece.

THIS IS THE ONLY CODE ALLOWED TO WRITE TO lse-kb/lse-errors/lse-skills ON
BEHALF OF A DREAM. dream_runner.py never calls an ES-mutating Tools method;
it only ever writes dreams/YYYY-MM-DD/proposals.jsonl. This file reads that
proposals.jsonl, re-validates every proposal against the code-enforced
invariants below (never trusting dream_runner's own generation-time state —
ES may have changed since), renders each one in the SCRIBE-1 confirm-gate
block shape, asks a human yes/no PER PROPOSAL (DESIGN.md's dataflow diagram:
"human confirm-gate (SCRIBE-1 format, per-proposal yes/no)" — a stricter grain
than the debrief skill's own single combined yes, deliberately: unsupervised,
machine-generated proposals get more granular human control), then applies
approved ones through goethe.py's OWN Tools class — dynamically loaded and
instantiated exactly the way goethe_mcp.py does it (make_instance() below is
a deliberate mirror of goethe_mcp.py:183-208) — so there is exactly one
write path into ES/kb regardless of whether the caller is a human MCP session
or an applied dream proposal.

HARD INVARIANTS (DESIGN.md §2 row 3), each enforced fail-closed (reject, not
apply) by a dedicated check function below:
  (a) never raise quality — check_quality_raise() re-fetches the CURRENT
      quality_score at apply time (not the proposal's generation-time
      snapshot) and rejects if the proposal's own new_quality would exceed
      it. record_outcome structurally cannot raise quality (its own
      docstring: success=True "does NOT re-elevate quality") — this check
      only ever fires for mentor_correct and skill_record's internal
      near-duplicate collision path (see check_skill_collision_raise).
  (b) never source_tier=ground_truth — check_ground_truth().
  (c) never touch a quarantined doc (stale=true AND quality<=0.2) except
      type=="quarantine-delete-request" — check_quarantine(). No pass built
      so far (Prompts 2.2-2.4) ever emits that type; it is recognized here
      purely so the exception clause in the spec has a real name to check
      against, not invented as a working feature today.
  (d) every applied write carries origin=dream + provenance matching
      ^dream-\\d{4}-\\d{2}-\\d{2}$ — see the ONE-EXCEPTION note below.
  (e) dream_runner.py's own job (session_id prefix exclusion), not this file's.

ONE EXCEPTION TO "ONE WRITE PATH" — origin/provenance stamping and dedup
stats merge: mentor_correct/record_outcome have NO origin or provenance
parameter at all (goethe.py's own docs: index_to_kb "has no
provenance/origin parameter today"; corpus-audit.md confirms lse-kb's live
mapping has no origin field yet — that is REFACTOR-4's job, not shipped).
Invariant (d) still requires stamping it on every applied write, so
immediately after a successful mentor_correct/record_outcome call on an
EXISTING doc, this file issues one narrowly-scoped es.update() adding
{"origin": "dream", "provenance": "dream-YYYY-MM-DD"} (dynamic field
addition — Elasticsearch allows this under default mapping) and, for dedup
merges only, the union of empirical_runs/success_count/failure_count
between keep and retire (the "union of runs/ok/fail stats" Prompt 2.5 asks
for — mentor_correct itself has no parameter for these fields either). This
is bookkeeping/tagging, never a semantic decision (what changes, by how
much) — that always flows through the same Tools method a human would call.
skill_record already accepts a real `provenance` argument, so no
supplementary provenance stamp is needed there; only `origin` gets the same
one-line es.update() afterward.

CONFIRM-GATE: DESIGN.md §6.4's exact block shape, with the file-write header
replaced per §6.4's own dream_apply.py note — a TARGET: <doc_id> header for
proposals touching an existing doc, a REPORT: <path> header for a fresh
skill-candidate. A dedup pair (mentor_correct + record_outcome linked by
`pair_id`) is rendered and confirmed as ONE unit (DESIGN.md §6.5: apply the
correction before the demotion; never leave the pair half-applied by a human
answering yes to one half and no to the other).

DREAM_AUTO_APPLY (DESIGN.md §2 row 2): comma-separated proposal types that
skip the interactive prompt. Defaults to "" — everything is manual until a
type earns two consecutive weeks of zero rejected-in-hindsight applies
(Thread 4's job to measure, not this file's).

OUTPUT: alongside the input proposals.jsonl, writes applied.jsonl (one line
per successfully-applied proposal, with the Tools call's own return message)
and rejected.jsonl (one line per rejected proposal, invariant failure or a
human "no", with the reason) — Prompt 2.5's "rejected proposals are logged
with reason to the dream dir."

USAGE
  # Dry-run (default): renders and validates everything, asks nothing,
  # calls no Tools method — safe to run to preview a batch.
  python3 dream_apply.py --proposals dreams/2026-07-11/proposals.jsonl

  # Real run: interactive, per-proposal yes/no, actually writes to ES.
  python3 dream_apply.py --proposals dreams/2026-07-11/proposals.jsonl --no-dry-run

ENV (same GOETHE_ prefix convention as goethe.py/goethe_mcp.py/dream_runner.py)
  GOETHE_ES_URL, GOETHE_OLLAMA_URL, GOETHE_EMBED_MODEL  — same valves Tools()
                                    itself reads; overridden the same way
                                    goethe_mcp.py's make_instance() does.
  GOETHE_PATH                      path to goethe.py to dynamically load
                                    (default: this script's own directory)
  GOETHE_DREAM_AUTO_APPLY           comma-separated proposal types allowed to
                                    skip the interactive prompt (default "")
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime

import dream_runner as dr  # sibling module: reuse validate_proposal_shape, not a second validator

__version__ = "0.1.0"

QUARANTINE_DELETE_TYPE = "quarantine-delete-request"  # DESIGN.md §2 row 3(c) -- not
                                                        # produced by any pass yet (2.2-2.4)

_TIER_CEILING = {"ground_truth": 1.0, "primary": 0.8, "secondary": 0.6, "inferred": 0.4}


# --- config / valve-style env defaults --------------------------------------

def _es_url_default() -> str:
    return os.environ.get("GOETHE_ES_URL", "http://127.0.0.1:9200")


def _ollama_url_default() -> str:
    return os.environ.get("GOETHE_OLLAMA_URL", "http://127.0.0.1:11434")


def _embed_model_default() -> str:
    return os.environ.get("GOETHE_EMBED_MODEL", "nomic-embed-text")


def _goethe_path_default() -> str:
    return os.environ.get("GOETHE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "goethe.py"))


def _dream_auto_apply_default() -> str:
    return os.environ.get("GOETHE_DREAM_AUTO_APPLY", "")


# --- dynamic Tools loading (mirrors goethe_mcp.py:159-208 verbatim) ---------

def load_tools_class(goethe_path: str):
    """Dynamically import goethe.py by file path and return its Tools class
    — the exact mechanism goethe_mcp.py itself uses (tools/goethe_mcp.py
    ~line 159), so 'import the Tools class like goethe_mcp does' is literally
    true, not just similar in spirit."""
    import importlib.util

    abspath = os.path.abspath(goethe_path)
    if not os.path.isfile(abspath):
        raise SystemExit(f"[dream_apply] goethe file not found: {abspath}")
    spec = importlib.util.spec_from_file_location("goethe_mod", abspath)
    if spec is None or spec.loader is None:
        raise SystemExit(f"[dream_apply] cannot load module from {abspath}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "Tools"):
        raise SystemExit("[dream_apply] goethe module has no `Tools` class")
    return mod.Tools


def make_tools_instance(Tools, es_url: str, ollama_url: str, embed_model: str):
    """Instantiate Tools() and override ES_URL/OLLAMA_URL/EMBED_MODEL valves
    — same override mechanism as goethe_mcp.py's make_instance(), scoped to
    just the valves this file's checks and applies actually touch."""
    inst = Tools()
    valves = inst.valves
    overrides = {"ES_URL": es_url, "OLLAMA_URL": ollama_url, "EMBED_MODEL": embed_model}
    try:
        dumped = valves.model_dump() if hasattr(valves, "model_dump") else valves.dict()
    except Exception:
        dumped = {}
    inst.valves = type(valves)(**{**dumped, **overrides})
    return inst


# --- proposal loading / grouping ---------------------------------------------

def load_proposals(path: str) -> list:
    proposals = []
    with open(path, "rt", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                proposals.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"[dream_apply] WARNING: {path}:{lineno} unparseable, skipped ({exc})",
                      file=sys.stderr)
    return proposals


def group_proposals(proposals: list) -> list:
    """Group by pair_id (dedup keep+retire, applied/confirmed as one unit
    per DESIGN.md §6.5's non-atomicity guidance); every other proposal is
    its own singleton group. Preserves first-seen order."""
    groups = []
    seen_pair_ids = {}
    for p in proposals:
        pair_id = p.get("pair_id")
        if pair_id:
            if pair_id in seen_pair_ids:
                groups[seen_pair_ids[pair_id]].append(p)
                continue
            seen_pair_ids[pair_id] = len(groups)
            groups.append([p])
        else:
            groups.append([p])
    return groups


# --- invariant checks (fail-closed: any None-returning check means OK) -----

def fetch_kb_doc(es, doc_id: str):
    try:
        resp = es.get(
            index="lse-kb", id=doc_id,
            _source=["title", "quality_score", "stale", "source_tier",
                     "empirical_runs", "success_count", "failure_count",
                     "consecutive_failures"],
        )
        return resp["_source"]
    except Exception:
        return None


def check_quarantine(current_doc: dict, proposal_type: str):
    """DESIGN.md §2 row 3(c)."""
    if not current_doc:
        return None
    if current_doc.get("stale") and float(current_doc.get("quality_score", 1.0) or 1.0) <= 0.2:
        if proposal_type != QUARANTINE_DELETE_TYPE:
            return (
                "target doc is quarantined (stale=true, quality<=0.2) — only "
                f"{QUARANTINE_DELETE_TYPE!r} may touch it"
            )
    return None


def check_ground_truth(args: dict):
    """DESIGN.md §2 row 3(b)."""
    if args.get("source_tier") == "ground_truth":
        return "proposal sets source_tier=ground_truth — dream-origin entries can never self-grant it"
    return None


def check_provenance_format(args: dict):
    """DESIGN.md §2 row 3(d), the provenance half. Same regex as
    dream_runner.py's validate_proposal_shape — re-checked here too since
    proposals.jsonl could in principle be hand-edited between generation
    and apply."""
    provenance = args.get("provenance")
    if provenance is not None and not re.fullmatch(r"dream-\d{4}-\d{2}-\d{2}", str(provenance)):
        return f"provenance {provenance!r} does not match the fixed 'dream-YYYY-MM-DD' form"
    return None


def check_quality_raise(args: dict, current_doc: dict):
    """DESIGN.md §2 row 3(a). Compares the proposal's OWN baked-in
    new_quality (what a human sees rendered at confirm time) against the
    doc's CURRENT live quality_score (re-fetched at apply time, which may
    have drifted since the proposal was generated) — never recomputed, so a
    doc that changed underneath the proposal fails closed instead of being
    silently re-justified."""
    new_q = args.get("new_quality")
    if new_q is None or current_doc is None:
        return None
    cur_q = float(current_doc.get("quality_score", 0.0) or 0.0)
    if float(new_q) > cur_q:
        return f"would raise quality {cur_q:.2f} -> {float(new_q):.2f} — rejected (never raise)"
    return None


def check_evidence_thin(args: dict, min_len: int = 20):
    """Defense-in-depth re-check of DESIGN.md §6.2's evidence floor —
    dream_runner.py's validator already enforces this at generation time;
    re-checked here in case proposals.jsonl was edited by hand."""
    if "evidence" in args:
        evidence = args.get("evidence") or ""
        if len(evidence) < min_len:
            return f"evidence is {len(evidence)} chars, under the {min_len}-char floor"
    return None


def check_skill_collision_raise(tools, args: dict):
    """skill_record's OWN internal near-dup path (cosine>=0.92) updates an
    EXISTING lse-skills doc's quality to max(existing, new) — invariant (a)
    applies here too, but there is no doc_id in a skill-candidate proposal
    to check ahead of time, so this runs the SAME kNN lookup skill_record
    will run internally, predicts the collision, and rejects if it would
    raise an existing skill's quality above its current value. Returns None
    (safe to proceed) if no collision is predicted, or if the prediction
    itself fails (fails OPEN here only — skill_record's own tier ceiling
    still applies as a backstop; this is a best-effort second check on top
    of it, not the only guard)."""
    try:
        occupation = str(args.get("occupation", ""))
        task = str(args.get("task", ""))
        procedure = str(args.get("procedure", ""))
        steps = [s.strip() for s in re.split(r"[;\n]+", procedure) if s.strip()]
        embed_input = f"{occupation}: {task}\n" + "\n".join(steps)
        embedding = tools._embed(embed_input[:8000])
        es = tools._es()
        dup = es.search(
            index="lse-skills",
            body={
                "knn": {"field": "embedding", "query_vector": embedding, "k": 1, "num_candidates": 10},
                "_source": ["skill_id", "quality"],
                "size": 1,
            },
        )["hits"]["hits"]
    except Exception as exc:
        print(f"[dream_apply] WARNING: skill-collision precheck failed ({exc}) — "
              "proceeding on skill_record's own tier ceiling alone", file=sys.stderr)
        return None
    if not dup or dup[0].get("_score", 0) < 0.92:
        return None  # fresh create, nothing to raise
    existing_q = float(dup[0]["_source"].get("quality", 0.0))
    source_tier = args.get("source_tier", "inferred")
    proposed_q = float(args.get("quality", 0.5))
    ceiling = _TIER_CEILING.get(source_tier, 0.4)
    effective_q = max(0.2, min(proposed_q, 0.7, ceiling))
    if effective_q > existing_q:
        return (
            f"would collide with existing skill {dup[0]['_source'].get('skill_id')!r} "
            f"(quality {existing_q:.2f}) and raise it to {effective_q:.2f} — rejected"
        )
    return None


def check_procedure_step_count(args: dict):
    """skill_record itself rejects procedure with fewer than 2 ';'/newline
    steps ('that is a fact, not a skill'). Checked here ahead of the call so
    a rejection shows up as a clean invariant-log entry, not a wasted
    confirmed-then-failed apply."""
    procedure = str(args.get("procedure", ""))
    steps = [s.strip() for s in re.split(r"[;\n]+", procedure) if s.strip()]
    if len(steps) < 2:
        return "procedure has fewer than 2 steps — skill_record would reject this as a fact, not a skill"
    return None


def validate_proposal_for_apply(p: dict, es) -> str:
    """Returns None if OK to present at the confirm-gate, else a reason
    string. Runs dream_runner.py's own structural validator FIRST (shape,
    known type, provenance format, thin demote evidence), then this file's
    deeper, apply-time/live-state checks."""
    shape_err = dr.validate_proposal_shape(p)
    if shape_err:
        return f"structural: {shape_err}"

    args = p.get("args", {})
    ptype = p.get("type")
    call = p.get("call")

    err = check_ground_truth(args) or check_provenance_format(args) or check_evidence_thin(args)
    if err:
        return err

    if call in ("mentor_correct", "record_outcome") and "doc_id" in args:
        current_doc = fetch_kb_doc(es, args["doc_id"])
        if current_doc is None:
            return f"doc_id {args['doc_id']!r} not found in lse-kb at apply time (deleted? renamed?)"
        err = check_quarantine(current_doc, ptype) or check_quality_raise(args, current_doc)
        if err:
            return err

    if call == "skill_record":
        err = check_procedure_step_count(args)
        if err:
            return err

    return None


# --- confirm-gate rendering + interactive prompt ----------------------------

def _fmt_block(call: str, idx: int, total: int, lines: list, multiline_fields: dict) -> str:
    header = f"――― ES PROPOSAL {idx}/{total}: {call} ―――"
    out = [header]
    for label, value in lines:
        out.append(f"{label:<18} {value}")
    for label, value in multiline_fields.items():
        out.append(f"{label}:")
        for line in str(value).splitlines() or [""]:
            out.append(f"  {line}")
    return "\n".join(out)


def render_group(group: list, dream_dir: str) -> str:
    """DESIGN.md §6.4's block shape, header adapted per its own dream_apply.py
    note: TARGET: <doc_id> for an existing-doc proposal, REPORT: <path> for a
    fresh skill-candidate that names no target doc."""
    first = group[0]
    doc_ids = [p["args"]["doc_id"] for p in group if "doc_id" in p.get("args", {})]
    if doc_ids:
        target = " (merge from ".join(doc_ids) + (")" if len(doc_ids) > 1 else "")
        top = f"――― TARGET: {target} ―――"
    else:
        top = f"――― REPORT: {os.path.join(dream_dir, 'report.md')} (reference) ―――"

    blocks = [top, ""]
    for i, p in enumerate(group, 1):
        args = p.get("args", {})
        call = p.get("call", "?")
        lines = []
        multiline = {}
        if call == "mentor_correct":
            lines = [("doc_id:", args.get("doc_id", "")),
                     ("new_quality:", args.get("new_quality", ""))]
            multiline = {"correction": args.get("correction", "")}
        elif call == "record_outcome":
            lines = [("doc_id:", args.get("doc_id", "")),
                     ("success:", args.get("success", False)),
                     ("notes:", args.get("notes", "") or "(none)")]
            multiline = {"evidence": args.get("evidence", "")}
        elif call == "kb_verify":
            lines = [("doc_id:", args.get("doc_id", "")),
                     ("note:", "READ-ONLY phase-1 probe suggestion — writes nothing")]
        elif call == "skill_record":
            lines = [
                ("task:", args.get("task", "")),
                ("occupation:", args.get("occupation", "")),
                ("trigger:", p.get("trigger", "")),
                ("provenance:", args.get("provenance", "")),
                ("source_tier:", args.get("source_tier", "")),
                ("quality:", args.get("quality", "")),
                ("preconditions:", args.get("preconditions", "") or "(none)"),
                ("verification:", args.get("verification", "")),
                ("failure_modes:", args.get("failure_modes", "") or "(none)"),
                ("evidence (episode ids):", ", ".join(p.get("evidence", [])) or "(none)"),
            ]
            multiline = {"procedure": args.get("procedure", "")}
        blocks.append(_fmt_block(call, i, len(group), lines, multiline))
        blocks.append(f"why:               {p.get('why', '')}")
        blocks.append("")

    if len(group) > 1:
        question = f"Commit this {first.get('type')} (pair — {len(group)} calls, applied together)? (yes/no)"
    else:
        question = f"Commit this {first.get('type')} ({len(group)} call)? (yes/no)"
    blocks.append(question)
    return "\n".join(blocks)


def ask_yes_no(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} > ").strip().lower()
    except EOFError:
        answer = ""
    return answer in ("y", "yes")


# --- apply -------------------------------------------------------------

def _stamp_dream_fields(es, doc_id: str, today: str, extra: dict = None) -> None:
    """The ONE exception to pure Tools-passthrough — see module docstring's
    ONE EXCEPTION note. Adds origin/provenance (and, for dedup, the merged
    runs/ok/fail stats) as a plain dynamic-field ES update, never deciding
    any quality/content change itself."""
    doc = {"origin": "dream", "provenance": f"dream-{today}"}
    if extra:
        doc.update(extra)
    es.update(index="lse-kb", id=doc_id, body={"doc": doc})


def apply_group(tools, group: list, dry_run: bool) -> list:
    """Applies one confirmed group. Returns a list of
    {"proposal":..., "result":...} dicts, one per proposal actually applied
    (or that would be, under --dry-run)."""
    es = tools._es()
    today = date.today().isoformat()
    results = []

    # Dedup pairs need the keep-doc's pre-merge stats BEFORE mentor_correct
    # overwrites anything, so the union is computed from real pre-apply state.
    pre_state = {}
    if len(group) > 1:
        for p in group:
            doc_id = p.get("args", {}).get("doc_id")
            if doc_id:
                pre_state[doc_id] = fetch_kb_doc(es, doc_id) or {}

    for p in group:
        call = p.get("call")
        args = p.get("args", {})
        if dry_run:
            results.append({"proposal": p, "result": f"[dry-run] would call {call}({args})"})
            continue

        if call == "mentor_correct":
            result = tools.mentor_correct(args["doc_id"], args["correction"], args["new_quality"])
            extra = None
            if len(group) > 1:
                # dedup merge: union the runs/ok/fail stats across keep+retire
                # (Prompt 2.5's explicit ask — mentor_correct has no parameter
                # for these fields, see module docstring's ONE EXCEPTION note).
                other = [x for x in group if x is not p and x.get("args", {}).get("doc_id") != args["doc_id"]]
                retire_id = other[0]["args"]["doc_id"] if other else None
                keep_pre = pre_state.get(args["doc_id"], {})
                retire_pre = pre_state.get(retire_id, {}) if retire_id else {}
                extra = {
                    "empirical_runs": (keep_pre.get("empirical_runs", 0) or 0) + (retire_pre.get("empirical_runs", 0) or 0),
                    "success_count": (keep_pre.get("success_count", 0) or 0) + (retire_pre.get("success_count", 0) or 0),
                    "failure_count": (keep_pre.get("failure_count", 0) or 0) + (retire_pre.get("failure_count", 0) or 0),
                }
            _stamp_dream_fields(es, args["doc_id"], today, extra)
            results.append({"proposal": p, "result": result})

        elif call == "record_outcome":
            result = tools.record_outcome(args["doc_id"], args["success"],
                                           args.get("notes", ""), args.get("evidence", ""))
            _stamp_dream_fields(es, args["doc_id"], today)
            results.append({"proposal": p, "result": result})

        elif call == "kb_verify":
            result = tools.kb_verify(args["doc_id"])  # phase 1 only -- read-only, no stamp needed
            results.append({"proposal": p, "result": result})

        elif call == "skill_record":
            result = tools.skill_record(
                task=args["task"], occupation=args["occupation"], procedure=args["procedure"],
                verification=args["verification"], preconditions=args.get("preconditions", ""),
                failure_modes=args.get("failure_modes", ""), provenance=args.get("provenance", ""),
                quality=args.get("quality", 0.5), source_tier=args.get("source_tier", "inferred"),
            )
            # provenance is already a real skill_record arg; origin still isn't.
            skill_id_match = re.search(r"SKILL (?:created|updated): (\S+)", result or "")
            if skill_id_match:
                try:
                    import hashlib
                    slug_id = skill_id_match.group(1)
                    doc_hash = hashlib.sha256(slug_id.encode()).hexdigest()[:16]
                    es.update(index="lse-skills", id=doc_hash, body={"doc": {"origin": "dream"}})
                except Exception as exc:
                    print(f"[dream_apply] WARNING: origin stamp on lse-skills failed ({exc}) "
                          "-- skill_record's own write still succeeded", file=sys.stderr)
            results.append({"proposal": p, "result": result})

        else:
            results.append({"proposal": p, "result": f"ERROR: unknown call {call!r}, not applied"})

    return results


# --- main ----------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="dream_apply.py",
        description="TRAUM-ENGINE apply gate — the ONLY code allowed to write dream "
        "proposals to ES. Prompt 2.5. See docs/dreaming/DESIGN.md.",
    )
    ap.add_argument("--proposals", required=True, help="path to a dream run's proposals.jsonl")
    ap.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True,
                    help="render + validate + ask, but never actually call a Tools method "
                    "(default: true). Pass --no-dry-run to actually write to ES.")
    ap.add_argument("--es-url", default=_es_url_default())
    ap.add_argument("--ollama-url", default=_ollama_url_default())
    ap.add_argument("--embed-model", default=_embed_model_default())
    ap.add_argument("--goethe-path", default=_goethe_path_default(),
                    help="path to goethe.py to dynamically load (default: alongside this script)")
    ap.add_argument("--auto-apply-types", default=_dream_auto_apply_default(),
                    help="comma-separated proposal types allowed to skip the interactive "
                    "prompt (default: '' — DESIGN.md §2 row 2, earned via eval, not by hand)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    dream_dir = os.path.dirname(os.path.abspath(args.proposals)) or "."
    auto_apply_types = {t.strip() for t in args.auto_apply_types.split(",") if t.strip()}

    proposals = load_proposals(args.proposals)
    mode = "[dry-run] " if args.dry_run else ""
    print(f"[dream_apply] {mode}loaded {len(proposals)} proposal(s) from {args.proposals}",
          file=sys.stderr)
    if not proposals:
        print("[dream_apply] nothing to do.", file=sys.stderr)
        return

    Tools = load_tools_class(args.goethe_path)
    tools = make_tools_instance(Tools, args.es_url, args.ollama_url, args.embed_model)
    es = tools._es()

    groups = group_proposals(proposals)
    applied_path = os.path.join(dream_dir, "applied.jsonl")
    rejected_path = os.path.join(dream_dir, "rejected.jsonl")
    applied_f = open(applied_path, "at", encoding="utf-8")
    rejected_f = open(rejected_path, "at", encoding="utf-8")

    n_applied = n_rejected_invariant = n_rejected_human = n_auto = 0
    try:
        for group in groups:
            reasons = [validate_proposal_for_apply(p, es) for p in group]
            bad = next((r for r in reasons if r), None)
            if bad:
                n_rejected_invariant += 1
                for p in group:
                    rejected_f.write(json.dumps({
                        "proposal": p, "reason": f"invariant: {bad}",
                        "rejected_at": datetime.now().astimezone().isoformat(),
                    }) + "\n")
                print(f"[dream_apply] REJECTED (invariant): {bad}", file=sys.stderr)
                continue

            print("\n" + render_group(group, dream_dir) + "\n", file=sys.stderr)

            ptype = group[0].get("type")
            if ptype in auto_apply_types:
                confirmed = True
                n_auto += 1
                print(f"[dream_apply] auto-applied (type {ptype!r} in --auto-apply-types)",
                      file=sys.stderr)
            else:
                confirmed = ask_yes_no("Apply?")

            if not confirmed:
                n_rejected_human += 1
                for p in group:
                    rejected_f.write(json.dumps({
                        "proposal": p, "reason": "human declined",
                        "rejected_at": datetime.now().astimezone().isoformat(),
                    }) + "\n")
                continue

            results = apply_group(tools, group, args.dry_run)
            n_applied += len(results)
            for r in results:
                applied_f.write(json.dumps({
                    "proposal": r["proposal"], "result": r["result"],
                    "applied_at": datetime.now().astimezone().isoformat(),
                    "dry_run": args.dry_run,
                }) + "\n")
                print(f"[dream_apply] {mode}{r['result']}", file=sys.stderr)
    finally:
        applied_f.close()
        rejected_f.close()

    print(
        f"[dream_apply] {mode}done. applied={n_applied} (auto={n_auto}) "
        f"rejected_invariant={n_rejected_invariant} rejected_human={n_rejected_human} "
        f"-> {applied_path}, {rejected_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
