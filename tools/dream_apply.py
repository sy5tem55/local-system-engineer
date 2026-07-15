#!/usr/bin/env python3
"""
dream_apply.py — TRAUM-ENGINE apply gate (v0.2.0)
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

ONE EXCEPTION TO "ONLY WRITES ES/kb" (Thread 3, Prompt 3.6): a `prompt-rule`
proposal (`call == "append_learned_rule"`) never touches ES at all — it
appends one entry to the generated include file prompts/learned-rules.md.
This is still the same confirm-gate, the same per-proposal yes/no, the same
applied.jsonl/rejected.jsonl logging, and the same code-enforced invariant
discipline as everything else in this file — it is just a file write instead
of a Tools call, because there is no Tools method for "add a standing prompt
instruction" and there must never be one that edits prompts/node4090*
directly. check_prompt_rule_target() below re-validates, at apply time
against the proposal's own live args, that the target is EXACTLY
prompts/learned-rules.md — never prompts/node4090* or anywhere else — even
though dream_runner.py's validate_proposal_shape() already enforces the same
thing structurally at generation time (proposals.jsonl could in principle be
hand-edited between the two). See docs/dreaming/DESIGN.md §8 for the operator
merge workflow this file feeds.

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
  (f) prompt-rule proposals may ONLY ever target prompts/learned-rules.md,
      never prompts/node4090* — check_prompt_rule_target(), Prompt 3.6.

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
one-line es.update() afterward. index_to_kb (the "kb-fact" proposal type,
Thread 1 Prompt 1.5's SCRIBE-1 format, reused verbatim per DESIGN.md §6.2)
has NEITHER provenance NOR origin — it gets the same full stamp as
mentor_correct/record_outcome (both fields), located via the doc_id it
returns in its own "KB created: doc_id=..." / "KB updated (refined):
doc_id=..." result string, not skill_record's origin-only special case.

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
  GOETHE_REPO_ROOT                  repo root append_learned_rule resolves
                                    prompts/learned-rules.md against (Prompt
                                    3.6; default: current working directory —
                                    run this script from the repo root, same
                                    assumption the --proposals usage examples
                                    above already make with relative paths)
"""

import argparse
import glob
import json
import os
import re
import sys
import sqlite3
from datetime import date, datetime

import dream_runner as dr  # sibling module: reuse validate_proposal_shape, not a second validator
import dream_digest        # Prompt 3.4: morning digest refresh at end of run

__version__ = "0.2.0"

QUARANTINE_DELETE_TYPE = "quarantine-delete-request"  # DESIGN.md §2 row 3(c) -- produced by
                                                        # quarantine-delete-request pass (run_pass_quarantine_delete)

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


def _repo_root_default() -> str:
    return os.environ.get("GOETHE_REPO_ROOT", os.getcwd())


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


# Proposal queue with expiry (Prompt 4.4 / Thread 4)
PROPOSAL_EXPIRY_DAYS = 14  # proposals expire after 14 days


def _proposal_date_from_path(path: str) -> str | None:
    """Extract the date string (YYYY-MM-DD) from a proposals file path.
    Returns None if the date cannot be extracted."""
    # Path pattern: dreams/YYYY-MM-DD/proposals-*.jsonl
    parts = os.path.normpath(path).split(os.sep)
    for i, part in enumerate(parts):
        if part.startswith("proposals"):
            # The date is the parent directory
            if i > 0:
                parent = parts[i - 1]
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parent):
                    return parent
    return None


def load_proposals_with_expiry(path: str, expiry_days: int = PROPOSAL_EXPIRY_DAYS) -> list:
    """Load proposals from a file, filtering out expired ones.
    Proposals expire after expiry_days from their generation date (extracted from path).
    Returns (proposals, expired_count)."""
    proposals = load_proposals(path)
    if not proposals:
        return [], 0

    # Extract date from path
    prop_date = _proposal_date_from_path(path)
    if prop_date is None:
        # Can't determine date, keep all proposals
        return proposals, 0

    try:
        from datetime import timedelta
        gen_date = datetime.fromisoformat(prop_date).replace(tzinfo=None)
        cutoff = (datetime.now() - timedelta(days=expiry_days)).date()
        if gen_date.date() < cutoff:
            # All proposals in this file are expired
            print(f"[dream_apply] {path}: {len(proposals)} proposal(s) expired "
                  f"(generated {prop_date}, older than {expiry_days} days)",
                  file=sys.stderr)
            return [], len(proposals)
    except (ValueError, TypeError):
        # Date parsing failed, keep all proposals
        pass

    return proposals, 0


