#!/usr/bin/env python3
"""friction_report.py — read-only session friction post-mortem generator.

Reads episode JSONL records from the last N day-directories (before today),
classifies every non-ok record with the data-driven literal pattern table
(tools/friction_classifiers.json), joins per-session summaries from
manifest.db, and writes a markdown report to --out.

Stdlib only. READ-ONLY: the only file written is --out.
"""
import argparse
import datetime
import glob
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict


def find_manifest(default):
    """Use default if present; else first manifest.db found under its parent dir."""
    if os.path.exists(default):
        return default
    base = os.path.dirname(os.path.abspath(default))
    for root, _dirs, files in os.walk(base):
        if "manifest.db" in files:
            return os.path.join(root, "manifest.db")
    return None


def day_dirs(episode_dir, days):
    """Last N day-directories before today, oldest first."""
    today = datetime.date.today()
    out = []
    for i in range(days, 0, -1):
        d = today - datetime.timedelta(days=i)
        p = os.path.join(episode_dir, d.isoformat())
        if os.path.isdir(p):
            out.append((d.isoformat(), p))
    return out


def load_records(episode_dir, days):
    """Return (records, per_day_totals) for all episode lines in the window."""
    records = []
    per_day = {}
    for date, path in day_dirs(episode_dir, days):
        total = 0
        for f in sorted(glob.glob(os.path.join(path, "sess-*.jsonl"))):
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    total += 1
                    rec["_file"] = os.path.basename(f)
                    rec["_date"] = date
                    if rec.get("exit_class") != "ok":
                        records.append(rec)
        per_day[date] = total
    return records, per_day


def record_text(rec):
    a = rec.get("args_redacted", "")
    if not isinstance(a, str):
        a = json.dumps(a, default=str)
    return (rec.get("result_truncated") or "") + " \n " + a


def classify(rec, categories):
    """First category whose exit_class matches and has a pattern hit;
    then any pattern hit; else unclassified_<exit_class>."""
    text = record_text(rec)
    ec = rec.get("exit_class") or "unknown"
    for cat in categories:
        if cat.get("exit_class") and cat["exit_class"] != ec:
            continue
        if any(p in text for p in cat["patterns"]):
            return cat["name"], True
    for cat in categories:
        if any(p in text for p in cat["patterns"]):
            return cat["name"], True
    return "unclassified_" + ec, False


def load_sessions(manifest_path, session_ids):
    """Per-session summaries from manifest.db (read-only)."""
    out = {}
    if not manifest_path:
        return out
    con = sqlite3.connect("file:" + manifest_path + "?mode=ro", uri=True)
    try:
        ph = ",".join("?" for _ in session_ids)
        for row in con.execute(
            "SELECT session_id, start_ts, end_ts, n_calls, n_errors, tools_used, bytes"
            " FROM sessions WHERE session_id IN (" + ph + ")",
            list(session_ids),
        ):
            out[row[0]] = {
                "start_ts": row[1],
                "end_ts": row[2],
                "n_calls": row[3],
                "n_errors": row[4],
                "tools_used": row[5],
                "bytes": row[6],
            }
    finally:
        con.close()
    return out


SIGNAL_KEYWORDS = ('ERROR','FAIL','BLOCKED','[exit','Traceback','Error','error','timed out','Timeout','UnicodeDecodeError','403','404','No module','No pfSense')


def _pick_signal_line(result_truncated):
    lines = [line.strip() for line in result_truncated.splitlines() if line.strip()]
    if not lines:
        return ''
    for line in lines:
        if any(k in line for k in SIGNAL_KEYWORDS):
            return line
    return lines[0]




def _pick_category_sample(records):
    if not records:
        return ''
    generic = {'Error', 'error', 'ERROR', 'FAIL'}
    kw_records = {}
    kw_line = {}
    kw_line_any = {}
    for rec in records:
        text = rec.get('result_truncated', '') or ''
        seen = set()
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            for k in SIGNAL_KEYWORDS:
                if k in line:
                    if k not in seen:
                        seen.add(k)
                    if line.startswith(k) and k not in kw_line:
                        kw_line[k] = line
                    if k not in kw_line_any:
                        kw_line_any[k] = line
        for k in seen:
            kw_records[k] = kw_records.get(k, 0) + 1
    if not kw_records:
        for rec in records:
            text = rec.get('result_truncated', '') or ''
            for line in text.splitlines():
                line = line.strip()
                if line:
                    return line
        return ''
    specific = {k: c for k, c in kw_records.items() if k not in generic}
    pool = specific if specific else dict(kw_records)
    best = sorted(pool.items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]
    return kw_line.get(best, kw_line_any.get(best, best))

