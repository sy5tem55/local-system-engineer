#!/usr/bin/env python3
"""dataset_lint.py — DATA-2 (2026-07-18): lint gold/eval JSONL datasets.

Rules (per ROADMAP Workstream D):
  1. Schema: every row needs id, query, expected (non-empty list), topic,
     provenance. Unattributed rows are REJECTED — same rule as skill_record.
  2. Duplicate-query detection (case/whitespace-normalized).
  3. Expected-file existence: every file in expected[] must exist in kb/.
  4. Duplicate ids rejected.

Exit 0 = clean, 1 = findings (line-numbered, machine-grepable "LINT-FAIL").
Wired into run_tests scope="data" and scope="all" (PROVE-1).

Usage:
  python3 scripts/dataset_lint.py                       # default: v2 gold set
  python3 scripts/dataset_lint.py eval/foo.jsonl [...]  # explicit files
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KB_DIR = REPO / "kb"
DEFAULT = [REPO / "eval" / "retrieval-gold-v2.jsonl"]
REQUIRED = ("id", "query", "expected", "topic", "provenance")


def lint(path: Path) -> list:
    findings = []
    if not path.exists():
        return [f"LINT-FAIL {path}: file does not exist"]
    seen_q, seen_id = {}, {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            findings.append(f"LINT-FAIL {path}:{n}: invalid JSON ({e})")
            continue
        for f in REQUIRED:
            if f not in row or row[f] in ("", [], None):
                findings.append(
                    f"LINT-FAIL {path}:{n}: missing/empty required field '{f}'"
                    + (" — unattributed rows are rejected" if f == "provenance" else "")
                )
        exp = row.get("expected")
        if isinstance(exp, list):
            for fname in exp:
                if not (KB_DIR / fname).exists():
                    findings.append(
                        f"LINT-FAIL {path}:{n}: expected file kb/{fname} does not exist"
                    )
        elif exp is not None:
            findings.append(f"LINT-FAIL {path}:{n}: 'expected' must be a list")
        q = " ".join(str(row.get("query", "")).lower().split())
        if q and q in seen_q:
            findings.append(
                f"LINT-FAIL {path}:{n}: duplicate query (first at line {seen_q[q]})"
            )
        seen_q.setdefault(q, n)
        rid = row.get("id")
        if rid and rid in seen_id:
            findings.append(
                f"LINT-FAIL {path}:{n}: duplicate id '{rid}' (first at line {seen_id[rid]})"
            )
        seen_id.setdefault(rid, n)
    return findings


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]] or DEFAULT
    all_findings = []
    total_rows = 0
    for p in paths:
        if p.exists():
            total_rows += sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
        all_findings += lint(p)
    if all_findings:
        print("\n".join(all_findings))
        print(f"dataset_lint: {len(all_findings)} finding(s) in {len(paths)} file(s)")
        return 1
    print(f"dataset_lint: OK — {total_rows} rows across {len(paths)} file(s), 0 findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
