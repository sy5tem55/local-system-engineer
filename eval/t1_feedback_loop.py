"""
T1 feedback-loop logic for the T0/T1 coding-eval suite
(eval/test-suite-coding-t0t1-v1.md).

SCOPE, DELIBERATELY NARROW (2026-07-07): this module implements ONLY the
piece of "How to run" step 3 that is genuinely new relative to T0 -- the
pytest-feedback retry loop. It does NOT drive a real model. The suite's
original harness (`v35_harness.py`, which connected to goethe_mcp over MCP
streamable-HTTP and drove llama-server's chat-completions API with the real
tool schema) was never committed to this repo and its /tmp/lse/ scratch copy
has since been cleared -- see eval/eval-report-v8.md for the only surviving
description of what it did, and CURRENT-STATE.md's "Outstanding" note. This
module was written without it, on purpose: the retry-loop control flow (run
the model, run the tests, decide whether to stop or feed failures back, do
that up to K times) does not need a live model to be written or verified
correctly, and re-deriving it from a decoupled `propose_fn` callback means it
can be unit-tested now and wired into a real harness later without changes
to this file.

Wiring this into an actual model-driving harness means providing a
`propose_fn(history) -> TurnResult` that:
  1. Sends `history` (OpenAI-style message list) to the model via its real
     tool schema (pulled live from goethe_mcp, same pattern the retired
     harness used).
  2. Lets the model call execute_command / read_file / write_file etc. for
     real against the task directory, through goethe.py's normal safety
     gates -- this module never touches the task's source files itself,
     only its test file (read-only, via pytest).
  3. Returns a TurnResult once the model declares itself done (or gives up).

run_pytest() is the concrete, already-verified half: confirmed working
against a live scratch task 2026-07-07 (stub -> NotImplementedError failures
with full file:line/assertion detail, exit 1; fixed implementation -> exit
0, clean pass). This is what replaced `mcp__goethe__run_tests` in the doc's
corrected "How to run" section -- run_tests turned out to be a hardcoded
5-scope allowlist with no arbitrary-path parameter, unusable here.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class TurnResult:
    """What propose_fn must return after driving one model turn for a task."""

    done: bool
    # Free-form note for the harness's own bookkeeping (e.g. tool-call count,
    # wall-clock time for this turn) -- not interpreted by this module.
    meta: dict = field(default_factory=dict)


@dataclass
class RoundLog:
    attempt: int          # 0 = first attempt, 1..K = retry rounds
    passed: bool
    test_output: str


@dataclass
class T1Outcome:
    task_dir: str
    passed: bool
    iterations_used: int       # retry rounds actually consumed; 0 = passed on first attempt
    max_iterations: int        # K, the ceiling (retry rounds, not total attempts)
    final_test_output: str
    hit_budget: bool           # True iff it never passed and exhausted K
    rounds: list[RoundLog] = field(default_factory=list)


@dataclass
class T0Outcome:
    task_dir: str
    passed: bool
    test_output: str


PropposeFn = Callable[[list[dict]], TurnResult]


def run_pytest(task_dir: str, timeout_s: int = 60) -> tuple[bool, str]:
    """Run pytest with the interpreter executing this harness.

    Returns (passed, raw_combined_stdout_stderr). This is the mechanism
    eval/test-suite-coding-t0t1-v1.md's corrected "How to run" section
    specifies in place of mcp__goethe__run_tests.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short"],
            cwd=task_dir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {timeout_s}s running pytest in {task_dir!r}"
    except FileNotFoundError as exc:
        return False, f"ERROR: could not run pytest in {task_dir!r}: {exc}"

    output = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode == 0, output


def build_feedback_turn(test_output: str) -> dict:
    """The exact next-turn content fed back to the model on a T1 retry.

    Kept as its own function (not inlined) so wording changes are a one-line
    diff and testable in isolation from the loop control flow.
    """
    content = (
        "Tests are failing. Raw pytest output:\n\n"
        f"{test_output}\n\n"
        "Fix the issue and let me know when you're done. Do not modify the "
        "test file."
    )
    return {"role": "user", "content": content}


def run_t0_task(
    task_dir: str,
    task_prompt: str,
    propose_fn: PropposeFn,
    test_timeout_s: int = 60,
) -> T0Outcome:
    """T0 protocol: single shot, zero scaffold, no feedback.

    The model never sees the test result -- it's run exactly once, after the
    model stops, for scoring only. Included alongside run_t1_task() for
    symmetry with "How to run" steps 2/3, since it shares run_pytest().
    """
    history = [{"role": "user", "content": task_prompt}]
    propose_fn(history)  # model works; harness-specific tool execution happens inside propose_fn
    passed, output = run_pytest(task_dir, timeout_s=test_timeout_s)
    return T0Outcome(task_dir=task_dir, passed=passed, test_output=output)


def run_t1_task(
    task_dir: str,
    task_prompt: str,
    propose_fn: PropposeFn,
    max_iterations: int,
    test_timeout_s: int = 60,
) -> T1Outcome:
    """T1 protocol: scaffold + verification loop.

    max_iterations is K per the doc's "K rationale" section: the number of
    RETRY rounds allowed after the first attempt, not the total attempt
    count. K=2 means up to 3 total attempts (1 initial + 2 retries). Stops
    early on the first clean pass regardless of K.

    propose_fn is called once per attempt (first try, then once per retry
    round) with the full running `history`. It is responsible for actually
    driving the model and letting it act on task_dir for real -- this
    function only decides whether to stop or keep going, and builds the
    feedback turn's content.
    """
    if max_iterations < 0:
        raise ValueError("max_iterations (K) must be >= 0")

    history: list[dict] = [{"role": "user", "content": task_prompt}]
    rounds: list[RoundLog] = []

    for attempt in range(max_iterations + 1):
        turn = propose_fn(history)
        history.append({"role": "assistant", "content": "", "declared_done": turn.done})

        passed, output = run_pytest(task_dir, timeout_s=test_timeout_s)
        rounds.append(RoundLog(attempt=attempt, passed=passed, test_output=output))

        if passed:
            return T1Outcome(
                task_dir=task_dir,
                passed=True,
                iterations_used=attempt,
                max_iterations=max_iterations,
                final_test_output=output,
                hit_budget=False,
                rounds=rounds,
            )

        if attempt >= max_iterations:
            return T1Outcome(
                task_dir=task_dir,
                passed=False,
                iterations_used=attempt,
                max_iterations=max_iterations,
                final_test_output=output,
                hit_budget=True,
                rounds=rounds,
            )

        history.append(build_feedback_turn(output))

    # Unreachable: the loop above always returns from inside the for-loop
    # body (either on a pass, or once attempt reaches max_iterations).
    raise RuntimeError("run_t1_task: loop exited without returning")
