#!/usr/bin/env python3
"""
dream_digest.py — TRAUM-INSIGHT morning digest (v0.1.0)
=============================================================================
TRAUM Thread 3, Prompt 3.4 (docs/traum-dreaming-plan.md). Companion to
tools/dream_runner.py (Prompts 2.1-2.4, 3.1-3.2 — the READ-ONLY proposer,
`--pass patterns`/`--pass insights` in particular) and tools/dream_apply.py
(Prompt 2.5 — the one write path, applied.jsonl/rejected.jsonl).

Generates /opt/local-se/dreams/latest-digest.md: a single, <=30-line file
for BOTH audiences named in the prompt — the operator reads it by hand, and
Prompt 3.5 (not yet built) wires a short summary of it into the gateway's
session-start [DREAM] banner. Four sections, in order:
  1. What changed in the KB overnight — real (non-dry-run) applied.jsonl
     entries from the most recent dream cycle's day-dir.
  2. Top 3 insights — parsed back out of the most recent report.md that
     actually contains a non-null "## Cross-session insights" section
     (Prompt 3.2's `--pass insights` narrative), searching backward across
     day-dirs up to --lookback-days since report.md is a SINGLE shared file
     per day-dir that the LAST pass run that day overwrites (write_report()
     in dream_runner.py has no per-pass filename — see its module comment;
     Thread 4's nightly orchestration is expected to run passes in sequence
     and apply between them, exactly like Prompt 2.7's first supervised
     dream did, so "most recent day-dir with an insights narrative" is the
     correct thing to surface, not necessarily today's).
  3. Pending human-gate items — proposals.jsonl entries, across day-dirs in
     the lookback window, whose canonical JSON does not appear (by content
     hash) in that same day-dir's applied.jsonl or rejected.jsonl yet. This
     is a lightweight preview of what Prompt 4.4's `dream_apply --queue`
     will formalize later in Thread 4 — not a replacement for it.
  4. One-line corpus stats — manifest.db session counts (total / dreamed /
     pending) plus best-effort lse-kb/lse-errors/lse-skills doc counts (ES
     reads are READ-ONLY, same `search_index`-style discipline as
     dream_runner.py, and never fatal if ES is unreachable — PH3-2 null-
     result discipline: say "ES unreachable" rather than silently omitting
     the line or crashing).

Every gather step is wrapped so a single missing/corrupt file degrades that
one section to a null-result line instead of aborting the whole digest
(same "failures must never break the caller" discipline as Prompt 1.3's
episode journaling try/except). `refresh_digest()` is the integration point
dream_runner.py and dream_apply.py both call at the end of their own main()
("at the end of every dream run" — Prompt 3.4's own phrasing covers both the
proposing half and the applying half of a dream run) — it never raises.

OUTPUT is hard-capped at 30 lines total (Prompt 3.4's own limit): if the
assembled content would run longer, it is truncated to 29 lines plus one
final "... N more lines omitted" marker line, deterministically (earliest
content wins, not a random sample).

USAGE
  # Standalone regeneration from the CLI (mirrors dream_runner.py/dream_apply.py
  # --dry-run convention: default true, prints the would-be digest to stdout).
  python3 dream_digest.py --dream-dir /opt/local-se/dreams --no-dry-run

ENV (same GOETHE_ prefix convention as dream_runner.py/dream_apply.py)
  GOETHE_DREAM_DIR      dream output root (default /opt/local-se/dreams)
  GOETHE_EPISODE_DIR    episode corpus root, for manifest.db (default /opt/local-se/episodes)
  GOETHE_ES_URL         Elasticsearch base URL (default http://127.0.0.1:9200)
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date

__version__ = "0.1.0"

MAX_DIGEST_LINES = 30
_DAY_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INSIGHT_LINE_RE = re.compile(
    r"^\d+\.\s+\*\*\[(?P<domain>[^/\]]+)/(?P<change>[^\]]+)\]\*\*\s+"
    r"\(confidence=(?P<conf>[0-9.]+)\)\s+—\s+(?P<obs>.+)$"
)
KB_INDICES = ("lse-kb", "lse-errors", "lse-skills")


# --- config / valve-style env defaults --------------------------------------

def _dream_dir_default() -> str:
    return os.environ.get("GOETHE_DREAM_DIR", "/opt/local-se/dreams")


def _episode_dir_default() -> str:
    return os.environ.get("GOETHE_EPISODE_DIR", "/opt/local-se/episodes")


def _es_url_default() -> str:
    return os.environ.get("GOETHE_ES_URL", "http://127.0.0.1:9200")


@dataclass
class DigestConfig:
    dream_dir: str
    manifest_db: str
    es_url: str
    dry_run: bool = True
    lookback_days: int = 14
    out_path: str | None = None  # default: <dream_dir>/latest-digest.md

    def digest_path(self) -> str:
        return self.out_path or os.path.join(self.dream_dir, "latest-digest.md")


# --- day-dir discovery --------------------------------------------------

def list_day_dirs(dream_dir: str) -> list[str]:
    """YYYY-MM-DD subdirectories of dream_dir that actually exist, sorted
    NEWEST FIRST (string sort == chronological sort for this format)."""
    if not os.path.isdir(dream_dir):
        return []
    names = [n for n in os.listdir(dream_dir) if _DAY_DIR_RE.match(n)
              and os.path.isdir(os.path.join(dream_dir, n))]
    return sorted(names, reverse=True)


def pick_primary_date(cfg: DigestConfig, today: str) -> str | None:
    """The day-dir this cycle's "what changed overnight" section reflects:
    today's dir if it exists, else the most recently existing dir (covers
    running the digest before today's first pass has written anything yet,
    or re-running it later against the same day), else None (no dream data
    at all -- a legitimate null result, e.g. brand-new install)."""
    day_dirs = list_day_dirs(cfg.dream_dir)
    if today in day_dirs:
        return today
    return day_dirs[0] if day_dirs else None


# --- jsonl loading / proposal identity ---------------------------------

def load_jsonl(path: str) -> list[dict]:
    """Tolerant JSONL reader -- skips unparseable lines rather than raising,
    same discipline as dream_apply.py's load_proposals()."""
    out: list[dict] = []
    if not os.path.exists(path):
        return out
    with open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def proposal_key(p: dict) -> str:
    """Stable content-hash identity for a proposal dict. proposals.jsonl
    entries carry no id field of their own (dream_runner.py's
    REQUIRED_PROPOSAL_KEYS is {type, call, args, why}), so identity has to
    be structural -- canonical (sorted-key) JSON, hashed. applied.jsonl/
    rejected.jsonl both store the original dict verbatim under "proposal"
    (dream_apply.py's apply_group()/main()), so the same function applied
    to that inner dict reproduces the same key."""
    canonical = json.dumps(p, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _truncate(text: str, n: int) -> str:
    text = " ".join(str(text).split())  # collapse embedded newlines/whitespace
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


# --- section 1: applied overnight ---------------------------------------

def gather_applied(cfg: DigestConfig, primary_date: str | None) -> tuple[list[dict], str | None]:
    """Real (non-dry-run) applied.jsonl entries from the primary day-dir
    only -- "overnight" means the most recent cycle, not a historical
    rollup. Returns (entries, note); note is set on a null result so the
    renderer can say WHY the section is empty (PH3-2 discipline: distinguish
    "nothing applied" from "no dream data at all")."""
    if primary_date is None:
        return [], "no dream cycles found yet"
    path = os.path.join(cfg.dream_dir, primary_date, "applied.jsonl")
    raw = load_jsonl(path)
    real = [e for e in raw if e.get("dry_run") is False]
    if not raw:
        return [], f"no applied.jsonl for {primary_date} (dream_apply not yet run this cycle)"
    if not real:
        return [], f"{len(raw)} apply(s) recorded for {primary_date}, all --dry-run (nothing actually written)"
    return real, None


# --- section 2: top insights ---------------------------------------------

def _extract_insights_section(report_text: str) -> str | None:
    """Returns the "## Cross-session insights" section body (the heading's
    own line excluded), or None if the heading is absent."""
    lines = report_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "## Cross-session insights":
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start:end])


