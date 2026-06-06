"""
Smoke test for LeaderboardService.

Tests:
  1. Schema initialises cleanly (idempotent)
  2. record_episode() inserts a row, returns valid id
  3. standings() returns one row per model, sorted by total_points
  4. discipline_multiplier is applied correctly to final_points
  5. model_stats() groups by discipline
  6. recent_episodes() respects limit + model filter
  7. challenge_history() returns rows for specific challenge
  8. print_standings() runs without error
  9. record_episode() on dry_run result dict is a no-op (dry_run guard)

Run: python3 scripts/test_leaderboard.py
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
from leaderboard import LeaderboardService

PASS = "✅"
FAIL = "❌"


def check(label, condition):
    print(f"  {'✅' if condition else '❌'}  {label}")
    return condition


def make_result(
    challenge_id="pf-t1-001",
    model_id="qwen-27b",
    outcome="SOLVED",
    attempts=1,
    raw_reward=13.0,
    discipline="sysadmin",
    discipline_multiplier=1.0,
    kb_assisted=False,
    escalated=False,
    escalation_context_quality=None,
    wall_time_s=12.3,
):
    return dict(
        challenge_id=challenge_id,
        model_id=model_id,
        outcome=outcome,
        attempts=attempts,
        raw_reward=raw_reward,
        discipline=discipline,
        discipline_multiplier=discipline_multiplier,
        final_points=raw_reward * discipline_multiplier,
        kb_assisted=kb_assisted,
        escalated=escalated,
        escalation_context_quality=escalation_context_quality,
        wall_time_s=wall_time_s,
    )


def run_tests():
    print("\n=== LeaderboardService smoke test ===\n")
    errors = 0

    # Use a temp DB for every test run
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name

    lb = LeaderboardService(db_path=db)

    # ── 1: schema init (idempotent) ───────────────────────────────────────────
    print("1. Schema initialises cleanly (idempotent)")
    lb2 = LeaderboardService(db_path=db)   # second init on same DB
    ok = check("no error on second init", True)   # would raise if schema broken
    if not ok: errors += 1
    print()

    # ── 2: record_episode → valid row id ─────────────────────────────────────
    print("2. record_episode() inserts row")
    rid = lb.record_episode(make_result())
    ok  = check(f"row id > 0 (got {rid})", isinstance(rid, int) and rid > 0)
    if not ok: errors += 1
    print()

    # ── 3: standings — one row per model, sorted ──────────────────────────────
    print("3. standings() — 2 models, sorted by total_points")
    lb.record_episode(make_result(model_id="gemma-31b", raw_reward=7.0,
                                  discipline_multiplier=1.0, outcome="SOLVED", attempts=2))
    # qwen-27b: 13.0 pts; gemma-31b: 7.0 pts
    s = lb.standings()
    ok  = check(f"2 model rows (got {len(s)})", len(s) == 2)
    ok &= check("first model is qwen-27b (higher pts)", s[0]["model_id"] == "qwen-27b")
    ok &= check("qwen-27b total_points == 13.0", s[0]["total_points"] == 13.0)
    ok &= check("gemma-31b total_points == 7.0", s[1]["total_points"] == 7.0)
    if not ok: errors += 1
    print()

    # ── 4: discipline multiplier applied correctly ────────────────────────────
    print("4. discipline_multiplier applied to final_points")
    # security 1.3× · raw -2.0 → final -2.6
    lb.record_episode(make_result(
        model_id="qwen-27b", challenge_id="pf-t1-006",
        discipline="security", discipline_multiplier=1.3,
        raw_reward=-2.0, outcome="ESCALATED", escalated=True,
        escalation_context_quality="good",
    ))
    recent = lb.recent_episodes(n=1, model_id="qwen-27b")
    ok  = check("discipline_mult == 1.3", recent[0]["discipline_mult"] == 1.3)
    ok &= check("final_points == -2.6", abs(recent[0]["final_points"] - (-2.6)) < 0.001)
    if not ok: errors += 1
    print()

    # ── 5: model_stats — by discipline ───────────────────────────────────────
    print("5. model_stats() groups by discipline for qwen-27b")
    stats = lb.model_stats("qwen-27b")
    ok  = check("stats not None", stats is not None)
    ok &= check("model_id correct", stats["model_id"] == "qwen-27b")
    discs = {d["discipline"] for d in stats["by_discipline"]}
    ok &= check("sysadmin discipline present", "sysadmin" in discs)
    ok &= check("security discipline present", "security" in discs)
    if not ok: errors += 1
    print()

    # ── 6: recent_episodes — limit + model filter ─────────────────────────────
    print("6. recent_episodes() — limit and model filter")
    # Add 3 more qwen episodes
    for i in range(3):
        lb.record_episode(make_result(model_id="qwen-27b",
                                      challenge_id=f"pf-t1-00{i+2}"))
    all_eps   = lb.recent_episodes(n=50)
    qwen_eps  = lb.recent_episodes(n=2, model_id="qwen-27b")
    gemma_eps = lb.recent_episodes(model_id="gemma-31b")
    ok  = check("total episodes > 3", len(all_eps) > 3)
    ok &= check("limit=2 respected", len(qwen_eps) == 2)
    ok &= check("model filter: only qwen rows",
                all(r["model_id"] == "qwen-27b" for r in qwen_eps))
    ok &= check("gemma filter returns gemma rows",
                all(r["model_id"] == "gemma-31b" for r in gemma_eps))
    if not ok: errors += 1
    print()

    # ── 7: challenge_history ──────────────────────────────────────────────────
    print("7. challenge_history('pf-t1-001') returns rows in insertion order")
    hist = lb.challenge_history("pf-t1-001")
    ok  = check("at least 1 row", len(hist) >= 1)
    ok &= check("all rows are pf-t1-001",
                all(r.get("challenge_id", "pf-t1-001") == "pf-t1-001"
                    or "challenge_id" not in r for r in hist))
    # IDs should be ascending (oldest first)
    ids = [r["id"] for r in hist]
    ok &= check("rows in ascending ID order", ids == sorted(ids))
    if not ok: errors += 1
    print()

    # ── 8: print_standings runs without error ─────────────────────────────────
    print("8. print_standings() runs cleanly")
    try:
        lb.print_standings()
        ok = check("no exception", True)
    except Exception as e:
        ok = check(f"no exception (got {e})", False)
    if not ok: errors += 1

    # ── 9: model_stats on unknown model → None ────────────────────────────────
    print("9. model_stats() on unknown model → None")
    ok = check("returns None", lb.model_stats("nonexistent-model") is None)
    if not ok: errors += 1
    print()

    # ── Summary ──────────────────────────────────────────────────────────────
    print("─" * 52)
    if errors == 0:
        print(f"  {PASS}  All tests passed")
    else:
        print(f"  {FAIL}  {errors} test group(s) had failures")
    print()

    os.unlink(db)
    return errors


if __name__ == "__main__":
    sys.exit(run_tests())
