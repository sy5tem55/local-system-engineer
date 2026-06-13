#!/usr/bin/env python3
"""
run_episode.py — Run a single LSE Challenge Arena episode.

Full stack:
  LSEChallengeEnv
    └─ EscalationWrapper
        └─ TimeLimit(max_episode_steps=3)
            └─ RecordEpisodeStatistics

Usage (from LUCIFER WSL2 project root):
    python3 scripts/run_episode.py --list
    python3 scripts/run_episode.py --challenge pf-t1-001 --dry-run
    python3 scripts/run_episode.py --challenge pf-t1-001
    python3 scripts/run_episode.py --challenge pf-t1-001 --model gemma-31b --endpoint http://192.168.1.NODE2:8080/v1/chat/completions
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from gymnasium.wrappers import TimeLimit, RecordEpisodeStatistics

sys.path.insert(0, str(Path(__file__).parent))
from lse_challenge_env import LSEChallengeEnv, _extract_json
from escalation_wrapper import EscalationWrapper
from leaderboard import LeaderboardService
from challenge_generator import ChallengeGenerator

# ── Defaults ──────────────────────────────────────────────────────────────────

DB_PATH        = "/opt/local-se/challenges.db"
LEADERBOARD_DB = "/opt/local-se/leaderboard.db"
MODEL_ENDPOINT = "http://localhost:8080/v1/chat/completions"
MODEL_ID       = "qwen3.6-27b-q4-64k"
# Match active profile: Qwen3.6 27B Q4_K_M · 64k · KV:q8_0 · think:3072
MAX_TOKENS     = 8192
TEMPERATURE    = 0.65

SYSTEM_PROMPT = (
    "You are a system administrator solving an infrastructure challenge on a real network.\n"
    "Read the challenge carefully. Use your knowledge of pfSense, Home Assistant, Linux, "
    "nmap, and networking.\n"
    "When you have gathered and reasoned through all required information, "
    "return your findings as a ```json code block using the EXACT key names "
    "listed in the OUTPUT FORMAT section. Do not add extra keys or rename them.\n"
    "Think step by step before producing the JSON block."
)


# ── Stack builder ─────────────────────────────────────────────────────────────

def build_env(db_path=DB_PATH, model_endpoint=MODEL_ENDPOINT, verbose=True, learn=True):
    base    = LSEChallengeEnv(db_path=db_path, model_endpoint=model_endpoint)
    wrapped = EscalationWrapper(base, verbose=verbose, learn=learn)
    wrapped = TimeLimit(wrapped, max_episode_steps=3)
    wrapped = RecordEpisodeStatistics(wrapped)
    return wrapped


# ── Model caller ──────────────────────────────────────────────────────────────

def call_model(obs, model_endpoint=MODEL_ENDPOINT, temperature=TEMPERATURE, use_thinking=False):
    parts = [obs["challenge"]]
    if obs.get("attempt_history"):
        parts.append("\n\nYOUR PRIOR ATTEMPTS:\n" + obs["attempt_history"])
    if obs.get("kb_context"):
        parts.append("\n\nCONTEXT (KB hit / web result):\n" + obs["kb_context"])

    payload = {
        "model":       "local",
        "messages":    [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": "\n".join(parts)},
        ],
        "max_tokens":  MAX_TOKENS,
        "temperature": temperature,
        "stream":      False,
    }
    if use_thinking:
        payload["chat_template_kwargs"] = {"thinking": True}

    try:
        resp = requests.post(model_endpoint, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return '```json\n{"error": "model_timeout"}\n```'
    except Exception as e:
        print(f"  [model] call failed: {e}")
        return '```json\n{"error": "call_failed"}\n```'


# ── Episode runner ────────────────────────────────────────────────────────────

def run_episode(challenge_id, model_id=MODEL_ID, model_endpoint=MODEL_ENDPOINT,
                db_path=DB_PATH, verbose=True, dry_run=False, learn=True):
    env = build_env(db_path=db_path, model_endpoint=model_endpoint, verbose=verbose, learn=learn)
    obs, info = env.reset(options={"challenge_id": challenge_id, "model_id": model_id})

    if dry_run:
        _print_separator("CHALLENGE PROMPT — dry run, no model call")
        print(obs["challenge"])
        env.close()
        return {"dry_run": True, "challenge_id": info.get("challenge_id", challenge_id)}

    cid  = info.get("challenge_id", challenge_id or "?")
    disc = info.get("discipline", "sysadmin")
    mult = info.get("discipline_multiplier", 1.0)

    _print_separator(f"Episode: {cid}  |  Model: {model_id}  |  {disc} {mult}×")
    if not learn:
        print("  [EVAL MODE] learning disabled — no leaderboard write, no challenge generation")

    terminated = truncated = False
    step_n     = 0
    t_start    = time.time()
    last_response = ""

    while not (terminated or truncated):
        step_n += 1
        use_thinking = "STAGNATION DETECTED" in obs.get("challenge", "")
        temp = 0.95 if use_thinking else TEMPERATURE
        mode_label = "thinking=ON, temp=0.95" if use_thinking else f"temp={temp}"
        print(f"  → Attempt {step_n}  [{mode_label}]  ...", flush=True)

        t0           = time.monotonic()
        response     = call_model(obs, model_endpoint, temperature=temp, use_thinking=use_thinking)
        last_response = response
        elapsed      = time.monotonic() - t0

        _print_response_summary(response, elapsed)
        obs, reward, terminated, truncated, info = env.step(response)
        _print_assertion_results(info, reward)

        if info.get("web_assist"):
            print("     ↳ Web search injected — one more attempt")
        if info.get("escalated"):
            print("     ↳ ESCALATED to Claude API")
        print()

    ep      = info.get("episode", {})
    outcome = _outcome_label(terminated, info)
    raw     = float(ep.get("r", reward))
    points  = raw * mult
    wall    = time.time() - t_start

    _print_separator(f"OUTCOME: {outcome}")
    print(f"  Attempts:    {step_n}")
    print(f"  Raw reward:  {raw:.1f}")
    print(f"  Multiplier:  {mult}×  ({disc})")
    print(f"  Points:      {points:.1f}")
    print(f"  Wall time:   {wall:.1f}s")
    print(f"  KB assisted: {info.get('kb_assisted', False)}")
    print(f"  Escalated:   {info.get('escalated', False)}")
    if info.get("escalated"):
        print(f"  Esc. quality:{info.get('escalation_context_quality', 'unknown')}")
    print()

    env.close()

    result = {
        "challenge_id":               cid,
        "model_id":                   model_id,
        "outcome":                    outcome,
        "attempts":                   step_n,
        "raw_reward":                 raw,
        "discipline":                 disc,
        "discipline_multiplier":      mult,
        "final_points":               points,
        "kb_assisted":                info.get("kb_assisted", False),
        "escalated":                  info.get("escalated", False),
        "escalation_context_quality": info.get("escalation_context_quality"),
        "wall_time_s":                round(wall, 1),
    }

    # Auto-record to leaderboard (skipped in --no-learn / --eval mode)
    if learn:
        try:
            lb = LeaderboardService(db_path=db_path.replace("challenges.db", "leaderboard.db"))
            lb_episode_id = lb.record_episode(result)
            result["leaderboard_episode_id"] = lb_episode_id
            if verbose:
                print(f"  Leaderboard: episode #{lb_episode_id} recorded → {lb.db_path}")
                lb.print_standings()
        except Exception as e:
            if verbose:
                print(f"  Leaderboard write failed (non-fatal): {e}")
    elif verbose:
        result["learning"] = "disabled"
        print("  Leaderboard: skipped (eval mode)")

    # ChallengeGenerator — propose follow-up challenges from discoveries
    if learn and result.get("outcome") == "SOLVED" and last_response:
        try:
            last_json = _extract_json(last_response)
            if last_json:
                gen = ChallengeGenerator(db_path=db_path)
                proposed = gen.process_episode(result, last_json, verbose=verbose)
                if proposed and verbose:
                    print(f"  [{len(proposed)} challenge(s) proposed → pending_review]")
                    print(f"  Review: python3 scripts/challenge_generator.py --list-pending")
        except Exception as e:
            if verbose:
                print(f"  ChallengeGenerator failed (non-fatal): {e}")

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _outcome_label(terminated, info):
    if info.get("escalated"):
        return "ESCALATED"
    if terminated:
        return "SOLVED"
    return "TRUNCATED"


def _print_separator(label=""):
    w = 62
    print(f"\n{'─'*w}")
    if label:
        print(f"  {label}")
        print(f"{'─'*w}")


def _print_response_summary(response, elapsed):
    print(f"     {elapsed:.1f}s | {len(response)} chars")
    m = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            parsed = json.loads(m.group(1))
            preview = {k: (str(v)[:40] if not isinstance(v, (list, dict))
                           else f"[{len(v)} items]" if isinstance(v, list)
                           else "{...}") for k, v in list(parsed.items())[:4]}
            print(f"     JSON: {preview}")
        except json.JSONDecodeError:
            print("     JSON block present but not parseable")
    else:
        snippet = response.replace("\n", " ")[:120]
        print(f"     No JSON block — response starts: {snippet!r}")


def _print_assertion_results(info, reward):
    results = info.get("assertion_results", [])
    passed  = sum(1 for r in results if r["passed"])
    print(f"     Assertions: {passed}/{len(results)}  |  reward: {reward:+.1f}")
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        desc = r.get("description", "")[:55]
        err  = f"  ← {r['error']}" if r.get("error") else ""
        print(f"       {icon} [{r['id']}] {desc}{err}")


def list_challenges(db_path=DB_PATH):
    env = LSEChallengeEnv(db_path=db_path)
    rows = env.list_challenges()
    print(f"\n  {'ID':<16} {'Discipline':<14} {'Mult':>5}  {'Domain':<15}  Title")
    print(f"  {'─'*16} {'─'*14} {'─'*5}  {'─'*15}  {'─'*30}")
    for c in rows:
        print(f"  {c['id']:<16} {c['discipline']:<14} {c['discipline_multiplier']:>5}  "
              f"{c['domain']:<15}  {c['title']}")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def run_bench(name, db_path=DB_PATH, model_id=MODEL_ID,
              model_endpoint=MODEL_ENDPOINT, verbose=True):
    """Run a frozen benchmark set in eval mode → write a Condition A report.

    Loads bench/<name>.json (from freeze_bench.py), runs every challenge with
    learning OFF (--eval semantics: no leaderboard, no KB writes), drift-checks
    each challenge's success_criteria against the frozen sha256, and writes a
    per-challenge solved/not + points report under bench/reports/. This is the
    Condition A baseline; Condition B is the same set re-run post-learning, and
    McNemar's paired test reads the two.
    """
    import hashlib  # noqa: PLC0415
    import sqlite3  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    bench_dir = Path(__file__).parent.parent / "bench"
    manifest_path = bench_dir / f"{name}.json"
    if not manifest_path.exists():
        print(f"No manifest at {manifest_path} — run: python3 scripts/freeze_bench.py --name {name}")
        return None

    manifest = json.loads(manifest_path.read_text())
    challenges = manifest.get("challenges", [])
    _print_separator(
        f"BENCH {name} — Condition A (eval, learning OFF) — {len(challenges)} challenge(s)"
    )

    # Drift check: frozen sha256 vs current DB
    con = sqlite3.connect(db_path)
    drift = []
    try:
        for c in challenges:
            row = con.execute(
                "SELECT success_criteria FROM challenges WHERE id=?", (c["id"],)
            ).fetchone()
            if not row:
                drift.append(f"{c['id']}: MISSING from DB")
            elif hashlib.sha256((row[0] or "").encode()).hexdigest() != c["success_criteria_sha256"]:
                drift.append(f"{c['id']}: success_criteria CHANGED since freeze")
    finally:
        con.close()
    if drift:
        print("  ⚠ FROZEN-SET DRIFT — baseline only valid against the frozen criteria:")
        for d in drift:
            print(f"      {d}")
        print("  Re-freeze (freeze_bench.py --force) as a NEW version if the change is intended.\n")

    results = []
    for c in challenges:
        r = run_episode(c["id"], model_id=model_id, model_endpoint=model_endpoint,
                        db_path=db_path, verbose=verbose, learn=False)
        results.append(r)

    solved = [r for r in results if r.get("outcome") == "SOLVED"]
    total_points = sum(float(r.get("final_points", 0) or 0) for r in results)
    report = {
        "bench": name,
        "condition": "A (baseline — learning disabled)",
        "model_id": model_id,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "n_challenges": len(results),
        "n_solved": len(solved),
        "total_points": round(total_points, 1),
        "frozen_set_drift": drift,
        "per_challenge": [
            {"id": r.get("challenge_id"), "outcome": r.get("outcome"),
             "attempts": r.get("attempts"), "points": r.get("final_points")}
            for r in results
        ],
    }
    reports_dir = bench_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = reports_dir / f"{name}-conditionA-{model_id}-{ts}.json"
    out.write_text(json.dumps(report, indent=2))

    _print_separator(f"BENCH RESULT — {name} Condition A")
    print(f"  Solved: {len(solved)}/{len(results)}   Points: {total_points:.1f}"
          + ("   [DRIFT — see above]" if drift else ""))
    for r in results:
        ic = "✅" if r.get("outcome") == "SOLVED" else "❌"
        print(f"   {ic} {str(r.get('challenge_id')):18} {str(r.get('outcome')):10} "
              f"{float(r.get('final_points', 0) or 0):.1f} pts")
    print(f"\n  Report: {out}")
    return report


def main():
    p = argparse.ArgumentParser(
        description="Run one LSE Challenge Arena episode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/run_episode.py --list
  python3 scripts/run_episode.py --challenge pf-t1-001 --dry-run
  python3 scripts/run_episode.py --challenge pf-t1-001
  python3 scripts/run_episode.py --challenge pf-t1-006 --model gemma-31b \\
      --endpoint http://192.168.1.NODE2:8080/v1/chat/completions
""",
    )
    p.add_argument("--challenge", "-c", default=None,
                   help="Challenge ID (e.g. pf-t1-001). Default: first T1 challenge.")
    p.add_argument("--model", "-m", default=MODEL_ID,
                   help=f"Model identifier label (default: {MODEL_ID})")
    p.add_argument("--endpoint", "-e", default=MODEL_ENDPOINT,
                   help=f"Model HTTP endpoint (default: {MODEL_ENDPOINT})")
    p.add_argument("--db", default=DB_PATH,
                   help=f"ChallengeDB path (default: {DB_PATH})")
    p.add_argument("--list", "-l", action="store_true",
                   help="List all challenges and exit")
    p.add_argument("--dry-run", action="store_true",
                   help="Print challenge prompt only, do not call model")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="Suppress EscalationWrapper verbose logs")
    p.add_argument("--json", action="store_true",
                   help="Print result as JSON (useful for scripting)")
    p.add_argument("--no-learn", action="store_true",
                   help="Do not record to leaderboard or generate challenges (eval-safe)")
    p.add_argument("--eval", action="store_true",
                   help="Evaluation mode: implies --no-learn (frozen benchmark runs)")
    p.add_argument("--bench", default=None,
                   help="Run a frozen set (e.g. lse-bench-v1) in eval mode → Condition A report")
    args = p.parse_args()

    if args.list:
        list_challenges(args.db)
        return

    if args.bench:
        run_bench(args.bench, db_path=args.db, model_id=args.model,
                  model_endpoint=args.endpoint, verbose=not args.quiet)
        return

    result = run_episode(
        challenge_id   = args.challenge,
        model_id       = args.model,
        model_endpoint = args.endpoint,
        db_path        = args.db,
        verbose        = not args.quiet,
        dry_run        = args.dry_run,
        learn          = not (args.no_learn or args.eval),
    )

    if args.json or result.get("dry_run"):
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