def parse_insight_lines(section_text: str) -> list[dict]:
    """Parses run_pass_insights()'s own narrative numbering
    (dream_runner.py ~line 2587): "N. **[domain/change]** (confidence=X.XX)
    — observation". Ignores the "- evidence:"/"- cost estimate:" detail
    lines beneath each entry; the digest only ever surfaces the headline."""
    out = []
    for line in section_text.splitlines():
        m = _INSIGHT_LINE_RE.match(line.strip())
        if m:
            out.append({
                "domain": m.group("domain"),
                "change": m.group("change"),
                "confidence": float(m.group("conf")),
                "observation": m.group("obs").strip(),
            })
    return out


def gather_top_insights(cfg: DigestConfig, primary_date: str | None, n: int = 3) -> tuple[list[dict], str | None, str | None]:
    """Searches day-dirs newest-first, starting at primary_date, for the
    most recent report.md carrying a NON-EMPTY Cross-session insights
    section (report.md is overwritten per-pass -- see module docstring --
    so "most recent WITH insights" is not always primary_date itself).
    Returns (top_n_insights_by_confidence, source_date, note)."""
    day_dirs = list_day_dirs(cfg.dream_dir)
    if primary_date and primary_date in day_dirs:
        # ensure primary_date is searched first even if it's somehow not
        # the newest (defensive; list_day_dirs is already sorted desc).
        day_dirs = [primary_date] + [d for d in day_dirs if d != primary_date]
    candidates = day_dirs[: max(1, cfg.lookback_days)]

    for d in candidates:
        report_path = os.path.join(cfg.dream_dir, d, "report.md")
        if not os.path.exists(report_path):
            continue
        try:
            with open(report_path, "rt", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        section = _extract_insights_section(text)
        if section is None:
            continue
        insights = parse_insight_lines(section)
        if insights:
            insights.sort(key=lambda x: x["confidence"], reverse=True)
            return insights[:n], d, None

    if not candidates:
        return [], None, "no dream cycles found yet"
    return [], None, f"no insights pass output in the last {len(candidates)} day-dir(s) (null result, PH3-2)"


# --- section 3: pending human-gate items ---------------------------------

def gather_pending(cfg: DigestConfig, primary_date: str | None) -> tuple[list[dict], str | None]:
    """Proposals across day-dirs in the lookback window whose content-hash
    does not appear in that same day's applied.jsonl/rejected.jsonl yet.
    Newest day-dirs first; each entry tagged with its source date. This is
    a preview, not the formal queue Prompt 4.4 (Thread 4) builds -- it has
    no expiry rule, no --queue flag, and no dedup across days by anything
    other than exact content match."""
    day_dirs = list_day_dirs(cfg.dream_dir)[: max(1, cfg.lookback_days)]
    if not day_dirs:
        return [], "no dream cycles found yet"

    pending: list[dict] = []
    for d in day_dirs:
        base = os.path.join(cfg.dream_dir, d)
        proposals = load_jsonl(os.path.join(base, "proposals.jsonl"))
        if not proposals:
            continue
        applied = load_jsonl(os.path.join(base, "applied.jsonl"))
        rejected = load_jsonl(os.path.join(base, "rejected.jsonl"))
        resolved = {proposal_key(e["proposal"]) for e in applied if "proposal" in e}
        resolved |= {proposal_key(e["proposal"]) for e in rejected if "proposal" in e}
        for p in proposals:
            if proposal_key(p) not in resolved:
                pending.append({"date": d, "proposal": p})
    if not pending:
        return [], "0 pending — human-gate queue is empty"
    return pending, None


# --- section 4: corpus stats ---------------------------------------------

def _manifest_session_counts(manifest_db: str) -> dict | None:
    if not os.path.exists(manifest_db):
        return None
    try:
        conn = sqlite3.connect(manifest_db, timeout=10)
        try:
            row = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN dreamed_at IS NOT NULL THEN 1 ELSE 0 END) "
                "FROM sessions"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    total = row[0] or 0
    dreamed = row[1] or 0
    return {"total": total, "dreamed": dreamed, "pending": total - dreamed}


