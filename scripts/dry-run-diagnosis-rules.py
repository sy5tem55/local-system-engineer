#!/usr/bin/env python3
"""scripts/dry-run-diagnosis-rules.py — SPEC-auto-adjudication-2026-08 §4/§8.

Read-only simulation of R1/R2/R3 (tools/diagnosis_rules.py) against the
CURRENT PENDING/APPLIED `diagnosis` proposals in a traum-state.db. Writes
NOTHING — no call to TraumState.record_proposals, and the database is opened
via a `file:...?mode=ro` URI so even a bug here cannot mutate it.

Simulates what live operation would have produced by walking rows in
`created_at` order: every APPLIED diagnosis is always a valid prior
(historical fact, never retroactively undone); every PENDING diagnosis is
evaluated against the priors accumulated so far (all APPLIED rows, plus
every earlier PENDING row that itself survived simulation) and, if it
survives, joins the prior pool for rows after it. A row rejected by R2/R3 or
superseded by R1 does NOT join the prior pool — this is what makes "four
reworded CancelledError diagnoses collapse to one, each of the other three
naming that one survivor" fall out naturally rather than chaining.

Usage:
    python3 scripts/dry-run-diagnosis-rules.py --db /opt/local-se/dreams/traum-state.db
    python3 scripts/dry-run-diagnosis-rules.py --db /path/to/a/COPY/of/traum-state.db \
        --r1-threshold 0.94 --no-rule-r3
"""
import argparse
import functools
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import diagnosis_rules as dr  # noqa: E402
import dream_runner  # noqa: E402


def _ollama_url_default() -> str:
    return os.environ.get("GOETHE_OLLAMA_URL", "http://127.0.0.1:11434")


def _embed_model_default() -> str:
    return os.environ.get("GOETHE_EMBED_MODEL", "qwen3-embedding:0.6b")


def load_pending_and_applied_diagnoses(db_path: str):
    """Read-only connection (file: URI, mode=ro) — cannot write even by
    accident. ORDER BY created_at ASC to replay decisions in the order they
    would have been made live."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT proposal_id, state, reason, created_at, payload_json FROM proposals "
        "WHERE proposal_type='diagnosis' AND state IN ('PENDING','APPLIED') "
        "ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        out.append({
            "proposal_id": row["proposal_id"],
            "state": row["state"],
            "created_at": row["created_at"],
            "proposal": json.loads(row["payload_json"]),
        })
    return out


def simulate(rows, *, embed_fn, r1_enabled, r2_enabled, r3_enabled,
             r1_threshold, r3_threshold):
    """Returns (decisions, counts). decisions: list of dicts, one per row,
    with keys proposal_id, real_state, verdict ('kept'|'SYSTEM_REJECTED'|
    'SUPERSEDED'), reason. counts: Counter of verdict/rule."""
    priors = [r for r in rows if r["state"] == "APPLIED"]
    kept = list(priors)
    embed_cache: dict = {}
    decisions = []
    counts = Counter()
    for row in rows:
        if row["state"] != "PENDING":
            decisions.append({
                "proposal_id": row["proposal_id"], "real_state": row["state"],
                "verdict": "kept", "reason": "already-applied (historical, not re-adjudicated)",
            })
            continue
        proposal = row["proposal"]
        verdict = None
        if r2_enabled:
            verdict = dr.rule_r2_third_party_resource_error(proposal)
            if verdict:
                counts["r2_rejected"] += 1
        if verdict is None and r3_enabled:
            verdict = dr.rule_r3_resolution_redundant(
                proposal, embed_fn=embed_fn, threshold=r3_threshold,
            )
            if verdict:
                counts["r3_rejected"] += 1
        if verdict is None and r1_enabled:
            verdict = dr.rule_r1_semantic_duplicate(
                proposal, kept, embed_fn=embed_fn, threshold=r1_threshold,
                embed_cache=embed_cache,
            )
            if verdict:
                counts["r1_superseded"] += 1
        if verdict is None:
            counts["kept_pending"] += 1
            decisions.append({
                "proposal_id": row["proposal_id"], "real_state": row["state"],
                "verdict": "kept", "reason": None,
            })
            kept.append(row)
        else:
            state, reason = verdict
            decisions.append({
                "proposal_id": row["proposal_id"], "real_state": row["state"],
                "verdict": state, "reason": reason,
            })
    return decisions, counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--ollama-url", default=_ollama_url_default())
    ap.add_argument("--embed-model", default=_embed_model_default())
    ap.add_argument("--r1-threshold", type=float, default=dr.DIAGNOSIS_DUP_THRESHOLD_DEFAULT)
    ap.add_argument("--r3-threshold", type=float, default=dr.DIAGNOSIS_REDUNDANT_THRESHOLD_DEFAULT)
    ap.add_argument("--no-rule-r1", action="store_true")
    ap.add_argument("--no-rule-r2", action="store_true")
    ap.add_argument("--no-rule-r3", action="store_true")
    args = ap.parse_args(argv)

    cfg = argparse.Namespace(ollama_url=args.ollama_url, embed_model=args.embed_model)
    embed_fn = functools.partial(dream_runner.embed_text, cfg)

    rows = load_pending_and_applied_diagnoses(args.db)
    pending_before = sum(1 for r in rows if r["state"] == "PENDING")
    print(f"[dry-run] {len(rows)} diagnosis row(s) loaded from {args.db} "
          f"({pending_before} PENDING, {len(rows) - pending_before} APPLIED)")
    print(f"[dry-run] thresholds: r1={args.r1_threshold} r3={args.r3_threshold}  "
          f"rules enabled: r1={not args.no_rule_r1} r2={not args.no_rule_r2} "
          f"r3={not args.no_rule_r3}")

    decisions, counts = simulate(
        rows, embed_fn=embed_fn,
        r1_enabled=not args.no_rule_r1, r2_enabled=not args.no_rule_r2,
        r3_enabled=not args.no_rule_r3,
        r1_threshold=args.r1_threshold, r3_threshold=args.r3_threshold,
    )

    for d in decisions:
        if d["real_state"] != "PENDING":
            continue
        tag = d["verdict"] if d["verdict"] != "kept" else "PENDING (survives)"
        reason = f"  {d['reason']}" if d["reason"] else ""
        print(f"  {d['proposal_id']}  ->  {tag}{reason}")

    survivors = sum(1 for d in decisions if d["real_state"] == "PENDING" and d["verdict"] == "kept")
    print(f"[dry-run] {pending_before} PENDING -> {survivors} survivor(s) "
          f"(r1_superseded={counts['r1_superseded']} r2_rejected={counts['r2_rejected']} "
          f"r3_rejected={counts['r3_rejected']})")
    print("[dry-run] wrote nothing (read-only connection; no record_proposals call).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
