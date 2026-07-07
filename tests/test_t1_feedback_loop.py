"""
Real (non-mocked) unit tests for eval/t1_feedback_loop.py.

"Real" in the sense that matters here: propose_fn implementations below
actually write files into a scratch task directory (tmp_path), and
run_t1_task/run_t0_task actually invoke a real `python3 -m pytest`
subprocess against that directory each round -- nothing about the
pass/fail signal is mocked or hand-constructed. Only the "model" itself
(what would normally be an MCP-driven llama-server chat-completions call)
is a stand-in, since this module is deliberately decoupled from that (see
eval/t1_feedback_loop.py's module docstring for why).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from t1_feedback_loop import (  # noqa: E402
    TurnResult,
    run_pytest,
    run_t0_task,
    run_t1_task,
)

STUB = '''def is_palindrome(s: str) -> bool:
    raise NotImplementedError
'''

WRONG_FIX = '''def is_palindrome(s: str) -> bool:
    return s == s[::-1]  # fails on "A man, a plan..." -- case/punctuation not handled
'''

CORRECT_FIX = '''import re

def is_palindrome(s: str) -> bool:
    cleaned = re.sub(r"[^a-z0-9]", "", s.lower())
    return cleaned == cleaned[::-1]
'''

TEST_FILE = '''from strings_utils import is_palindrome

def test_simple():
    assert is_palindrome("racecar")

def test_case_and_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama")

def test_false_case():
    assert not is_palindrome("hello")
'''


def _make_task(tmp_path, starting_code: str) -> str:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "strings_utils.py").write_text(starting_code)
    (task_dir / "test_strings_utils.py").write_text(TEST_FILE)
    return str(task_dir)


def test_run_pytest_reports_failure_with_detail(tmp_path):
    task_dir = _make_task(tmp_path, STUB)
    passed, output = run_pytest(task_dir)
    assert passed is False
    assert "NotImplementedError" in output
    assert "test_simple" in output


def test_run_pytest_reports_clean_pass(tmp_path):
    task_dir = _make_task(tmp_path, CORRECT_FIX)
    passed, output = run_pytest(task_dir)
    assert passed is True
    assert "3 passed" in output


def test_t1_passes_on_first_attempt_uses_zero_iterations(tmp_path):
    task_dir = _make_task(tmp_path, STUB)

    def propose_fn(history):
        # Simulate the model nailing it on the first try.
        Path(task_dir, "strings_utils.py").write_text(CORRECT_FIX)
        return TurnResult(done=True)

    outcome = run_t1_task(task_dir, "Implement is_palindrome.", propose_fn, max_iterations=2)
    assert outcome.passed is True
    assert outcome.iterations_used == 0
    assert outcome.hit_budget is False
    assert len(outcome.rounds) == 1


def test_t1_passes_after_one_retry_uses_one_iteration(tmp_path):
    task_dir = _make_task(tmp_path, STUB)
    calls = {"n": 0}

    def propose_fn(history):
        calls["n"] += 1
        if calls["n"] == 1:
            # First attempt: plausible-looking but wrong (case/punctuation bug).
            Path(task_dir, "strings_utils.py").write_text(WRONG_FIX)
        else:
            # Second attempt (after seeing the failure): correct fix.
            Path(task_dir, "strings_utils.py").write_text(CORRECT_FIX)
        return TurnResult(done=True)

    outcome = run_t1_task(task_dir, "Implement is_palindrome.", propose_fn, max_iterations=2)
    assert outcome.passed is True
    assert outcome.iterations_used == 1
    assert outcome.hit_budget is False
    assert len(outcome.rounds) == 2
    # First round must have actually failed with the punctuation case, proving
    # the feedback loop's "retry" branch -- not just the "pass" branch -- ran.
    assert outcome.rounds[0].passed is False
    assert "test_case_and_punctuation" in outcome.rounds[0].test_output
    assert outcome.rounds[1].passed is True


def test_t1_exhausts_budget_when_model_never_fixes_it(tmp_path):
    task_dir = _make_task(tmp_path, STUB)

    def propose_fn(history):
        # Simulate a model that keeps proposing the same wrong fix every round.
        Path(task_dir, "strings_utils.py").write_text(WRONG_FIX)
        return TurnResult(done=True)

    outcome = run_t1_task(task_dir, "Implement is_palindrome.", propose_fn, max_iterations=2)
    assert outcome.passed is False
    assert outcome.hit_budget is True
    assert outcome.iterations_used == 2          # ran attempt 0, 1, and 2 (K=2 retries)
    assert len(outcome.rounds) == 3               # 1 initial + 2 retries
    assert all(r.passed is False for r in outcome.rounds)


def test_t1_feedback_turn_is_actually_appended_to_history(tmp_path):
    task_dir = _make_task(tmp_path, STUB)
    seen_histories = []

    def propose_fn(history):
        seen_histories.append(len(history))
        Path(task_dir, "strings_utils.py").write_text(CORRECT_FIX if len(seen_histories) > 1 else WRONG_FIX)
        return TurnResult(done=True)

    run_t1_task(task_dir, "Implement is_palindrome.", propose_fn, max_iterations=1)
    # Round 1 sees just the task prompt (len=1). Round 2 must see the task
    # prompt + the failed round's assistant turn + the fed-back failure turn
    # (len=3) -- proving build_feedback_turn's output actually reaches the
    # model on the next call, not just that the loop "worked" overall.
    assert seen_histories == [1, 3]


def test_t0_never_retries_even_when_wrong(tmp_path):
    task_dir = _make_task(tmp_path, WRONG_FIX)
    call_count = {"n": 0}

    def propose_fn(history):
        call_count["n"] += 1
        return TurnResult(done=True)

    outcome = run_t0_task(task_dir, "Implement is_palindrome.", propose_fn)
    assert outcome.passed is False
    assert call_count["n"] == 1


def test_max_iterations_zero_means_single_shot_no_retries(tmp_path):
    task_dir = _make_task(tmp_path, STUB)
    calls = {"n": 0}

    def propose_fn(history):
        calls["n"] += 1
        return TurnResult(done=True)  # never fixes it

    outcome = run_t1_task(task_dir, "prompt", propose_fn, max_iterations=0)
    assert outcome.passed is False
    assert outcome.hit_budget is True
    assert outcome.iterations_used == 0
    assert calls["n"] == 1