def _es_doc_counts(es_url: str) -> dict:
    """Best-effort es.count() per index. Any failure (ES down, index
    missing, elasticsearch client not installed) degrades that index's
    count to None rather than raising -- corpus stats are informational,
    never load-bearing for anything downstream."""
    counts: dict = {}
    try:
        from elasticsearch import Elasticsearch  # noqa: PLC0415
    except ImportError:
        return {idx: None for idx in KB_INDICES}
    try:
        es = Elasticsearch(es_url, request_timeout=5)
    except Exception:
        return {idx: None for idx in KB_INDICES}
    for idx in KB_INDICES:
        try:
            counts[idx] = es.count(index=idx)["count"]
        except Exception:
            counts[idx] = None
    return counts


def gather_corpus_stats(cfg: DigestConfig) -> dict:
    sessions = _manifest_session_counts(cfg.manifest_db)
    docs = _es_doc_counts(cfg.es_url)
    return {"sessions": sessions, "docs": docs}


def render_corpus_line(stats: dict) -> str:
    parts = []
    sessions = stats.get("sessions")
    if sessions is None:
        parts.append("sessions: manifest.db unreadable")
    else:
        parts.append(
            f"sessions {sessions['total']} ({sessions['dreamed']} dreamed, "
            f"{sessions['pending']} pending)"
        )
    docs = stats.get("docs", {})
    doc_parts = []
    for idx in KB_INDICES:
        n = docs.get(idx)
        doc_parts.append(f"{idx}={n if n is not None else '?'}")
    if all(docs.get(idx) is None for idx in KB_INDICES):
        parts.append("ES unreachable")
    else:
        parts.append(" ".join(doc_parts))
    return "Corpus: " + " · ".join(parts)


