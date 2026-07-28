#!/usr/bin/env python3
"""
dream_apply.py — TRAUM-ENGINE apply gate (v0.5.0)
=============================================================================
Canonical, typed apply boundary for CLI and the TRAUM GUI. Preview/dry-run is
side-effect-free: it may perform the reads needed for CAS/invariant checks,
but never asks, claims, decides, writes a file, or calls a semantic write
tool. ``--no-dry-run`` is the explicit reconciliation/apply mode.

Approval atomically claims the full canonical proposal group, revalidates it
against current KB state, and invokes only fixed Tools methods. Authorization
is a temporary capability on that one Tools instance; no environment variable
or arbitrary shell command grants dream writes. A partial/ambiguous external
write becomes ``APPLY_FAILED`` for human reconciliation and is never replayed
automatically. Reject/defer and pair decisions are atomic in ``traum_state``.

``index_to_kb`` now receives ``origin="dream"`` directly and enforces the
dream quality/collision rule inside the Tools method. Existing-doc operations
still receive the narrow post-write origin/provenance bookkeeping described
below. Compatibility JSONL files are mirrors only; SQLite is authoritative.

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

NARROW BOOKKEEPING WRITE — origin/provenance stamping and dedup stats merge:
mentor_correct/record_outcome have no origin or provenance parameter.
Invariant (d) still requires stamping them on every applied write, so
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
one-line es.update() afterward. index_to_kb accepts `origin="dream"` on its
guarded call; the returned doc_id is then used for a narrow provenance stamp
and verification of the created/refined document.

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

MORNING QUEUE (Thread 4, Prompt 4.4): --queue scans EVERY YYYY-MM-DD day-dir
under --dream-dir (not just one proposals.jsonl), and lists every proposal
not yet resolved (present in that day-dir's applied.jsonl, rejected.jsonl, OR
the new expired.jsonl) — oldest day-dir first, grouped by proposal `type` so
same-shaped items batch together for review. It is read-only with respect to
ES/kb: it never loads goethe.py's Tools class at all, only local dream-dir
files (dream_digest.py's own list_day_dirs/load_jsonl/proposal_key are
reused verbatim so a proposal's identity/resolved-state matches the digest's
own "Pending human-gate" preview section exactly). Any pending proposal
whose day-dir is more than --stale-days (default 14) old is AUTO-EXPIRED as
part of explicit ``--no-dry-run`` queue reconciliation: one line is appended
to that day-dir's expired.jsonl and the proposal is excluded. The default
dry-run merely reports what would expire and writes nothing. A stale proposal
is never applied from old evidence; a later successful dream may propose it
again against current KB state.

MORNING REVIEW LOOP (~5 minutes; full runbook write-up is Prompt 4.9, not
yet done — this is the short version so the loop is usable today):
  1. `python3 dream_apply.py --queue` — preview everything pending and what
     would expire, oldest first, grouped by type (no writes).
  2. For each day-dir shown, apply that batch the normal way:
     `python3 dream_apply.py --proposals <dream-dir>/<date>/proposals.jsonl --no-dry-run`
     (still per-proposal yes/no — --queue only changes how you FIND what's
     waiting, never how it gets applied).
  3. Re-run `--queue` — it should now be empty (or down to only proposals
     from a run started after step 1).

USAGE
  # Dry-run (default): renders and validates everything, asks nothing,
  # calls no Tools method — safe to run to preview a batch.
  python3 dream_apply.py --proposals dreams/2026-07-11/proposals.jsonl

  # Real run: interactive, per-proposal yes/no, actually writes to ES.
  python3 dream_apply.py --proposals dreams/2026-07-11/proposals.jsonl --no-dry-run

  # Morning queue: side-effect-free list across all legacy day-dirs.
  python3 dream_apply.py --queue --dream-dir dreams

  # Explicitly reconcile legacy stale entries to expired.jsonl.
  python3 dream_apply.py --queue --dream-dir dreams --no-dry-run

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
  GOETHE_DREAM_DIR                  --queue only: dream output root to scan
                                    for YYYY-MM-DD day-dirs (default:
                                    /opt/local-se/dreams — same variable and
                                    default dream_runner.py/dream_digest.py
                                    already use for the same root)
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime

import dream_runner as dr  # sibling module: reuse validate_proposal_shape, not a second validator
import dream_digest        # Prompt 3.4: morning digest refresh at end of run
import traum_state

__version__ = "0.5.0"

QUARANTINE_DELETE_TYPE = "quarantine-delete-request"  # DESIGN.md §2 row 3(c) -- not
                                                        # produced by any pass yet (2.2-2.4)

_TIER_CEILING = {"ground_truth": 1.0, "primary": 0.8, "secondary": 0.6, "inferred": 0.4}

DREAM_QUEUE_STALE_DAYS = 14  # Prompt 4.4: proposals older than this (by their
                             # day-dir date) are auto-expired by --queue, not
                             # left to accumulate forever unreviewed.


# --- config / valve-style env defaults --------------------------------------

def _es_url_default() -> str:
    return os.environ.get("GOETHE_ES_URL", "http://127.0.0.1:9200")


def _ollama_url_default() -> str:
    return os.environ.get("GOETHE_OLLAMA_URL", "http://127.0.0.1:11434")


def _embed_model_default() -> str:
    return os.environ.get("GOETHE_EMBED_MODEL", "qwen3-embedding:0.6b")


def _goethe_path_default() -> str:
    return os.environ.get("GOETHE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "goethe.py"))


def _dream_auto_apply_default() -> str:
    return os.environ.get("GOETHE_DREAM_AUTO_APPLY", "")


def _repo_root_default() -> str:
    return os.environ.get("GOETHE_REPO_ROOT", os.getcwd())


def _dream_dir_default() -> str:
    """--queue only. Same env var and default dream_runner.py/dream_digest.py
    already use for the dream output root (a directory of YYYY-MM-DD
    day-dirs) -- deliberately the SAME variable, not a new one, so a single
    GOETHE_DREAM_DIR export configures all three tools consistently."""
    return os.environ.get("GOETHE_DREAM_DIR", "/opt/local-se/dreams")


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
        # Full _source is needed for the generation/apply CAS token. The
        # token helper ignores embeddings and other non-semantic metadata.
        resp = es.get(index="lse-kb", id=doc_id)
        return resp["_source"]
    except Exception as exc:
        status = getattr(getattr(exc, "meta", None), "status", None)
        if status == 404 or type(exc).__name__ in {"NotFoundError", "KeyError"}:
            return None
        raise dr.DependencyBlocked(
            "elasticsearch", f"read failed for lse-kb/{doc_id}: {exc}"
        ) from exc


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


def check_target_cas(proposal: dict, current_doc: dict | None):
    expected = proposal.get("expected_target_token")
    if not expected:
        return None  # legacy proposal: other live invariants still apply
    actual = traum_state.document_token(current_doc)
    if actual != expected:
        return (
            "target_changed_since_generation: expected token "
            f"{expected[:12]}, current {str(actual)[:12]} — review fresh evidence"
        )
    return None


def check_noop(proposal: dict, current_doc: dict | None):
    """Deterministic no-op detection; these never need a human decision."""
    if current_doc is None:
        return None
    call = proposal.get("call")
    args = proposal.get("args", {})
    if call == "mentor_correct":
        same_content = str(args.get("correction", "")) == str(current_doc.get("content", ""))
        try:
            same_quality = float(args.get("new_quality")) == float(
                current_doc.get("quality_score")
            )
        except (TypeError, ValueError):
            same_quality = False
        if same_content and same_quality:
            return "noop: target already has the proposed content and quality"
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
    only when the read-only precheck succeeds and predicts no unsafe raise.
    Dependency failure is typed BLOCKED/fail-closed; it never becomes a
    permanent rejection or an unchecked apply."""
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
        raise dr.DependencyBlocked("skill-collision-precheck", str(exc)) from exc
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


