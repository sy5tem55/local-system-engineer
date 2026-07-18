#!/usr/bin/env python3
"""harvest_gold.py — DATA-1 (2026-07-18): self-harvest gold-set candidates
from the LSE's own telemetry (no HF/Kaggle, ever).

Mines the episode journal ($GOETHE_EPISODE_DIR, default /opt/local-se/episodes)
for real `search_kb` failures — every NO-RESULTS miss becomes a CANDIDATE gold
row with full provenance (session file + timestamp). Candidates land in
eval/retrieval-gold-v2-candidates.jsonl for HUMAN labeling: a candidate is
promoted into eval/retrieval-gold-v2.jsonl only after a human fills expected[]
with the kb/ doc(s) that SHOULD have answered — auto-labeling would poison the
gold set (a miss for content the KB legitimately lacks is a KB gap, not a
retrieval failure; those belong in a "to index" list, not the gold set).

Re-runnable: dedupes against queries already in the gold set AND already in
the candidates file, so the nightly/weekly loop only surfaces NEW misses.
"""

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EPISODES = Path(os.environ.get("GOETHE_EPISODE_DIR", "/opt/local-se/episodes"))
GOLD = REPO / "eval" / "retrieval-gold-v2.jsonl"
CANDIDATES = REPO / "eval" / "retrieval-gold-v2-candidates.jsonl"


def norm(q: str) -> str:
    return " ".join(q.lower().split())


def existing_queries() -> set:
    seen = set()
    for path in (GOLD, CANDIDATES):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        seen.add(norm(json.loads(line).get("query", "")))
                    except json.JSONDecodeError:
                        pass
    return seen


def main() -> int:
    seen = existing_queries()
    new = []
    for jf in sorted(EPISODES.glob("*/*.jsonl")):
        for line in jf.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            if j.get("tool") != "search_kb":
                continue
            res = str(j.get("result_truncated", ""))
            if "no results" not in res.lower():
                continue
            q = str((j.get("args_redacted") or {}).get("query", "")).strip()
            if not q or norm(q) in seen:
                continue
            seen.add(norm(q))
            new.append(
                {
                    "id": f"cand-{j.get('ts', '')[:10]}-{len(seen):04d}",
                    "query": q,
                    "expected": [],  # HUMAN: fill with kb/ doc(s), then promote
                    "topic": "",
                    "provenance": f"episode {jf.parent.name}/{jf.name} ts={j.get('ts', '')}",
                    "status": "needs-label",
                }
            )
    if new:
        with open(CANDIDATES, "a", encoding="utf-8") as f:
            for row in new:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"harvest_gold: {len(new)} new candidate(s) appended to {CANDIDATES.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