# --- render ---------------------------------------------------------------

def render_digest(cfg: DigestConfig, today: str, primary_date: str | None,
                   applied: list[dict], applied_note: str | None,
                   insights: list[dict], insights_date: str | None, insights_note: str | None,
                   pending: list[dict], pending_note: str | None,
                   corpus: dict) -> str:
    lines: list[str] = []
    lines.append(f"# TRAUM dream digest — generated {today}"
                  + (f" (cycle: {primary_date})" if primary_date else " (no cycles yet)"))
    lines.append("")

    lines.append(f"## Applied overnight ({len(applied)})")
    if applied_note:
        lines.append(f"- {applied_note}")
    else:
        for e in applied[:6]:
            p = e.get("proposal", {})
            call = p.get("call", "?")
            args = p.get("args", {})
            target = args.get("doc_id") or args.get("title") or args.get("task") or "?"
            lines.append(f"- **{p.get('type', '?')}** `{call}` on {target} — {_truncate(p.get('why', ''), 70)}")
        if len(applied) > 6:
            lines.append(f"- … and {len(applied) - 6} more (see {primary_date}/applied.jsonl)")
    lines.append("")

    lines.append("## Top insights")
    if insights_note:
        lines.append(f"- {insights_note}")
    else:
        for i, ins in enumerate(insights, 1):
            lines.append(
                f"{i}. [{ins['domain']}/{ins['change']}] (confidence={ins['confidence']:.2f}) "
                f"— {_truncate(ins['observation'], 90)}"
            )
        if insights_date and insights_date != primary_date:
            lines.append(f"   (from {insights_date}, most recent insights pass)")
    lines.append("")

    lines.append(f"## Pending human-gate ({len(pending)})")
    if pending_note:
        lines.append(f"- {pending_note}")
    else:
        for entry in pending[:6]:
            p = entry["proposal"]
            lines.append(
                f"- [{entry['date']}] **{p.get('type', '?')}** via `{p.get('call', '?')}` "
                f"— {_truncate(p.get('why', ''), 60)}"
            )
        if len(pending) > 6:
            lines.append(f"- … and {len(pending) - 6} more")
    lines.append("")

    lines.append(render_corpus_line(corpus))

    if len(lines) > MAX_DIGEST_LINES:
        kept = lines[: MAX_DIGEST_LINES - 1]
        omitted = len(lines) - len(kept)
        kept.append(f"… {omitted} more line(s) omitted — see dreams/{primary_date or '<date>'}/report.md")
        lines = kept

    return "\n".join(lines) + "\n"


# --- orchestration ---------------------------------------------------------

