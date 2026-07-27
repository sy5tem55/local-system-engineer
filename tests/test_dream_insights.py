"""
Unit tests for the TRAUM-INSIGHT cross-session insight pass (Thread 3,
Prompt 3.2 — tools/dream_runner.py's "insights" pass).

Covers, entirely offline (no live LLM, no Elasticsearch — every LLM call
goes through a monkeypatched `dream_runner.request_dream_envelope`):
  - parse_dream_envelope/request_dream_envelope's `key` generalization
    (Prompt 3.2 reuses the "proposals" envelope machinery with key=
    "insights" rather than duplicating it).
  - build_session_summaries()/_render_session_summaries(): manifest.db row
    -> compact summary, tools_used JSON parsing (incl. malformed JSON),
    the --insights-max-sessions-in-prompt cap.
  - Each of the four domain builders (_domain_command_frequency,
    _domain_failure_retry, _domain_tool_usage, _domain_automation_candidates):
    empty patterns -> None (no LLM call), non-empty -> (text, valid_refs).
  - _validate_insight_item(): the structural checks (observation length,
    proposed_change enum, cost_estimate, confidence range/type) AND the
    code-enforced verbatim-evidence rule (hallucinated evidence_refs are
    dropped; an insight with zero surviving refs is rejected outright;
    kb_fact/skill sub-objects are only kept when complete).
  - _insight_to_proposal(): kb-fact/skill insights become real
    index_to_kb/skill_record-shaped proposals that pass the shared
    validate_proposal_shape() gate; prompt-rule/tool-change never do.
  - _run_insight_domain(): a domain with no underlying data makes ZERO LLM
    calls; a domain with data makes exactly one, wires accepted insights
    into both the insights list and (where proposal-shaped) the proposals
    list.
  - run_pass_insights() end-to-end: null result when there's nothing to
    feed the model, the "## Cross-session insights" report.md section, and
    the one-call-per-domain contract (4 domains -> at most 4 LLM calls).

Only dream_runner is imported (not dream_apply).

Run: python3 -m pytest tests/test_dream_insights.py -q
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

def _make_cfg(**overrides):
    cfg = dr.DreamConfig(
        episode_dir="/tmp/episodes",
        dream_dir="/tmp/dreams",
        manifest_db="/tmp/manifest.db",
        es_url="http://fake-es.invalid:9200",
        tasks_db="/tmp/tasks.db",
        agent_log="/tmp/does-not-exist/agent_commands.log",
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
        pass_name="insights",
        dry_run=True,
    )
    return replace(cfg, **overrides) if overrides else cfg


def _row(session_id, tools_used=None, n_calls=10, n_errors=0,
         start_ts="2026-06-01T10:00:00", end_ts="2026-06-01T10:30:00"):
    """manifest.db 'sessions' row stand-in -- build_session_summaries only
    ever does bracket access, so a plain dict is a legal sqlite3.Row
    substitute for tests."""
    return {
        "session_id": session_id,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "n_calls": n_calls,
        "n_errors": n_errors,
        "tools_used": json.dumps(tools_used if tools_used is not None else ["execute_command"]),
    }


SAMPLE_PATTERNS = {
    "command_frequency": [{"command": "ls -la", "count": 5}, {"command": "cat foo.txt", "count": 3}],
    "failure_retry": [{"command": "flaky-cmd", "rc": 1, "fail_line": 4, "retry_line": 6, "gap_lines": 2}],
    "tool_usage_by_week": {"CMD": {"2026-W23": 3, "2026-W24": 0}, "SEARCH": {"2026-W23": 1, "2026-W24": 2}},
    "weeks_observed": ["2026-W23", "2026-W24"],
    "automation_candidates": [{
        "sequence": ["ls -la", "cat foo.txt", "rm foo.txt"],
        "length": 3, "session_count": 3, "sessions": [0, 1, 2], "occurrence_count": 3,
    }],
}

EMPTY_PATTERNS = {
    "command_frequency": [], "failure_retry": [], "tool_usage_by_week": {},
    "weeks_observed": [], "automation_candidates": [],
}


# --- 1. envelope key generalization -----------------------------------------

class TestEnvelopeKeyGeneralization:
    def test_parse_dream_envelope_default_key_unchanged(self):
        env, err = dr.parse_dream_envelope('{"proposals": []}')
        assert err == ""
        assert env == {"proposals": []}

    def test_parse_dream_envelope_insights_key(self):
        env, err = dr.parse_dream_envelope('{"insights": [{"a": 1}]}', key="insights")
        assert err == ""
        assert env == {"insights": [{"a": 1}]}

    def test_parse_dream_envelope_wrong_key_present_rejected(self):
        env, err = dr.parse_dream_envelope('{"proposals": []}', key="insights")
        assert env is None
        assert "insights" in err


# --- 2. session summaries -----------------------------------------------------

class TestBuildSessionSummaries:
    def test_builds_summary_fields(self):
        rows = [_row("s1", tools_used=["execute_command", "search_kb"], n_calls=7, n_errors=1)]
        summaries = dr.build_session_summaries(rows, max_sessions=10)
        assert len(summaries) == 1
        s = summaries[0]
        assert s["session_id"] == "s1"
        assert s["n_calls"] == 7
        assert s["n_errors"] == 1
        assert s["tools_used"] == ["execute_command", "search_kb"]

    def test_caps_at_max_sessions(self):
        rows = [_row(f"s{i}") for i in range(5)]
        summaries = dr.build_session_summaries(rows, max_sessions=2)
        assert len(summaries) == 2

    def test_malformed_tools_used_json_degrades_to_empty_list(self):
        rows = [{"session_id": "s1", "start_ts": "t0", "end_ts": "t1",
                  "n_calls": 1, "n_errors": 0, "tools_used": "not json"}]
        summaries = dr.build_session_summaries(rows, max_sessions=10)
        assert summaries[0]["tools_used"] == []

    def test_render_empty_summaries(self):
        text = dr._render_session_summaries([])
        assert "no undreamed session summaries" in text

    def test_render_nonempty_includes_session_id(self):
        summaries = dr.build_session_summaries([_row("s1")], max_sessions=10)
        text = dr._render_session_summaries(summaries)
        assert "s1" in text


# --- 3. domain builders --------------------------------------------------------

class TestDomainBuilders:
    def test_command_frequency_empty_is_none(self):
        assert dr._domain_command_frequency(EMPTY_PATTERNS) is None

    def test_command_frequency_returns_text_and_refs(self):
        text, refs = dr._domain_command_frequency(SAMPLE_PATTERNS)
        assert "ls -la" in text
        assert refs == {"ls -la", "cat foo.txt"}

    def test_failure_retry_empty_is_none(self):
        assert dr._domain_failure_retry(EMPTY_PATTERNS) is None

    def test_failure_retry_returns_text_and_refs(self):
        text, refs = dr._domain_failure_retry(SAMPLE_PATTERNS)
        assert "flaky-cmd" in text
        assert refs == {"flaky-cmd"}

    def test_tool_usage_empty_is_none(self):
        assert dr._domain_tool_usage(EMPTY_PATTERNS) is None

    def test_tool_usage_refs_include_tags_and_weeks(self):
        text, refs = dr._domain_tool_usage(SAMPLE_PATTERNS)
        assert "CMD" in text and "SEARCH" in text
        assert refs == {"CMD", "SEARCH", "2026-W23", "2026-W24"}

    def test_automation_candidates_empty_is_none(self):
        assert dr._domain_automation_candidates(EMPTY_PATTERNS) is None

    def test_automation_candidates_refs_include_full_and_step_forms(self):
        text, refs = dr._domain_automation_candidates(SAMPLE_PATTERNS)
        assert "ls -la -> cat foo.txt -> rm foo.txt" in refs
        assert "ls -la" in refs and "cat foo.txt" in refs and "rm foo.txt" in refs


# --- 4. _validate_insight_item -------------------------------------------------

def _valid_item(**overrides):
    item = {
        "observation": "This is a sufficiently long observation about a pattern.",
        "evidence_refs": ["ls -la"],
        "cost_estimate": "a few wasted calls",
        "proposed_change": "prompt-rule",
        "confidence": 0.6,
    }
    item.update(overrides)
    return item


class TestValidateInsightItem:
    VALID_REFS = {"ls -la", "cat foo.txt"}

    def test_accepts_well_formed_item(self):
        cleaned, reason = dr._validate_insight_item(_valid_item(), self.VALID_REFS)
        assert reason is None
        assert cleaned["observation"].startswith("This is")
        assert cleaned["evidence_refs"] == ["ls -la"]

    def test_rejects_non_dict(self):
        cleaned, reason = dr._validate_insight_item("not a dict", self.VALID_REFS)
        assert cleaned is None and "not an object" in reason

    def test_rejects_short_observation(self):
        cleaned, reason = dr._validate_insight_item(_valid_item(observation="short"), self.VALID_REFS)
        assert cleaned is None and "observation" in reason

    def test_rejects_unknown_proposed_change(self):
        cleaned, reason = dr._validate_insight_item(_valid_item(proposed_change="rewrite-everything"), self.VALID_REFS)
        assert cleaned is None and "proposed_change" in reason

    def test_rejects_missing_cost_estimate(self):
        cleaned, reason = dr._validate_insight_item(_valid_item(cost_estimate=""), self.VALID_REFS)
        assert cleaned is None and "cost_estimate" in reason

    @pytest.mark.parametrize("bad_confidence", [1.5, -0.1, "high", None, True, False])
    def test_rejects_bad_confidence(self, bad_confidence):
        cleaned, reason = dr._validate_insight_item(_valid_item(confidence=bad_confidence), self.VALID_REFS)
        assert cleaned is None and "confidence" in reason

    def test_rejects_evidence_refs_not_a_list(self):
        cleaned, reason = dr._validate_insight_item(_valid_item(evidence_refs="ls -la"), self.VALID_REFS)
        assert cleaned is None and "evidence_refs" in reason

    def test_drops_hallucinated_refs_keeps_verified_ones(self):
        item = _valid_item(evidence_refs=["ls -la", "totally made up command"])
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert reason is None
        assert cleaned["evidence_refs"] == ["ls -la"]

    def test_rejects_when_zero_refs_verify(self):
        item = _valid_item(evidence_refs=["totally made up command"])
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert cleaned is None and "evidence_refs" in reason

    def test_kb_fact_detail_kept_when_complete(self):
        item = _valid_item(proposed_change="kb-fact", kb_fact={
            "title": "t", "content": "c", "topic": "general", "volatility": "fast",
        })
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert reason is None
        assert cleaned["kb_fact"] == {"title": "t", "content": "c", "topic": "general", "volatility": "fast"}

    def test_kb_fact_invalid_volatility_falls_back_to_slow(self):
        item = _valid_item(proposed_change="kb-fact", kb_fact={
            "title": "t", "content": "c", "topic": "general", "volatility": "bogus",
        })
        cleaned, _ = dr._validate_insight_item(item, self.VALID_REFS)
        assert cleaned["kb_fact"]["volatility"] == "slow"

    def test_kb_fact_detail_dropped_when_incomplete(self):
        item = _valid_item(proposed_change="kb-fact", kb_fact={"title": "", "content": ""})
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert reason is None
        assert "kb_fact" not in cleaned

    def test_skill_detail_kept_when_complete(self):
        item = _valid_item(proposed_change="skill", skill={
            "task": "t", "procedure": "p", "verification": "v",
            "preconditions": "", "failure_modes": "", "occupation": "sre",
        })
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert reason is None
        assert cleaned["skill"]["task"] == "t"
        assert cleaned["skill"]["occupation"] == "sre"

    def test_skill_detail_dropped_when_incomplete(self):
        item = _valid_item(proposed_change="skill", skill={"task": "t"})
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert reason is None
        assert "skill" not in cleaned

    def test_skill_occupation_defaults_when_blank(self):
        item = _valid_item(proposed_change="skill", skill={
            "task": "t", "procedure": "p", "verification": "v",
        })
        cleaned, _ = dr._validate_insight_item(item, self.VALID_REFS)
        assert cleaned["skill"]["occupation"] == "Local System Engineer"

    # -- prompt_rule sub-object (Prompt 3.6; gap closed by Prompt 3.9's own
    # "insight schema validation" ask -- kb_fact/skill each already had a
    # kept-when-complete/dropped-when-incomplete pair above, prompt_rule
    # had neither) --------------------------------------------------------

    def test_prompt_rule_detail_kept_when_complete(self):
        item = _valid_item(proposed_change="prompt-rule", prompt_rule={
            "rule": "Always run kb_verify before trusting stale docs.",
            "rationale": "Two sessions this month acted on an expired fact.",
            "section_hint": "ground-truth-before-action",
        })
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert reason is None
        assert cleaned["prompt_rule"] == {
            "rule": "Always run kb_verify before trusting stale docs.",
            "rationale": "Two sessions this month acted on an expired fact.",
            "section_hint": "ground-truth-before-action",
        }

    def test_prompt_rule_detail_dropped_when_incomplete(self):
        """Missing `rationale` (only `rule` present) -- same discipline as
        kb_fact/skill: the insight itself still validates (observation/
        evidence/etc. are all fine), but the incomplete detail sub-object
        is silently dropped rather than kept half-populated."""
        item = _valid_item(proposed_change="prompt-rule", prompt_rule={"rule": "Do the thing."})
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert reason is None
        assert "prompt_rule" not in cleaned

    def test_prompt_rule_detail_dropped_when_missing_entirely(self):
        item = _valid_item(proposed_change="prompt-rule")  # no prompt_rule key at all
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert reason is None
        assert "prompt_rule" not in cleaned

    def test_prompt_rule_section_hint_defaults_when_blank(self):
        item = _valid_item(proposed_change="prompt-rule", prompt_rule={
            "rule": "Do the thing.", "rationale": "Because reasons.", "section_hint": "",
        })
        cleaned, _ = dr._validate_insight_item(item, self.VALID_REFS)
        assert cleaned["prompt_rule"]["section_hint"] == "(unspecified)"

    def test_prompt_rule_never_carries_a_target_file_key(self):
        """dream_runner.py's own comment above the prompt-rule branch of
        _validate_insight_item: 'there is deliberately no target_file key
        read from the model here.' Even if a (malicious or confused) model
        reply includes one, it must not survive into the cleaned detail --
        the write target is fixed in code at proposal-generation time
        (_insight_to_proposal -> LEARNED_RULES_TARGET), never taken from
        model output, so there is no field here for a prompt-injected
        episode to steer."""
        item = _valid_item(proposed_change="prompt-rule", prompt_rule={
            "rule": "Do the thing.", "rationale": "Because reasons.",
            "target_file": "prompts/node4090-v0.6.0.md",  # must be ignored entirely
        })
        cleaned, reason = dr._validate_insight_item(item, self.VALID_REFS)
        assert reason is None
        assert "target_file" not in cleaned["prompt_rule"]


# --- 5. _insight_to_proposal ---------------------------------------------------

class TestInsightToProposal:
    def test_kb_fact_with_detail_becomes_index_to_kb_proposal(self):
        insight = {
            "observation": "obs", "evidence_refs": ["ls -la"], "cost_estimate": "x",
            "proposed_change": "kb-fact", "confidence": 0.7,
            "kb_fact": {"title": "T", "content": "C", "topic": "general", "volatility": "fast"},
        }
        p = dr._insight_to_proposal(insight, "command-frequency", "2026-07-12")
        assert p["type"] == "kb-fact"
        assert p["call"] == "index_to_kb"
        assert p["args"]["title"] == "T"
        assert p["args"]["content"] == "C"
        assert p["args"]["source_tier"] == "inferred"
        assert p["args"]["volatility"] == "fast"
        assert "provenance" not in p["args"]  # index_to_kb has no provenance param, DESIGN.md §6.2
        assert dr.validate_proposal_shape(p) is None

    def test_kb_fact_without_detail_is_none(self):
        insight = {
            "observation": "obs", "evidence_refs": ["ls -la"], "cost_estimate": "x",
            "proposed_change": "kb-fact", "confidence": 0.7,
        }
        assert dr._insight_to_proposal(insight, "command-frequency", "2026-07-12") is None

    def test_skill_with_detail_becomes_skill_record_proposal(self):
        insight = {
            "observation": "obs", "evidence_refs": ["ls -la"], "cost_estimate": "x",
            "proposed_change": "skill", "confidence": 0.7,
            "skill": {"task": "T", "procedure": "P", "verification": "V",
                       "preconditions": "", "failure_modes": "", "occupation": "sre"},
        }
        p = dr._insight_to_proposal(insight, "automation-candidates", "2026-07-12")
        assert p["type"] == "skill-candidate"
        assert p["call"] == "skill_record"
        assert p["args"]["provenance"] == "dream-2026-07-12"
        assert p["args"]["source_tier"] == "inferred"
        assert dr.validate_proposal_shape(p) is None

    @pytest.mark.parametrize("proposed_change", ["prompt-rule", "tool-change"])
    def test_non_proposal_shaped_changes_are_always_none(self, proposed_change):
        insight = {
            "observation": "obs", "evidence_refs": ["ls -la"], "cost_estimate": "x",
            "proposed_change": proposed_change, "confidence": 0.7,
        }
        assert dr._insight_to_proposal(insight, "command-frequency", "2026-07-12") is None

    def test_prompt_rule_with_detail_becomes_append_learned_rule_proposal(self):
        """The positive path the parametrized test above never exercises
        (it only ever passes an insight with NO prompt_rule key). Prompt
        3.9 gap: this is the one proposal-shaped branch of
        _insight_to_proposal that had zero test coverage of any kind."""
        insight = {
            "observation": "obs", "evidence_refs": ["ls -la"], "cost_estimate": "x",
            "proposed_change": "prompt-rule", "confidence": 0.7,
            "prompt_rule": {
                "rule": "Always run kb_verify before trusting stale docs.",
                "rationale": "Two sessions acted on an expired fact.",
                "section_hint": "ground-truth-before-action",
            },
        }
        p = dr._insight_to_proposal(insight, "tool-usage", "2026-07-12")
        assert p["type"] == "prompt-rule"
        assert p["call"] == "append_learned_rule"
        # target_file is the fixed module constant, not read from `insight`
        # at all (there is no such key on `insight` to read in the first
        # place -- see _validate_insight_item's own "no target_file key"
        # discipline, tested above).
        assert p["args"]["target_file"] == dr.LEARNED_RULES_TARGET == "prompts/learned-rules.md"
        assert p["args"]["rule"] == insight["prompt_rule"]["rule"]
        assert p["args"]["rationale"] == insight["prompt_rule"]["rationale"]
        assert p["args"]["provenance"] == "dream-2026-07-12"
        assert p["args"]["source_tier"] == "inferred"
        assert dr.validate_proposal_shape(p) is None

    def test_prompt_rule_without_detail_is_none(self):
        insight = {
            "observation": "obs", "evidence_refs": ["ls -la"], "cost_estimate": "x",
            "proposed_change": "prompt-rule", "confidence": 0.7,
        }
        assert dr._insight_to_proposal(insight, "command-frequency", "2026-07-12") is None


# --- 6. _run_insight_domain -----------------------------------------------------

class TestRunInsightDomain:
    def test_no_data_makes_zero_llm_calls(self, monkeypatch):
        called = []
        monkeypatch.setattr(dr, "request_dream_envelope",
                              lambda *a, **kw: called.append(1) or (None, "should not be called"))
        cfg = _make_cfg()
        insights, proposals, note = dr._run_insight_domain(
            cfg, "failure-retry", EMPTY_PATTERNS, "(none)", set(), "2026-07-12"
        )
        assert called == []
        assert insights == [] and proposals == []
        assert "no data" in note

    def test_with_data_makes_exactly_one_call_and_wires_proposal(self, monkeypatch):
        calls = []

        def fake(system_prompt, user_content, cfg, key="proposals"):
            calls.append((system_prompt, user_content, key))
            return {"insights": [{
                "observation": "ls -la dominates command frequency this run by a wide margin.",
                "evidence_refs": ["ls -la"],
                "cost_estimate": "trivial",
                "proposed_change": "kb-fact",
                "confidence": 0.5,
                "kb_fact": {"title": "T", "content": "C", "topic": "general", "volatility": "slow"},
            }]}, None

        monkeypatch.setattr(dr, "request_dream_envelope", fake)
        cfg = _make_cfg()
        insights, proposals, note = dr._run_insight_domain(
            cfg, "command-frequency", SAMPLE_PATTERNS, "(none)", set(), "2026-07-12"
        )
        assert len(calls) == 1
        assert calls[0][2] == "insights"
        assert len(insights) == 1
        assert len(proposals) == 1
        assert proposals[0]["type"] == "kb-fact"
        assert "1 insight(s) accepted" in note

    def test_envelope_failure_yields_empty_with_note(self, monkeypatch):
        monkeypatch.setattr(dr, "request_dream_envelope",
                              lambda *a, **kw: (None, "DREAMER UNAVAILABLE — down"))
        cfg = _make_cfg()
        insights, proposals, note = dr._run_insight_domain(
            cfg, "command-frequency", SAMPLE_PATTERNS, "(none)", set(), "2026-07-12"
        )
        assert insights == [] and proposals == []
        assert "DREAMER UNAVAILABLE" in note


# --- 7. run_pass_insights end-to-end --------------------------------------------

class TestRunPassInsightsEndToEnd:
    def test_null_result_when_nothing_to_feed(self, monkeypatch):
        monkeypatch.setattr(dr, "read_agent_log_window", lambda cfg: [])
        cfg = _make_cfg()
        proposals, narrative, null_record = dr.run_pass_insights(cfg, [], {}, [], [])
        assert proposals == []
        assert "Null result (PH3-2)" in narrative
        # Prompt 3.8: no patterns.json domain data and no session summaries
        # -- both bounded inputs were inspected and found empty.
        assert null_record["pass"] == "insights"
        assert null_record["looked"] is True
        assert null_record["reason"] == "no_data_to_feed"
        assert null_record["corpus_size"]["session_summaries"] == 0
        assert null_record["thresholds"]["insights_max_sessions_in_prompt"] == cfg.insights_max_sessions_in_prompt

    def test_registered_in_pass_funcs(self):
        assert dr.PASS_FUNCS["insights"] is dr.run_pass_insights

    def test_end_to_end_with_mocked_llm(self, monkeypatch):
        # 3 sessions, gap-separated, sharing a 3-command sequence -- same
        # fixture shape as test_dream_patterns.py's automation-candidate test.
        def block(day, hour):
            d = f"2026-06-{day:02d}"
            return [
                f"[{d} {hour}:00:00] CMD: ls -la (cwd=/tmp)",
                f"[{d} {hour}:00:01] DONE: rc=0 len=10",
                f"[{d} {hour}:00:02] CMD: cat foo.txt (cwd=/tmp)",
                f"[{d} {hour}:00:03] DONE: rc=0 len=5",
                f"[{d} {hour}:00:04] CMD: rm foo.txt (cwd=/tmp)",
                f"[{d} {hour}:00:05] DONE: rc=0 len=0",
            ]
        raw_lines = block(1, "10") + block(8, "11") + block(15, "09")
        monkeypatch.setattr(dr, "read_agent_log_window", lambda cfg: raw_lines)

        sessions = [_row("s1"), _row("s2")]
        calls = []

        def fake(system_prompt, user_content, cfg, key="proposals"):
            calls.append(system_prompt)
            if "AUTOMATION-CANDIDATES" in system_prompt:
                return {"insights": [{
                    "observation": "The 3-command cleanup sequence recurs across all 3 sessions.",
                    "evidence_refs": ["ls -la -> cat foo.txt -> rm foo.txt", "hallucinated ref"],
                    "cost_estimate": "9 manual calls collapse to 1 script call",
                    "proposed_change": "skill",
                    "confidence": 0.75,
                    "skill": {"task": "cleanup", "procedure": "p", "verification": "v",
                               "preconditions": "", "failure_modes": "", "occupation": "sre"},
                }]}, None
            return {"insights": []}, None

        monkeypatch.setattr(dr, "request_dream_envelope", fake)
        cfg = _make_cfg(patterns_session_gap_minutes=60)
        proposals, narrative, null_record = dr.run_pass_insights(cfg, sessions, {}, [], [])

        # 4 domains total; failure-retry has no data (no failing commands in
        # this fixture) so it must be skipped -- at most 3 real calls.
        assert len(calls) <= len(dr.INSIGHT_DOMAINS)
        assert len(proposals) == 1
        assert proposals[0]["type"] == "skill-candidate"
        assert dr.validate_proposal_shape(proposals[0]) is None
        # A real insight was accepted this run -> non-null.
        assert null_record is None
        assert "## Cross-session insights" in narrative
        assert "flowed into proposals.jsonl" in narrative
        assert "hallucinated ref" not in narrative


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