def scan_proposal_queue(dream_dir: str, expiry_days: int = PROPOSAL_EXPIRY_DAYS) -> list:
    """Scan all day-dirs for pending (non-expired, non-applied, non-rejected) proposals.
    Returns a list of (path, proposals) tuples, newest day-dirs first."""
    from datetime import timedelta
    queue = []
    expired_total = 0

    # Find all day-dirs (YYYY-MM-DD pattern)
    day_dirs = []
    try:
        for entry in os.listdir(dream_dir):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry):
                day_dirs.append(entry)
    except OSError:
        return []

    # Sort newest first
    day_dirs.sort(reverse=True)

    for day in day_dirs:
        base = os.path.join(dream_dir, day)

        # Check if this day-dir has applied/rejected records
        applied_keys = set()
        rejected_keys = set()
        for jsonl_file in ("applied.jsonl", "rejected.jsonl"):
            jsonl_path = os.path.join(base, jsonl_file)
            if os.path.exists(jsonl_path):
                with open(jsonl_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entry = json.loads(line)
                                prop = entry.get("proposal", {})
                                # Use type+call+why as a simple key
                                key = (prop.get("type"), prop.get("call"), prop.get("why", "")[:100])
                                if jsonl_file == "applied.jsonl":
                                    applied_keys.add(key)
                                else:
                                    rejected_keys.add(key)
                            except json.JSONDecodeError:
                                continue

        # Find all proposal files in this day-dir
        proposal_files = glob.glob(os.path.join(base, "proposals-*.jsonl"))
        for prop_path in proposal_files:
            proposals, expired = load_proposals_with_expiry(prop_path, expiry_days)
            expired_total += expired

            # Filter out already resolved proposals
            pending = []
            for p in proposals:
                key = (p.get("type"), p.get("call"), p.get("why", "")[:100])
                if key not in applied_keys and key not in rejected_keys:
                    pending.append(p)

            if pending:
                queue.append((prop_path, pending))

    if expired_total > 0:
        print(f"[dream_apply] queue scan: {expired_total} expired proposal(s) filtered out",
              file=sys.stderr)
    return queue


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


def check_prompt_rule_target(call: str, args: dict):
    """DESIGN.md §2 row 3(f) / plan Prompt 3.9's own named test: 'validator
    rejects prompt-rule proposals targeting prompts/node4090*'. No-op for
    every call except append_learned_rule. Re-checks, against the
    proposal's own live args at apply time, exactly what
    dream_runner.py's validate_proposal_shape() already enforces
    structurally at generation time — proposals.jsonl could in principle be
    hand-edited between the two, same reasoning as
    check_provenance_format() above."""
    if call != "append_learned_rule":
        return None
    target = args.get("target_file")
    if target != dr.LEARNED_RULES_TARGET:
        return (
            f"append_learned_rule target_file must be exactly "
            f"{dr.LEARNED_RULES_TARGET!r}, got {target!r} — refusing to write "
            "prompt-rule content anywhere else, especially prompts/node4090*"
        )
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

    err = (check_ground_truth(args) or check_provenance_format(args)
           or check_evidence_thin(args) or check_prompt_rule_target(call, args))
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
    file_targets = [p["args"]["target_file"] for p in group if "target_file" in p.get("args", {})]
    targets = doc_ids or file_targets
    if targets:
        target = " (merge from ".join(targets) + (")" if len(targets) > 1 else "")
        top = f"――― TARGET: {target} ―――"
    else:
        # Pass-scoped report names as of Thread 4 (report-<pass>.md); the
        # glob keeps legacy shared-report.md day-dirs readable too.
        reports = sorted(glob.glob(os.path.join(dream_dir, "report*.md")))
        ref = ", ".join(reports) if reports else os.path.join(dream_dir, "report*.md")
        top = f"――― REPORT: {ref} (reference) ―――"

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
        elif call == "index_to_kb":
            # DESIGN.md §6.4's exact index_to_kb confirm-gate block shape.
            lines = [
                ("title:", args.get("title", "")),
                ("topic:", args.get("topic", "")),
                ("source_tier:", args.get("source_tier", "")),
                ("quality_score:", args.get("quality_score", "")),
                ("verified_against:", args.get("verified_against", "") or "(not applicable)"),
                ("volatility:", args.get("volatility", "slow")),
            ]
            multiline = {
                "evidence": args.get("evidence", "") or "(none — source_tier is not ground_truth)",
                "content": args.get("content", ""),
            }
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
        elif call == "append_learned_rule":
            lines = [
                ("target_file:", args.get("target_file", "")),
                ("section_hint:", args.get("section_hint", "") or "(unspecified)"),
                ("provenance:", args.get("provenance", "")),
                ("source_tier:", args.get("source_tier", "")),
                ("evidence refs:", ", ".join(p.get("evidence", [])) or "(none)"),
            ]
            multiline = {"rule": args.get("rule", ""), "rationale": args.get("rationale", "")}
        elif call == "es_delete":
            lines = [
                ("doc_id:", args.get("doc_id", "")),
            ]
            multiline = {}

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


LEARNED_RULES_HEADER = """# Learned Rules — TRAUM prompt-rule proposals (generated, human-gated)

> Populated ONLY by `tools/dream_apply.py`, one entry per human-confirmed
> `prompt-rule` proposal (TRAUM Thread 3, Prompt 3.6). Full merge workflow:
> `docs/dreaming/DESIGN.md` §8.
>
> This file is a STAGING AREA, not a live prompt — nothing here is loaded by
> `goethe.py`/llama-ui today, and it must never become an `#include` of
> `prompts/node4090-*` without an explicit, separately-reviewed change to
> that loading path. NEVER edit `prompts/node4090-*` directly from this
> file, from `dream_apply.py`, or from any dream. The operator reviews each
> "## Pending" entry by hand and, if accepted, folds its `rule` text into
> the NEXT `prompts/node4090-vX.Y.Z` version bump (the same v0.5.x -> v0.6.0
> discipline every other prompt change already follows), then moves the
> entry down to "## Merged" annotated with the version that absorbed it.
> Entries are append-only otherwise — never delete a pending or rejected
> entry, edit its status instead, so this file stays a legible history of
> every rule TRAUM has ever proposed.

## Pending

## Merged
"""


def _learned_rules_entry_text(args: dict, evidence: list, today: str) -> str:
    """One '## Pending' entry, Prompt 3.6's fixed shape — see DESIGN.md §8
    for the field-by-field contract this mirrors."""
    evidence_str = ", ".join(evidence) if evidence else "(none)"
    title = args["rule"].strip()[:60].rstrip()
    return (
        f"### {today} — {title} [status: pending]\n"
        f"- rule: {args['rule']}\n"
        f"- rationale: {args['rationale']}\n"
        f"- section_hint: {args.get('section_hint', '') or '(unspecified)'}\n"
        f"- evidence: {evidence_str}\n"
        f"- dream: {args.get('provenance', f'dream-{today}')}\n"
        "\n"
    )


def append_learned_rule(repo_root: str, args: dict, evidence: list, today: str) -> str:
    """Prompt 3.6's one exception to Tools-passthrough (see module
    docstring's ONE EXCEPTION note above). Appends one entry under
    prompts/learned-rules.md's '## Pending' heading, creating the file with
    LEARNED_RULES_HEADER if it doesn't exist yet. `args["target_file"]` has
    already been validated (check_prompt_rule_target) to be EXACTLY
    dr.LEARNED_RULES_TARGET before this is ever called — this function does
    not re-derive the path from args, it uses the same fixed constant, so a
    validator bug can't be compounded by this function trusting args anyway.
    Returns a short result string, same shape as a Tools method's own
    return value, so apply_group()/applied.jsonl logging needs no special
    case for this call."""
    path = os.path.join(repo_root, dr.LEARNED_RULES_TARGET)
    if os.path.isfile(path):
        with open(path, "rt", encoding="utf-8") as f:
            text = f.read()
    else:
        text = LEARNED_RULES_HEADER

    entry = _learned_rules_entry_text(args, evidence, today)
    marker = "## Merged"
    idx = text.find(marker)
    if idx == -1:
        # Marker missing (hand-edited file?) — fail closed by appending both
        # the entry and a fresh Merged heading rather than silently
        # dropping the new entry or guessing at file structure.
        text = text.rstrip("\n") + "\n\n" + entry + "## Merged\n"
    else:
        text = text[:idx] + entry + text[idx:]

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wt", encoding="utf-8") as f:
        f.write(text)
    return f"learned-rules.md updated (pending entry appended): {path}"


def apply_group(tools, group: list, dry_run: bool, repo_root: str = ".") -> list:
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

        elif call == "index_to_kb":
            # "kb-fact" proposals (DESIGN.md §6.2, reused verbatim from
            # Thread 1's SCRIBE-1 debrief format) -- a NEW doc, never an
            # existing doc_id, so none of the doc_id-gated checks above
            # apply; check_ground_truth already ran on args.source_tier at
            # the top of validate_proposal_for_apply.
            result = tools.index_to_kb(
                content=args["content"], title=args["title"], topic=args.get("topic", "general"),
                source_url=args.get("source_url", ""), quality_score=args.get("quality_score", 0.5),
                source_tier=args.get("source_tier", "inferred"), evidence=args.get("evidence", ""),
                verified_against=args.get("verified_against", ""), volatility=args.get("volatility", "slow"),
            )
            doc_id_match = re.search(r"doc_id=(\S+)", result or "")
            if doc_id_match:
                _stamp_dream_fields(es, doc_id_match.group(1), today)
            else:
                print(f"[dream_apply] WARNING: could not parse doc_id from index_to_kb result "
                      f"({result!r}) -- origin/provenance NOT stamped", file=sys.stderr)
            results.append({"proposal": p, "result": result})

        elif call == "append_learned_rule":
            # Prompt 3.6 — the one call in this loop that never touches ES.
            result = append_learned_rule(repo_root, args, p.get("evidence", []), today)
            results.append({"proposal": p, "result": result})

        elif call == "es_delete":
            # quarantine-delete-request: delete a quarantined doc from lse-kb
            # check_quarantine() already ran at the top of the loop and allows
            # this type on quarantined docs — it is the ONLY type that may.
            doc_id = args["doc_id"]
            result = es.delete(index="lse-kb", id=doc_id)
            results.append({"proposal": p, "result": f"deleted doc_id={doc_id} from lse-kb (found={result.get('found', False)})"})

        else:
            results.append({"proposal": p, "result": f"ERROR: unknown call {call!r}, not applied"})

    return results


def _stamp_dreamed_at(dream_dir, manifest_db, dry_run):
    """Prompt 2.7 - auto-stamp dreamed_at for sessions considered in this run.
    Reads sessions-*.jsonl companion files and updates manifest.db.
    Returns number of sessions stamped."""
    session_files = glob.glob(os.path.join(dream_dir, "sessions-*.jsonl"))
    if not session_files:
        return 0
    session_ids = set()
    for sf in session_files:
        with open(sf, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        sid = json.loads(line).get("session_id")
                        if sid:
                            session_ids.add(sid)
                    except json.JSONDecodeError:
                        continue
    if not session_ids or dry_run:
        return 0
    try:
        conn = sqlite3.connect(manifest_db)
        now = datetime.now().astimezone().isoformat()
        stamped = 0
        for sid in session_ids:
            cur = conn.execute(
                "UPDATE sessions SET dreamed_at = ? WHERE session_id = ? AND dreamed_at IS NULL",
                (now, sid)
            )
            stamped += cur.rowcount
        conn.commit()
        conn.close()
        print(f"[dream_apply] stamped dreamed_at={now[:19]} for {stamped} session(s) "
              f"in {manifest_db}", file=sys.stderr)
        return stamped
    except Exception as exc:
        print(f"[dream_apply] WARNING: failed to stamp dreamed_at: {exc}", file=sys.stderr)
        return 0


# --- auto-apply earn path with A/B eval (DESIGN.md §2 row 2) ---------------

AUTO_APPLY_DB = "/opt/local-se/dreams/auto-apply-eval.db"

_AUTO_APPLY_SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_type TEXT NOT NULL,
    call_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    dry_run INTEGER NOT NULL DEFAULT 0,
    evidence TEXT
);
CREATE TABLE IF NOT EXISTS earn_thresholds (
    proposal_type TEXT PRIMARY KEY,
    min_runs INTEGER NOT NULL DEFAULT 10,
    min_success_rate REAL NOT NULL DEFAULT 0.85,
    earned_at TEXT,
    earned_by TEXT
);
"""


def _init_eval_db(db_path: str) -> sqlite3.Connection:
    """Initialize the auto-apply evaluation database."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.executescript(_AUTO_APPLY_SCHEMA)
    conn.commit()
    return conn


def _record_eval_outcome(db_path: str, proposal_type: str, call_type: str,
                         outcome: str, evidence: str = "") -> None:
    """Record an outcome for a proposal type in the eval database."""
    try:
        conn = _init_eval_db(db_path)
        now = datetime.now().astimezone().isoformat()
        conn.execute(
            "INSERT INTO eval_outcomes (proposal_type, call_type, outcome, applied_at, dry_run, evidence) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (proposal_type, call_type, outcome, now, evidence[:500])
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"[dream_apply] WARNING: failed to record eval outcome: {exc}",
              file=sys.stderr)


def _check_earn_path(db_path: str, proposal_type: str,
                     min_runs: int = 10, min_success_rate: float = 0.85) -> tuple:
    """Check if a proposal type has earned auto-apply status.
    Returns (earned: bool, stats: dict)."""
    try:
        conn = _init_eval_db(db_path)
        # Get stats for this proposal type (non-dry-run outcomes only)
        row = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as successes "
            "FROM eval_outcomes WHERE proposal_type = ? AND dry_run = 0",
            (proposal_type,)
        ).fetchone()
        total = row[0] or 0
        successes = row[1] or 0
        success_rate = successes / total if total > 0 else 0.0

        earned = total >= min_runs and success_rate >= min_success_rate
        stats = {
            "total": total,
            "successes": successes,
            "success_rate": round(success_rate, 3),
            "min_runs": min_runs,
            "min_success_rate": min_success_rate,
            "earned": earned,
        }

        # Update the thresholds table if earned
        if earned:
            conn.execute(
                "INSERT OR REPLACE INTO earn_thresholds "
                "(proposal_type, min_runs, min_success_rate, earned_at, earned_by) "
                "VALUES (?, ?, ?, ?, 'auto-earn-path')",
                (proposal_type, min_runs, min_success_rate,
                 datetime.now().astimezone().isoformat())
            )
            conn.commit()

        conn.close()
        return earned, stats
    except Exception as exc:
        print(f"[dream_apply] WARNING: failed to check earn path: {exc}",
              file=sys.stderr)
        return False, {"error": str(exc)}