def write_digest(cfg: DigestConfig) -> str:
    """Builds the digest text and, unless cfg.dry_run, writes it to
    cfg.digest_path(). Each gather step is independently exception-guarded
    so one bad file degrades one section, not the whole digest. Returns the
    rendered text either way (callers/tests can inspect it without a
    filesystem round-trip)."""
    today = date.today().isoformat()

    try:
        primary_date = pick_primary_date(cfg, today)
    except Exception as exc:
        primary_date = None
        print(f"[dream_digest] WARNING: day-dir discovery failed ({exc})", file=sys.stderr)

    try:
        applied, applied_note = gather_applied(cfg, primary_date)
    except Exception as exc:
        applied, applied_note = [], f"gather failed: {exc}"

    try:
        insights, insights_date, insights_note = gather_top_insights(cfg, primary_date)
    except Exception as exc:
        insights, insights_date, insights_note = [], None, f"gather failed: {exc}"

    try:
        pending, pending_note = gather_pending(cfg, primary_date)
    except Exception as exc:
        pending, pending_note = [], f"gather failed: {exc}"

    try:
        corpus = gather_corpus_stats(cfg)
    except Exception as exc:
        corpus = {"sessions": None, "docs": {idx: None for idx in KB_INDICES}}
        print(f"[dream_digest] WARNING: corpus stats gather failed ({exc})", file=sys.stderr)

    text = render_digest(cfg, today, primary_date, applied, applied_note,
                          insights, insights_date, insights_note,
                          pending, pending_note, corpus)

    if cfg.dry_run:
        print(f"[dream_digest] [dry-run] would write {cfg.digest_path()}:", file=sys.stderr)
        print(text)
        return text

    out_path = cfg.digest_path()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wt", encoding="utf-8") as f:
        f.write(text)
    print(f"[dream_digest] wrote {out_path} ({len(text.splitlines())} lines)", file=sys.stderr)
    return text


def refresh_digest(*, dream_dir: str, episode_dir: str | None = None, manifest_db: str | None = None,
                    es_url: str, dry_run: bool = True, lookback_days: int = 14,
                    out_path: str | None = None) -> str | None:
    """Integration point for dream_runner.py/dream_apply.py: builds its own
    DigestConfig from plain kwargs (deliberately NOT importing either
    caller's own Config dataclass, to keep this module a leaf dependency)
    and calls write_digest(). NEVER raises -- "at the end of every dream
    run" (Prompt 3.4) must never turn a successful pass/apply into a
    reported failure just because the digest step hiccuped, same
    discipline as Prompt 1.3's episode-journaling try/except. Returns the
    rendered text on success, None on failure (logged to stderr either way)."""
    try:
        manifest_db = manifest_db or os.path.join(episode_dir or _episode_dir_default(), "manifest.db")
        cfg = DigestConfig(
            dream_dir=dream_dir, manifest_db=manifest_db, es_url=es_url,
            dry_run=dry_run, lookback_days=lookback_days, out_path=out_path,
        )
        return write_digest(cfg)
    except Exception as exc:
        print(f"[dream_digest] WARNING: digest refresh failed non-fatally ({exc})", file=sys.stderr)
        return None


# --- CLI --------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="dream_digest.py",
        description="TRAUM-INSIGHT morning digest builder (Prompt 3.4). See "
        "docs/dreaming/DESIGN.md and tools/dream_runner.py/dream_apply.py.",
    )
    ap.add_argument("--dream-dir", default=_dream_dir_default())
    ap.add_argument("--episode-dir", default=_episode_dir_default())
    ap.add_argument("--manifest-db", default=None,
                    help="default: <episode-dir>/manifest.db")
    ap.add_argument("--es-url", default=_es_url_default())
    ap.add_argument("--lookback-days", type=int, default=14)
    ap.add_argument("--out", default=None, help="default: <dream-dir>/latest-digest.md")
    ap.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True,
                    help="print the digest instead of writing it (default: true)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    manifest_db = args.manifest_db or os.path.join(args.episode_dir, "manifest.db")
    cfg = DigestConfig(
        dream_dir=args.dream_dir, manifest_db=manifest_db, es_url=args.es_url,
        dry_run=args.dry_run, lookback_days=args.lookback_days, out_path=args.out,
    )
    write_digest(cfg)


if __name__ == "__main__":
    main()
