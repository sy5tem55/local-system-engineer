"""
Smoke test for EscalationWrapper — all external HTTP calls are mocked.

Tests:
  1. reset() — no KB hit
  2. reset() — KB hit injected into observation
  3. step() — first-attempt solve, no KB bonus
  4. step() — first-attempt solve + KB hit -> +2 bonus
  5. step() x2 identical -> stagnation-breaking prompt injected
  6. step() x3 identical -> web search fires, truncated=False
  7. web-assisted attempt fails -> escalation, terminated=True
  8. _cosine() helper
  9. _assess_context_quality()

Run: python3 scripts/test_escalation_wrapper.py
"""

import sys
import os
import math
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(__file__))

from lse_challenge_env import LSEChallengeEnv
from escalation_wrapper import (
    EscalationWrapper,
    _cosine,
    _assess_context_quality,
)

PASS = "✅"
FAIL = "❌"

# ── Override DB path to sandbox copy ─────────────────────────────────────────
_orig_env_init = LSEChallengeEnv.__init__
def _patched_env_init(self, db_path="/sessions/epic-sleepy-dijkstra/tmp/test_challenges.db", **kw):
    _orig_env_init(self, db_path=db_path, **kw)
LSEChallengeEnv.__init__ = _patched_env_init


def check(label, condition):
    print(f"  {'✅' if condition else '❌'}  {label}")
    return condition


def _stagnation_embed(text):
    """Always returns same unit vector -> cosine=1.0 for any pair."""
    return [1.0 / math.sqrt(3)] * 3


def make_wrapper(kb_result=None, embed_fn=None):
    env = LSEChallengeEnv(render_mode="ansi")
    w = EscalationWrapper(env, verbose=False)
    w._embed = MagicMock(side_effect=embed_fn or _stagnation_embed)
    w._search_kb = MagicMock(return_value=kb_result)
    w._index_to_kb = MagicMock()
    w._record_error = MagicMock()
    w._searxng_search = MagicMock(return_value="Web result: check firewall logs")
    w._call_claude = MagicMock(
        return_value='```json\n{"devices": [{"ip":"192.168.1.50","mac":"aa:bb:cc:01"}]}\n```'
    )
    return w


CORRECT = """
```json
{
  "devices": [
    {"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:01", "hostname": "pfsense"},
    {"ip": "192.168.1.57", "mac": "aa:bb:cc:dd:ee:02", "hostname": "LUCIFER"},
    {"ip": "192.168.1.90", "mac": "1c:af:4a:04:5f:b6", "hostname": "Samsung-TV"},
    {"ip": "192.168.1.100","mac": "aa:bb:cc:dd:ee:04", "hostname": "ha-pi"},
    {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:05", "hostname": "node2"}
  ]
}
```
"""

BAD = '```json\n{"devices": []}\n```'


