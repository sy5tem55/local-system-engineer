#!/usr/bin/env python3
"""
freeze_bench.py — create/verify an immutable benchmark set (e.g. lse-bench-v1).

A frozen bench is the fixed challenge set used for pre/post comparison
(Condition A baseline vs Condition B post-learning). ONLY challenges whose EVERY
assertion is verify_ssh-backed qualify, so every baseline number reflects real
world state, never model self-report.

The manifest bench/<name>.json pins each challenge id + a sha256 of its
success_criteria — reproducible and tamper-evident: if a challenge's criteria
change after freezing, --verify (and the bench runner) flag drift.

Usage:
  python3 scripts/freeze_bench.py --name lse-bench-v1           # create (refuses if exists)
  python3 scripts/freeze_bench.py --name lse-bench-v1 --verify  # DB vs manifest drift check
  python3 scripts/freeze_bench.py --name lse-bench-v1 --force   # re-freeze (new baseline needed)
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = "/opt/local-se/challenges.db"
BENCH_DIR = Path(__file__).parent.parent / "bench"


def _sha(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()


def _bench_validity(success_criteria_json: str, mode: str):
    """Return (ok, reason). A bench challenge must be ground-truth AND solvable:
      - has assertions, every one verify_ssh-backed (scores reflect the world,
        not model self-report);
      - if mode == 'write', it MUST carry an `actuation` block — otherwise the
        model cannot change the world and the challenge is a deterministic fail.
    """
    try:
        sc = json.loads(success_criteria_json or "{}")
    except Exception:
        return False, "success_criteria is not valid JSON"
    asserts = sc.get("assertions", [])
    if not asserts:
        return False, "no assertions"
    if not all(isinstance(a, dict) and "verify_ssh" in a for a in asserts):
        return False, "not all assertions verify_ssh-backed (self-report)"
    if mode == "write" and "actuation" not in sc:
        return False, "write-mode but no actuation block (unsolvable — model cannot act)"
    return True, "ok"


def select_challenges(db):
    rows = db.execute(
        "SELECT id, title, tier, mode, discipline_multiplier, success_criteria "
        "FROM challenges WHERE status='active' ORDER BY id"
    ).fetchall()
    selected, excluded = [], []
    for cid, title, tier, mode, mult, sc in rows:
        ok, reason = _bench_validity(sc, mode)
        if ok:
            selected.append({
                "id": cid, "title": title, "tier": tier,
                "discipline_multiplier": mult,
                "success_criteria_sha256": _sha(sc),
            })
        else:
            excluded.append((cid, reason))
    return selected, excluded


def main():
    ap = argparse.ArgumentParser(description="Freeze/verify a ground-truth benchmark set")
    ap.add_argument("--name", default="lse-bench-v1")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--verify", action="store_true", help="Check DB against an existing manifest")
    ap.add_argument("--force", action="store_true", help="Overwrite an existing frozen manifest")
    a = ap.parse_args()

    BENCH_DIR.mkdir(exist_ok=True)
    manifest_path = BENCH_DIR / f"{a.name}.json"

    db = sqlite3.connect(a.db)
    try:
        selected, excluded = select_challenges(db)
    finally:
        db.close()

    if not selected:
        print("No bench-valid challenges found — nothing qualifies for the frozen set.")
        print("A bench challenge needs all-verify_ssh assertions AND (if write-mode) an actuation block.")
        for cid, reason in excluded:
            print(f"  excluded {cid}: {reason}")
        sys.exit(1)

    if a.verify:
        if not manifest_path.exists():
            print(f"No manifest at {manifest_path} — create it first.")
            sys.exit(1)
        man = json.loads(manifest_path.read_text())
        cur = {c["id"]: c["success_criteria_sha256"] for c in selected}
        frozen_ids = {c["id"] for c in man["challenges"]}
        drift = []
        for c in man["challenges"]:
            now = cur.get(c["id"])
            if now is None:
                drift.append(f"{c['id']}: MISSING from DB")
            elif now != c["success_criteria_sha256"]:
                drift.append(f"{c['id']}: success_criteria CHANGED since freeze")
        new = sorted(set(cur) - frozen_ids)
        print(f"Manifest {a.name}: {len(man['challenges'])} frozen challenge(s)")
        print("DRIFT:\n  " + "\n  ".join(drift) if drift else "OK — all frozen challenges match the DB")
        if new:
            print(f"NOTE: {len(new)} new verify_ssh challenge(s) not in the freeze: {new}")
            print("  (re-freeze with --force to include them — that defines a new baseline)")
        sys.exit(1 if drift else 0)

    if manifest_path.exists() and not a.force:
        print(f"{manifest_path} already exists — a frozen set is immutable by design.")
        print("Use --verify to drift-check, or --force to re-freeze (requires a fresh baseline).")
        sys.exit(1)

    manifest = {
        "name": a.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_rule": "active challenges whose every assertion is verify_ssh-backed (ground-truth only)",
        "n_challenges": len(selected),
        "challenges": selected,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Froze {len(selected)} challenge(s) -> {manifest_path}")
    for c in selected:
        print(f"  {c['id']:18} T{c['tier']}  {c['title']}")
    if excluded:
        print(f"\nExcluded {len(excluded)} active challenge(s) — not bench-valid:")
        for cid, reason in excluded:
            print(f"  {cid:18} {reason}")


if __name__ == "__main__":
    main()
