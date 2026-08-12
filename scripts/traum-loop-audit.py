#!/usr/bin/env python3
"""scripts/traum-loop-audit.py — ground truth: is the TRAUM feedback loop alive?

Roadmap item 2 (docs/ROADMAP-2026-08.md) went five days stale because nobody
re-measured it between sessions. This script is that re-measurement, made
runnable instead of remembered. It is NOT an LLM pass — it is four cheap,
deterministic checks against ground truth, shaped like
`lse-stack-health-check`: a status table, a verdict per row, an explicit
recovery pointer when a row is red. An LLM layer that *interprets* these
numbers is a later, separate step (see docs/ROADMAP-2026-08.md item 2) —
this script only measures.

FOUR QUESTIONS, EACH FROM A DIFFERENT GROUND-TRUTH SOURCE
  1. Are skills being retrieved?        skill_search calls in recent episodes
  2. Are outcomes being recorded?       skill_outcome calls in recent episodes,
                                         split into attempted / succeeded /
                                         errored (the split that mattered in
                                         docs/reports/2026-08-12-skill-feedback-loop-fork.md
                                         — a tool that fires but always errors
                                         looks identical to "never called" if
                                         you only count attempts)
  3. Is the applied KB being consulted? search_kb calls in recent episodes
  4. Is the dream loop completing?      traum-state.db runs + attempts,
                                         most recent run's pass completion

READ-ONLY, ALWAYS
  traum-state.db is opened via `file:...?mode=ro` (AGENTS.md: never open it
  any other way). Episode files are opened for read only. lse-skills is
  queried via ES _search/_count only — no write, no update, no delete.

USAGE
    python3 scripts/traum-loop-audit.py
    python3 scripts/traum-loop-audit.py --lookback-days 7 --json
    python3 scripts/traum-loop-audit.py --episode-dir /tmp/some-episodes \\
        --traum-db /path/to/a/copy/of/traum-state.db
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sqlite3
import urllib.request
from datetime import datetime, timedelta, timezone

DAY_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _episode_dir_default() -> str:
    return os.environ.get("GOETHE_EPISODE_DIR", "/opt/local-se/episodes")


def _traum_db_default() -> str:
    return "/opt/local-se/dreams/traum-state.db"


def _es_url_default() -> str:
    return os.environ.get("GOETHE_ES_URL", "http://127.0.0.1:9200")


def _open_session_file(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "rt", encoding="utf-8")


def _day_dirs_since(episode_dir: str, since_date) -> list:
    """Day-dirs (YYYY-MM-DD) at or after since_date, sorted. String comparison
    is correct here because the format is fixed-width zero-padded."""
    if not os.path.isdir(episode_dir):
        return []
    since_str = since_date.strftime("%Y-%m-%d")
    out = []
    for name in sorted(os.listdir(episode_dir)):
        if DAY_DIR_RE.match(name) and name >= since_str:
            full = os.path.join(episode_dir, name)
            if os.path.isdir(full):
                out.append(full)
    return out


def iter_recent_tool_calls(episode_dir: str, since_days: int, now=None):
    """Yield parsed tool-call dicts (one per journaled line) from every
    session file under a day-dir at or after `now - since_days`.

    Malformed lines are skipped (partial writes from a concurrently-
    appending gateway) — same tolerance as episode_index.parse_session_file,
    duplicated here rather than imported so this script has zero import-time
    dependency on tools/ (it must keep working even if dream_runner.py or
    episode_index.py won't import, since it exists to catch exactly that
    kind of breakage).
    """
    now = now or datetime.now(timezone.utc)
    since_date = (now - timedelta(days=since_days)).date()
    for day_dir in _day_dirs_since(episode_dir, since_date):
        for name in sorted(os.listdir(day_dir)):
            if not (name.endswith(".jsonl") or name.endswith(".jsonl.gz")):
                continue
            path = os.path.join(day_dir, name)
            try:
                with _open_session_file(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(obj, dict):
                            yield obj
            except OSError:
                continue


def check_skill_retrieval(episode_dir: str, since_days: int, now=None) -> dict:
    """Q1 — are skills being retrieved at all."""
    calls = [c for c in iter_recent_tool_calls(episode_dir, since_days, now)
             if c.get("tool") == "skill_search"]
    return {
        "question": "are skills being retrieved?",
        "metric": "skill_search calls",
        "count": len(calls),
        "ok": len(calls) > 0,
        "last_ts": max((c.get("ts") for c in calls), default=None),
    }


def check_outcome_recording(episode_dir: str, since_days: int, now=None) -> dict:
    """Q2 — are outcomes being recorded, and if calls happen, do they land.

    The split matters: 0 attempts and 0 successes look identical from the
    lse-skills index alone (see docs/reports/2026-08-12-skill-feedback-loop-fork.md)
    but mean completely different things — one is "nothing calls it", the
    other is "it's called and silently failing". Report both.
    """
    calls = [c for c in iter_recent_tool_calls(episode_dir, since_days, now)
             if c.get("tool") == "skill_outcome"]
    succeeded = [c for c in calls
                 if "SKILL outcome recorded" in (c.get("result_truncated") or "")]
    errored = [c for c in calls
               if "SKILL outcome error" in (c.get("result_truncated") or "")
               or "SKILL outcome rejected" in (c.get("result_truncated") or "")]
    return {
        "question": "are outcomes being recorded?",
        "metric": "skill_outcome calls",
        "attempted": len(calls),
        "succeeded": len(succeeded),
        "errored": len(errored),
        # ok only when at least one attempt in-window actually landed —
        # "it was called" is not the bar, "it wrote" is.
        "ok": len(succeeded) > 0,
        "last_error": (errored[-1].get("result_truncated") if errored else None),
    }


def check_kb_consultation(episode_dir: str, since_days: int, now=None) -> dict:
    """Q3 — is the applied KB being consulted (search_kb calls)."""
    calls = [c for c in iter_recent_tool_calls(episode_dir, since_days, now)
             if c.get("tool") == "search_kb"]
    return {
        "question": "is the applied KB being consulted?",
        "metric": "search_kb calls",
        "count": len(calls),
        "ok": len(calls) > 0,
        "last_ts": max((c.get("ts") for c in calls), default=None),
    }


def check_dream_loop_completion(traum_db_path: str, since_days: int, now=None) -> dict:
    """Q4 — is the dream loop completing (traum-state.db runs + attempts).

    Opened strictly read-only (file:...?mode=ro) — a bug here structurally
    cannot write to the live state the whole system trusts.
    """
    now = now or datetime.now(timezone.utc)
    since_iso = (now - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%S")
    uri = f"file:{traum_db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        runs = conn.execute(
            "SELECT run_id, state, summary_json, created_at, finished_at "
            "FROM runs WHERE created_at >= ? ORDER BY created_at DESC",
            (since_iso,),
        ).fetchall()
    finally:
        conn.close()

    parsed = []
    for r in runs:
        try:
            summary = json.loads(r["summary_json"] or "{}")
        except json.JSONDecodeError:
            summary = {}
        parsed.append({
            "run_id": r["run_id"],
            "state": r["state"],
            "passes_good": summary.get("passes_good"),
            "passes_total": summary.get("passes_total"),
            "created_at": r["created_at"],
            "finished_at": r["finished_at"],
        })

    latest = parsed[0] if parsed else None
    ok = bool(
        latest
        and latest["state"] == "SUCCEEDED"
        and latest["passes_good"] is not None
        and latest["passes_good"] == latest["passes_total"]
    )
    return {
        "question": "is the dream loop completing?",
        "metric": "traum-state.db runs",
        "runs_in_window": len(parsed),
        "latest_run": latest,
        "ok": ok,
    }


def _es_get(url: str, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def check_lse_skills_index(es_url: str) -> dict:
    """Supplementary ground truth (not one of the four core questions, but
    cheap and directly load-bearing for Q2): total recorded successes/
    failures across every skill in the live index, right now."""
    try:
        r = _es_get(f"{es_url}/lse-skills/_search?size=100")
    except Exception as exc:  # noqa: BLE001 — report, don't crash the audit
        return {"reachable": False, "error": str(exc)}
    hits = r.get("hits", {}).get("hits", [])
    total_succ = sum((h["_source"].get("stats") or {}).get("episode_successes", 0)
                      for h in hits)
    total_fail = sum((h["_source"].get("stats") or {}).get("episode_failures", 0)
                      for h in hits)
    used = sum(1 for h in hits
               if (h["_source"].get("stats") or {}).get("episode_successes", 0)
               or (h["_source"].get("stats") or {}).get("episode_failures", 0))
    return {
        "reachable": True,
        "skills": len(hits),
        "total_recorded_successes": total_succ,
        "total_recorded_failures": total_fail,
        "skills_with_any_outcome": used,
    }


def run_audit(episode_dir: str, traum_db_path: str, es_url: str,
              since_days: int, now=None) -> dict:
    return {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "lookback_days": since_days,
        "skill_retrieval": check_skill_retrieval(episode_dir, since_days, now),
        "outcome_recording": check_outcome_recording(episode_dir, since_days, now),
        "kb_consultation": check_kb_consultation(episode_dir, since_days, now),
        "dream_loop": check_dream_loop_completion(traum_db_path, since_days, now),
        "lse_skills_index": check_lse_skills_index(es_url),
    }


def _fmt_row(label: str, ok, detail: str) -> str:
    mark = "✅" if ok else "❌"
    return f"| {label:<24} | {mark} | {detail} |"


def render_report(audit: dict) -> str:
    lines = ["## TRAUM Loop Audit", "",
             f"lookback: {audit['lookback_days']} day(s) · generated {audit['generated_at']}",
             "",
             "| Check | Status | Detail |",
             "|-------|--------|--------|"]

    sr = audit["skill_retrieval"]
    lines.append(_fmt_row("Skill retrieval", sr["ok"],
                           f"{sr['count']} skill_search call(s), last {sr['last_ts']}"))

    orr = audit["outcome_recording"]
    detail = (f"{orr['attempted']} attempted / {orr['succeeded']} succeeded / "
              f"{orr['errored']} errored")
    if not orr["ok"] and orr["errored"]:
        detail += f" — last error: {orr['last_error']}"
    lines.append(_fmt_row("Outcome recording", orr["ok"], detail))

    kb = audit["kb_consultation"]
    lines.append(_fmt_row("KB consultation", kb["ok"],
                           f"{kb['count']} search_kb call(s), last {kb['last_ts']}"))

    dl = audit["dream_loop"]
    if dl["latest_run"]:
        lr = dl["latest_run"]
        detail = (f"{dl['runs_in_window']} run(s) in window; latest {lr['run_id']} "
                  f"{lr['state']} ({lr['passes_good']}/{lr['passes_total']} passes)")
    else:
        detail = "0 runs in window"
    lines.append(_fmt_row("Dream loop completion", dl["ok"], detail))

    idx = audit["lse_skills_index"]
    if idx.get("reachable"):
        idx_ok = idx["skills_with_any_outcome"] > 0
        detail = (f"{idx['skills_with_any_outcome']}/{idx['skills']} skills with any "
                  f"outcome · {idx['total_recorded_successes']} successes / "
                  f"{idx['total_recorded_failures']} failures, all time")
    else:
        idx_ok = False
        detail = f"unreachable: {idx.get('error')}"
    lines.append(_fmt_row("lse-skills index (all-time)", idx_ok, detail))

    lines.append("")
    all_ok = sr["ok"] and orr["ok"] and kb["ok"] and dl["ok"]
    if all_ok:
        lines.append("**Loop is alive.** All checks green.")
    else:
        red = [name for name, chk in
               (("skill retrieval", sr), ("outcome recording", orr),
                ("KB consultation", kb), ("dream loop completion", dl))
               if not chk["ok"]]
        lines.append(f"**{len(red)} check(s) red:** {', '.join(red)}. "
                     "See docs/reports/2026-08-12-skill-feedback-loop-fork.md for the "
                     "outcome-recording failure mode this script is built to catch.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episode-dir", default=_episode_dir_default())
    ap.add_argument("--traum-db", default=_traum_db_default())
    ap.add_argument("--es-url", default=_es_url_default())
    ap.add_argument("--lookback-days", type=int, default=3)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of the table")
    args = ap.parse_args()

    audit = run_audit(args.episode_dir, args.traum_db, args.es_url, args.lookback_days)

    if args.json:
        print(json.dumps(audit, indent=2, default=str))
        return

    print(render_report(audit))


if __name__ == "__main__":
    main()