def run_tests():
    print("\n=== EscalationWrapper smoke test ===\n")
    errors = 0

    # ── 1: reset, no KB hit ───────────────────────────────────────────────────
    print("1. reset() — no KB hit")
    w = make_wrapper(kb_result=None)
    obs, info = w.reset(options={"challenge_id": "pf-t1-001", "model_id": "qwen-27b"})
    ok  = check("obs has challenge key", "challenge" in obs)
    ok &= check("kb_context empty", obs["kb_context"] == "")
    ok &= check("_search_kb called once", w._search_kb.call_count == 1)
    ok &= check("_kb_assisted is False", w._kb_assisted is False)
    if not ok: errors += 1
    print()

    # ── 2: reset, KB hit ─────────────────────────────────────────────────────
    print("2. reset() — KB hit injected")
    w = make_wrapper(kb_result="Prior session: pfSense at 192.168.1.50")
    obs, info = w.reset(options={"challenge_id": "pf-t1-001", "model_id": "qwen-27b"})
    ok  = check("kb_context contains hit text", "192.168.1.50" in obs["kb_context"])
    ok &= check("_kb_assisted is True", w._kb_assisted is True)
    ok &= check("KB CONTEXT in challenge text", "KB CONTEXT" in obs["challenge"])
    if not ok: errors += 1
    print()

    # ── 3: solve attempt 1, no KB bonus ──────────────────────────────────────
    print("3. step() — correct response, attempt 1 -> terminated, reward=13.0")
    w = make_wrapper(kb_result=None)
    w.reset(options={"challenge_id": "pf-t1-001", "model_id": "qwen-27b"})
    obs, reward, terminated, truncated, info = w.step(CORRECT)
    ok  = check("terminated == True", terminated is True)
    ok &= check("truncated == False", truncated is False)
    ok &= check("reward == 13.0", reward == 13.0)
    ok &= check("info['escalated'] == False", info.get("escalated") is False)
    ok &= check("_index_to_kb called (solution indexed)", w._index_to_kb.call_count >= 1)
    if not ok: errors += 1
    print()

    # ── 4: solve + KB hit -> +2 bonus ────────────────────────────────────────
    print("4. step() — correct response + KB hit -> reward=15.0")
    w = make_wrapper(kb_result="KB context: pfSense at 192.168.1.50")
    w.reset(options={"challenge_id": "pf-t1-001", "model_id": "qwen-27b"})
    _, reward, terminated, _, _ = w.step(CORRECT)
    ok  = check("terminated == True", terminated is True)
    ok &= check("reward == 15.0 (13 + 2 KB bonus)", reward == 15.0)
    if not ok: errors += 1
    print()

    # ── 5: stagnation x2 -> frame-break injected ─────────────────────────────
    print("5. step() x2 identical -> stagnation-breaking prompt in obs")
    w = make_wrapper()
    w.reset(options={"challenge_id": "pf-t1-001", "model_id": "qwen-27b"})
    w.step(BAD)                                      # attempt 1
    obs2, _, t2, tr2, _ = w.step(BAD)               # attempt 2: stagnation_count=1
    ok  = check("not terminated", t2 is False)
    ok &= check("not truncated", tr2 is False)
    ok &= check("STAGNATION DETECTED in challenge", "STAGNATION DETECTED" in obs2["challenge"])
    ok &= check("_stagnation_injected is True", w._stagnation_injected is True)
    if not ok: errors += 1
    print()

    # ── 6: stagnation x3 -> web search fires ─────────────────────────────────
    print("6. step() x3 identical -> web search fires, episode still open")
    w = make_wrapper()
    w.reset(options={"challenge_id": "pf-t1-001", "model_id": "qwen-27b"})
    w.step(BAD)
    w.step(BAD)
    obs3, r3, t3, tr3, info3 = w.step(BAD)          # stagnation_count=2 -> web
    ok  = check("not terminated", t3 is False)
    ok &= check("truncated=False (web keeps episode open)", tr3 is False)
    ok &= check("_searxng_search called", w._searxng_search.call_count >= 1)
    ok &= check("web result in obs['kb_context']", "Web result" in obs3["kb_context"])
    ok &= check("_index_to_kb called (web result indexed)", w._index_to_kb.call_count >= 1)
    ok &= check("reward == 0.0", r3 == 0.0)
    ok &= check("info['web_assist'] == True", info3.get("web_assist") is True)
    if not ok: errors += 1
    print()

    # ── 7: web-assisted attempt fails -> escalation ───────────────────────────
    # Reward breakdown: -5 escalation + 1 indexing + 2 context quality = -2
    # ("assert" appears in "assertion not satisfied" -> _assess_context_quality -> "good")
    print("7. web-assisted attempt fails -> escalation, reward=-2.0 (-5+1+2)")
    w = make_wrapper()
    w.reset(options={"challenge_id": "pf-t1-001", "model_id": "qwen-27b"})
    w.step(BAD)
    w.step(BAD)
    w.step(BAD)                                      # web search
    _, r4, t4, tr4, info4 = w.step(BAD)             # escalation
    ok  = check("terminated == True", t4 is True)
    ok &= check("truncated == False", tr4 is False)
    ok &= check("reward == -2.0", r4 == -2.0)
    ok &= check("info['escalated'] == True", info4.get("escalated") is True)
    ok &= check("_call_claude called once", w._call_claude.call_count == 1)
    ok &= check("_record_error called", w._record_error.call_count >= 1)
    ok &= check("_index_to_kb called >=2 (web + escalation)", w._index_to_kb.call_count >= 2)
    if not ok: errors += 1
    print()

    # ── 8: _cosine helper ────────────────────────────────────────────────────
    print("8. _cosine() helper")
    ok  = check("identical -> 1.0", abs(_cosine([1,0,0],[1,0,0]) - 1.0) < 1e-9)
    ok &= check("orthogonal -> 0.0", abs(_cosine([1,0,0],[0,1,0])) < 1e-9)
    ok &= check("empty -> 0.0", _cosine([], []) == 0.0)
    ok &= check("mismatched len -> 0.0", _cosine([1,0],[0,1,0]) == 0.0)
    if not ok: errors += 1
    print()

    # ── 9: _assess_context_quality ───────────────────────────────────────────
    print("9. _assess_context_quality()")
    ok  = check("no attempts -> poor", _assess_context_quality([], []) == "poor")
    ok &= check("vague reasons -> poor",
                _assess_context_quality(["a","b"], ["timeout","timeout"]) == "poor")
    ok &= check("specific + 2 attempts -> good",
                _assess_context_quality(["a","b"], ["a1: NameError: port not found"]) == "good")
    if not ok: errors += 1
    print()

    # ── Summary ──────────────────────────────────────────────────────────────
    print("─" * 52)
    if errors == 0:
        print(f"  {PASS}  All tests passed")
    else:
        print(f"  {FAIL}  {errors} test group(s) had failures")
    print()
    return errors


if __name__ == "__main__":
    try:
        import gymnasium
    except ImportError:
        import subprocess
        subprocess.run(
            ["pip", "install", "gymnasium", "--break-system-packages", "-q"],
            check=True,
        )
    sys.exit(run_tests())