def _get_earned_types(db_path: str) -> list:
    """Get all proposal types that have earned auto-apply status."""
    try:
        conn = _init_eval_db(db_path)
        rows = conn.execute(
            "SELECT proposal_type FROM earn_thresholds WHERE earned_at IS NOT NULL"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def _print_earn_status(db_path: str) -> None:
    """Print the current earn path status for all proposal types."""
    try:
        conn = _init_eval_db(db_path)
        rows = conn.execute(
            "SELECT proposal_type, COUNT(*) as total, "
            "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as successes "
            "FROM eval_outcomes WHERE dry_run = 0 "
            "GROUP BY proposal_type ORDER BY total DESC"
        ).fetchall()
        if not rows:
            print("[dream_apply] earn-path: no outcomes recorded yet", file=sys.stderr)
            conn.close()
            return
        print("\n[dream_apply] earn-path status:", file=sys.stderr)
        for row in rows:
            ptype, total, successes = row
            rate = successes / total if total > 0 else 0.0
            earned = "✓ EARNED" if total >= 10 and rate >= 0.85 else f"({total}/10 runs, {rate:.0%})"
            print(f"  {ptype}: {successes}/{total} ({rate:.0%}) {earned}", file=sys.stderr)
        conn.close()
    except Exception as exc:
        print(f"[dream_apply] WARNING: failed to print earn status: {exc}", file=sys.stderr)


# --- main ----------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="dream_apply.py",
        description="TRAUM-ENGINE apply gate — the ONLY code allowed to write dream "
        "proposals to ES. Prompt 2.5. See docs/dreaming/DESIGN.md.",
    )
    ap.add_argument("--queue", action="store_true",
                    help="scan all day-dirs for pending proposals (newest first), "
                    "filtering expired (>14 days) and already-resolved proposals")
    ap.add_argument("--earn-status", action="store_true",
                    help="show auto-apply earn path status and exit")
    ap.add_argument("--expiry-days", type=int, default=PROPOSAL_EXPIRY_DAYS,
                    help=f"proposal expiry in days (default: {PROPOSAL_EXPIRY_DAYS})")
    ap.add_argument("--proposals", required=False, help="path to a dream run's proposals.jsonl")
    ap.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True,
                    help="render + validate + ask, but never actually call a Tools method "
                    "(default: true). Pass --no-dry-run to actually write to ES.")
    ap.add_argument("--es-url", default=_es_url_default())
    ap.add_argument("--ollama-url", default=_ollama_url_default())
    ap.add_argument("--embed-model", default=_embed_model_default())
    ap.add_argument("--goethe-path", default=_goethe_path_default(),
                    help="path to goethe.py to dynamically load (default: alongside this script)")
    ap.add_argument("--repo-root", default=_repo_root_default(),
                    help="repo root append_learned_rule (Prompt 3.6) resolves "
                    "prompts/learned-rules.md against (default: $GOETHE_REPO_ROOT or cwd)")
    ap.add_argument("--manifest-db", default="/opt/local-se/episodes/manifest.db",
                    help="path to manifest.db for dreamed_at stamping (default: /opt/local-se/episodes/manifest.db)")

    ap.add_argument("--auto-apply-types", default=_dream_auto_apply_default(),
                    help="comma-separated proposal types allowed to skip the interactive "
                    "prompt (default: '' — DESIGN.md §2 row 2, earned via eval, not by hand)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.earn_status:
        _print_earn_status(AUTO_APPLY_DB)
        return
    if not args.queue and not args.proposals:
        print("[dream_apply] error: either --proposals or --queue is required",
              file=sys.stderr)
        sys.exit(1)
    if args.queue:
        dream_dir = os.environ.get("GOETHE_DREAM_DIR", "/opt/local-se/dreams")
    else:
        dream_dir = os.path.dirname(os.path.abspath(args.proposals)) or "."
    auto_apply_types = {t.strip() for t in args.auto_apply_types.split(",") if t.strip()}
    # Add empirically earned types
    earned = _get_earned_types(AUTO_APPLY_DB)
    auto_apply_types.update(earned)
    if earned:
        print(f"[dream_apply] earned auto-apply types: {', '.join(earned)}", file=sys.stderr)

    if args.queue:
        # Queue mode: scan all day-dirs for pending proposals
        queue = scan_proposal_queue(dream_dir, args.expiry_days)
        proposals = []
        for path, props in queue:
            proposals.extend(props)
        mode = "[dry-run] " if args.dry_run else ""
        print(f"[dream_apply] {mode}queue mode: {len(proposals)} pending proposal(s) "
              f"from {len(queue)} file(s) in {dream_dir}", file=sys.stderr)
    else:
        proposals = load_proposals(args.proposals)
        mode = "[dry-run] " if args.dry_run else ""
        print(f"[dream_apply] {mode}loaded {len(proposals)} proposal(s) from {args.proposals}",
              file=sys.stderr)
    if not proposals:
        print("[dream_apply] nothing to do.", file=sys.stderr)
        # Still stamp dreamed_at - sessions were considered even if no proposals
        _stamp_dreamed_at(dream_dir, args.manifest_db, args.dry_run)
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

            results = apply_group(tools, group, args.dry_run, args.repo_root)
            n_applied += len(results)
            for r in results:
                applied_f.write(json.dumps({
                    "proposal": r["proposal"], "result": r["result"],
                    "applied_at": datetime.now().astimezone().isoformat(),
                    "dry_run": args.dry_run,
                }) + "\n")
                print(f"[dream_apply] {mode}{r['result']}", file=sys.stderr)
                # Record eval outcome for earn path tracking
                if not args.dry_run:
                    prop = r["proposal"]
                    outcome = "success" if "ERROR" not in r.get("result", "") else "failure"
                    _record_eval_outcome(
                        AUTO_APPLY_DB,
                        prop.get("type", "unknown"),
                        prop.get("call", "unknown"),
                        outcome,
                        r.get("result", "")[:200]
                    )
    finally:
        applied_f.close()
        rejected_f.close()

    print(
        f"[dream_apply] {mode}done. applied={n_applied} (auto={n_auto}) "
        f"rejected_invariant={n_rejected_invariant} rejected_human={n_rejected_human} "
        f"-> {applied_path}, {rejected_path}",
        file=sys.stderr,
    )

    # Prompt 2.7: stamp dreamed_at for sessions considered in this run
    _stamp_dreamed_at(dream_dir, args.manifest_db, args.dry_run)


    # Prompt 3.4 (TRAUM-INSIGHT): refresh the morning digest "at the end of
    # every dream run" -- the apply half in this file's case, so applied
    # overnight KB changes show up promptly. args.dry_run here means the
    # SAME thing it means throughout apply_group(): if this was a preview
    # run, nothing was actually applied, so the digest must not claim it was
    # (gather_applied() also filters on dry_run itself as defense-in-depth).
    dream_digest.refresh_digest(
        dream_dir=dream_dir, es_url=args.es_url, dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
