#!/usr/bin/env python3
"""Verify an implementer's handover claims against the live repository.

WHY THIS EXISTS (2026-08-02). The return leg of a handover used to be the
operator pasting an implementer's prose summary back into the reviewing
thread. That is manual work for the operator, lossy for the reviewer (who
still has to read the real artifacts), and it creates a trust surface: the
reviewer ends up verifying claims ABOUT claims.

The reviewer has direct access to the repo. So the return leg should be a
POINTER -- "done <commit>" -- and everything else should be checked, not
recounted.

This script does the mechanical half of that check. It reads the ACCEPTANCE
block from a handover report and tests each assertion against reality:
does the commit exist, did exactly those files change, does the suite
actually report that number at that commit, is ruff clean on the new files.

It does NOT replace judgement. It cannot tell you whether the design is
right, whether a guard is narrow enough, or whether a "regression" is
actually the intended fix -- all things that mattered on this project. It
clears the mechanical claims so a human or a reviewing model spends its
attention on the parts that need it.

ACCEPTANCE BLOCK FORMAT -- put this at the end of the report:

    <!-- ACCEPTANCE
    task: node-facts
    commit: 24391cb
    tests_before: 728
    tests_after: 743
    files_changed: tools/node_facts.py, tests/test_node_facts.py
    ruff_clean: tools/node_facts.py, tests/test_node_facts.py
    runtime_verified: true
    -->

Usage:
    python3 scripts/verify-handover.py docs/reports/2026-08-02-node-facts.md
    python3 scripts/verify-handover.py <report> --run-tests   # slow, authoritative
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCK_RE = re.compile(r"<!--\s*ACCEPTANCE(.*?)-->", re.S)


def sh(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def parse_block(path: str) -> dict:
    m = BLOCK_RE.search(open(path, encoding="utf-8").read())
    if not m:
        raise SystemExit(f"no ACCEPTANCE block found in {path}")
    out = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def as_list(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--run-tests", action="store_true",
                    help="actually run the suite (slow; otherwise the count is UNVERIFIED)")
    args = ap.parse_args()

    claims = parse_block(args.report)
    results: list[tuple[str, bool | None, str]] = []

    def check(name, ok, detail):
        results.append((name, ok, detail))

    # --- commit exists -----------------------------------------------------
    commit = claims.get("commit", "")
    if commit:
        rc, out = sh(["git", "rev-parse", "--verify", f"{commit}^{{commit}}"])
        check("commit exists", rc == 0, out.splitlines()[0] if out else "")
    else:
        check("commit exists", None, "no commit claimed")

    # --- files changed matches the commit ----------------------------------
    if commit and claims.get("files_changed"):
        rc, out = sh(["git", "show", "--name-only", "--format=", commit])
        actual = {l.strip() for l in out.splitlines() if l.strip()}
        claimed = set(as_list(claims["files_changed"]))
        missing, extra = claimed - actual, actual - claimed
        ok = not missing and not extra
        detail = ""
        if missing:
            detail += f"claimed but not in commit: {sorted(missing)} "
        if extra:
            detail += f"in commit but not claimed: {sorted(extra)}"
        check("files_changed matches commit", ok, detail or f"{len(actual)} file(s)")

    # --- working tree clean ------------------------------------------------
    rc, out = sh(["git", "status", "--porcelain"])
    check("working tree clean", out == "", out[:160] or "clean")

    # --- ruff clean on the named files -------------------------------------
    if claims.get("ruff_clean"):
        files = as_list(claims["ruff_clean"])
        missing = [f for f in files if not os.path.exists(os.path.join(REPO, f))]
        if missing:
            check("ruff_clean files exist", False, f"missing: {missing}")
        else:
            rc, out = sh(["/home/sy5/miniforge3/bin/ruff", "check", *files])
            check("ruff clean on claimed files", rc == 0, out.splitlines()[-1] if out else "clean")

    # --- test count --------------------------------------------------------
    claimed_after = claims.get("tests_after")
    if claimed_after and args.run_tests:
        rc, out = sh(["/home/sy5/owui/bin/python3", "-m", "pytest", "tests/", "-q"])
        m = re.search(r"(\d+) passed", out)
        actual = m.group(1) if m else "?"
        check(f"suite reports {claimed_after} passed", actual == claimed_after,
              f"actual: {actual} passed")
    elif claimed_after:
        check(f"suite reports {claimed_after} passed", None,
              "UNVERIFIED -- re-run with --run-tests")

    # --- report ------------------------------------------------------------
    width = max(len(n) for n, _, _ in results) + 2
    print(f"handover verification: {args.report}")
    print("-" * (width + 46))
    failed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
        if ok is False:
            failed += 1
        print(f"  {name:<{width}} {mark:5} {detail[:70]}")
    print()
    print(f"{failed} mechanical claim(s) failed.")
    if claims.get("runtime_verified", "").lower() not in ("true", "yes"):
        print("NOTE: runtime_verified is not true -- treat behavioural claims as "
              "test-only evidence.")
    print("This checks mechanical claims only. Design correctness, guard "
          "narrowness and\nhazard handling still need a reviewer.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
