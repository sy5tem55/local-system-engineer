"""
Unit tests for the TRAUM-INSIGHT morning digest (Thread 3, Prompt 3.4 —
tools/dream_digest.py), added by Prompt 3.9's own named test: "digest
<=30 lines".

Covers, entirely offline (no live Elasticsearch, no filesystem corpus
beyond tmp_path-scoped synthetic day-dirs):
  - render_digest() never exceeds MAX_DIGEST_LINES (30) even when every
    section is fed far more content than fits, and the truncation, when it
    fires, ends in the documented "... N more line(s) omitted" marker as
    the LAST line (deterministic: earliest content wins, not a random
    sample -- render_digest()'s own docstring in dream_digest.py).
  - a normal, small digest comfortably under the cap is NOT truncated (the
    marker line must not appear when nothing was actually cut).
  - day-dir discovery / gather_* null-result notes on a corpus with
    nothing in it yet ("no dream cycles found yet") -- the honest-empty
    case every gather_* step documents.

Run: python3 -m pytest tests/test_dream_digest.py -q
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_digest as dd  # noqa: E402


# --- fixtures / helpers ------------------------------------------------------

def _make_cfg(tmp_path, **overrides):
    cfg = dd.DigestConfig(
        dream_dir=str(tmp_path / "dreams"),
        manifest_db=str(tmp_path / "manifest.db"),  # never created -> None gather
        es_url="http://fake-es.invalid:9200",
        dry_run=True,
        lookback_days=14,
        out_path=None,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _applied_entry(i):
    return {
        "proposal": {
            "type": "dedup", "call": "mentor_correct",
            "args": {"doc_id": f"doc-{i}"},
            "why": f"synthetic applied item {i} for overflow testing",
        },
        "dry_run": False,
    }


def _insight_entry(i):
    return {
        "domain": "command-frequency", "change": "kb-fact",
        "confidence": 0.5, "observation": f"synthetic insight number {i} for overflow testing",
    }


def _pending_entry(i, date="2026-07-12"):
    return {
        "date": date,
        "proposal": {
            "type": "reverify", "call": "kb_verify",
            "args": {"doc_id": f"pending-doc-{i}"},
            "why": f"synthetic pending item {i}",
        },
    }


EMPTY_CORPUS = {"sessions": None, "docs": {idx: None for idx in dd.KB_INDICES}}


# --- 1. the <=30-line cap itself ---------------------------------------------

class TestDigestLineCap:
    def test_never_exceeds_max_lines_even_with_heavy_overflow(self, tmp_path):
        cfg = _make_cfg(tmp_path)
        # Every section fed far more than could ever fit in 30 lines --
        # applied/pending are internally capped at 6 shown + 1 "more" line
        # by render_digest() itself, but `insights` has NO such per-section
        # cap in render_digest() (gather_top_insights() is what normally
        # caps it to top-3 by confidence; calling render_digest() directly,
        # as this test does, bypasses that upstream cap on purpose --
        # exactly the "what if a caller passed something huge" case the
        # MAX_DIGEST_LINES hard-truncate exists to backstop).
        text = dd.render_digest(
            cfg, today="2026-07-12", primary_date="2026-07-12",
            applied=[_applied_entry(i) for i in range(20)], applied_note=None,
            insights=[_insight_entry(i) for i in range(40)],
            insights_date="2026-07-12", insights_note=None,
            pending=[_pending_entry(i) for i in range(20)], pending_note=None,
            corpus=EMPTY_CORPUS,
        )
        lines = text.splitlines()
        assert len(lines) <= dd.MAX_DIGEST_LINES
        assert len(lines) == dd.MAX_DIGEST_LINES  # this fixture WILL overflow
        assert "more line(s) omitted" in lines[-1]

    def test_truncation_marker_is_deterministic_earliest_content_wins(self, tmp_path):
        """Same oversized input rendered twice -> byte-identical output
        (render_digest() takes no randomness), and the FIRST insight
        (not some arbitrary later one) survives into the kept lines --
        "earliest content wins, not a random sample" per the module
        docstring."""
        cfg = _make_cfg(tmp_path)
        kwargs = dict(
            today="2026-07-12", primary_date="2026-07-12",
            applied=[], applied_note="0 apply(s) recorded for 2026-07-12, all --dry-run",
            insights=[_insight_entry(i) for i in range(50)],
            insights_date="2026-07-12", insights_note=None,
            pending=[], pending_note="0 pending — human-gate queue is empty",
            corpus=EMPTY_CORPUS,
        )
        text_1 = dd.render_digest(cfg, **kwargs)
        text_2 = dd.render_digest(cfg, **kwargs)
        assert text_1 == text_2
        assert "synthetic insight number 0 " in text_1
        assert "synthetic insight number 49" not in text_1  # cut by the cap

    def test_small_digest_is_not_truncated(self, tmp_path):
        """Sanity control: a normal, small digest must NOT hit the
        truncation path at all -- the omission marker line must be absent
        when nothing was actually cut."""
        cfg = _make_cfg(tmp_path)
        text = dd.render_digest(
            cfg, today="2026-07-12", primary_date="2026-07-12",
            applied=[_applied_entry(1)], applied_note=None,
            insights=[_insight_entry(1)], insights_date="2026-07-12", insights_note=None,
            pending=[_pending_entry(1)], pending_note=None,
            corpus=EMPTY_CORPUS,
        )
        lines = text.splitlines()
        assert len(lines) < dd.MAX_DIGEST_LINES
        assert not any("more line(s) omitted" in ln for ln in lines)

    def test_write_digest_end_to_end_respects_cap(self, tmp_path):
        """Same overflow scenario, but through the real gather_* pipeline
        against an on-disk day-dir (write_digest -> gather_applied/
        gather_top_insights/gather_pending/gather_corpus_stats), not
        render_digest() called directly. gather_top_insights() caps to
        top-3 by confidence on its own, so this is a DIFFERENT code path
        than TestDigestLineCap above -- both must independently respect
        MAX_DIGEST_LINES."""
        day_dir = tmp_path / "dreams" / "2026-07-12"
        day_dir.mkdir(parents=True)
        report_lines = ["# TRAUM dream report", "", "## Cross-session insights", ""]
        for i in range(10):
            report_lines.append(
                f"{i + 1}. **[command-frequency/kb-fact]** (confidence=0.90) — "
                f"finding number {i} in an oversized report.md"
            )
            report_lines.append(f"   - evidence: cmd-{i}")
            report_lines.append("")
        (day_dir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")

        proposals = [_pending_entry(i)["proposal"] for i in range(15)]
        import json
        with open(day_dir / "proposals.jsonl", "wt", encoding="utf-8") as f:
            for p in proposals:
                f.write(json.dumps(p) + "\n")
        # No applied.jsonl/rejected.jsonl -> all 15 proposals are "pending".

        cfg = _make_cfg(tmp_path, dry_run=True)
        text = dd.write_digest(cfg)
        lines = text.splitlines()
        assert len(lines) <= dd.MAX_DIGEST_LINES


# --- 2. honest-empty corpus (no dream cycles yet) ----------------------------

class TestDigestOnEmptyCorpus:
    def test_no_dream_dir_at_all(self, tmp_path):
        cfg = _make_cfg(tmp_path)  # dream_dir never created
        text = dd.write_digest(cfg)
        assert "no cycles yet" in text
        assert "no dream cycles found yet" in text
        lines = text.splitlines()
        assert len(lines) <= dd.MAX_DIGEST_LINES

    def test_pick_primary_date_none_on_empty_dream_dir(self, tmp_path):
        (tmp_path / "dreams").mkdir()
        cfg = _make_cfg(tmp_path)
        assert dd.pick_primary_date(cfg, today="2026-07-12") is None


# --- pass-scoped day-dir files (Thread 4 prerequisite) ----------------------
# dream_runner.py now writes report-<pass>.md / proposals-<pass>.jsonl;
# day_dir_files() must take the union of pass-scoped names and the legacy
# shared name so Threads 2-3 day-dirs stay readable.

class TestPassScopedDayDirFiles:

    def _proposal(self, i):
        return {"type": "dedup", "call": "mentor_correct",
                "args": {"doc_id": f"doc-{i}"}, "why": f"synthetic proposal {i}"}

    def test_union_of_scoped_and_legacy(self, tmp_path):
        import json
        base = tmp_path / "dreams" / "2026-07-12"
        base.mkdir(parents=True)
        for name in ("proposals-dedup.jsonl", "proposals-stale-contradiction.jsonl",
                     "proposals.jsonl"):
            with open(base / name, "wt", encoding="utf-8") as f:
                f.write(json.dumps(self._proposal(name)) + "\n")
        files = dd.day_dir_files(str(base), "proposals", "jsonl")
        assert len(files) == 3
        assert files[-1].endswith("proposals.jsonl")  # legacy last
        assert files[0].endswith("proposals-dedup.jsonl")  # sorted scoped first

    def test_gather_pending_reads_all_pass_files(self, tmp_path):
        import json
        cfg = _make_cfg(tmp_path)
        base = tmp_path / "dreams" / "2026-07-12"
        base.mkdir(parents=True)
        with open(base / "proposals-dedup.jsonl", "wt", encoding="utf-8") as f:
            f.write(json.dumps(self._proposal(1)) + "\n")
        with open(base / "proposals-error-cluster.jsonl", "wt", encoding="utf-8") as f:
            f.write(json.dumps(self._proposal(2)) + "\n")
        pending, note = dd.gather_pending(cfg, "2026-07-12")
        assert note is None
        assert len(pending) == 2