def check_kb_fact_collision_raise(tools, args: dict):
    """Mirror index_to_kb's KNN dedup before a dream-origin KB fact write."""
    try:
        content = str(args.get("content", ""))[:50000]
        embedding = tools._embed(content)
        dup = tools._es().search(
            index="lse-kb",
            body={
                "knn": {"field": "embedding", "query_vector": embedding,
                        "k": 1, "num_candidates": 10},
                "_source": ["quality_score"], "size": 1,
            },
        )["hits"]["hits"]
    except Exception as exc:
        raise dr.DependencyBlocked("kb-fact-collision-precheck", str(exc)) from exc
    if not dup or dup[0].get("_score", 0) < 0.92:
        return None
    existing_q = float(dup[0]["_source"].get("quality_score", 0.0) or 0.0)
    tier = args.get("source_tier", "inferred")
    effective_q = min(float(args.get("quality_score", 0.5)), _TIER_CEILING.get(tier, 0.4))
    if effective_q > existing_q:
        return (
            f"would collide with existing KB doc {dup[0].get('_id')!r} and raise "
            f"quality {existing_q:.2f} -> {effective_q:.2f} — rejected"
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
        err = (check_target_cas(p, current_doc) or check_noop(p, current_doc)
               or check_quarantine(current_doc, ptype)
               or check_quality_raise(args, current_doc))
        if err:
            return err

    if call == "kb_verify" and "doc_id" in args:
        current_doc = fetch_kb_doc(es, args["doc_id"])
        if current_doc is None:
            return f"doc_id {args['doc_id']!r} not found in lse-kb at apply time"
        err = check_target_cas(p, current_doc) or check_quarantine(current_doc, ptype)
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
        _reports = dream_digest.day_dir_files(dream_dir, "report", "md")
        _ref = ", ".join(_reports) if _reports else os.path.join(dream_dir, "report-*.md")
        top = f"――― REPORT: {_ref} (reference) ―――"

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
        blocks.append(_fmt_block(call, i, len(group), lines, multiline))
        blocks.append(f"why:               {p.get('why', '')}")
        blocks.append("")

    if len(group) > 1:
        question = f"Commit this {first.get('type')} (pair — {len(group)} calls, applied together)? (yes/no)"
    else:
        question = f"Commit this {first.get('type')} ({len(group)} call)? (yes/no)"
    blocks.append(question)
    return traum_state.redact_persisted_text("\n".join(blocks)) or ""


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

    entry = traum_state.redact_persisted_text(
        _learned_rules_entry_text(args, evidence, today)
    ) or ""
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


class ApplyError(RuntimeError):
    """A confirmed operation did not produce a verifiable success result."""


def _checked_result(call: str, result):
    text = str(result or "")
    success = {
        "mentor_correct": lambda s: s.startswith("Mentor correction applied:"),
        "record_outcome": lambda s: s.startswith("Outcome recorded:"),
        "kb_verify": lambda s: s.startswith(("kb_verify phase 1", "VERIFY phase1:")),
        "skill_record": lambda s: bool(re.match(r"^SKILL (?:created|updated): \S+", s)),
        "index_to_kb": lambda s: bool(
            re.match(r"^KB (?:created|updated \(refined\)): doc_id=\S+", s)
        ),
        "append_learned_rule": lambda s: s.startswith("learned-rules.md updated"),
    }.get(call)
    if success is None or not success(text):
        safe_text = traum_state.redact_persisted_text(text)
        raise ApplyError(f"{call} returned a non-success result: {safe_text!r}")
    return result


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
            result = _checked_result(
                call, tools.mentor_correct(
                    args["doc_id"], args["correction"], args["new_quality"]
                )
            )
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
            result = _checked_result(
                call, tools.record_outcome(
                    args["doc_id"], args["success"], args.get("notes", ""),
                    args.get("evidence", "")
                )
            )
            _stamp_dream_fields(es, args["doc_id"], today)
            results.append({"proposal": p, "result": result})

        elif call == "kb_verify":
            result = _checked_result(
                call, tools.kb_verify(args["doc_id"])
            )  # phase 1 only -- read-only, no stamp needed
            results.append({"proposal": p, "result": result})

        elif call == "skill_record":
            result = _checked_result(call, tools.skill_record(
                task=args["task"], occupation=args["occupation"], procedure=args["procedure"],
                verification=args["verification"], preconditions=args.get("preconditions", ""),
                failure_modes=args.get("failure_modes", ""), provenance=args.get("provenance", ""),
                quality=args.get("quality", 0.5), source_tier=args.get("source_tier", "inferred"),
            ))
            # provenance is already a real skill_record arg; origin still isn't.
            skill_id_match = re.search(r"SKILL (?:created|updated): (\S+)", result or "")
            if skill_id_match:
                try:
                    import hashlib
                    slug_id = skill_id_match.group(1)
                    doc_hash = hashlib.sha256(slug_id.encode()).hexdigest()[:16]
                    es.update(index="lse-skills", id=doc_hash, body={"doc": {"origin": "dream"}})
                except Exception as exc:
                    raise ApplyError(
                        "skill_record wrote but mandatory origin=dream stamp failed; "
                        f"reconcile before retry: {exc}"
                    ) from exc
            else:
                raise ApplyError(
                    "skill_record wrote but returned no parseable skill id; mandatory "
                    "origin=dream stamp could not be verified"
                )
            results.append({"proposal": p, "result": result})

        elif call == "index_to_kb":
            # "kb-fact" proposals (DESIGN.md §6.2, reused verbatim from
            # Thread 1's SCRIBE-1 debrief format) -- a NEW doc, never an
            # existing doc_id, so none of the doc_id-gated checks above
            # apply; check_ground_truth already ran on args.source_tier at
            # the top of validate_proposal_for_apply.
            result = _checked_result(call, tools.index_to_kb(
                content=args["content"], title=args["title"], topic=args.get("topic", "general"),
                source_url=args.get("source_url", ""), quality_score=args.get("quality_score", 0.5),
                source_tier=args.get("source_tier", "inferred"), evidence=args.get("evidence", ""),
                verified_against=args.get("verified_against", ""), volatility=args.get("volatility", "slow"),
                origin="dream",
            ))
            doc_id_match = re.search(r"doc_id=(\S+)", result or "")
            if doc_id_match:
                _stamp_dream_fields(es, doc_id_match.group(1), today)
            else:
                raise ApplyError(
                    "index_to_kb wrote but returned no parseable doc_id; origin/provenance "
                    "could not be verified — reconcile before retry"
                )
            results.append({"proposal": p, "result": result})

        elif call == "append_learned_rule":
            # Prompt 3.6 — the one call in this loop that never touches ES.
            result = _checked_result(
                call, append_learned_rule(
                    repo_root, args, p.get("evidence", []), today
                )
            )
            results.append({"proposal": p, "result": result})

        else:
            raise ApplyError(f"unknown call {call!r}, not applied")

    return results


# --- canonical non-interactive decision API (GUI + CLI) ---------------------

def _as_state(state_or_path) -> traum_state.TraumState:
    if isinstance(state_or_path, traum_state.TraumState):
        return state_or_path
    return traum_state.TraumState(str(state_or_path))


def _canonical_group(state: traum_state.TraumState, proposal_id: str) -> list[dict]:
    selected = state.get_proposal(proposal_id)
    if selected is None:
        raise traum_state.NotFoundError(f"proposal not found: {proposal_id}")
    pair_id = selected["proposal"].get("pair_id")
    if not pair_id:
        return [selected]
    rows = state.list_proposals(limit=100000)
    group = [
        row for row in rows
        if row["attempt_id"] == selected["attempt_id"]
        and row["proposal"].get("pair_id") == pair_id
    ]
    return sorted(group, key=lambda row: row["created_at"])


def _load_tools_for_decision(tools, es_url, ollama_url, embed_model, goethe_path):
    if tools is not None:
        return tools
    Tools = load_tools_class(goethe_path)
    return make_tools_instance(Tools, es_url, ollama_url, embed_model)


def preview_proposal(state_or_path, proposal_id: str, *, tools=None,
                     expected_revision: int | None = None,
                     es_url: str | None = None, ollama_url: str | None = None,
                     embed_model: str | None = None,
                     goethe_path: str | None = None,
                     repo_root: str | None = None) -> dict:
    """Read, render, and live-validate a proposal without changing state.

    This function performs only ES/model reads needed by invariant checks. It
    never claims a proposal, invokes a write tool, writes a decision log, or
    refreshes the digest.
    """
    state = _as_state(state_or_path)
    rows = _canonical_group(state, proposal_id)
    parent = state.get_attempt(rows[0]["attempt_id"])
    if parent is None or parent["state"] not in traum_state.CONSUMABLE_OUTCOMES:
        raise traum_state.ConflictError(
            "proposal is not reviewable until its parent attempt completes successfully"
        )
    if expected_revision is not None and rows[0]["revision"] != expected_revision:
        raise traum_state.ConflictError(
            f"proposal revision changed: expected {expected_revision}, "
            f"got {rows[0]['revision']}"
        )
    tool_obj = _load_tools_for_decision(
        tools, es_url or _es_url_default(), ollama_url or _ollama_url_default(),
        embed_model or _embed_model_default(), goethe_path or _goethe_path_default(),
    )
    es = tool_obj._es()
    reasons = []
    for row in rows:
        proposal = row["proposal"]
        reason = validate_proposal_for_apply(proposal, es)
        if reason is None and proposal.get("call") == "skill_record":
            reason = check_skill_collision_raise(tool_obj, proposal.get("args", {}))
        if reason is None and proposal.get("call") == "index_to_kb":
            reason = check_kb_fact_collision_raise(tool_obj, proposal.get("args", {}))
        reasons.append(reason)
    attempt = state.get_attempt(rows[0]["attempt_id"])
    day_dir = _attempt_day_dir(state, attempt) or os.path.dirname(state.db_path)
    return {
        "proposal_id": proposal_id,
        "proposal_ids": [row["proposal_id"] for row in rows],
        "revision": rows[0]["revision"],
        "state": rows[0]["state"],
        "valid": not any(reasons),
        "reasons": reasons,
        "rendered": render_group([row["proposal"] for row in rows], day_dir),
    }


def _attempt_day_dir(state: traum_state.TraumState, attempt) -> str | None:
    """Resolve the day directory that holds an attempt's artifacts.

    A controller attempt records one absolute ``proposals`` path.  A
    legacy-imported attempt records a *list* of bare filenames plus the day, so
    ``os.path.dirname`` on the raw value raises TypeError and blocks preview and
    the decision mirror.  Returns None when no real directory can be resolved,
    so callers never write stray files into the dreams root.
    """
    artifacts = (attempt or {}).get("artifacts") or {}
    artifact = artifacts.get("proposals") or ""
    if isinstance(artifact, (list, tuple)):
        artifact = next((item for item in artifact
                         if isinstance(item, str) and item), "")
    if isinstance(artifact, str):
        parent = os.path.dirname(artifact)
        if parent:
            return parent
    day = artifacts.get("day")
    if isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        candidate = os.path.join(os.path.dirname(state.db_path), day)
        if os.path.isdir(candidate):
            return candidate
    return None


def _append_compat_decision(state: traum_state.TraumState, rows: list[dict],
                            filename: str, entry_builder) -> None:
    """Best-effort mirror for legacy digest readers; SQLite stays canonical."""
    attempt = state.get_attempt(rows[0]["attempt_id"])
    day_dir = _attempt_day_dir(state, attempt)
    if not day_dir:
        return
    path = os.path.join(day_dir, filename)
    try:
        with open(path, "at", encoding="utf-8") as f:
            for row in rows:
                entry = traum_state.redact_persisted_value(entry_builder(row))
                f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        print(f"[dream_apply] WARNING: canonical decision succeeded but legacy "
              f"{filename} mirror failed ({exc})", file=sys.stderr)


def decide_proposal(state_or_path, proposal_id: str, decision: str, *,
                    expected_revision: int | None = None,
                    reason: str | None = None, defer_until: str | None = None,
                    actor: str = "local-operator", tools=None,
                    es_url: str | None = None, ollama_url: str | None = None,
                    embed_model: str | None = None,
                    goethe_path: str | None = None,
                    repo_root: str | None = None) -> dict:
    """Make one canonical approve/reject/defer decision.

    Approval performs live invariant/CAS validation, atomically claims the
    whole proposal pair, executes without a shell, and finalizes every member
    together. A crash/partial external write becomes ``APPLY_FAILED`` and is
    never auto-replayed. Repeated calls on an APPLIED proposal are idempotent.
    """
    state = _as_state(state_or_path)
    decision = decision.lower()
    rows = _canonical_group(state, proposal_id)
    ids = [row["proposal_id"] for row in rows]
    revisions = {row["proposal_id"]: row["revision"] for row in rows}
    if expected_revision is not None:
        revisions[proposal_id] = expected_revision

    if decision in {"reject", "defer"}:
        updated = state.transition_proposals(
            ids, decision, actor=actor, reason=reason,
            defer_until=defer_until, expected_revisions=revisions,
        )
        if decision == "reject":
            now = datetime.now().astimezone().isoformat()
            _append_compat_decision(
                state, rows, "rejected.jsonl",
                lambda row: {"proposal": row["proposal"],
                             "reason": reason or "human declined",
                             "rejected_at": now},
            )
        return {"decision": decision, "state": updated[0]["state"],
                "proposals": updated}
    if decision != "approve":
        raise ValueError("decision must be approve, reject, or defer")

    if all(row["state"] == "APPLIED" for row in rows):
        return {"decision": "approve", "state": "APPLIED",
                "proposals": rows, "idempotent": True}

    tool_obj = _load_tools_for_decision(
        tools, es_url or _es_url_default(), ollama_url or _ollama_url_default(),
        embed_model or _embed_model_default(), goethe_path or _goethe_path_default(),
    )
    preview = preview_proposal(
        state, proposal_id, tools=tool_obj, repo_root=repo_root or _repo_root_default()
    )
    if not preview["valid"]:
        updated = state.transition_proposals(
            ids, "system_reject", actor="system-invariant",
            reason="; ".join(r for r in preview["reasons"] if r),
            expected_revisions=revisions,
        )
        return {"decision": "system_reject", "state": "SYSTEM_REJECTED",
                "reasons": preview["reasons"], "proposals": updated}

    claimed = state.claim_proposals(
        ids, actor=actor, expected_revisions=revisions
    )
    auth_missing = not hasattr(tool_obj, "_dream_apply_authorized")
    prior_auth = getattr(tool_obj, "_dream_apply_authorized", False)
    tool_obj._dream_apply_authorized = True
    try:
        results = apply_group(
            tool_obj, [row["proposal"] for row in claimed], dry_run=False,
            repo_root=repo_root or _repo_root_default(),
        )
    except Exception as exc:
        safe_exc = traum_state.redact_persisted_text(exc) or "redacted apply failure"
        failed = state.finalize_proposals(
            ids, succeeded=False, actor=actor,
            reason=f"{type(exc).__name__}: {safe_exc}",
        )
        raise ApplyError(
            f"proposal apply failed closed; reconcile before retry: {safe_exc}"
        ) from exc
    finally:
        if auth_missing:
            try:
                delattr(tool_obj, "_dream_apply_authorized")
            except AttributeError:
                pass
        else:
            tool_obj._dream_apply_authorized = prior_auth

    applied = state.finalize_proposals(
        ids, succeeded=True, actor=actor, result=results
    )
    now = datetime.now().astimezone().isoformat()
    result_by_id = {
        r["proposal"].get("proposal_id"): r["result"] for r in results
    }
    _append_compat_decision(
        state, rows, "applied.jsonl",
        lambda row: {
            "proposal": row["proposal"],
            "result": result_by_id.get(row["proposal_id"], "applied"),
            "applied_at": now, "dry_run": False,
        },
    )
    return {"decision": "approve", "state": "APPLIED",
            "proposals": applied, "results": results, "idempotent": False}


# --- queue mode (Prompt 4.4, TRAUM-AUTO) -----------------------------------
# Read-only w.r.t. ES/kb -- never loads goethe.py's Tools class. Only reads
# local dream-dir files (reusing dream_digest.py's own day-dir/jsonl/identity
# helpers so a proposal's "is this resolved yet" state matches the digest's
# preview section exactly) and, when it finds something stale, appends to a
# new expired.jsonl next to applied.jsonl/rejected.jsonl.

def gather_queue(dream_dir: str, today, stale_days: int = DREAM_QUEUE_STALE_DAYS,
                 reconcile: bool = False):
    """Walks every YYYY-MM-DD day-dir under dream_dir, OLDEST FIRST, and
    returns (pending, expired):
      pending -- proposals not yet applied/rejected/expired, each tagged with
                 its source date and age_days, in oldest-day-dir-first order
                 (Prompt 4.4: "oldest first").
      expired -- proposals this call JUST auto-expired (age_days > stale_days),
                 each tagged with date/age_days/reason -- reported back so the
                 caller can tell the operator what changed this run.

    A proposal already present (by dream_digest.proposal_key content hash) in
    its day-dir's applied.jsonl, rejected.jsonl, OR expired.jsonl is resolved
    and excluded from `pending`. Newly-expired proposals are appended only
    when ``reconcile=True`` (CLI ``--no-dry-run``). The default queue preview
    is side-effect-free and reports what *would* expire without resolving it.

    A day-dir whose name fails to parse as a date is defensively treated as
    age_days=0 (never auto-expired on a parse failure -- fail closed toward
    "keep it pending for a human to see", not toward silent data loss)."""
    day_dirs = sorted(dream_digest.list_day_dirs(dream_dir))  # ascending == oldest first
    pending: list = []
    expired: list = []

    for d in day_dirs:
        base = os.path.join(dream_dir, d)
        proposals = []
        for _ppath in dream_digest.day_dir_files(base, "proposals", "jsonl"):
            proposals.extend(dream_digest.load_jsonl(_ppath))
        if not proposals:
            continue
        applied = dream_digest.load_jsonl(os.path.join(base, "applied.jsonl"))
        rejected = dream_digest.load_jsonl(os.path.join(base, "rejected.jsonl"))
        expired_prior = dream_digest.load_jsonl(os.path.join(base, "expired.jsonl"))
        resolved = {
            dream_digest.proposal_key(e["proposal"]) for e in applied
            if "proposal" in e and e.get("dry_run") is False
        }
        resolved |= {dream_digest.proposal_key(e["proposal"]) for e in rejected if "proposal" in e}
        resolved |= {dream_digest.proposal_key(e["proposal"]) for e in expired_prior if "proposal" in e}

        try:
            age_days = (today - date.fromisoformat(d)).days
        except ValueError:
            age_days = 0  # malformed dir name -- fail closed, never auto-expire

        newly_expired_here = []
        for p in proposals:
            if dream_digest.proposal_key(p) in resolved:
                continue
            if age_days > stale_days:
                entry = {
                    "proposal": p,
                    "reason": f"stale (>{stale_days}d, age={age_days}d) -- auto-expired; "
                              "re-dream will re-propose if still true",
                    "expired_at": datetime.now().astimezone().isoformat(),
                    "age_days": age_days,
                }
                newly_expired_here.append(entry)
                expired.append({**entry, "date": d})
            else:
                pending.append({"date": d, "age_days": age_days, "proposal": p})

        if newly_expired_here and reconcile:
            with open(os.path.join(base, "expired.jsonl"), "at", encoding="utf-8") as f:
                for entry in newly_expired_here:
                    f.write(json.dumps(
                        traum_state.redact_persisted_value(entry)
                    ) + "\n")

    return pending, expired


def group_queue_by_type(pending: list) -> dict:
    """Buckets already-oldest-first `pending` entries by proposal `type`,
    preserving each bucket's oldest-first order. Bucket order itself falls
    out for free: dict insertion order means whichever type's OLDEST pending
    proposal is encountered first (i.e. is oldest overall) leads the listing
    -- the type that has been waiting longest gets reviewed first, not
    alphabetical order."""
    buckets: dict = {}
    for entry in pending:
        ptype = entry["proposal"].get("type", "unknown")
        buckets.setdefault(ptype, []).append(entry)
    return buckets


def render_queue(buckets: dict, today) -> str:
    """Human-readable listing for stdout -- deliberately plain text (not the
    SCRIBE-1 confirm-gate block shape render_group() uses below): --queue is
    a read-only inventory to scan quickly, not a per-proposal apply prompt."""
    total = sum(len(v) for v in buckets.values())
    lines = [f"=== dream_apply --queue: {total} pending proposal(s) as of {today.isoformat()} ==="]
    for ptype, entries in buckets.items():
        lines.append(f"\n-- {ptype} ({len(entries)} pending, oldest first) --")
        for e in entries:
            p = e["proposal"]
            pair = f" pair_id={p['pair_id']}" if p.get("pair_id") else ""
            why = dream_digest._truncate(p.get("why", ""), 100)
            lines.append(f"  [{e['date']}, {e['age_days']}d old]{pair} {p.get('call', '?')} — {why}")
    return traum_state.redact_persisted_text("\n".join(lines)) or ""


def cmd_queue(args) -> None:
    today = date.today()
    dry_run = bool(getattr(args, "dry_run", True))
    pending, expired = gather_queue(
        args.dream_dir, today, stale_days=args.stale_days,
        reconcile=not dry_run,
    )

    if expired:
        by_date = {}
        for e in expired:
            by_date.setdefault(e["date"], 0)
            by_date[e["date"]] += 1
        detail = ", ".join(f"{d}:{n}" for d, n in sorted(by_date.items()))
        verb = "auto-expired" if not dry_run else "[dry-run] would auto-expire"
        destination = " -> <day-dir>/expired.jsonl" if not dry_run else ""
        print(f"[dream_apply] {verb} {len(expired)} stale (>{args.stale_days}d) "
              f"proposal(s) this run ({detail}){destination}", file=sys.stderr)

    if not pending:
        print(f"[dream_apply] queue is empty -- 0 pending proposal(s) under {args.dream_dir}",
              file=sys.stderr)
        return

    buckets = group_queue_by_type(pending)
    print(render_queue(buckets, today))
    print(
        f"\n[dream_apply] {len(pending)} pending across {len(buckets)} type(s) under "
        f"{args.dream_dir}. Apply a day's batch with: python3 dream_apply.py --proposals "
        f"{args.dream_dir}/<date>/proposals.jsonl --no-dry-run",
        file=sys.stderr,
    )


# --- main ----------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="dream_apply.py",
        description="TRAUM-ENGINE apply gate — the ONLY code allowed to write dream "
        "proposals to ES. Prompt 2.5. See docs/dreaming/DESIGN.md.",
    )
    ap.add_argument("--proposals", default=None,
                    help="path to a dream run's proposals.jsonl (required unless --queue)")
    ap.add_argument("--queue", action="store_true",
                    help="Prompt 4.4: list pending human-gate proposals across ALL day-dirs "
                    "under --dream-dir, oldest first, grouped by type; auto-expires anything "
                    "older than --stale-days. Read-only w.r.t. ES -- does not load goethe.py. "
                    "See MORNING REVIEW LOOP in this module's docstring.")
    ap.add_argument("--dream-dir", default=_dream_dir_default(),
                    help="--queue only: dream output root to scan for day-dirs "
                    "(default: $GOETHE_DREAM_DIR or /opt/local-se/dreams)")
    ap.add_argument("--stale-days", type=int, default=DREAM_QUEUE_STALE_DAYS,
                    help="--queue only: auto-expire proposals older than this many days "
                    f"(default: {DREAM_QUEUE_STALE_DAYS})")
    ap.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True,
                    help="side-effect-free preview: render + read-only validate, do not ask "
                    "or resolve anything (default: true). Pass --no-dry-run to decide/apply.")
    ap.add_argument("--state-db", default=None,
                    help="canonical state DB (default: <dream-root>/traum-state.db)")
    ap.add_argument("--es-url", default=_es_url_default())
    ap.add_argument("--ollama-url", default=_ollama_url_default())
    ap.add_argument("--embed-model", default=_embed_model_default())
    ap.add_argument("--goethe-path", default=_goethe_path_default(),
                    help="path to goethe.py to dynamically load (default: alongside this script)")
    ap.add_argument("--repo-root", default=_repo_root_default(),
                    help="repo root append_learned_rule (Prompt 3.6) resolves "
                    "prompts/learned-rules.md against (default: $GOETHE_REPO_ROOT or cwd)")
    ap.add_argument("--auto-apply-types", default=_dream_auto_apply_default(),
                    help="comma-separated proposal types allowed to skip the interactive "
                    "prompt (default: '' — DESIGN.md §2 row 2, earned via eval, not by hand)")
    return ap.parse_args(argv)


