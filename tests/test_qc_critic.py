"""
Unit tests for tools/qc_critic.py -- the adversarial QC critic (Part 2A of
the 2026-08-12 TRAUM feedback-loop work).

Covers:
  1. Parsing tolerates <think> blocks, code fences, and surrounding prose
     -- same noise dream_runner.parse_dream_envelope tolerates.
  2. Every failure mode (empty reply, bad JSON, unknown verdict, missing
     reason, ERROR:/BUDGET_EXHAUSTED: from the LLM cascade, a raised
     exception) fails OPEN to "keep", never silently and never as
     "reject".                                            [load-bearing]
  3. Hazard D: run_qc_critic and everything it calls contain no write path
     -- proven by grepping the module source for TraumState/record_proposals/
     sqlite3.connect / es.update / es.index, not just by reading the
     docstring's claim.                                   [load-bearing]
  4. Hazard E: non-diagnosis proposals are skipped, not critiqued.
  5. format_proposal_for_critique surfaces the mechanical rule verdict when
     given one, and says "none fired (novel)" when not.

Run:
    /home/sy5/owui/bin/python3 -m pytest tests/test_qc_critic.py -v
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import qc_critic as qc  # noqa: E402


# ---------------------------------------------------------------------------
# parse_critic_reply -- happy path + noise tolerance
# ---------------------------------------------------------------------------

def test_parse_plain_json():
    r = qc.parse_critic_reply('{"verdict": "reject", "reason": "circular resolution"}')
    assert r == {"verdict": "reject", "reason": "circular resolution"}


def test_parse_strips_think_block():
    reply = '<think>let me consider...</think>{"verdict": "keep", "reason": "no objection found"}'
    r = qc.parse_critic_reply(reply)
    assert r["verdict"] == "keep"
    assert r["reason"] == "no objection found"


def test_parse_strips_code_fence():
    reply = '```json\n{"verdict": "needs_work", "reason": "resolution too thin"}\n```'
    r = qc.parse_critic_reply(reply)
    assert r["verdict"] == "needs_work"


def test_parse_tolerates_surrounding_prose():
    reply = 'Here is my verdict:\n{"verdict": "reject", "reason": "third-party fact, not ours"}\nDone.'
    r = qc.parse_critic_reply(reply)
    assert r["verdict"] == "reject"


# ---------------------------------------------------------------------------
# Fail-open behavior -- load-bearing
# ---------------------------------------------------------------------------

def test_empty_reply_fails_open_to_keep():
    r = qc.parse_critic_reply("")
    assert r["verdict"] == "keep"
    assert "empty" in r["reason"]


def test_malformed_json_fails_open_to_keep():
    r = qc.parse_critic_reply("{not valid json at all")
    assert r["verdict"] == "keep"


def test_unknown_verdict_fails_open_to_keep():
    r = qc.parse_critic_reply('{"verdict": "approve", "reason": "looks fine"}')
    assert r["verdict"] == "keep"
    assert "unknown verdict" in r["reason"]


def test_missing_reason_fails_open_to_keep():
    """A verdict with no reason cannot be audited by a human -- must not
    pass through as a bare 'reject' with nothing to check it against."""
    r = qc.parse_critic_reply('{"verdict": "reject"}')
    assert r["verdict"] == "keep"
    assert "no reason" in r["reason"]


def test_truncated_think_block_fails_open_to_keep():
    r = qc.parse_critic_reply("<think>still thinking, ran out of budget")
    assert r["verdict"] == "keep"


def test_llm_cascade_error_fails_open_to_keep():
    def _erroring_llm(system_prompt, user_content):
        return "ERROR: dreamer circuit breaker open"
    result = qc.critique_proposal({"args": {"error_text": "x"}}, _erroring_llm)
    assert result["verdict"] == "keep"
    assert "critic call failed" in result["reason"]


def test_llm_budget_exhausted_fails_open_to_keep():
    def _budget_llm(system_prompt, user_content):
        return "BUDGET_EXHAUSTED: max_llm_calls reached"
    result = qc.critique_proposal({"args": {"error_text": "x"}}, _budget_llm)
    assert result["verdict"] == "keep"


def test_raised_exception_fails_open_to_keep():
    def _boom(system_prompt, user_content):
        raise TimeoutError("cascade timed out")
    result = qc.critique_proposal({"args": {"error_text": "x"}}, _boom)
    assert result["verdict"] == "keep"
    assert "critic call raised" in result["reason"]


# ---------------------------------------------------------------------------
# Hazard D -- no write path exists in this module, proven not assumed
# ---------------------------------------------------------------------------

def test_module_has_no_write_path():
    """Grep the actual CODE (not the module docstring's own prose, which
    legitimately names these terms to explain the guarantee) for real
    call/import sites."""
    src = (REPO_ROOT / "tools" / "qc_critic.py").read_text()
    # Strip the leading module docstring so its prose can't false-positive
    # the check -- code starts after the second """ delimiter.
    assert src.startswith('"""')
    _, _, code_only = src[3:].partition('"""')
    forbidden_call_sites = [
        "record_proposals(", "TraumState(", "import traum_state",
        "from traum_state", "es.update(", "es.index(", "sqlite3.connect(",
        "\"INSERT INTO", "'INSERT INTO",
    ]
    for token in forbidden_call_sites:
        assert token not in code_only, f"qc_critic.py must never contain {token!r} (Hazard D)"


def test_run_qc_critic_returns_verdicts_only_never_mutates_input():
    proposals = [
        {"proposal_id": "prp_1", "type": "diagnosis",
         "args": {"error_text": "boom", "resolution": "fix it"}},
    ]
    snapshot = [dict(p) for p in proposals]

    def _fake_llm(system_prompt, user_content):
        return '{"verdict": "keep", "reason": "no objection"}'

    results, counts = qc.run_qc_critic(proposals, _fake_llm)
    assert proposals == snapshot  # untouched
    assert counts == {"keep": 1, "needs_work": 0, "reject": 0}
    assert results[0]["proposal_id"] == "prp_1"
    assert results[0]["verdict"] == "keep"


# ---------------------------------------------------------------------------
# Hazard E -- scope to diagnosis
# ---------------------------------------------------------------------------

def test_non_diagnosis_proposals_are_skipped():
    proposals = [
        {"proposal_id": "prp_dedup", "type": "dedup", "args": {}},
        {"proposal_id": "prp_diag", "type": "diagnosis", "args": {"error_text": "x"}},
    ]
    calls = []

    def _fake_llm(system_prompt, user_content):
        calls.append(user_content)
        return '{"verdict": "keep", "reason": "fine"}'

    results, counts = qc.run_qc_critic(proposals, _fake_llm)
    assert len(results) == 1
    assert results[0]["proposal_id"] == "prp_diag"
    assert len(calls) == 1  # the dedup proposal never reached the critic


# ---------------------------------------------------------------------------
# format_proposal_for_critique
# ---------------------------------------------------------------------------

def test_format_includes_rule_verdict_when_given():
    text = qc.format_proposal_for_critique(
        {"args": {"error_text": "x"}}, prior_rule_verdict="R1: SUPERSEDED by prp_x (APPLIED)")
    assert "R1: SUPERSEDED by prp_x (APPLIED)" in text


def test_format_says_novel_when_no_rule_fired():
    text = qc.format_proposal_for_critique({"args": {"error_text": "x"}})
    assert "none fired (novel)" in text
