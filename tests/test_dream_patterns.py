"""
Unit tests for the TRAUM-INSIGHT audit-log miner (Thread 3, Prompt 3.1 —
tools/dream_runner.py's "patterns" pass).

Covers, against synthetic agent_commands.log fixtures (no live filesystem
corpus, no Elasticsearch, no Ollama, no LLM call anywhere in the pass under
test):
  - parse_agent_log_lines(): compact tag-line format extraction (ts/tag/
    detail/cwd/rc) and structural skip of the 2-line "bootstrap era" block
    (corpus-audit.md (a)).
  - command_frequency(): count + deterministic tie-break ordering.
  - find_failure_retries(): failure->retry adjacency, in-window vs.
    out-of-window, and the "DONE with no preceding CMD" edge case.
  - tool_usage_by_week(): zero-filled tag x week matrix, DONE excluded.
  - infer_sessions(): inactivity-gap session boundary inference (the log
    carries no session_id of its own).
  - find_automation_candidates(): longest-first repeated-sequence mining,
    the min-sessions bar, and cross-length de-duplication (a qualifying
    longer sequence suppresses its own shorter sub-sequences).
  - run_pass_patterns() end-to-end: dry-run vs. --no-dry-run patterns.json
    write, and the two PH3-2 null-result paths (log missing, log present
    but zero parseable events).

Only dream_runner is imported (not dream_apply) so this file has no
dependency on the apply-gate side of TRAUM-ENGINE.

Run: python3 -m pytest tests/test_dream_patterns.py -q
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_runner as dr  # noqa: E402


# --- fixtures / helpers ------------------------------------------------------

def _make_cfg(agent_log="/tmp/does-not-exist/agent_commands.log", dream_dir="/tmp/dreams",
              dry_run=True, **overrides):
    """Minimal DreamConfig -- only agent_log/dream_dir/dry_run and whichever
    patterns_* fields a test cares about matter here; every other field just
    needs a legal value (patterns_* fields already default sanely on the
    dataclass itself)."""
    cfg = dr.DreamConfig(
        episode_dir="/tmp/episodes",
        dream_dir=dream_dir,
        manifest_db="/tmp/manifest.db",
        es_url="http://fake-es.invalid:9200",
        tasks_db="/tmp/tasks.db",
        agent_log=agent_log,
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
        pass_name="patterns",
        dry_run=dry_run,
    )
    return replace(cfg, **overrides) if overrides else cfg


def _cmd(ts, cmd, cwd="/tmp"):
    return f"[{ts}] CMD: {cmd} (cwd={cwd})"


def _done(ts, rc, length=10):
    return f"[{ts}] DONE: rc={rc} len={length}"


def _three_cmd_block(day, hour):
    """One inferred 'session' worth of lines: ls -la / cat foo.txt / rm
    foo.txt, each immediately DONE rc=0. Used by the automation-candidate
    tests below (3 of these, spaced days apart, form 3 distinct sessions
    all sharing the same 3-command sequence)."""
    d = f"2026-06-{day:02d}"
    return [
        _cmd(f"{d} {hour}:00:00", "ls -la"),
        _done(f"{d} {hour}:00:01", 0),
        _cmd(f"{d} {hour}:00:02", "cat foo.txt"),
        _done(f"{d} {hour}:00:03", 0),
        _cmd(f"{d} {hour}:00:04", "rm foo.txt"),
        _done(f"{d} {hour}:00:05", 0),
    ]


BOOTSTRAP_BLOCK = [
    "[2026-05-23 22:12:51] ▶ COMMAND",
    '  cmd : find /home/sy5/ -name "Qwen3.6-27B-Q5_K_M.gguf" 2>/dev/null',
    "  cwd : /home/sy5",
    "─" * 20,
]


# --- 1. parse_agent_log_lines -----------------------------------------------

class TestParseAgentLogLines:
    def test_skips_bootstrap_era_block(self):
        lines = BOOTSTRAP_BLOCK + [_cmd("2026-06-01 10:00:00", "ls -la")]
        events = dr.parse_agent_log_lines(lines)
        assert len(events) == 1
        assert events[0]["tag"] == "CMD"

    def test_extracts_ts_tag_detail_cwd(self):
        lines = [_cmd("2026-06-01 10:00:00", "ls -la", cwd="/opt/local-se")]
        events = dr.parse_agent_log_lines(lines)
        e = events[0]
        assert e["ts"] == "2026-06-01 10:00:00"
        assert e["tag"] == "CMD"
        assert e["detail"] == "ls -la"
        assert e["cwd"] == "/opt/local-se"
        assert e["line_no"] == 1

    def test_line_without_cwd_suffix(self):
        lines = ["[2026-06-01 10:00:00] SEARCH: llama.cpp latest stable release max=5"]
        events = dr.parse_agent_log_lines(lines)
        assert events[0]["cwd"] is None
        assert events[0]["detail"] == "llama.cpp latest stable release max=5"

    def test_done_line_parses_rc(self):
        events = dr.parse_agent_log_lines([_done("2026-06-01 10:00:01", 1)])
        assert events[0]["tag"] == "DONE"
        assert events[0]["rc"] == 1

    def test_done_line_malformed_rc_is_none(self):
        events = dr.parse_agent_log_lines(["[2026-06-01 10:00:01] DONE: something odd"])
        assert events[0]["rc"] is None

    def test_unrecognized_lines_are_skipped_not_raised(self):
        lines = ["not a log line at all", "", "   "]
        assert dr.parse_agent_log_lines(lines) == []

    def test_line_no_is_1_indexed_position_in_input(self):
        lines = ["garbage", _cmd("2026-06-01 10:00:00", "ls -la")]
        events = dr.parse_agent_log_lines(lines)
        assert events[0]["line_no"] == 2


# --- 2. command_frequency ----------------------------------------------------

class TestCommandFrequency:
    def test_counts_and_orders_by_count_desc(self):
        lines = [_cmd("2026-06-01 10:00:00", "a"), _cmd("2026-06-01 10:00:01", "b"),
                  _cmd("2026-06-01 10:00:02", "a"), _cmd("2026-06-01 10:00:03", "a")]
        events = dr.parse_agent_log_lines(lines)
        freq = dr.command_frequency(events, top_n=10)
        assert freq[0] == {"command": "a", "count": 3}
        assert freq[1] == {"command": "b", "count": 1}

    def test_ties_broken_by_first_seen_order(self):
        lines = [_cmd("2026-06-01 10:00:00", "second-defined"),
                  _cmd("2026-06-01 10:00:01", "first-defined")]
        # both appear once each -- first-defined command text was seen
        # first only if it's genuinely first in the input; here
        # "second-defined" is issued first, so it must sort first despite
        # its lexically larger name.
        events = dr.parse_agent_log_lines(lines)
        freq = dr.command_frequency(events, top_n=10)
        assert [f["command"] for f in freq] == ["second-defined", "first-defined"]

    def test_ignores_non_cmd_tags(self):
        events = dr.parse_agent_log_lines([
            "[2026-06-01 10:00:00] SEARCH: something max=5",
            _done("2026-06-01 10:00:01", 0),
        ])
        assert dr.command_frequency(events, top_n=10) == []

    def test_top_n_caps_output(self):
        lines = [_cmd(f"2026-06-01 10:00:{i:02d}", f"cmd{i}") for i in range(5)]
        events = dr.parse_agent_log_lines(lines)
        assert len(dr.command_frequency(events, top_n=2)) == 2


# --- 3. find_failure_retries -------------------------------------------------

class TestFindFailureRetries:
    def test_retry_within_window_is_found(self):
        lines = [
            _cmd("2026-06-01 10:00:00", "flaky-cmd"),
            _done("2026-06-01 10:00:01", 1),
            _cmd("2026-06-01 10:00:02", "flaky-cmd"),
            _done("2026-06-01 10:00:03", 0),
        ]
        events = dr.parse_agent_log_lines(lines)
        retries = dr.find_failure_retries(events, window_lines=5)
        assert len(retries) == 1
        assert retries[0]["command"] == "flaky-cmd"
        assert retries[0]["rc"] == 1
        assert retries[0]["gap_lines"] == 1

    def test_retry_outside_window_is_not_found(self):
        lines = [
            _cmd("2026-06-01 10:00:00", "flaky-cmd"),
            _done("2026-06-01 10:00:01", 1),
        ]
        # pad with unrelated events pushing the retry past the window
        lines += [f"[2026-06-01 10:00:{i:02d}] SEARCH: filler {i}" for i in range(2, 10)]
        lines.append(_cmd("2026-06-01 10:00:59", "flaky-cmd"))
        events = dr.parse_agent_log_lines(lines)
        retries = dr.find_failure_retries(events, window_lines=3)
        assert retries == []

    def test_successful_command_is_not_a_failure(self):
        lines = [_cmd("2026-06-01 10:00:00", "ok-cmd"), _done("2026-06-01 10:00:01", 0),
                  _cmd("2026-06-01 10:00:02", "ok-cmd"), _done("2026-06-01 10:00:03", 0)]
        events = dr.parse_agent_log_lines(lines)
        assert dr.find_failure_retries(events, window_lines=10) == []

    def test_done_with_no_preceding_cmd_is_skipped_not_crashed(self):
        events = dr.parse_agent_log_lines([_done("2026-06-01 10:00:00", 1)])
        assert dr.find_failure_retries(events, window_lines=10) == []

    def test_different_command_after_failure_does_not_count_as_retry(self):
        lines = [_cmd("2026-06-01 10:00:00", "cmd-a"), _done("2026-06-01 10:00:01", 1),
                  _cmd("2026-06-01 10:00:02", "cmd-b")]
        events = dr.parse_agent_log_lines(lines)
        assert dr.find_failure_retries(events, window_lines=10) == []


# --- 4. tool_usage_by_week ---------------------------------------------------

class TestToolUsageByWeek:
    def test_zero_fills_every_tag_across_every_observed_week(self):
        lines = [
            "[2026-06-01 10:00:00] SEARCH: x max=5",   # 2026-W23
            "[2026-06-15 10:00:00] READ: /etc/hosts",  # 2026-W25 (SEARCH silent this week)
        ]
        events = dr.parse_agent_log_lines(lines)
        usage, weeks = dr.tool_usage_by_week(events)
        assert weeks == sorted(weeks)
        assert set(usage["SEARCH"]) == set(weeks)
        assert set(usage["READ"]) == set(weeks)
        # SEARCH fired in the first observed week, silent (zero) afterward
        assert usage["SEARCH"][weeks[0]] == 1
        assert usage["SEARCH"][weeks[-1]] == 0
        assert usage["READ"][weeks[0]] == 0
        assert usage["READ"][weeks[-1]] == 1

    def test_done_tag_excluded(self):
        events = dr.parse_agent_log_lines([
            _cmd("2026-06-01 10:00:00", "ls -la"), _done("2026-06-01 10:00:01", 0),
        ])
        usage, _weeks = dr.tool_usage_by_week(events)
        assert "DONE" not in usage
        assert "CMD" in usage


# --- 5. infer_sessions -------------------------------------------------------

class TestInferSessions:
    def test_single_session_when_no_gap_exceeds_threshold(self):
        lines = [_cmd("2026-06-01 10:00:00", "a"), _cmd("2026-06-01 10:05:00", "b")]
        events = dr.parse_agent_log_lines(lines)
        sessions = dr.infer_sessions(events, gap_minutes=30)
        assert len(sessions) == 1
        assert len(sessions[0]) == 2

    def test_splits_on_gap_exceeding_threshold(self):
        lines = [_cmd("2026-06-01 10:00:00", "a"), _cmd("2026-06-01 12:00:00", "b")]
        events = dr.parse_agent_log_lines(lines)
        sessions = dr.infer_sessions(events, gap_minutes=30)
        assert len(sessions) == 2

    def test_gap_exactly_at_threshold_does_not_split(self):
        # 30 minutes apart, threshold 30 -- strictly-greater-than semantics
        lines = [_cmd("2026-06-01 10:00:00", "a"), _cmd("2026-06-01 10:30:00", "b")]
        events = dr.parse_agent_log_lines(lines)
        sessions = dr.infer_sessions(events, gap_minutes=30)
        assert len(sessions) == 1

    def test_empty_events_yields_no_sessions(self):
        assert dr.infer_sessions([], gap_minutes=30) == []


# --- 6. find_automation_candidates -------------------------------------------

class TestFindAutomationCandidates:
    def test_finds_sequence_recurring_across_min_sessions(self):
        command_lists = [
            ["ls -la", "cat foo.txt", "rm foo.txt"],
            ["ls -la", "cat foo.txt", "rm foo.txt"],
            ["ls -la", "cat foo.txt", "rm foo.txt"],
        ]
        candidates = dr.find_automation_candidates(
            command_lists, min_len=3, max_len=8, min_sessions=3
        )
        assert len(candidates) == 1
        c = candidates[0]
        assert c["sequence"] == ["ls -la", "cat foo.txt", "rm foo.txt"]
        assert c["session_count"] == 3
        assert c["sessions"] == [0, 1, 2]

    def test_below_min_sessions_bar_is_not_reported(self):
        command_lists = [
            ["ls -la", "cat foo.txt", "rm foo.txt"],
            ["ls -la", "cat foo.txt", "rm foo.txt"],
        ]
        candidates = dr.find_automation_candidates(
            command_lists, min_len=3, max_len=8, min_sessions=3
        )
        assert candidates == []

    def test_longer_match_suppresses_nested_shorter_duplicate(self):
        # a 4-command sequence recurs across 3 sessions -- the nested
        # 3-command sub-sequence should NOT also be reported separately.
        command_lists = [
            ["a", "b", "c", "d"],
            ["a", "b", "c", "d"],
            ["a", "b", "c", "d"],
        ]
        candidates = dr.find_automation_candidates(
            command_lists, min_len=3, max_len=8, min_sessions=3
        )
        assert len(candidates) == 1
        assert candidates[0]["sequence"] == ["a", "b", "c", "d"]
        assert candidates[0]["length"] == 4

    def test_below_min_len_is_never_considered(self):
        command_lists = [["a", "b"], ["a", "b"], ["a", "b"]]
        candidates = dr.find_automation_candidates(
            command_lists, min_len=3, max_len=8, min_sessions=3
        )
        assert candidates == []

    def test_sequences_only_within_a_session_not_across(self):
        # "b","c" bridges session 0's tail and session 1's head only if
        # sessions were concatenated -- they must NOT be, since each
        # command_list is already one session's own ordered commands.
        command_lists = [["a", "b"], ["c", "d"]]
        candidates = dr.find_automation_candidates(
            command_lists, min_len=2, max_len=8, min_sessions=1
        )
        sequences = {tuple(c["sequence"]) for c in candidates}
        assert ("b", "c") not in sequences
        assert ("a", "b") in sequences
        assert ("c", "d") in sequences


# --- 7. run_pass_patterns end-to-end ------------------------------------------

class TestRunPassPatternsEndToEnd:
    def _write_log(self, tmp_path):
        lines = _three_cmd_block(1, "10") + _three_cmd_block(8, "11") + _three_cmd_block(15, "09")
        log_path = tmp_path / "agent_commands.log"
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(log_path)

    def test_null_result_when_log_missing(self, tmp_path):
        cfg = _make_cfg(agent_log=str(tmp_path / "nope.log"), dream_dir=str(tmp_path / "dreams"))
        proposals, narrative, null_record = dr.run_pass_patterns(cfg, [], {}, [], [])
        assert proposals == []
        assert "Null result (PH3-2)" in narrative
        assert "not found or empty" in narrative
        # Prompt 3.8: structured null_record — "didn't look" (log never
        # opened, corpus_size is all zeros), not "looked and found nothing".
        assert null_record["pass"] == "patterns"
        assert null_record["result"] == "null"
        assert null_record["looked"] is False
        assert null_record["reason"] == "log_missing_or_empty"
        assert null_record["corpus_size"]["raw_lines"] == 0
        assert null_record["thresholds"]["patterns_min_sequence_len"] == cfg.patterns_min_sequence_len

    def test_null_result_when_log_has_only_bootstrap_lines(self, tmp_path):
        log_path = tmp_path / "agent_commands.log"
        log_path.write_text("\n".join(BOOTSTRAP_BLOCK) + "\n", encoding="utf-8")
        cfg = _make_cfg(agent_log=str(log_path), dream_dir=str(tmp_path / "dreams"))
        proposals, narrative, null_record = dr.run_pass_patterns(cfg, [], {}, [], [])
        assert proposals == []
        assert "Null result (PH3-2)" in narrative
        assert "zero compact-tag-line events" in narrative
        assert null_record["looked"] is True
        assert null_record["reason"] == "no_matching_events"
        assert null_record["corpus_size"]["raw_lines"] > 0
        assert null_record["corpus_size"]["events"] == 0

    def test_dry_run_prints_json_and_writes_nothing(self, tmp_path, capsys):
        log_path = self._write_log(tmp_path)
        dream_dir = tmp_path / "dreams"
        cfg = _make_cfg(agent_log=log_path, dream_dir=str(dream_dir), dry_run=True,
                         patterns_session_gap_minutes=60)
        proposals, narrative, null_record = dr.run_pass_patterns(cfg, [], {}, [], [])
        assert proposals == []
        assert not dream_dir.exists()
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["sessions_inferred"] == 3
        assert len(payload["automation_candidates"]) == 1
        assert "Written to" in narrative
        # Real findings this run (1 automation candidate) -> non-null.
        assert null_record is None

    def test_no_dry_run_writes_patterns_json_to_disk(self, tmp_path):
        log_path = self._write_log(tmp_path)
        dream_dir = tmp_path / "dreams"
        cfg = _make_cfg(agent_log=log_path, dream_dir=str(dream_dir), dry_run=False,
                         patterns_session_gap_minutes=60)
        proposals, narrative, null_record = dr.run_pass_patterns(cfg, [], {}, [], [])
        assert proposals == []
        assert null_record is None
        written = list(dream_dir.glob("*/patterns.json"))
        assert len(written) == 1
        payload = json.loads(written[0].read_text(encoding="utf-8"))
        assert payload["sessions_inferred"] == 3
        assert payload["automation_candidates"][0]["sequence"] == [
            "ls -la", "cat foo.txt", "rm foo.txt"
        ]

    def test_patterns_out_override(self, tmp_path):
        log_path = self._write_log(tmp_path)
        out_path = tmp_path / "custom" / "patterns.json"
        cfg = _make_cfg(agent_log=log_path, dream_dir=str(tmp_path / "dreams"), dry_run=False,
                         patterns_session_gap_minutes=60, patterns_out=str(out_path))
        dr.run_pass_patterns(cfg, [], {}, [], [])
        assert out_path.exists()

    def test_generates_zero_proposals_always(self, tmp_path):
        """patterns is a raw-analytics pass, not a KB-write proposal
        generator (DESIGN.md §6.2's four proposal types don't include it) --
        proposals must be [] regardless of what was found."""
        log_path = self._write_log(tmp_path)
        cfg = _make_cfg(agent_log=log_path, dream_dir=str(tmp_path / "dreams"),
                         patterns_session_gap_minutes=60)
        proposals, _narrative, _null_record = dr.run_pass_patterns(cfg, [], {}, [], [])
        assert proposals == []

    def test_null_result_when_all_domains_empty_but_events_present(self, tmp_path):
        """A window that parses (events > 0) but mines zero findings across
        ALL four sub-passes is a distinct null shape from log-missing or
        no-matching-events above: looked=True (Prompt 3.8's "nothing there",
        not "didn't look") since raw_lines/events are both non-zero.

        command_frequency and automation_candidates only ever look at
        CMD-tagged events (command_frequency() / session_command_lists());
        tool_usage_by_week() explicitly excludes the DONE tag ("DONE is
        CMD's own completion marker, not a distinct tool" -- its own
        docstring); failure_retry needs a CMD before it can pair a failing
        DONE with a retry. A log with ONLY unpaired DONE lines (no CMD
        ever) therefore mines zero rows in all four -- a fixture that
        actually exercises this branch, not a NOTE/other-tag line, which
        would still populate tool_usage_by_week."""
        log_path = tmp_path / "agent_commands.log"
        log_path.write_text(
            "[2026-06-01 10:00:00] DONE: rc=0 len=5\n"
            "[2026-06-01 10:05:00] DONE: rc=0 len=5\n",
            encoding="utf-8",
        )
        cfg = _make_cfg(agent_log=str(log_path), dream_dir=str(tmp_path / "dreams"),
                         patterns_session_gap_minutes=60)
        proposals, narrative, null_record = dr.run_pass_patterns(cfg, [], {}, [], [])
        assert proposals == []
        assert null_record is not None
        assert null_record["reason"] == "all_domains_empty"
        assert null_record["looked"] is True
        assert null_record["corpus_size"]["events"] == 2
        assert "Null result (PH3-2)" in narrative
        assert "all four sub-passes" in narrative

    def test_registered_in_pass_funcs(self):
        assert dr.PASS_FUNCS["patterns"] is dr.run_pass_patterns


# --- 8. patterns.json determinism (Prompt 3.9) ---------------------------------

class TestPatternsJsonDeterminism:
    """Prompt 3.9's own named test: 'patterns.json determinism (fixed
    fixture log -> fixed output)'. mine_patterns() is already documented
    as a pure function (module comment above parse_agent_log_lines: "no
    file I/O, no network, no randomness, no LLM call"); write_patterns_json
    wraps it with one non-deterministic field, generated_at (datetime.now()
    at write time) -- these tests pin BOTH: the pure in-memory mining is
    byte-identical run to run, and the on-disk patterns.json is identical
    run to run once generated_at is excluded."""

    def _write_log(self, tmp_path):
        lines = _three_cmd_block(1, "10") + _three_cmd_block(8, "11") + _three_cmd_block(15, "09")
        log_path = tmp_path / "agent_commands.log"
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(log_path)

    def test_mine_patterns_is_pure(self, tmp_path):
        log_path = self._write_log(tmp_path)
        cfg = _make_cfg(agent_log=log_path, patterns_session_gap_minutes=60)
        raw_lines = dr.read_agent_log_window(cfg)
        events = dr.parse_agent_log_lines(raw_lines)
        result_1 = dr.mine_patterns(events, cfg)
        result_2 = dr.mine_patterns(events, cfg)
        assert result_1 == result_2

    def test_write_patterns_json_deterministic_modulo_generated_at(self, tmp_path):
        log_path = self._write_log(tmp_path)
        dream_dir_1 = tmp_path / "dreams1"
        dream_dir_2 = tmp_path / "dreams2"
        cfg_1 = _make_cfg(agent_log=log_path, dream_dir=str(dream_dir_1), dry_run=False,
                           patterns_session_gap_minutes=60)
        cfg_2 = _make_cfg(agent_log=log_path, dream_dir=str(dream_dir_2), dry_run=False,
                           patterns_session_gap_minutes=60)
        dr.run_pass_patterns(cfg_1, [], {}, [], [])
        dr.run_pass_patterns(cfg_2, [], {}, [], [])

        written_1 = list(dream_dir_1.glob("*/patterns.json"))
        written_2 = list(dream_dir_2.glob("*/patterns.json"))
        assert len(written_1) == 1 and len(written_2) == 1
        payload_1 = json.loads(written_1[0].read_text(encoding="utf-8"))
        payload_2 = json.loads(written_2[0].read_text(encoding="utf-8"))

        # generated_at is the ONE field allowed to differ -- it is a
        # wall-clock write timestamp, not mined data (write_patterns_json's
        # own docstring: "payload = {'generated_at': ..., **patterns}").
        assert "generated_at" in payload_1 and "generated_at" in payload_2
        del payload_1["generated_at"]
        del payload_2["generated_at"]
        assert payload_1 == payload_2

    def test_different_fixture_produces_different_output(self, tmp_path):
        """Sanity control for the two tests above: this ISN'T a test that
        always trivially passes (e.g. because of a bug that made every run
        return {} regardless of input) -- a genuinely different fixture log
        must mine a genuinely different result."""
        log_path_a = self._write_log(tmp_path)
        log_path_b = tmp_path / "other_agent_commands.log"
        log_path_b.write_text(
            "\n".join(_three_cmd_block(1, "10")) + "\n", encoding="utf-8"
        )
        cfg_a = _make_cfg(agent_log=log_path_a, patterns_session_gap_minutes=60)
        cfg_b = _make_cfg(agent_log=str(log_path_b), patterns_session_gap_minutes=60)
        events_a = dr.parse_agent_log_lines(dr.read_agent_log_window(cfg_a))
        events_b = dr.parse_agent_log_lines(dr.read_agent_log_window(cfg_b))
        result_a = dr.mine_patterns(events_a, cfg_a)
        result_b = dr.mine_patterns(events_b, cfg_b)
        assert result_a != result_b
        assert result_a["sessions_inferred"] == 3
        assert result_b["sessions_inferred"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# --- redact_log_text (Thread 4 prerequisite: agent-log secret redaction) ----
# The Thread 3 close's live run surfaced a plaintext password in a repeated
# `sshpass -p` command in agent_commands.log; redaction now happens at parse
# time inside parse_agent_log_lines() so no downstream consumer (frequency
# table, patterns.json, insights LLM prompt) ever sees the raw secret.

class TestRedactLogText:

    def test_sshpass_password_flag_redacted(self):
        out = dr.redact_log_text("sshpass -p 'Sup3rSecret!' ssh lse-admin@node3090 uptime")
        assert "Sup3rSecret!" not in out
        assert "[REDACTED:cli-credential]" in out
        assert out.startswith("sshpass -p ")
        assert out.endswith("ssh lse-admin@node3090 uptime")

    def test_bearer_token_redacted(self):
        out = dr.redact_log_text('curl -H "Authorization: Bearer abc123.def-456" http://host/')
        assert "abc123" not in out
        assert "[REDACTED:bearer-token]" in out

    def test_assignment_style_secret_redacted(self):
        out = dr.redact_log_text("export PFSENSE_API_KEY=abcdef123456789012 && run-thing")
        assert "abcdef123456789012" not in out
        assert out.startswith("export PFSENSE_API_KEY=")
        assert "[REDACTED:pattern-match]" in out

    def test_innocent_single_letter_flags_untouched(self):
        # `-u` (sort/python) deliberately NOT matched -- redacting its argument
        # would corrupt the frequency table for innocent commands.
        for cmd in ("sort -u /tmp/list.txt", "python -u script.py --verbose",
                    "ls -la /opt/local-se"):
            assert dr.redact_log_text(cmd) == cmd

    def test_empty_string_safe(self):
        assert dr.redact_log_text("") == ""

    def test_parse_agent_log_lines_applies_redaction(self):
        lines = [_cmd("2026-07-01 10:00:00", "sshpass -p hunter2secret ssh node3090 uptime"),
                 _done("2026-07-01 10:00:01", 0)]
        events = dr.parse_agent_log_lines(lines)
        assert events[0]["tag"] == "CMD"
        assert "hunter2secret" not in events[0]["detail"]
        assert "[REDACTED:cli-credential]" in events[0]["detail"]

    def test_frequency_table_counts_redacted_command_as_one(self):
        # Identical raw commands redact to identical strings, so the count
        # survives redaction (3 occurrences -> one entry, count 3).
        lines = []
        for i in range(3):
            lines.append(_cmd(f"2026-07-01 10:0{i}:00", "sshpass -p hunter2secret ssh node uptime"))
            lines.append(_done(f"2026-07-01 10:0{i}:30", 0))
        events = dr.parse_agent_log_lines(lines)
        freq = dr.command_frequency(events, top_n=10)
        assert len(freq) == 1 and freq[0]["count"] == 3
        assert "hunter2secret" not in freq[0]["command"]