def _state_path_for_proposals(args, day_dir: str) -> str:
    if args.state_db:
        return args.state_db
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", os.path.basename(day_dir)):
        return traum_state.default_db_path(os.path.dirname(day_dir))
    return traum_state.default_db_path(args.dream_dir)


def main(argv=None) -> None:
    args = parse_args(argv)

    if args.queue:
        cmd_queue(args)
        return

    if not args.proposals:
        raise SystemExit("[dream_apply] --proposals is required unless --queue is given")

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

    # Preview is intentionally boring: validate/render and stop. No prompt,
    # state DB, decision JSONL, digest refresh, environment authorization, or
    # write-capable Tools method is reached.
    if args.dry_run:
        for group in groups:
            reasons = [validate_proposal_for_apply(p, es) for p in group]
            for p, reason in zip(group, reasons):
                if reason is None and p.get("call") == "skill_record":
                    reason = check_skill_collision_raise(tools, p.get("args", {}))
                if reason is None and p.get("call") == "index_to_kb":
                    reason = check_kb_fact_collision_raise(tools, p.get("args", {}))
                if reason:
                    print(f"[dream_apply] [dry-run] would system-reject: {reason}",
                          file=sys.stderr)
            print("\n" + render_group(group, dream_dir) + "\n", file=sys.stderr)
        print(f"[dream_apply] [dry-run] previewed {len(proposals)} proposal(s); "
              "no decisions recorded", file=sys.stderr)
        return

    state_path = _state_path_for_proposals(args, dream_dir)
    state = traum_state.TraumState(state_path) if os.path.exists(state_path) else None
    applied_path = os.path.join(dream_dir, "applied.jsonl")
    rejected_path = os.path.join(dream_dir, "rejected.jsonl")
    resolved = set()
    for path in (applied_path, rejected_path, os.path.join(dream_dir, "expired.jsonl")):
        for entry in dream_digest.load_jsonl(path):
            if "proposal" in entry and not (
                path == applied_path and entry.get("dry_run") is not False
            ):
                resolved.add(dream_digest.proposal_key(entry["proposal"]))

    n_applied = n_rejected_invariant = n_rejected_human = n_auto = 0
    for group in groups:
        if all(dream_digest.proposal_key(p) in resolved for p in group):
            print("[dream_apply] already resolved — idempotent skip", file=sys.stderr)
            continue
        reasons = [validate_proposal_for_apply(p, es) for p in group]
        for i, p in enumerate(group):
            if reasons[i] is None and p.get("call") == "skill_record":
                reasons[i] = check_skill_collision_raise(tools, p.get("args", {}))
            if reasons[i] is None and p.get("call") == "index_to_kb":
                reasons[i] = check_kb_fact_collision_raise(tools, p.get("args", {}))
        bad = next((r for r in reasons if r), None)
        canonical_id = group[0].get("proposal_id")
        canonical = bool(state and canonical_id and state.get_proposal(canonical_id))
        if bad:
            n_rejected_invariant += len(group)
            if canonical:
                state.transition_proposals(
                    [p["proposal_id"] for p in group], "system_reject",
                    actor="system-invariant", reason=bad,
                )
            else:
                with open(rejected_path, "at", encoding="utf-8") as f:
                    for p in group:
                        f.write(json.dumps(traum_state.redact_persisted_value({
                            "proposal": p, "reason": f"invariant: {bad}",
                            "rejected_at": datetime.now().astimezone().isoformat(),
                        })) + "\n")
            print(f"[dream_apply] SYSTEM_REJECTED (invariant/no-op): {bad}", file=sys.stderr)
            continue

        print("\n" + render_group(group, dream_dir) + "\n", file=sys.stderr)
        ptype = group[0].get("type")
        # Reverify is a documented read-only probe, not a semantic write and
        # not an expansion of GOETHE_DREAM_AUTO_APPLY. All semantic proposal
        # types still require a human unless the evidence-earned allowlist
        # already contains them.
        safe_probe = ptype == "reverify"
        if safe_probe or ptype in auto_apply_types:
            confirmed = True
            n_auto += 1
            source = "built-in read-only probe" if safe_probe else "earned allowlist"
            print(f"[dream_apply] automatic ({source}): type={ptype!r}", file=sys.stderr)
        else:
            confirmed = ask_yes_no("Apply?")

        if not confirmed:
            n_rejected_human += len(group)
            if canonical:
                decide_proposal(state, canonical_id, "reject", tools=tools,
                                reason="human declined")
            else:
                with open(rejected_path, "at", encoding="utf-8") as f:
                    for p in group:
                        f.write(json.dumps(traum_state.redact_persisted_value({
                            "proposal": p, "reason": "human declined",
                            "rejected_at": datetime.now().astimezone().isoformat(),
                        })) + "\n")
            continue

        if canonical:
            decision_result = decide_proposal(
                state, canonical_id, "approve", tools=tools,
                repo_root=args.repo_root,
            )
            results = decision_result.get("results", [])
        else:
            auth_missing = not hasattr(tools, "_dream_apply_authorized")
            prior_auth = getattr(tools, "_dream_apply_authorized", False)
            tools._dream_apply_authorized = True
            try:
                results = apply_group(tools, group, False, args.repo_root)
            finally:
                if auth_missing:
                    try:
                        delattr(tools, "_dream_apply_authorized")
                    except AttributeError:
                        pass
                else:
                    tools._dream_apply_authorized = prior_auth
            with open(applied_path, "at", encoding="utf-8") as f:
                for result in results:
                    f.write(json.dumps(traum_state.redact_persisted_value({
                        "proposal": result["proposal"], "result": result["result"],
                        "applied_at": datetime.now().astimezone().isoformat(),
                        "dry_run": False,
                    })) + "\n")
        n_applied += len(results)
        for result in results:
            safe_result = traum_state.redact_persisted_text(result["result"])
            print(f"[dream_apply] {safe_result}", file=sys.stderr)

    print(
        f"[dream_apply] done. applied={n_applied} (auto={n_auto}) "
        f"rejected_invariant={n_rejected_invariant} rejected_human={n_rejected_human} "
        f"-> {applied_path}, {rejected_path}",
        file=sys.stderr,
    )

    # Prompt 3.4 (TRAUM-INSIGHT): refresh the morning digest "at the end of
    # every dream run" -- the apply half in this file's case, so applied
    # overnight KB changes show up promptly. args.dry_run here means the
    # SAME thing it means throughout apply_group(): if this was a preview
    # run, nothing was actually applied, so the digest must not claim it was
    # (gather_applied() also filters on dry_run itself as defense-in-depth).
    dream_digest.refresh_digest(
        dream_dir=dream_dir, es_url=args.es_url, dry_run=False,
    )


if __name__ == "__main__":
    main()
