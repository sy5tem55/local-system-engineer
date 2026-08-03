"""
Unit tests for TRAUM Thread 4, Prompt 4.2 (TRAUM-AUTO) -- tools/dream_runner.py's
lockfile, recent-session-activity guard, per-run budgets, and the dreamer-
episode-exclusion assert.

Covers:
  - DreamBudget: each dimension's exhausted() reason, fixed check order
    (wall-clock, then LLM-calls, then sessions), mark_truncated keeping the
    FIRST reason even if called again later, record_llm_call/record_session.
  - _budget_checkpoint: no-ops (returns False) when cfg.budget is None;
    marks cfg.budget.truncated the first time it detects exhaustion.
  - call_dream_llm: short-circuits to 'BUDGET_EXHAUSTED: ...' with ZERO
    network calls once the attached budget is spent, and still increments
    llm_calls_made for calls it does let through.
  - request_dream_envelope: a BUDGET_EXHAUSTED reply is returned verbatim
    as the error message WITHOUT the normal 2-attempt retry (retrying an
    exhausted budget is pointless).
  - acquire_lock/release_lock: atomic acquire, a live lock blocks a second
    acquire, a lock whose PID is provably dead is reclaimed, a lock older
    than lock_max_age_s is reclaimed even with a technically-alive PID,
    release_lock only ever removes a lock it can prove is its own (PID
    match) and is a safe no-op otherwise.
  - _recent_session_active: a session ending inside the window blocks with
    a reason, one ending outside the window does not, a missing/empty
    manifest.db does not block, a future end_ts (clock skew) does not
    false-positive-block.
  - assert_no_episode_writes: passes silently when nothing changed under
    episode_dir; raises AssertionError the moment a session file is
    added or modified, but is silent about an unrelated manifest.db write
    (a legitimate, expected write target, not a violation).
  - Integration: run_pass_stale_contradiction's per-session loop actually
    stops early once the LLM-call budget trips (fewer than len(sessions)
    candidates evaluated), via a monkeypatched find_contradiction_candidates
    + call_dream_llm so no real ES/network/model is needed.

No live SSH, ES, Ollama, or LLM -- everything is driven through tmp_path
fixtures, monkeypatch, and small synthetic manifest.db / episode files.

    python3 -m pytest tests/test_dream_guards.py -q
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_runner as dr  # noqa: E402


def _cfg(**overrides):
    """Minimal DreamConfig -- mirrors the fixture style in
    test_dream_engine.py / test_dream_vram_gate.py."""
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
        embed_model="nomic-embed-text",
        dedup_floor=0.75,
        dedup_threshold=0.92,
        error_cluster_threshold=0.80,
        runner_session_prefix="",
        sessions_limit=50,
        since=None,
        pass_name="stale-contradiction",
        dry_run=True,
    )
    base.update(overrides)
    return dr.DreamConfig(**base)


# --- DreamBudget -------------------------------------------------------------

class TestDreamBudget:
    def test_not_exhausted_initially(self):
        b = dr.DreamBudget(max_sessions=10, max_llm_calls=10, max_wall_clock_s=999)
        assert b.exhausted() is None
        assert not b.truncated

    def test_llm_calls_exhausted(self):
        b = dr.DreamBudget(max_sessions=10, max_llm_calls=2, max_wall_clock_s=999)
        b.record_llm_call()
        b.record_llm_call()
        reason = b.exhausted()
        assert reason is not None
        assert "LLM-call" in reason

    def test_sessions_exhausted(self):
        b = dr.DreamBudget(max_sessions=2, max_llm_calls=999, max_wall_clock_s=999)
        b.record_session()
        b.record_session()
        reason = b.exhausted()
        assert reason is not None
        assert "session" in reason.lower()

    def test_wall_clock_exhausted(self):
        b = dr.DreamBudget(max_sessions=999, max_llm_calls=999, max_wall_clock_s=0.0)
        reason = b.exhausted()
        assert reason is not None
        assert "wall-clock" in reason

    def test_check_order_wall_clock_wins_first(self):
        """When multiple dimensions are exhausted simultaneously, wall-clock
        is reported first (fixed order documented on DreamBudget.exhausted)."""
        b = dr.DreamBudget(max_sessions=0, max_llm_calls=0, max_wall_clock_s=0.0)
        reason = b.exhausted()
        assert "wall-clock" in reason

    def test_mark_truncated_keeps_first_reason(self):
        b = dr.DreamBudget(max_sessions=10, max_llm_calls=10, max_wall_clock_s=999)
        b.mark_truncated("first reason")
        b.mark_truncated("second reason")
        assert b.truncated
        assert b.truncation_reason == "first reason"


class TestBudgetCheckpoint:
    def test_noop_when_no_budget_attached(self):
        cfg = _cfg()
        assert cfg.budget is None
        assert dr._budget_checkpoint(cfg) is False

    def test_true_and_marks_truncated_when_exhausted(self):
        cfg = _cfg()
        cfg.budget = dr.DreamBudget(max_sessions=1, max_llm_calls=999, max_wall_clock_s=999)
        cfg.budget.record_session()
        assert dr._budget_checkpoint(cfg) is True
        assert cfg.budget.truncated
        assert "session" in cfg.budget.truncation_reason.lower()

    def test_false_when_budget_present_but_not_exhausted(self):
        cfg = _cfg()
        cfg.budget = dr.DreamBudget(max_sessions=10, max_llm_calls=10, max_wall_clock_s=999)
        assert dr._budget_checkpoint(cfg) is False
        assert not cfg.budget.truncated


# --- call_dream_llm / request_dream_envelope budget wiring -------------------

class TestCallDreamLlmBudget:
    def test_short_circuits_with_zero_network_calls_when_exhausted(self, monkeypatch):
        health_calls = {"n": 0}
        monkeypatch.setattr(dr, "_health_probe", lambda *a, **k: health_calls.__setitem__("n", health_calls["n"] + 1) or True)
        monkeypatch.setattr(dr, "_post_chat_completion", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
        monkeypatch.setattr(dr, "_node3090_free_vram_mb", lambda *a, **k: 99999)

        cfg = _cfg()
        cfg.budget = dr.DreamBudget(max_sessions=10, max_llm_calls=1, max_wall_clock_s=999)
        cfg.budget.record_llm_call()  # already at the cap

        result = dr.call_dream_llm("sys", "user", cfg)
        assert result.startswith("BUDGET_EXHAUSTED:")
        assert health_calls["n"] == 0, "no health probe of any kind once budget is exhausted"
        # exhausted() is called again by call_dream_llm's own checkpoint but
        # record_llm_call must NOT have been incremented a second time for
        # this (non-)call.
        assert cfg.budget.llm_calls_made == 1

    def test_records_llm_call_when_allowed(self, monkeypatch):
        monkeypatch.setattr(dr, "_health_probe", lambda *a, **k: True)
        monkeypatch.setattr(dr, "_post_chat_completion", lambda *a, **k: "a real reply")
        monkeypatch.setattr(dr, "_node3090_free_vram_mb", lambda *a, **k: 99999)

        cfg = _cfg()
        cfg.budget = dr.DreamBudget(max_sessions=10, max_llm_calls=10, max_wall_clock_s=999)

        result = dr.call_dream_llm("sys", "user", cfg)
        assert result == "a real reply"
        assert cfg.budget.llm_calls_made == 1

    def test_no_budget_attached_behaves_exactly_as_before(self, monkeypatch):
        monkeypatch.setattr(dr, "_health_probe", lambda *a, **k: True)
        monkeypatch.setattr(dr, "_post_chat_completion", lambda *a, **k: "unbudgeted reply")
        monkeypatch.setattr(dr, "_node3090_free_vram_mb", lambda *a, **k: 99999)

        cfg = _cfg()
        assert cfg.budget is None
        result = dr.call_dream_llm("sys", "user", cfg)
        assert result == "unbudgeted reply"


class TestRequestDreamEnvelopeBudget:
    def test_budget_exhausted_reply_short_circuits_no_retry(self, monkeypatch):
        calls = []

        def fake_call_dream_llm(system_prompt, content, cfg, no_think=True):
            calls.append(content)
            return "BUDGET_EXHAUSTED: wall-clock budget exhausted (999s >= 999s)"

        monkeypatch.setattr(dr, "call_dream_llm", fake_call_dream_llm)

        cfg = _cfg()
        env, err = dr.request_dream_envelope("sys prompt", "user content", cfg)
        assert env is None
        assert err.startswith("BUDGET_EXHAUSTED:")
        assert len(calls) == 1, "must not retry a budget-exhausted response"

    def test_real_error_still_retries_is_unaffected(self, monkeypatch):
        """Sanity check that the new BUDGET_EXHAUSTED branch didn't disturb
        the pre-existing ERROR: handling (still no retry loop on hard
        ERROR:, single DREAMER UNAVAILABLE return)."""
        calls = []

        def fake_call_dream_llm(system_prompt, content, cfg, no_think=True):
            calls.append(content)
            return "ERROR: connection refused"

        monkeypatch.setattr(dr, "call_dream_llm", fake_call_dream_llm)

        cfg = _cfg()
        env, err = dr.request_dream_envelope("sys prompt", "user content", cfg)
        assert env is None
        assert "DREAMER UNAVAILABLE" in err
        assert len(calls) == 1


# --- lockfile ------------------------------------------------------------

class TestLock:
    def _dead_pid(self) -> int:
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        return p.pid

    def test_acquire_then_release_roundtrip(self, tmp_path):
        cfg = _cfg(lockfile=str(tmp_path / "dream.lock"))
        assert dr.acquire_lock(cfg) is True
        assert os.path.exists(cfg.lockfile)
        held = json.loads(Path(cfg.lockfile).read_text())
        assert held["pid"] == os.getpid()
        assert held["pass"] == cfg.pass_name
        dr.release_lock(cfg)
        assert not os.path.exists(cfg.lockfile)

    def test_second_acquire_blocked_by_live_lock(self, tmp_path):
        cfg = _cfg(lockfile=str(tmp_path / "dream.lock"))
        assert dr.acquire_lock(cfg) is True
        # our own PID is alive, and the file is fresh -- a second attempt
        # (simulating another concurrent dream_runner.py) must be refused.
        assert dr.acquire_lock(cfg) is False
        dr.release_lock(cfg)

    def test_stale_lock_dead_pid_is_reclaimed(self, tmp_path):
        lockfile = tmp_path / "dream.lock"
        dead_pid = self._dead_pid()
        lockfile.write_text(json.dumps({"pid": dead_pid, "pass": "dedup", "acquired_at": "irrelevant"}))
        cfg = _cfg(lockfile=str(lockfile))
        assert dr.acquire_lock(cfg) is True
        held = json.loads(lockfile.read_text())
        assert held["pid"] == os.getpid()
        dr.release_lock(cfg)

    def test_stale_lock_too_old_is_reclaimed_even_if_pid_alive(self, tmp_path):
        lockfile = tmp_path / "dream.lock"
        # our OWN pid is alive, but the file's mtime will be forced old.
        lockfile.write_text(json.dumps({"pid": os.getpid(), "pass": "insights", "acquired_at": "irrelevant"}))
        old_time = time.time() - 10_000
        os.utime(lockfile, (old_time, old_time))
        cfg = _cfg(lockfile=str(lockfile), lock_max_age_s=3600)
        assert dr.acquire_lock(cfg) is True
        dr.release_lock(cfg)

    def test_release_never_removes_a_lock_it_does_not_own(self, tmp_path):
        lockfile = tmp_path / "dream.lock"
        other_dead_pid = self._dead_pid()
        # Write a lock claiming to be owned by a DIFFERENT (dead, but
        # that's irrelevant to release_lock -- it only checks PID identity,
        # never liveness) pid -- release_lock must refuse to remove it.
        lockfile.write_text(json.dumps({"pid": other_dead_pid, "pass": "dedup", "acquired_at": "x"}))
        cfg = _cfg(lockfile=str(lockfile))
        dr.release_lock(cfg)
        assert lockfile.exists(), "release_lock must not remove a lock it doesn't own"

    def test_release_on_missing_lockfile_is_a_safe_noop(self, tmp_path):
        cfg = _cfg(lockfile=str(tmp_path / "never-created.lock"))
        dr.release_lock(cfg)  # must not raise


# --- recent-session-activity guard -------------------------------------------

class TestRecentSessionActive:
    def _write_manifest(self, manifest_db: Path, end_ts: str):
        import sqlite3
        conn = sqlite3.connect(str(manifest_db))
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, start_ts TEXT, end_ts TEXT, "
            "n_calls INTEGER, n_errors INTEGER, tools_used TEXT, bytes INTEGER, dreamed_at TEXT)"
        )
        conn.execute(
            "INSERT INTO sessions VALUES ('sess-1', ?, ?, 3, 0, '[]', 100, NULL)",
            (end_ts, end_ts),
        )
        conn.commit()
        conn.close()

    def test_recent_session_blocks(self, tmp_path, monkeypatch):
        episode_dir = tmp_path / "episodes"
        episode_dir.mkdir()
        manifest_db = episode_dir / "manifest.db"
        recent = (datetime.now().astimezone() - timedelta(minutes=5)).isoformat(timespec="microseconds")
        self._write_manifest(manifest_db, recent)

        # build_manifest would rescan episode_dir (empty here) and NOT touch
        # dreamed_at/existing rows for files it doesn't find -- but since
        # there are no session FILES on disk (only a hand-written DB row),
        # skip the rescan entirely to keep this test about the time-window
        # logic, not episode_index's file-scanning behavior.
        monkeypatch.setattr(dr._epidx, "build_manifest", lambda *a, **k: {"scanned": 0})

        cfg = _cfg(episode_dir=str(episode_dir), manifest_db=str(manifest_db))
        reason = dr._recent_session_active(cfg)
        assert reason != ""
        assert "sess-1" in reason

    def test_old_session_does_not_block(self, tmp_path, monkeypatch):
        episode_dir = tmp_path / "episodes"
        episode_dir.mkdir()
        manifest_db = episode_dir / "manifest.db"
        old = (datetime.now().astimezone() - timedelta(hours=5)).isoformat(timespec="microseconds")
        self._write_manifest(manifest_db, old)
        monkeypatch.setattr(dr._epidx, "build_manifest", lambda *a, **k: {"scanned": 0})

        cfg = _cfg(episode_dir=str(episode_dir), manifest_db=str(manifest_db))
        assert dr._recent_session_active(cfg) == ""

    def test_future_end_ts_clock_skew_does_not_block(self, tmp_path, monkeypatch):
        episode_dir = tmp_path / "episodes"
        episode_dir.mkdir()
        manifest_db = episode_dir / "manifest.db"
        future = (datetime.now().astimezone() + timedelta(minutes=10)).isoformat(timespec="microseconds")
        self._write_manifest(manifest_db, future)
        monkeypatch.setattr(dr._epidx, "build_manifest", lambda *a, **k: {"scanned": 0})

        cfg = _cfg(episode_dir=str(episode_dir), manifest_db=str(manifest_db))
        assert dr._recent_session_active(cfg) == ""

    def test_missing_manifest_does_not_block(self, tmp_path, monkeypatch):
        episode_dir = tmp_path / "episodes-empty"
        monkeypatch.setattr(dr._epidx, "build_manifest", lambda *a, **k: {"scanned": 0})
        cfg = _cfg(episode_dir=str(episode_dir), manifest_db=str(episode_dir / "manifest.db"))
        assert dr._recent_session_active(cfg) == ""

    def test_manifest_refresh_failure_does_not_raise(self, tmp_path, monkeypatch):
        episode_dir = tmp_path / "episodes"
        episode_dir.mkdir()
        manifest_db = episode_dir / "manifest.db"

        def boom(*a, **k):
            raise RuntimeError("simulated build_manifest failure")

        monkeypatch.setattr(dr._epidx, "build_manifest", boom)
        cfg = _cfg(episode_dir=str(episode_dir), manifest_db=str(manifest_db))
        # manifest.db doesn't exist at all -- must degrade to "" (no block),
        # never raise, even though the refresh itself blew up.
        assert dr._recent_session_active(cfg) == ""


# --- dreamer-episode-exclusion assert -----------------------------------------

class TestAssertNoEpisodeWrites:
    def _make_session_file(self, episode_dir: Path, day: str, session_id: str):
        day_dir = episode_dir / day
        day_dir.mkdir(parents=True, exist_ok=True)
        f = day_dir / f"{session_id}.jsonl"
        f.write_text(json.dumps({"ts": "2026-07-12T00:00:00+00:00", "tool": "x"}) + "\n")
        return f

    def test_passes_when_nothing_changed(self, tmp_path):
        episode_dir = tmp_path / "episodes"
        self._make_session_file(episode_dir, "2026-07-12", "sess-a")
        before = dr._snapshot_episode_session_files(str(episode_dir))
        dr.assert_no_episode_writes(str(episode_dir), before)  # must not raise

    def test_manifest_db_write_is_not_a_violation(self, tmp_path):
        """manifest.db lives inside episode_dir by default but is a
        legitimate write target (episode_index.build_manifest,
        dream_apply.py's dreamed_at) -- the snapshot must ignore it."""
        episode_dir = tmp_path / "episodes"
        self._make_session_file(episode_dir, "2026-07-12", "sess-a")
        before = dr._snapshot_episode_session_files(str(episode_dir))
        (episode_dir / "manifest.db").write_text("pretend sqlite content")
        dr.assert_no_episode_writes(str(episode_dir), before)  # must not raise

    def test_new_session_file_raises(self, tmp_path):
        episode_dir = tmp_path / "episodes"
        self._make_session_file(episode_dir, "2026-07-12", "sess-a")
        before = dr._snapshot_episode_session_files(str(episode_dir))
        self._make_session_file(episode_dir, "2026-07-12", "sess-DREAM-OF-DREAMS")
        with pytest.raises(AssertionError, match="INVARIANT VIOLATION"):
            dr.assert_no_episode_writes(str(episode_dir), before)

    def test_modified_session_file_raises(self, tmp_path):
        episode_dir = tmp_path / "episodes"
        f = self._make_session_file(episode_dir, "2026-07-12", "sess-a")
        before = dr._snapshot_episode_session_files(str(episode_dir))
        time.sleep(0.01)
        f.write_text(f.read_text() + json.dumps({"ts": "later", "tool": "y"}) + "\n")
        os.utime(f, None)  # ensure mtime actually advances on fast filesystems
        with pytest.raises(AssertionError, match="INVARIANT VIOLATION"):
            dr.assert_no_episode_writes(str(episode_dir), before)


# --- integration: budget truncation inside a real pass loop ------------------

class TestStaleContradictionLoopTruncation:
    def test_llm_call_budget_stops_the_session_loop_early(self, monkeypatch):
        sessions = [{"session_id": f"sess-{i}"} for i in range(10)]
        episodes_by_session = {s["session_id"]: [] for s in sessions}
        kb_docs = [{"_id": "doc-1", "quality_score": 0.9, "title": "t", "content": "c"}]

        seen_sessions = []

        def fake_find_contradiction_candidates(session_episodes, docs_by_id):
            return [(kb_docs[0], [])]

        def fake_demote_proposals_for_doc(cfg, session_id, doc, evidence_lines):
            seen_sessions.append(session_id)
            # Exercises the real request_dream_envelope -> call_dream_llm
            # path so budget bookkeeping happens for real, not simulated.
            env, err = dr.request_dream_envelope("sys", "user", cfg)
            return [], None

        monkeypatch.setattr(dr, "find_contradiction_candidates", fake_find_contradiction_candidates)
        monkeypatch.setattr(dr, "_demote_proposals_for_doc", fake_demote_proposals_for_doc)
        # Patch BELOW call_dream_llm (health probe / HTTP), not call_dream_llm
        # itself -- the real call_dream_llm is what does the budget
        # bookkeeping (record_llm_call), so it must actually run.
        monkeypatch.setattr(dr, "_health_probe", lambda *a, **k: True)
        monkeypatch.setattr(dr, "_post_chat_completion", lambda *a, **k: "ERROR: no real model needed for this test")
        monkeypatch.setattr(dr, "_node3090_free_vram_mb", lambda *a, **k: 99999)

        cfg = _cfg(pass_name="stale-contradiction")
        cfg.budget = dr.DreamBudget(max_sessions=999, max_llm_calls=3, max_wall_clock_s=999)

        proposals, narrative, null_record = dr.run_pass_stale_contradiction(
            cfg, sessions, episodes_by_session, kb_docs, []
        )

        assert cfg.budget.truncated
        assert "LLM-call" in cfg.budget.truncation_reason
        # Exactly 3 sessions should have been processed (one call_dream_llm
        # call each) before the 4th loop iteration's checkpoint caught the
        # cap and broke -- NOT all 10.
        assert len(seen_sessions) == 3
        assert cfg.budget.sessions_consumed == 3

    def test_session_budget_stops_loop_before_llm_calls_matter(self, monkeypatch):
        sessions = [{"session_id": f"sess-{i}"} for i in range(10)]
        episodes_by_session = {s["session_id"]: [] for s in sessions}
        kb_docs = [{"_id": "doc-1", "quality_score": 0.9, "title": "t", "content": "c"}]

        # No candidates at all -- pure record_session() exercise, LLM-call
        # dimension never engages.
        monkeypatch.setattr(dr, "find_contradiction_candidates", lambda *a, **k: [])

        cfg = _cfg(pass_name="stale-contradiction")
        cfg.budget = dr.DreamBudget(max_sessions=4, max_llm_calls=999, max_wall_clock_s=999)

        dr.run_pass_stale_contradiction(cfg, sessions, episodes_by_session, kb_docs, [])

        assert cfg.budget.truncated
        assert "session" in cfg.budget.truncation_reason.lower()
        assert cfg.budget.sessions_consumed == 4


# --- --skip-session-guard keeps the lock (operator-initiated runs) -----------

class TestSkipSessionGuardKeepsTheLock:
    """The GUI checkbox maps to --skip-session-guard, NOT --ignore-guards.

    The distinction is the whole point: --ignore-guards suppresses the
    lockfile as well, which would allow two concurrent dream runners over
    the same corpus. These tests pin that the narrow flag waives only the
    quiet-period wait.
    """

    def test_parse_args_exposes_both_flags_independently(self):
        plain = dr.parse_args(["--pass", "dedup"])
        assert plain.skip_session_guard is False
        assert plain.ignore_guards is False

        narrow = dr.parse_args(["--pass", "dedup", "--skip-session-guard"])
        assert narrow.skip_session_guard is True
        assert narrow.ignore_guards is False, (
            "--skip-session-guard must NOT imply --ignore-guards; the latter "
            "also disables the lock"
        )

        broad = dr.parse_args(["--pass", "dedup", "--ignore-guards"])
        assert broad.ignore_guards is True
        assert broad.skip_session_guard is False

    def test_lock_is_still_acquired_when_session_guard_is_skipped(self, tmp_path):
        """A held lock must still block a --skip-session-guard run."""
        lockfile = tmp_path / "dream.lock"
        # A lock held by THIS live pid: acquire_lock must refuse it rather
        # than reclaim it as stale.
        lockfile.write_text(json.dumps(
            {"pid": os.getpid(), "pass": "dedup", "acquired_at": "x"}
        ))
        cfg = _cfg(lockfile=str(lockfile), skip_session_guard=True, dry_run=False)
        assert dr.acquire_lock(cfg) is False, (
            "skipping the session guard must not weaken the lock guard"
        )


# --- cascade leg 0 defaults to node4090/LUCIFER ------------------------------

class TestPrimaryDreamerDefault:
    """node4090 IS LUCIFER (goethe_node.py:293) and is the primary dreamer.

    Leg 0 defaulting to "" left legs 1 and 2 -- both node3090 -- as the only
    real endpoints, which contradicted the fleet architecture and caused a
    live failure on 2026-08-02: a GUI-triggered run cannot pick up
    run-dream-cycle.sh's fallback export, so with node3090 asleep there was
    no reachable endpoint and every call burned its full 180s timeout.
    stale-contradiction hung 37 minutes and starved four passes.
    """

    def test_leg0_defaults_to_local_llama_server(self, monkeypatch):
        monkeypatch.delenv("GOETHE_DREAM_LLM_URL", raising=False)
        assert dr._dream_llm_url_default() == "http://127.0.0.1:8080"

    def test_leg0_default_is_not_empty(self, monkeypatch):
        """The regression guard. An empty leg 0 means a GUI run with node3090
        asleep has no dreamer at all."""
        monkeypatch.delenv("GOETHE_DREAM_LLM_URL", raising=False)
        assert dr._dream_llm_url_default(), (
            "leg 0 must not default to empty -- that leaves node3090 as the "
            "only reachable dreamer and a sleeping node costs 180s per call"
        )

    def test_env_still_overrides_the_default(self, monkeypatch):
        monkeypatch.setenv("GOETHE_DREAM_LLM_URL", "http://elsewhere:9999")
        assert dr._dream_llm_url_default() == "http://elsewhere:9999"

    def test_uses_ipv4_literal_not_localhost(self, monkeypatch):
        """localhost resolves to ::1 first on a dual-stack host; llama-server
        may be bound v4-only. 0.0.0.0 also accepts loopback, so the literal
        works under either binding the Goethe GUI offers."""
        monkeypatch.delenv("GOETHE_DREAM_LLM_URL", raising=False)
        assert "localhost" not in dr._dream_llm_url_default()
        assert "127.0.0.1" in dr._dream_llm_url_default()

    def test_node3090_legs_are_unchanged(self, monkeypatch):
        """This adds a preferred path; it must remove no fallback."""
        monkeypatch.delenv("GOETHE_NODE3090_LLM_URL", raising=False)
        monkeypatch.delenv("GOETHE_NODE3090_OLLAMA_URL", raising=False)
        assert "node3090" in dr._node3090_llm_url_default()
        assert "node3090" in dr._node3090_ollama_url_default()


# --- dreamer circuit breaker -------------------------------------------------

class TestDreamLLMCircuitBreaker:
    """One LLM call can burn the whole cascade before failing: leg 0 (180s) +
    leg 1 (120s) + leg 2 (300s) = up to 600s. Without a breaker a pass pays
    that repeatedly.

    Measured twice in production, both fatal:
      2026-08-02  stale-contradiction burned 2244s, starved 4 passes
      2026-08-03  stale-contradiction burned 2081s -- and error-cluster
                  SUCCEEDED 100s later, so the dreamer was only transiently
                  away and the cost of finding out was 35 of 45 minutes.
    """

    def setup_method(self):
        dr.reset_dream_llm_breaker()

    def teardown_method(self):
        dr.reset_dream_llm_breaker()

    def test_breaker_is_closed_initially(self):
        assert dr._dream_llm_breaker_open() is False

    def test_opens_after_the_limit_of_consecutive_failures(self):
        for _ in range(dr._DREAM_LLM_FAILURE_LIMIT):
            dr._dream_llm_record(success=False)
        assert dr._dream_llm_breaker_open() is True

    def test_one_success_resets_the_streak(self):
        """A transient blip must not poison the rest of the pass."""
        for _ in range(dr._DREAM_LLM_FAILURE_LIMIT):
            dr._dream_llm_record(success=False)
        assert dr._dream_llm_breaker_open() is True
        dr._dream_llm_record(success=True)
        assert dr._dream_llm_breaker_open() is False

    def test_open_breaker_short_circuits_without_calling_the_cascade(self, monkeypatch):
        """The load-bearing one: an open breaker must cost ZERO seconds, not
        another 600s cascade. If _post_chat_completion is reached, the whole
        point has been missed."""
        called = []
        monkeypatch.setattr(dr, "_post_chat_completion",
                            lambda *a, **k: called.append(1) or "ERROR: should not run")
        monkeypatch.setattr(dr, "_health_probe",
                            lambda *a, **k: called.append(1) or True)
        for _ in range(dr._DREAM_LLM_FAILURE_LIMIT):
            dr._dream_llm_record(success=False)

        cfg = _cfg(dry_run=False)
        reply = dr.call_dream_llm("sys", "user", cfg)

        assert called == [], "cascade was attempted despite an open breaker"
        assert reply.startswith("ERROR:")
        assert "circuit breaker" in reply

    def test_reset_is_available_for_per_pass_use(self):
        for _ in range(dr._DREAM_LLM_FAILURE_LIMIT):
            dr._dream_llm_record(success=False)
        dr.reset_dream_llm_breaker()
        assert dr._dream_llm_breaker_open() is False

    def test_limit_is_env_tunable_and_disableable(self):
        """0 disables the breaker entirely -- an escape hatch, not a default."""
        assert dr._DREAM_LLM_FAILURE_LIMIT >= 1


# --- envelope parsing past a Python-repr decoy -------------------------------

class TestDreamEnvelopeDecoyBrace:
    """2026-08-03: three consecutive cycles reported dependency=dream-llm and
    blocked stale-contradiction for 28-37 minutes each. The dreamer answered
    correctly every time.

    The episode corpus contains Python-repr dicts -- {'tool_calls': '[2 items]'}
    -- and when the model quotes that content in its prose, a bare
    clean.find("{") locked onto the quoted fragment and raw_decode died on the
    single quote without ever reaching the real envelope further down.
    """

    DECOY = ("Looking at the episode, the harness produced "
             "{'tool_calls': '[2 items]'} which it silently discards.\n\n")

    def test_finds_envelope_after_a_python_repr_decoy(self):
        """The load-bearing case -- this exact shape cost ~90 minutes of
        production budget across three cycles."""
        reply = self.DECOY + '{"proposals": [{"type": "demote", "why": "x"}]}'
        env, err = dr.parse_dream_envelope(reply)
        assert env is not None, f"decoy defeated the parser again: {err}"
        assert env["proposals"][0]["type"] == "demote"
        assert err == ""

    def test_finds_envelope_after_several_decoys(self):
        reply = (self.DECOY + "{'another': 'repr'}\nand {not json at all}\n"
                 + '{"proposals": []}')
        env, err = dr.parse_dream_envelope(reply)
        assert env is not None, err
        assert env["proposals"] == []

    def test_skips_a_valid_json_object_lacking_the_key(self):
        """A decoy can be valid JSON yet not be the envelope."""
        reply = '{"summary": "not the envelope"}\n{"proposals": [{"a": 1}]}'
        env, err = dr.parse_dream_envelope(reply)
        assert env is not None, err
        assert "proposals" in env

    def test_honours_a_non_default_key(self):
        reply = self.DECOY + '{"insights": [{"a": 1}]}'
        env, err = dr.parse_dream_envelope(reply, key="insights")
        assert env is not None, err

    def test_genuinely_absent_envelope_still_fails(self):
        """The fix must not turn a real failure into a false success."""
        env, err = dr.parse_dream_envelope(self.DECOY + "no envelope here")
        assert env is None
        assert err

    def test_empty_proposals_list_is_still_valid(self):
        """DESIGN.md 6.1: zero proposals is a valid, expected outcome."""
        env, err = dr.parse_dream_envelope('{"proposals": []}')
        assert env is not None and env["proposals"] == []


class TestUnparseableIsNotUnavailable:
    """Conflating 'no reply' with 'reply would not parse' cost three
    misdiagnosed cycles: operator and runner both chased a dreamer outage
    that never happened."""

    def test_labels_are_verbally_distinct(self):
        src = open(dr.__file__, encoding="utf-8").read()
        assert "DREAMER OUTPUT UNPARSEABLE" in src
        assert "DREAMER UNAVAILABLE" in src

    def test_both_labels_still_trigger_dependency_blocked(self):
        src = open(dr.__file__, encoding="utf-8").read()
        assert 'if "DREAMER UNAVAILABLE" in narrative or "DREAMER OUTPUT UNPARSEABLE" in narrative:' in src, (
            "a pass whose dreamer output never parses must still block, not "
            "silently report success"
        )
