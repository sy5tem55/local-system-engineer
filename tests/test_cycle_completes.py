"""
Unit tests for SPEC-cycle-completes-2026-08 -- the three defects that kept a
full TRAUM cycle from ever finishing:

  Defect 1: error-cluster asked request_dream_envelope() for the two-array
            {"diagnoses": [...], "skill_candidates": [...]} envelope its own
            prompt describes, but validated the single-key "proposals"
            default -- every reply was rejected, in production, since the
            diagnosis type shipped.
  Defect 2: run-dream-cycle.sh handed every pass the WHOLE remaining cycle
            budget; one pass that legitimately used its time starved every
            pass behind it.
  Defect 3: a pass-level budget stop was recorded BLOCKED / error_type=
            DependencyBlocked -- indistinguishable from a real dependency
            failure to the operator, even though call_dream_llm's own
            request-level BUDGET_EXHAUSTED: handling already treats this as
            a deliberate stop, not a failure.

Plus the two minor §5/§8 hardening items (payload field, unterminated
<think> handling) and the §8 item 5 test-PATH fix (covered by tests/
conftest.py + test_ui_router.py's existing skip-vs-pass test, not repeated
here).

Covers spec §10 tests 1-5 (envelope), 6-7 (wall clock, against the actual
shipped tools/run-dream-cycle.sh text), 8-9 (budget reclassification via a
real dr.main() + real TraumState round trip), 10-11 (hardening).

Run: python3 -m pytest tests/test_cycle_completes.py -q
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_runner as dr  # noqa: E402
import traum_state as ts  # noqa: E402


def _cfg(**overrides):
    """Same minimal DreamConfig fixture as test_dream_guards.py."""
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
        pass_name="error-cluster",
        dry_run=True,
    )
    base.update(overrides)
    return dr.DreamConfig(**base)


# --- Defect 1 / Hazard A / Hazard B: two-key envelope contract --------------

class TestErrorClusterEnvelopeContract:
    """SPEC tests 1-5."""

    def test_1_only_diagnoses_populated_is_accepted(self):
        env, err = dr.parse_dream_envelope(
            '{"diagnoses": [{"error_text": "x"}], "skill_candidates": []}',
            keys=("diagnoses", "skill_candidates"),
        )
        assert env is not None, err
        assert env["diagnoses"][0]["error_text"] == "x"

    def test_2_only_skill_candidates_populated_is_accepted(self):
        """Hazard A -- validating only 'diagnoses' would silently drop this."""
        env, err = dr.parse_dream_envelope(
            '{"skill_candidates": [{"task": "y"}]}',
            keys=("diagnoses", "skill_candidates"),
        )
        assert env is not None, err
        assert env["skill_candidates"][0]["task"] == "y"

    def test_3_both_present_but_empty_is_a_valid_zero_result(self):
        env, err = dr.parse_dream_envelope(
            '{"diagnoses": [], "skill_candidates": []}',
            keys=("diagnoses", "skill_candidates"),
        )
        assert env is not None, err
        assert env["diagnoses"] == [] and env["skill_candidates"] == []

    def test_4_neither_key_is_rejected_naming_both(self):
        env, err = dr.parse_dream_envelope(
            '{"unrelated": []}', keys=("diagnoses", "skill_candidates"),
        )
        assert env is None
        assert "diagnoses" in err and "skill_candidates" in err

    def test_5_default_single_key_callers_are_unaffected(self):
        """Hazard B -- the multi-key opt-in must not become the new default
        for demote/dedup/insights, which still validate exactly one key."""
        # the envelope error-cluster's OWN prompt asks for, with no
        # "proposals" key -- every other (single-key, default) caller must
        # still reject it, proving the multi-key tolerance did not leak
        # into the shared default.
        env, err = dr.parse_dream_envelope(
            '{"diagnoses": [{"a": 1}], "skill_candidates": []}'
        )
        assert env is None
        assert "proposals" in err

        env, err = dr.parse_dream_envelope(
            '{"diagnoses": [{"a": 1}]}', key="insights",
        )
        assert env is None
        assert "insights" in err

    def test_error_cluster_call_site_opts_in_at_the_call_site_not_the_default(self):
        """Regression guard on Hazard B: only the error-cluster call site
        passes keys=; demote/dedup/insights must still call with the plain
        single-key default."""
        src = (REPO_ROOT / "tools" / "dream_runner.py").read_text()
        assert 'keys=("diagnoses", "skill_candidates")' in src
        # exactly one call site passes `keys=`
        assert src.count("keys=(\"diagnoses\", \"skill_candidates\")") == 1

    def test_draft_error_cluster_proposals_stages_a_diagnosis_only_reply(self, monkeypatch):
        """End-to-end through _draft_error_cluster_proposals: this is the
        exact call that was structurally incapable of emitting a proposal
        in production (SPEC §2)."""
        monkeypatch.setattr(
            dr, "request_dream_envelope",
            lambda *a, **kw: (
                {"diagnoses": [{
                    "error_text": "et", "context": "ctx", "interpretation": "interp",
                    "resolution": "res", "anti_response": "", "why": "why",
                }], "skill_candidates": []},
                None,
            ),
        )
        cfg = _cfg(pass_name="error-cluster")
        diagnoses, skills, note = dr._draft_error_cluster_proposals(
            cfg, [{"session_id": "s1", "tool": "t", "exit_class": "e",
                    "result_truncated": "r", "key": "ep1"}], [],
        )
        assert note is None
        assert len(diagnoses) == 1 and diagnoses[0]["type"] == "diagnosis"
        assert skills == []

    def test_request_dream_envelope_forwards_keys_and_names_both_in_retry(self, monkeypatch):
        """The corrective retry message must name the SAME keys the model
        was asked for the first time (mirrors the existing single-key
        behaviour tested by TestUnparseableIsNotUnavailable in
        test_dream_guards.py)."""
        replies = iter([
            '{"nonsense": true}',
            '{"diagnoses": [], "skill_candidates": [{"task": "t"}]}',
        ])
        seen_content = []

        def fake_call(system_prompt, content, cfg, no_think=True):
            seen_content.append(content)
            return next(replies)

        monkeypatch.setattr(dr, "call_dream_llm", fake_call)
        monkeypatch.setattr(dr, "_dream_llm_record", lambda **k: None)

        cfg = _cfg(pass_name="error-cluster")
        env, err = dr.request_dream_envelope(
            "sys", "user content", cfg, keys=("diagnoses", "skill_candidates"),
        )
        assert env is not None, err
        assert "diagnoses" in seen_content[1] and "skill_candidates" in seen_content[1]


# --- Defect 2 / Hazard C: per-pass wall-clock allocation ---------------------

class TestPerPassWallClockAllocation:
    """SPEC tests 6-7, exercised against the actual arithmetic shipped in
    tools/run-dream-cycle.sh (not a reimplementation) -- extracted verbatim
    and run under bash for a matrix of inputs."""

    @staticmethod
    def _extract_budget_formula() -> str:
        script = (REPO_ROOT / "tools" / "run-dream-cycle.sh").read_text()
        m = re.search(
            r'(passes_left=\$\(\( total_passes.*?\n(?:.*\n)*?  fi\n)',
            script,
        )
        assert m, "budget-share formula block not found in run-dream-cycle.sh"
        return m.group(1)

    def _pass_budget(self, remaining_seconds, total_passes, pass_index, floor=60):
        formula = self._extract_budget_formula()
        script = (
            f"PASS_FLOOR_SECONDS={floor}\n"
            f"total_passes={total_passes}\n"
            f"pass_index={pass_index}\n"
            f"remaining_seconds={remaining_seconds}\n"
            f"{formula}\n"
            "echo $pass_budget\n"
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        return int(result.stdout.strip())

    def test_6_first_pass_gets_a_share_not_the_whole_cycle(self):
        # 5 passes, 2700s remaining -> a share (~540s), not all 2700.
        budget = self._pass_budget(remaining_seconds=2700, total_passes=5, pass_index=1)
        assert budget == 540
        assert budget < 2700

    def test_6_an_early_finisher_returns_its_remainder_to_the_pool(self):
        # Pass 1 was budgeted 540s (2700/5) but actually only used 100s, so
        # by the time pass 2 starts only 2600s (not 2160s) has elapsed --
        # remaining_seconds is recomputed from the wall clock, not
        # decremented by the a-priori allocation. Pass 2's 1-of-4-remaining
        # share must reflect the LARGER remaining pool.
        naive_if_full_share_consumed = self._pass_budget(
            remaining_seconds=2700 - 540, total_passes=5, pass_index=2)
        actual_after_early_finish = self._pass_budget(
            remaining_seconds=2700 - 100, total_passes=5, pass_index=2)
        assert actual_after_early_finish > naive_if_full_share_consumed

    def test_7_slice_never_falls_below_the_floor_when_time_permits(self):
        # 90s left, 3 passes -> naive share is 30s, below the 60s floor, but
        # 90 > 60 so the floor is honoured by borrowing from later passes.
        budget = self._pass_budget(remaining_seconds=90, total_passes=3, pass_index=1, floor=60)
        assert budget == 60

    def test_7_last_pass_gets_what_is_genuinely_left_even_under_the_floor(self):
        # Only 45s left and it's the last pass -- there is nothing to
        # borrow from. Must get the real 45s, not be starved to 0 waiting
        # for a floor that isn't available, and not fabricate time that
        # doesn't exist.
        budget = self._pass_budget(remaining_seconds=45, total_passes=5, pass_index=5, floor=60)
        assert budget == 45

    def test_digest_still_takes_whatever_is_left_unallocated(self):
        """Digest is deliberately OUTSIDE the passes[] loop/allocation --
        SPEC §8 item 2: 'Digest keeps taking what is left.' Regression
        guard: the digest invocation must not have gained a
        --budget-max-wall-clock-s share computed the same way as a pass."""
        script = (REPO_ROOT / "tools" / "run-dream-cycle.sh").read_text()
        digest_block = script.split("refreshing operator digest")[1][:600]
        assert "pass_budget" not in digest_block
        assert "remaining_seconds" in digest_block

    def test_hazard_c_timeout_kill_after_still_present(self):
        script = (REPO_ROOT / "tools" / "run-dream-cycle.sh").read_text()
        assert "timeout --signal=TERM --kill-after=10s" in script


# --- Defect 3 / Hazard D / Hazard E: budget exhaustion is not a dependency --

class TestBudgetExhaustionReclassification:
    """SPEC tests 8-9, through the real dr.main() + a real TraumState db --
    same fault-injection pattern as TestMainFaultInjection in
    test_dream_crash_discipline.py."""

    def _run_main(self, tmp_path, monkeypatch, fake_pass):
        episode_dir = tmp_path / "episodes"
        dream_dir = tmp_path / "dreams"
        episode_dir.mkdir()
        dream_dir.mkdir()

        class _FakeES:
            def search(self, *a, **k):
                return {"hits": {"hits": []}}

        monkeypatch.setattr(dr, "es_client", lambda cfg: _FakeES())
        monkeypatch.setattr(dr._epidx, "build_manifest", lambda *a, **k: {"scanned": 0})
        monkeypatch.setattr(dr.dream_digest, "refresh_digest", lambda **k: None)
        monkeypatch.setitem(dr.PASS_FUNCS, "patterns", fake_pass)

        argv = [
            "--pass", "patterns",
            "--episode-dir", str(episode_dir),
            "--dream-dir", str(dream_dir),
            "--agent-log", str(tmp_path / "agent.log"),
            "--no-dry-run",
        ]
        rc = dr.main(argv)
        state_db = dream_dir / "traum-state.db"
        assert state_db.exists()
        return rc, ts.TraumState(str(state_db))

    def test_8_budget_exhaustion_with_proposals_is_succeeded(self, tmp_path, monkeypatch):
        captured = {}

        def fake_pass(cfg, sessions, episodes_by_session, kb_docs, error_docs):
            cfg.budget.truncated = True
            cfg.budget.truncation_reason = "session budget exhausted (50 >= 50)"
            captured["attempt_id"] = cfg.attempt_id
            proposal = {
                "type": "diagnosis", "call": "record_error",
                "args": {"error_text": "et", "context": "ctx",
                         "interpretation": "interp", "resolution": "res",
                         "anti_response": ""},
                "evidence": [], "why": "partial-but-real result",
            }
            return [proposal], "patterns pass: stopped early on budget.", None

        rc, state = self._run_main(tmp_path, monkeypatch, fake_pass)
        attempt = state.get_attempt(captured["attempt_id"])

        assert attempt["state"] == "SUCCEEDED", attempt
        assert attempt["error_type"] is None
        assert attempt["summary"]["budget_truncated"] is True
        assert attempt["summary"]["budget_truncation_reason"] == (
            "session budget exhausted (50 >= 50)"
        )

    def test_8_budget_exhaustion_without_proposals_is_null(self, tmp_path, monkeypatch):
        captured = {}

        def fake_pass(cfg, sessions, episodes_by_session, kb_docs, error_docs):
            cfg.budget.truncated = True
            cfg.budget.truncation_reason = "LLM-call budget exhausted (10 >= 10)"
            captured["attempt_id"] = cfg.attempt_id
            null_record = {
                "reason": "no_candidates_before_truncation", "looked": True,
                "corpus_size": 0, "thresholds": {},
            }
            return [], "patterns pass: stopped early on budget, nothing found yet.", null_record

        rc, state = self._run_main(tmp_path, monkeypatch, fake_pass)
        attempt = state.get_attempt(captured["attempt_id"])

        assert attempt["state"] == "NULL", attempt
        assert attempt["error_type"] is None
        assert attempt["summary"]["budget_truncated"] is True
        assert attempt["summary"]["budget_truncation_reason"] == (
            "LLM-call budget exhausted (10 >= 10)"
        )

    def test_9_a_real_dependency_failure_is_still_blocked(self, tmp_path, monkeypatch):
        """Hazard D: only the budget-exhaustion path changes. A genuine
        dependency failure (dreamer unavailable, nothing produced) must
        still come out BLOCKED / error_type=DependencyBlocked."""
        captured = {}

        def fake_pass(cfg, sessions, episodes_by_session, kb_docs, error_docs):
            captured["attempt_id"] = cfg.attempt_id
            return [], "DREAMER UNAVAILABLE — (no reply)", None

        rc, state = self._run_main(tmp_path, monkeypatch, fake_pass)
        attempt = state.get_attempt(captured["attempt_id"])

        assert attempt["state"] == "BLOCKED", attempt
        assert attempt["error_type"] == "DependencyBlocked"


# --- §5/§8 item 4: hardening --------------------------------------------------

class TestThinkingSuppressionHardening:
    def test_10_build_payload_carries_new_field_and_keeps_existing_ones(self):
        import json as _json
        cfg_content = "some content"
        payload = _json.loads(dr._build_payload("sys", cfg_content, no_think=True))
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert payload["thinking_budget_tokens"] == 0
        assert payload["messages"][-1]["content"].endswith("/no_think")

    def test_11_unterminated_think_block_names_truncation(self):
        reply = "<think>reasoning that never closes because the reply was cut off"
        env, err = dr.parse_dream_envelope(reply)
        assert env is None
        assert "truncat" in err.lower()
        assert "no JSON object in reply" not in err

    def test_11_unterminated_think_before_a_real_envelope_is_still_handled(self):
        """Content after an unterminated <think> is unreasoned-about and
        must not be scanned for a false-positive envelope."""
        reply = '<think>still thinking... {"proposals": [{"a": 1}]}'
        env, err = dr.parse_dream_envelope(reply)
        assert env is None
        assert "truncat" in err.lower()

    def test_terminated_think_block_is_unaffected(self):
        """Non-regression: a normal, properly-closed <think> block must
        still be stripped and the envelope after it still found."""
        reply = '<think>ordinary reasoning</think>\n{"proposals": []}'
        env, err = dr.parse_dream_envelope(reply)
        assert env is not None, err
        assert env["proposals"] == []
