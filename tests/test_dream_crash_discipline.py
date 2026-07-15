"""
Unit + fault-injection tests for TRAUM Thread 4, Prompt 4.3 (TRAUM-AUTO) --
crash discipline: tools/dream_runner.py's record_crash_error/
write_failure_report/_handle_crash + main()'s try/except/finally, and
tools/dream_digest.py's 3-consecutive-failed-nights escalation banner.

Covers:
  - record_crash_error: dry-run makes zero ES calls; a new crash creates a
    doc (index="lse-errors-1024", provenance="dream-infra", context="dream-runner");
    a REPEAT of the same error text (same normalized-hash id) bumps
    occurrence_count via get+update instead of creating a second doc; total
    ES failure is swallowed and reported back as a string, never raised.
  - write_failure_report: dry-run prints without writing; a real write
    produces report.md with a "## FAILED" banner, the exception type/
    message, a traceback, and an explicit "safe to re-dream" statement,
    plus one JSON line appended to crashes.jsonl with the right fields.
  - _handle_crash: calls all three steps (report, record_error, digest
    refresh) and never raises even when every single one of them is made
    to fail internally -- a broken crash-handler must not replace the
    original crash.
  - Fault injection through the REAL main(): a pass_func monkeypatched to
    raise mid-run still (a) gets caught, (b) writes a real FAILED
    report.md and crashes.jsonl to disk, (c) attempts an ES write via a
    FakeES double (context=dream-runner, provenance=dream-infra), (d)
    leaves manifest.db's dreamed_at completely untouched, (e) still
    releases the lock in `finally` (no orphaned lock after a crash), and
    (f) re-raises the ORIGINAL exception (main() does not swallow it --
    the process is expected to exit non-zero).
  - gather_crash_streak: counts consecutive crashes.jsonl-bearing day-dirs
    walking backward from today; breaks on a missing day-dir, an existing
    day-dir with no/empty crashes.jsonl, and respects lookback_days as an
    outer bound.
  - render_digest's ESCALATION banner: absent below the 3-night threshold,
    present at/above it, and positioned early enough to survive
    MAX_DIGEST_LINES truncation even when every other section is
    overflowing.

No live ES, SSH, or LLM -- FakeES double + tmp_path-scoped synthetic
day-dirs/manifest.db throughout.

    python3 -m pytest tests/test_dream_crash_discipline.py -q
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_runner as dr  # noqa: E402
import dream_digest as dd  # noqa: E402


class FakeES:
    """Minimal in-memory ES double for record_crash_error's get/update/index
    shape -- deliberately smaller than test_dream_engine.py's FakeES (no
    .search/.delete needed here), kept local to match this codebase's
    one-fixture-per-test-file convention."""

    def __init__(self):
        self.store = {}  # (index, id) -> dict
        self.calls = []

    def get(self, *, index, id, **kw):
        self.calls.append(("get", index, id))
        if (index, id) not in self.store:
            raise KeyError(f"no such doc {index}/{id}")
        return {"_source": dict(self.store[(index, id)])}

    def update(self, *, index, id, body, **kw):
        self.calls.append(("update", index, id))
        self.store.setdefault((index, id), {}).update(body.get("doc", {}))
        return {"result": "updated"}

    def index(self, *, index, id=None, document=None, **kw):
        self.calls.append(("index", index, id))
        self.store[(index, id)] = dict(document or {})
        return {"result": "created"}


def _cfg(**overrides):
    base = dict(
        episode_dir="/tmp/episodes-does-not-exist",
        dream_dir="/tmp/dreams-does-not-exist",
        manifest_db="/tmp/episodes-does-not-exist/manifest.db",
        es_url="http://fake-es.invalid:9200",
        tasks_db="/tmp/tasks.db",
        agent_log="/tmp/agent_commands.log",
        dream_llm_url="",
        node3090_llm_url="http://node3090.home.arpa:8080",
        node3090_ollama_url="http://node3090.home.arpa:11434",
        node3090_fallback_model="qwen3:4b",
        ollama_url="http://127.0.0.1:11434",
        embed_model="qwen3-embedding:0.6b",
        dedup_floor=0.75,
        dedup_threshold=0.92,
        error_cluster_threshold=0.80,
        runner_session_prefix="",
        sessions_limit=50,
        since=None,
        pass_name="patterns",
        dry_run=True,
    )
    base.update(overrides)
    return dr.DreamConfig(**base)


# --- record_crash_error -------------------------------------------------

class TestRecordCrashError:
    def test_dry_run_makes_zero_es_calls(self, monkeypatch):
        es = FakeES()
        monkeypatch.setattr(dr, "es_client", lambda cfg: es)
        cfg = _cfg(dry_run=True)

        msg = dr.record_crash_error(cfg, "boom: something broke", context="dream-runner")

        assert es.calls == []
        assert msg.startswith("[dry-run] would record_error")
        assert "dream-infra" in msg

    def test_new_error_creates_doc_with_provenance_and_context(self, monkeypatch):
        es = FakeES()
        monkeypatch.setattr(dr, "es_client", lambda cfg: es)
        cfg = _cfg(dry_run=False)

        msg = dr.record_crash_error(cfg, "KeyError: 'foo'", context="dream-runner")

        assert "created" in msg
        index_calls = [c for c in es.calls if c[0] == "index"]
        assert len(index_calls) == 1
        _, index_name, doc_id = index_calls[0]
        assert index_name == "lse-errors-1024"
        doc = es.store[(index_name, doc_id)]
        assert doc["context"] == "dream-runner"
        assert doc["provenance"] == "dream-infra"
        assert doc["error_text"] == "KeyError: 'foo'"
        assert doc["occurrence_count"] == 1
        assert doc["first_seen"] == doc["last_seen"]

    def test_repeat_error_bumps_occurrence_count_not_a_new_doc(self, monkeypatch):
        es = FakeES()
        monkeypatch.setattr(dr, "es_client", lambda cfg: es)
        cfg = _cfg(dry_run=False)

        dr.record_crash_error(cfg, "TimeoutError: node3090 unreachable", context="dream-runner")
        msg2 = dr.record_crash_error(cfg, "TimeoutError: node3090 unreachable", context="dream-runner")

        assert "updated" in msg2
        assert len(es.store) == 1  # same hash -> same doc, not two
        (doc,) = es.store.values()
        assert doc["occurrence_count"] == 2

    def test_case_and_whitespace_normalized_to_same_hash(self, monkeypatch):
        """Same normalization as goethe.py's own record_error -- collapses
        whitespace and lowercases before hashing, so trivially-different
        renderings of the same underlying error still dedup."""
        es = FakeES()
        monkeypatch.setattr(dr, "es_client", lambda cfg: es)
        cfg = _cfg(dry_run=False)

        dr.record_crash_error(cfg, "Connection   Refused", context="dream-runner")
        dr.record_crash_error(cfg, "connection refused", context="dream-runner")

        assert len(es.store) == 1

    def test_total_es_failure_is_swallowed_not_raised(self, monkeypatch):
        def broken_es_client(cfg):
            raise ConnectionError("ES is down")

        monkeypatch.setattr(dr, "es_client", broken_es_client)
        cfg = _cfg(dry_run=False)

        msg = dr.record_crash_error(cfg, "whatever", context="dream-runner")  # must not raise
        assert "NOT be updated" in msg or "failed" in msg.lower()


# --- write_failure_report -------------------------------------------------

class TestWriteFailureReport:
    def test_dry_run_prints_and_writes_nothing(self, tmp_path, capsys):
        dream_dir = tmp_path / "dreams"
        cfg = _cfg(dream_dir=str(dream_dir), dry_run=True, pass_name="dedup")
        exc = ValueError("synthetic failure")

        report_path, crashes_path = dr.write_failure_report(cfg, exc, sessions_count=7)

        assert not os.path.exists(report_path)
        assert not os.path.exists(crashes_path)
        out = capsys.readouterr().out
        assert "FAILED" in out
        assert "synthetic failure" in out

    def test_real_write_produces_failed_banner_and_crash_record(self, tmp_path):
        dream_dir = tmp_path / "dreams"
        cfg = _cfg(dream_dir=str(dream_dir), dry_run=False, pass_name="insights")

        try:
            raise RuntimeError("simulated insights crash")
        except RuntimeError as exc:
            report_path, crashes_path = dr.write_failure_report(cfg, exc, sessions_count=3)

        report_text = Path(report_path).read_text()
        assert "## FAILED" in report_text
        assert "RuntimeError: simulated insights crash" in report_text
        assert "Traceback" in report_text
        assert "safe to re-dream" in report_text.lower()
        assert "Sessions considered before the crash: 3" in report_text

        crash_lines = Path(crashes_path).read_text().strip().splitlines()
        assert len(crash_lines) == 1
        record = json.loads(crash_lines[0])
        assert record["pass"] == "insights"
        assert record["error_type"] == "RuntimeError"
        assert record["sessions_considered"] == 3

    def test_crashes_jsonl_appends_not_overwrites(self, tmp_path):
        dream_dir = tmp_path / "dreams"
        cfg1 = _cfg(dream_dir=str(dream_dir), dry_run=False, pass_name="dedup")
        cfg2 = _cfg(dream_dir=str(dream_dir), dry_run=False, pass_name="error-cluster")

        dr.write_failure_report(cfg1, ValueError("first"), sessions_count=0)
        _, crashes_path = dr.write_failure_report(cfg2, ValueError("second"), sessions_count=0)

        lines = Path(crashes_path).read_text().strip().splitlines()
        assert len(lines) == 2
        passes = {json.loads(ln)["pass"] for ln in lines}
        assert passes == {"dedup", "error-cluster"}


# --- _handle_crash ---------------------------------------------------------

class TestHandleCrash:
    def test_calls_all_three_steps(self, monkeypatch):
        calls = []
        monkeypatch.setattr(dr, "write_failure_report", lambda *a, **k: calls.append("report"))
        monkeypatch.setattr(dr, "record_crash_error", lambda *a, **k: calls.append("record") or "ok")
        monkeypatch.setattr(dr.dream_digest, "refresh_digest", lambda *a, **k: calls.append("digest"))

        cfg = _cfg()
        dr._handle_crash(cfg, ValueError("x"), sessions_count=0)

        assert calls == ["report", "record", "digest"]

    def test_never_raises_even_if_every_step_fails(self, monkeypatch):
        monkeypatch.setattr(dr, "write_failure_report",
                             lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        monkeypatch.setattr(dr, "record_crash_error",
                             lambda *a, **k: (_ for _ in ()).throw(ConnectionError("es down")))
        monkeypatch.setattr(dr.dream_digest, "refresh_digest",
                             lambda *a, **k: (_ for _ in ()).throw(RuntimeError("digest broke too")))

        cfg = _cfg()
        dr._handle_crash(cfg, ValueError("original crash"), sessions_count=0)  # must not raise


# --- fault injection through the REAL main() -------------------------------

class TestMainFaultInjection:
    def test_injected_exception_triggers_full_crash_discipline(self, tmp_path, monkeypatch):
        episode_dir = tmp_path / "episodes"
        dream_dir = tmp_path / "dreams"
        episode_dir.mkdir()
        dream_dir.mkdir()

        es = FakeES()
        monkeypatch.setattr(dr, "es_client", lambda cfg: es)
        monkeypatch.setattr(dr._epidx, "build_manifest", lambda *a, **k: {"scanned": 0})
        monkeypatch.setattr(dr.dream_digest, "refresh_digest", lambda **k: None)

        def exploding_pass(cfg, sessions, episodes_by_session, kb_docs, error_docs):
            raise RuntimeError("injected fault for Prompt 4.3 testing")

        monkeypatch.setitem(dr.PASS_FUNCS, "patterns", exploding_pass)

        argv = [
            "--pass", "patterns",
            "--episode-dir", str(episode_dir),
            "--dream-dir", str(dream_dir),
            "--agent-log", str(tmp_path / "agent.log"),
            "--no-dry-run",
        ]

        with pytest.raises(RuntimeError, match="injected fault for Prompt 4.3 testing"):
            dr.main(argv)

        today = date.today().isoformat()
        out_dir = dream_dir / today
        # Pass-scoped as of the Thread 4 prerequisite fix: a crashed pass
        # writes report-<pass>.md, never the (legacy) shared report.md.
        report_text = (out_dir / "report-patterns.md").read_text()
        assert "## FAILED" in report_text
        assert "injected fault for Prompt 4.3 testing" in report_text

        crash_lines = (out_dir / "crashes.jsonl").read_text().strip().splitlines()
        assert len(crash_lines) == 1
        record = json.loads(crash_lines[0])
        assert record["pass"] == "patterns"
        assert record["error_type"] == "RuntimeError"

        index_calls = [c for c in es.calls if c[0] == "index"]
        assert len(index_calls) == 1
        (doc,) = es.store.values()
        assert doc["context"] == "dream-runner"
        assert doc["provenance"] == "dream-infra"
        assert "injected fault" in doc["error_text"]

        # the lock must be released even though the run crashed -- no
        # orphaned lockfile blocking tomorrow's (or a manual re-)run.
        assert not (dream_dir / ".dream.lock").exists()

    def test_dreamed_at_never_touched_on_crash(self, tmp_path, monkeypatch):
        import sqlite3

        episode_dir = tmp_path / "episodes"
        dream_dir = tmp_path / "dreams"
        episode_dir.mkdir()
        dream_dir.mkdir()
        manifest_db = episode_dir / "manifest.db"

        conn = sqlite3.connect(str(manifest_db))
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, start_ts TEXT, end_ts TEXT, "
            "n_calls INTEGER, n_errors INTEGER, tools_used TEXT, bytes INTEGER, dreamed_at TEXT)"
        )
        old_ts = (date.today() - timedelta(days=2)).isoformat() + "T00:00:00+00:00"
        conn.execute("INSERT INTO sessions VALUES ('sess-x', ?, ?, 1, 0, '[]', 10, NULL)",
                     (old_ts, old_ts))
        conn.commit()
        conn.close()

        monkeypatch.setattr(dr, "es_client", lambda cfg: FakeES())
        monkeypatch.setattr(dr._epidx, "build_manifest", lambda *a, **k: {"scanned": 0})
        monkeypatch.setattr(dr.dream_digest, "refresh_digest", lambda **k: None)

        def exploding_pass(cfg, sessions, episodes_by_session, kb_docs, error_docs):
            raise RuntimeError("crash after session selection")

        monkeypatch.setitem(dr.PASS_FUNCS, "dedup", exploding_pass)

        argv = [
            "--pass", "dedup",
            "--episode-dir", str(episode_dir),
            "--dream-dir", str(dream_dir),
            "--manifest-db", str(manifest_db),
            "--agent-log", str(tmp_path / "agent.log"),
            "--no-dry-run",
        ]
        with pytest.raises(RuntimeError):
            dr.main(argv)

        conn = sqlite3.connect(str(manifest_db))
        row = conn.execute("SELECT dreamed_at FROM sessions WHERE session_id='sess-x'").fetchone()
        conn.close()
        assert row[0] is None


# --- gather_crash_streak ----------------------------------------------------

class TestGatherCrashStreak:
    def _crashy_day(self, dream_dir: Path, day: date, n: int = 1):
        day_dir = dream_dir / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        with open(day_dir / "crashes.jsonl", "at") as f:
            for i in range(n):
                f.write(json.dumps({"pass": "dedup", "error_type": "X"}) + "\n")

    def _clean_day(self, dream_dir: Path, day: date):
        day_dir = dream_dir / day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        (day_dir / "report.md").write_text("fine")

    def test_zero_when_nothing_crashed(self, tmp_path):
        dream_dir = tmp_path / "dreams"
        dream_dir.mkdir()
        cfg = dd.DigestConfig(dream_dir=str(dream_dir), manifest_db="/tmp/x", es_url="http://x", lookback_days=14)
        streak, last = dd.gather_crash_streak(cfg, date.today().isoformat())
        assert streak == 0
        assert last is None

    def test_three_consecutive_nights(self, tmp_path):
        dream_dir = tmp_path / "dreams"
        today = date.today()
        for offset in range(3):
            self._crashy_day(dream_dir, today - timedelta(days=offset))
        cfg = dd.DigestConfig(dream_dir=str(dream_dir), manifest_db="/tmp/x", es_url="http://x", lookback_days=14)

        streak, last = dd.gather_crash_streak(cfg, today.isoformat())
        assert streak == 3
        assert last == today.isoformat()

    def test_clean_night_breaks_the_streak(self, tmp_path):
        dream_dir = tmp_path / "dreams"
        today = date.today()
        self._crashy_day(dream_dir, today)
        self._clean_day(dream_dir, today - timedelta(days=1))  # breaks it here
        self._crashy_day(dream_dir, today - timedelta(days=2))
        cfg = dd.DigestConfig(dream_dir=str(dream_dir), manifest_db="/tmp/x", es_url="http://x", lookback_days=14)

        streak, last = dd.gather_crash_streak(cfg, today.isoformat())
        assert streak == 1
        assert last == today.isoformat()

    def test_missing_day_dir_breaks_the_streak(self, tmp_path):
        dream_dir = tmp_path / "dreams"
        today = date.today()
        self._crashy_day(dream_dir, today)
        # deliberately skip today-1 entirely (no day-dir at all)
        self._crashy_day(dream_dir, today - timedelta(days=2))
        cfg = dd.DigestConfig(dream_dir=str(dream_dir), manifest_db="/tmp/x", es_url="http://x", lookback_days=14)

        streak, _ = dd.gather_crash_streak(cfg, today.isoformat())
        assert streak == 1

    def test_respects_lookback_days_bound(self, tmp_path):
        dream_dir = tmp_path / "dreams"
        today = date.today()
        for offset in range(10):
            self._crashy_day(dream_dir, today - timedelta(days=offset))
        cfg = dd.DigestConfig(dream_dir=str(dream_dir), manifest_db="/tmp/x", es_url="http://x", lookback_days=4)

        streak, _ = dd.gather_crash_streak(cfg, today.isoformat())
        assert streak == 4


# --- render_digest escalation banner ----------------------------------------

class TestRenderDigestEscalationBanner:
    def _base_kwargs(self, today):
        return dict(
            cfg=dd.DigestConfig(dream_dir="/tmp/x", manifest_db="/tmp/x", es_url="http://x"),
            today=today, primary_date=None,
            applied=[], applied_note="no dream cycles found yet",
            insights=[], insights_date=None, insights_note="no dream cycles found yet",
            pending=[], pending_note="no dream cycles found yet",
            corpus={"sessions": None, "docs": {idx: None for idx in dd.KB_INDICES}},
        )

    def test_absent_below_threshold(self):
        today = date.today().isoformat()
        text = dd.render_digest(**self._base_kwargs(today), crash_streak=2, crash_last_date=today)
        assert "ESCALATION" not in text

    def test_present_at_threshold(self):
        today = date.today().isoformat()
        text = dd.render_digest(**self._base_kwargs(today), crash_streak=3, crash_last_date=today)
        assert "ESCALATION" in text
        assert "3 consecutive failed dream nights" in text
        assert today in text

    def test_banner_survives_truncation(self):
        """Force overflow the SAME way test_dream_digest.py's own
        heavy-overflow test does: `insights` has no per-section cap in
        render_digest() itself (unlike applied/pending, which cap at 6 +
        a "more" line) -- gather_top_insights() normally caps it upstream,
        so calling render_digest() directly with many insights, as here,
        is exactly the "what if a caller passed something huge" case
        MAX_DIGEST_LINES exists to backstop. Confirms the ESCALATION
        banner -- rendered near the very top -- survives even though the
        tail gets cut."""
        today = date.today().isoformat()
        kwargs = self._base_kwargs(today)
        kwargs["insights"] = [
            {"domain": "command-frequency", "change": "kb-fact", "confidence": 0.5,
             "observation": f"synthetic overflow insight number {i}"}
            for i in range(40)
        ]
        kwargs["insights_date"] = today
        kwargs["insights_note"] = None
        text = dd.render_digest(**kwargs, crash_streak=5, crash_last_date=today)

        assert "ESCALATION" in text
        assert len(text.splitlines()) <= dd.MAX_DIGEST_LINES
        assert "more line(s) omitted" in text