def build_report(records, per_day, categories, sessions, days, episode_dir, manifest_path):
    lines = []
    ap = lines.append
    today = datetime.date.today().isoformat()
    ap("# Session Friction Post-Mortem — last %d days" % days)
    ap("")
    ap("- Generated: %s" % datetime.datetime.now().isoformat(timespec="seconds"))
    ap("- Episode dir: %s" % episode_dir)
    ap("- Manifest: %s" % (manifest_path or "(not found)"))
    ap("- Window: %s .. %s (day-dirs before today)" % (
        min(per_day) if per_day else "n/a", max(per_day) if per_day else "n/a"))
    ap("")
    ec = Counter(r.get("exit_class") or "unknown" for r in records)
    total = sum(per_day.values())
    ap("## Corpus overview")
    ap("")
    ap("| metric | value |")
    ap("|---|---|")
    ap("| episode records in window | %d |" % total)
    ap("| non-ok records (friction) | %d |" % len(records))
    for k in ("timeout", "error", "denied"):
        ap("| %s | %d |" % (k, ec.get(k, 0)))
    other = len(records) - ec.get("timeout", 0) - ec.get("error", 0) - ec.get("denied", 0)
    if other:
        ap("| other | %d |" % other)
    if total:
        ap("| friction rate | %.1f%% |" % (100.0 * len(records) / total))
    ap("")
    ap("## Classification (%d categories)" % len(categories))
    ap("")
    by_cat = defaultdict(list)
    for r in records:
        name, _ = classify(r, categories)
        by_cat[name].append(r)
    ap("| category | count | % of non-ok | exit_class | sample signature |")
    ap("|---|---|---|---|---|")
    for cat in sorted(categories, key=lambda c: -len(by_cat.get(c["name"], []))):
        n = len(by_cat.get(cat["name"], []))
        if not n:
            continue
        sample = by_cat[cat["name"]][0].get("result_truncated") or ""
        sample = _pick_category_sample(by_cat[cat["name"]])[:60].replace("|", "\\|").replace("\n", " ")
        ap("| %s | %d | %.1f%% | %s | %s |" % (
            cat["name"], n, 100.0 * n / max(1, len(records)),
            cat.get("exit_class", "-"), sample))
    un = len(by_cat.get("unclassified_timeout", [])) + len(by_cat.get("unclassified_error", [])) + len(by_cat.get("unclassified_denied", []))
    if un:
        ap("| unclassified | %d | %.1f%% | - | no literal pattern matched |" % (un, 100.0 * un / max(1, len(records))))
    ap("")
    ap("## Per-day breakdown")
    ap("")
    day_ec = defaultdict(Counter)
    for r in records:
        day_ec[r["_date"]][r.get("exit_class") or "unknown"] += 1
    ap("| day | records | non-ok | timeout | error | denied |")
    ap("|---|---|---|---|---|---|")
    for date in sorted(per_day):
        c = day_ec.get(date, Counter())
        ap("| %s | %d | %d | %d | %d | %d |" % (
            date, per_day[date], sum(c.values()),
            c.get("timeout", 0), c.get("error", 0), c.get("denied", 0)))
    ap("")
    ap("## Friction by tool")
    ap("")
    tool_c = Counter(r.get("tool") or "?" for r in records)
    ap("| tool | non-ok |")
    ap("|---|---|")
    for t, n in tool_c.most_common():
        ap("| %s | %d |" % (t, n))
    ap("")
    ap("## Per-session friction summary")
    ap("")
    sess_ids = sorted({r.get("session_id") for r in records if r.get("session_id")})
    per_sess = Counter(r.get("session_id") or "?" for r in records)
    ap("| session | non-ok | manifest n_calls | manifest n_errors | tools |")
    ap("|---|---|---|---|---|")
    for sid, n in per_sess.most_common(15):
        m = sessions.get(sid, {})
        ap("| %s | %d | %s | %s | %s |" % (
            sid, n, m.get("n_calls", "-"), m.get("n_errors", "-"),
            (m.get("tools_used") or "-")[:40]))
    if len(per_sess) > 15:
        ap("| ... | | | | %d more sessions |" % (len(per_sess) - 15))
    ap("")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Read-only session friction post-mortem generator.")
    p.add_argument("--days", type=int, default=7,
                   help="number of day-directories before today (default 7)")
    p.add_argument("--episode-dir", default="/opt/local-se/episodes",
                   help="episode base dir (default /opt/local-se/episodes)")
    p.add_argument("--manifest", default="/opt/local-se/manifest.db",
                   help="manifest.db path; searched under parent if missing "
                        "(default /opt/local-se/manifest.db)")
    p.add_argument("--classifiers", default="tools/friction_classifiers.json",
                   help="classifier table path (default tools/friction_classifiers.json)")
    p.add_argument("--out", required=True, help="markdown report output path")
    a = p.parse_args(argv)

    with open(a.classifiers) as fh:
        categories = json.load(fh)
    records, per_day = load_records(a.episode_dir, a.days)
    manifest_path = find_manifest(a.manifest)
    sess_ids = sorted({r.get("session_id") for r in records if r.get("session_id")})
    sessions = load_sessions(manifest_path, sess_ids)
    report = build_report(records, per_day, categories, sessions,
                          a.days, a.episode_dir, manifest_path)
    with open(a.out, "w") as fh:
        fh.write(report)
    ec = Counter(r.get("exit_class") or "unknown" for r in records)
    print("wrote %s: %d non-ok records (timeout=%d error=%d denied=%d)" % (
        a.out, len(records), ec.get("timeout", 0), ec.get("error", 0), ec.get("denied", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
