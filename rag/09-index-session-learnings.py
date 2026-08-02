#!/usr/bin/env python3
"""Index kb/session-learnings.md into lse-kb so the compound loop closes.

WHY THIS EXISTS (2026-08-02). The `lse-session-debrief` skill has been
appending hard-won findings to kb/session-learnings.md for months -- 34
entries, 1,300+ lines. Measured on 2026-08-02: that file was indexed into
lse-kb-1024 exactly ZERO times. Nothing read it back. It was write-only
memory, which is precisely the failure that writing lessons down is supposed
to prevent: every entry had to be rediscovered at full price.

This makes the file retrievable through search_kb, and is deliberately a
repeatable pipeline step rather than a one-off migration -- a one-off would
leave the loop broken again as soon as the next debrief is written. Re-run it
after any debrief.

CHUNKING. One document per `## Session` heading. Whole-file indexing would
return 1,300 lines for a question about one incident, which is useless at
retrieval time; per-entry chunking returns the incident that actually matches.

TRUST. source_tier="primary" (ceiling 0.8), quality 0.7. These are first-hand
observations measured on this system, but they are written up after the fact
by an agent, so they are deliberately NOT claimed as ground_truth (ceiling
1.0) -- that tier is reserved and should not be self-granted for post-hoc
narrative. origin="local-probe": the substance of these entries is command
output and live measurement.

IDEMPOTENCY. index_to_kb() updates rather than duplicates on cosine > 0.92,
so re-running is safe. --dry-run reports what would be indexed and touches
nothing.

OBSERVED ON FIRST RUN (2026-08-02): 34 entries -> 9 created, 25 "refined".
The refine path is index_to_kb's dedup (cosine > 0.92) updating an existing
near-duplicate's quality WITHOUT re-tagging its identity, so only the 9 newly
created docs carry topic="session-learnings" and a source_url back to this
file. The other 25 incidents are retrievable through their pre-existing docs.
Consequence: do NOT use `topic:session-learnings` as a coverage metric -- it
counts creations, not coverage.

Usage:
    python3 rag/09-index-session-learnings.py --dry-run
    python3 rag/09-index-session-learnings.py
    python3 rag/09-index-session-learnings.py --limit 1     # smoke test
"""
from __future__ import annotations

import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

LEARNINGS = os.path.join(REPO, "kb", "session-learnings.md")
ENTRY_RE = re.compile(r"^## Session .*$", re.M)


def split_entries(text: str) -> list[tuple[str, str]]:
    """[(heading, full entry text)] -- one per `## Session` block."""
    marks = list(ENTRY_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start():end].strip()
        heading = m.group(0).lstrip("#").strip()
        out.append((heading, body))
    return out


def slug(heading: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
    return s[:80]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0,
                    help="index at most N entries (0 = all); use 1 to smoke-test")
    args = ap.parse_args()

    if not os.path.isfile(LEARNINGS):
        print(f"ERROR: {LEARNINGS} not found")
        return 2

    entries = split_entries(open(LEARNINGS, encoding="utf-8").read())
    if not entries:
        print("ERROR: no '## Session' entries found -- has the file format changed?")
        return 2

    if args.limit:
        entries = entries[:args.limit]

    print(f"{len(entries)} entr{'y' if len(entries)==1 else 'ies'} to index "
          f"from {LEARNINGS}")

    if args.dry_run:
        for heading, body in entries:
            print(f"  [dry-run] {len(body):6d} chars  {heading[:78]}")
        print("\nnothing was written (--dry-run)")
        return 0

    import goethe  # noqa: PLC0415
    tools = goethe.Tools()

    ok = failed = 0
    for heading, body in entries:
        try:
            res = tools.index_to_kb(
                content=body,
                title=heading,
                topic="session-learnings",
                source_url=f"kb/session-learnings.md#{slug(heading)}",
                quality_score=0.7,
                source_tier="primary",
                volatility="slow",
                origin="local-probe",
                evidence="post-session debrief; findings measured live on LUCIFER",
            )
            ok += 1
            print(f"  OK   {heading[:70]}\n       -> {str(res)[:110]}")
        except Exception as exc:  # noqa: BLE001 -- report and continue
            failed += 1
            print(f"  FAIL {heading[:70]}\n       -> {type(exc).__name__}: {exc}")

    print(f"\nindexed={ok} failed={failed} of {len(entries)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
