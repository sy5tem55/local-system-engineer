#!/usr/bin/env python3
"""
One-off migration for SPEC-gate-toil-2026-08's V3 gap: existing `diagnosis`
proposal rows were fingerprinted under the pre-fix, full-body formula.
traum_state.canonical_proposal now narrows `diagnosis` identity to
{type, call, args.error_text, args.context} (Sec5.2), but repeat_prior()
matches on the STORED `fingerprint` column -- a historical row's fingerprint
was computed and written before this fix existed, so it never collides with
a freshly-computed narrow fingerprint for the same semantic identity, even
though the identity is unchanged. Confirmed live 2026-08-09: a fresh
error-cluster run produced prp_597940d2, byte-identical on error_text+
context to an already-APPLIED lse-errors-1024 doc, and it stayed PENDING
instead of superseding, because the applied row's stored fingerprint was
still the old full-body hash.

Two-phase, dry-run-by-default, scoped to proposal_type='diagnosis' only
(same Hazard B scoping as the code fix -- no other proposal type is ever
touched by this script):

  Phase 1 -- RECOMPUTE: for every diagnosis row, recompute `fingerprint`
  from its stored payload_json using the current (narrow)
  traum_state.proposal_fingerprint(). No state changes in this phase --
  APPLIED/REJECTED/SUPERSEDED/etc. rows keep their state, they just become
  correctly matchable as `prior` candidates going forward.

  Phase 2 -- SUPERSEDE: walk all diagnosis rows ordered by created_at ASC.
  For each (new) fingerprint, the first row whose state is in
  repeat_prior's own matched-state set becomes the anchor/prior. Any LATER
  row with the same fingerprint that is CURRENTLY "STAGED" or "PENDING"
  gets flipped to SUPERSEDED -- exactly the condition
  TraumState.record_proposals' own repeat_prior branch uses at insert time
  (Sec5.3: reason names the prior's id and state). DEFERRED/APPLYING/
  terminal rows are left alone; this script does not invent a broader
  supersede condition than the code it is patching up after.

--dry-run (default): report what would change, write nothing.
--apply: perform the migration inside one transaction, after writing a
  timestamped .bak copy of the database next to it.

Usage:
    python3 scripts/backfill_diagnosis_fingerprints.py --db /opt/local-se/dreams/traum-state.db
    python3 scripts/backfill_diagnosis_fingerprints.py --db /opt/local-se/dreams/traum-state.db --apply
"""
import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import traum_state as ts  # noqa: E402

_REPEAT_ELIGIBLE_STATES = {
    "STAGED", "PENDING", "DEFERRED", "APPLYING", "APPLIED",
    "REJECTED", "SUPERSEDED", "APPLY_FAILED",
}


def _is_repeat_eligible(row) -> bool:
    if row["state"] in _REPEAT_ELIGIBLE_STATES:
        return True
    return row["state"] == "SYSTEM_REJECTED" and str(row["reason"] or "").startswith(
        ("malformed:", "noop:", "invariant:")
    )


def build_plan(rows):
    """rows: list of sqlite3.Row (proposal_id, fingerprint, payload_json,
    state, reason, created_at), ORDER BY created_at ASC. Returns
    (recompute_plan, supersede_plan)."""
    new_fp_by_id = {}
    recompute_plan = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        new_fp = ts.proposal_fingerprint(payload)
        new_fp_by_id[row["proposal_id"]] = new_fp
        if new_fp != row["fingerprint"]:
            recompute_plan.append((row["proposal_id"], row["fingerprint"], new_fp))

    by_id = {row["proposal_id"]: row for row in rows}
    anchors = {}
    supersede_plan = []
    for row in rows:
        new_fp = new_fp_by_id[row["proposal_id"]]
        anchor_id = anchors.get(new_fp)
        if anchor_id is None:
            if _is_repeat_eligible(row):
                anchors[new_fp] = row["proposal_id"]
            continue
        if row["proposal_id"] == anchor_id:
            continue
        if row["state"] in {"STAGED", "PENDING"}:
            anchor_row = by_id[anchor_id]
            supersede_plan.append((row["proposal_id"], anchor_id, anchor_row["state"]))
    return recompute_plan, supersede_plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT proposal_id, fingerprint, payload_json, state, reason, revision, "
        "created_at FROM proposals WHERE proposal_type='diagnosis' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()

    print(f"[backfill] {len(rows)} diagnosis proposal rows found in {args.db}")
    recompute_plan, supersede_plan = build_plan(rows)

    print(f"[backfill] {len(recompute_plan)} rows need fingerprint recompute:")
    for pid, old_fp, new_fp in recompute_plan:
        print(f"    {pid}: {old_fp[:12]}... -> {new_fp[:12]}...")

    print(f"[backfill] {len(supersede_plan)} rows would be superseded:")
    for pid, prior_id, prior_state in supersede_plan:
        print(f"    {pid} -> superseded by {prior_id} ({prior_state})")

    if not args.apply:
        print("[backfill] dry-run only -- pass --apply to write changes")
        return 0

    backup_path = (
        f"{args.db}.bak-gate-toil-backfill-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    shutil.copy2(args.db, backup_path)
    print(f"[backfill] backed up db to {backup_path}")

    store = ts.TraumState(args.db)
    with store._tx() as tx:
        for pid, _old_fp, new_fp in recompute_plan:
            tx.execute(
                "UPDATE proposals SET fingerprint=? WHERE proposal_id=?",
                (new_fp, pid),
            )
        now = ts.utc_now()
        for pid, prior_id, prior_state in supersede_plan:
            reason = f"exact_already_resolved_or_queued:{prior_id}:{prior_state}"
            tx.execute(
                "UPDATE proposals SET state='SUPERSEDED',revision=revision+1,"
                "reason=?,updated_at=? WHERE proposal_id=?",
                (reason, now, pid),
            )
            store._event(
                tx, "proposal", pid, "SUPERSEDED", "system",
                {"reason": reason, "migration": "gate-toil-backfill"},
            )
    print(
        f"[backfill] applied: {len(recompute_plan)} fingerprints recomputed, "
        f"{len(supersede_plan)} proposals superseded"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
