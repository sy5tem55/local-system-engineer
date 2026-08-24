#!/usr/bin/env python3
"""Contract tests for planner v2 (Goethe v0.3.2) — atomized plans + tasks.db ledger.

Covers: envelope→ledger write (steps_json), the plan_step_done strike loop
(evidence gate, next-prompt handoff, block close), failed→revise routing,
revise-mode merge (done history preserved), per-step packaged_prompt fallback,
and the PLANNER_FORCE_URL Step-0 health-probed override.

No Elasticsearch and no LLM needed: _call_node_planner is monkeypatched with
canned v2 envelopes; TASKS_DB points at a per-test temp SQLite file.

Run on LUCIFER: /home/sy5/owui/bin/python3 -m pytest tests/test_planner_ledger.py -q
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe  # noqa: E402

GOOD_EVIDENCE = "jq '. | length' overrides.json -> 14 entries; file present at /tmp/overrides.json"

ENV_NEW = {
    "task_id": "dns00001",
    "intent": "plan",
    "goal_summary": "migrate pfSense DNS resolver to Pi-hole on sy5berry",
    "sessions_estimate": 3,
    "single_session": False,
    "confidence": "high",
    "abort_criteria": "stop if home.arpa resolution breaks for any static host",
    "steps": [
        {
            "n": 1,
            "what": "dump pfSense Unbound host overrides to overrides.json",
            "depends_on": [],
            "inputs": "pfSense REST API (read-only)",
            "output": "overrides.json",
            "web_calls": 0,
            "tool_calls": 2,
            "verify": "jq length overrides.json > 0",
            "packaged_prompt": "GOAL: DNS migration. STEP 1 ONLY: dump pfSense host "
            "overrides via pfsense_graphql to overrides.json. VERIFY: jq length > 0. "
            "STOP after this step.",
        },
        {
            "n": 2,
            "what": "install Pi-hole on sy5berry and import overrides.json",
            "depends_on": [1],
            "inputs": "overrides.json from step 1",
            "output": "pi-hole resolving imported names",
            "web_calls": 1,
            "tool_calls": 4,
            "verify": "dig @sy5berry.lan pfsense.home.arpa returns 192.168.1.50",
            "packaged_prompt": "GOAL: DNS migration. STEP 2 ONLY: import "
            "overrides.json into Pi-hole custom DNS. VERIFY: dig @sy5berry. "
            "STOP after this step.",
        },
    ],
}

ENV_REVISED = {
    "task_id": "dns00001",
    "intent": "plan",
    "goal_summary": "migrate pfSense DNS resolver to Pi-hole on sy5berry",
    "sessions_estimate": 2,
    "single_session": False,
    "confidence": "medium",
    "abort_criteria": "stop if home.arpa resolution breaks for any static host",
    "steps": [
        {
            "n": 2,
            "what": "fix Pi-hole FTL config then import overrides.json",
            "depends_on": [1],
            "inputs": "overrides.json from step 1",
            "output": "pi-hole resolving imported names",
            "web_calls": 1,
            "tool_calls": 4,
            "verify": "dig @sy5berry.lan pfsense.home.arpa returns 192.168.1.50",
            "packaged_prompt": "STEP 2 ONLY (revised): fix FTL config, re-import. STOP after.",
        },
        {
            "n": 3,
            "what": "point one test client at Pi-hole and validate",
            "depends_on": [2],
            "inputs": "working Pi-hole from step 2",
            "output": "validated client resolution",
            "web_calls": 0,
            "tool_calls": 3,
            "verify": "nslookup pfsense.home.arpa on test client → 192.168.1.50",
            "packaged_prompt": "STEP 3 ONLY: point test client, validate. STOP after.",
        },
    ],
}


@pytest.fixture()
def tools(monkeypatch, tmp_path):
    # ── Hermetic isolation (added 2026-07-29) ────────────────────────────────
    # These two lines exist because the suite silently stopped being offline.
    #
    # planner() resolves its backend from the PERSISTED Console selection
    # (goethe_planner_state) before falling back to the PLANNER_BACKEND valve.
    # An operator clicking "use" on Claude in the Goethe Console therefore
    # changed what EVERY un-parameterised planner() call does — including this
    # suite. The _call_node_planner monkeypatch below patches the LOCAL
    # backend, so the dispatcher routed straight past it to
    # _call_claude_planner, which shells out to `claude -p`: 16 tests × live
    # API calls × a 180s ceiling, burning real subscription quota, with results
    # depending on the state of a web UI.
    #
    # Point the state store at a temp path (the module honours this env var
    # precisely for isolation) and pin the valve. Do not remove either line —
    # without them this file is neither offline nor deterministic.
    monkeypatch.setenv("GOETHE_PLANNER_STATE_PATH", str(tmp_path / "planner-backend.json"))

    t = goethe.Tools()
    t.valves.LOG_FILE = str(tmp_path / "audit.log")
    t.valves.TASKS_DB = str(tmp_path / "tasks.db")
    t.valves.PLANNER_BACKEND = "local"
    # planner() auto-attaches KB material; that reaches Elasticsearch, which
    # this suite must not require. Stub it to a no-op passthrough.
    monkeypatch.setattr(
        t, "_augment_context_with_kb",
        lambda task, context="": context,
    )
    monkeypatch.setattr(
        t, "_call_node_planner",
        lambda task, context="", no_think=False: json.dumps(ENV_NEW),
    )
    return t


def plan_tid(result: str) -> str:
    """Extract the SERVER-generated ledger id from a planner() return."""
    import re

    m = re.search(r"task_id=([0-9a-f]{8})", result)
    assert m, f"no task_id in: {result[:200]}"
    return m.group(1)


def read_block(t, tid):
    conn = t._tasks_db()
    row = conn.execute(
        "SELECT status, plan, done_steps, next_prompt, steps_json "
        "FROM task_blocks WHERE task_id=?", (tid,),
    ).fetchone()
    conn.close()
    assert row, f"no block {tid}"
    return {
        "status": row[0], "plan": row[1], "done": row[2],
        "next_prompt": row[3], "steps": json.loads(row[4]),
    }


class TestPlannerNewPlan:
    def test_envelope_writes_step_ledger(self, tools):
        r = tools.planner("migrate DNS to pi-hole")
        assert "PLAN ENVELOPE accepted (new)" in r
        assert "steps=2 atomized" in r
        tid = plan_tid(r)
        # v0.3.3: model-supplied task_id (schema-example collision) is IGNORED
        assert tid != "dns00001"
        assert f"plan_step_done('{tid}', 1" in r
        b = read_block(tools, tid)
        assert b["status"] == "open"
        assert [s["status"] for s in b["steps"]] == ["pending", "pending"]
        assert "STEP 1 ONLY" in b["next_prompt"]
        assert "YOU ARE EXECUTING STEP 1 ONLY" in b["next_prompt"]

    def test_missing_per_step_prompt_gets_fallback(self, tools, monkeypatch):
        env = json.loads(json.dumps(ENV_NEW))
        for s in env["steps"]:
            s.pop("packaged_prompt")
        env.pop("task_id")
        monkeypatch.setattr(
            tools, "_call_node_planner",
            lambda task, context="", no_think=False: json.dumps(env),
        )
        r = tools.planner("migrate DNS to pi-hole")
        assert "PLAN ENVELOPE accepted" in r
        assert "YOU ARE EXECUTING STEP 1 ONLY" in r

    def test_invalid_mode_rejected(self, tools):
        assert "mode must be" in tools.planner("x", mode="bogus")

    def test_malformed_reply_retried_once_then_accepted(self, tools, monkeypatch):
        # v0.3.3: first reply is thinking-only garbage, retry succeeds.
        replies = iter(
            ["<think>let me plan this carefully...</think>", json.dumps(ENV_NEW)]
        )
        contexts = []

        def fake(task, context="", no_think=False):
            contexts.append(context)
            return next(replies)

        monkeypatch.setattr(tools, "_call_node_planner", fake)
        r = tools.planner("migrate DNS to pi-hole")
        assert "PLAN ENVELOPE accepted" in r
        assert len(contexts) == 2
        assert "PREVIOUS REPLY REJECTED" in contexts[1]

    def test_two_bad_replies_surface_unavailable(self, tools, monkeypatch):
        monkeypatch.setattr(
            tools, "_call_node_planner",
            lambda task, context="", no_think=False: '{"intent": "plan"}',
        )
        r = tools.planner("migrate DNS to pi-hole")
        assert "PLANNER UNAVAILABLE" in r
        assert "after retry" in r
        assert "no 'steps'" in r

    def test_revise_without_task_id_rejected(self, tools):
        assert "requires task_id" in tools.planner("x", mode="revise")


class TestPlanStepDone:
    def _plan(self, tools):
        return plan_tid(tools.planner("migrate DNS to pi-hole"))

    def test_strike_returns_next_step_with_ledger(self, tools):
        tid = self._plan(tools)
        r = tools.plan_step_done(tid, 1, evidence=GOOD_EVIDENCE)
        assert "Step 1 struck ✔ (1/2 done, 1 remaining)" in r
        assert "STEP 2 ONLY" in r
        assert "✔ step 1" in r  # ledger summary in the fresh-context prompt
        b = read_block(tools, tid)
        assert b["steps"][0]["status"] == "done"
        assert b["steps"][0]["evidence"] == GOOD_EVIDENCE
        assert "step 1" in b["done"]

    def test_thin_evidence_rejected(self, tools):
        tid = self._plan(tools)
        r = tools.plan_step_done(tid, 1, evidence="it worked")
        assert "rejected" in r.lower()
        assert read_block(tools, tid)["steps"][0]["status"] == "pending"

    def test_last_strike_closes_block(self, tools):
        tid = self._plan(tools)
        tools.plan_step_done(tid, 1, evidence=GOOD_EVIDENCE)
        r = tools.plan_step_done(tid, 2, evidence=GOOD_EVIDENCE)
        assert "ALL 2 STEPS COMPLETE" in r
        assert read_block(tools, tid)["status"] == "done"

    def test_failed_routes_to_revise(self, tools):
        tid = self._plan(tools)
        tools.plan_step_done(tid, 1, evidence=GOOD_EVIDENCE)
        r = tools.plan_step_done(
            tid, 2, evidence="dig @sy5berry.lan → SERVFAIL; FTL refuses to start",
            failed=True,
        )
        assert "FAILED" in r
        assert f"mode='revise', task_id='{tid}'" in r
        b = read_block(tools, tid)
        assert b["status"] == "open"
        assert b["steps"][1]["status"] == "failed"

    def test_double_strike_is_noop(self, tools):
        tid = self._plan(tools)
        tools.plan_step_done(tid, 1, evidence=GOOD_EVIDENCE)
        r = tools.plan_step_done(tid, 1, evidence=GOOD_EVIDENCE)
        assert "already struck" in r

    def test_unknown_block_and_step(self, tools):
        assert "no task block" in tools.plan_step_done("nope", 1, evidence=GOOD_EVIDENCE)
        tid = self._plan(tools)
        assert "no step 9" in tools.plan_step_done(tid, 9, evidence=GOOD_EVIDENCE)

    def test_task_resume_works_on_planner_block(self, tools):
        # regression: SELECT * + 11-value unpack broke on the steps_json column
        tid = self._plan(tools)
        tools.plan_step_done(tid, 1, evidence=GOOD_EVIDENCE)
        r = tools.task_resume(tid)
        assert f"TASK BLOCK {tid}" in r
        assert "step 1" in r  # done list
        assert "STEP 2 ONLY" in r  # next_prompt carries the next atomized step


class TestPlannerRevise:
    def test_revise_merges_done_history(self, tools, monkeypatch):
        tid = plan_tid(tools.planner("migrate DNS to pi-hole"))
        tools.plan_step_done(tid, 1, evidence=GOOD_EVIDENCE)
        tools.plan_step_done(
            tid, 2, evidence="dig SERVFAIL; FTL config invalid line 12",
            failed=True,
        )
        captured = {}

        def fake_planner(task, context="", no_think=False):
            captured["context"] = context
            return json.dumps(ENV_REVISED)

        monkeypatch.setattr(tools, "_call_node_planner", fake_planner)
        r = tools.planner("migrate DNS to pi-hole", mode="revise", task_id=tid)
        assert "PLAN ENVELOPE accepted (revise)" in r
        assert "(+1 already done)" in r
        # the planner saw the ledger, including the failure evidence
        assert "LEDGER" in captured["context"]
        assert "[COMPLETED] dump pfSense" in captured["context"]
        assert "[FAILED]" in captured["context"]
        b = read_block(tools, tid)
        ns = [(s["n"], s["status"]) for s in b["steps"]]
        assert ns == [(1, "done"), (2, "pending"), (3, "pending")]
        assert "STEP 2 ONLY (revised)" in b["next_prompt"]

    def test_revise_unknown_block(self, tools):
        r = tools.planner("x", mode="revise", task_id="missing1")
        assert "no task block" in r


class TestPlannerForceUrl:
    def test_force_url_used_when_healthy(self, tools, monkeypatch):
        import io
        import urllib.request as ureq

        calls = []

        class FakeResp(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        bodies = []

        def fake_urlopen(req, timeout=0):
            url = req if isinstance(req, str) else req.full_url
            calls.append(url)
            if url.endswith("/health"):
                return FakeResp(b"ok")
            bodies.append(json.loads(req.data.decode()))
            return FakeResp(
                json.dumps(
                    {"choices": [{"message": {"content": json.dumps(ENV_NEW)}}]}
                ).encode()
            )

        monkeypatch.setattr(ureq, "urlopen", fake_urlopen)
        # un-patch the canned _call_node_planner so the real cascade runs
        monkeypatch.setattr(
            tools, "_call_node_planner", goethe.Tools._call_node_planner.__get__(tools)
        )
        tools.valves.PLANNER_FORCE_URL = "http://fake-gemma:8085"
        r = tools.planner("migrate DNS to pi-hole")
        assert "PLAN ENVELOPE accepted" in r
        assert calls[0] == "http://fake-gemma:8085/health"
        assert calls[1].startswith("http://fake-gemma:8085/v1/chat/completions")
        # v0.4.6 payload contract: envelope headroom + a think kill-switch
        # that llama.cpp ACTUALLY honours. The v0.3.3 assertion here was
        # "thinking_budget_tokens" == 0, which is not a llama.cpp API field:
        # the server silently dropped it, so this test passed while every
        # real planner call ran with reasoning fully enabled and burned its
        # whole token budget in <think>. Measured on build b10106,
        # chat_template_kwargs is the only knob that reaches the template.
        assert bodies[0]["max_tokens"] == 8192
        assert bodies[0]["chat_template_kwargs"] == {"enable_thinking": False}
        assert "thinking_budget_tokens" not in bodies[0]


class TestDetachOnSlow:
    """v1.14.x detach-on-slow (ff7dd9bc, 2026-08-24): a planner() call whose
    backend lands AFTER the inline threshold must return "PLAN IN PROGRESS"
    promptly, leave an in-progress ledger row, and let the background worker
    finalize the SAME row in place. The fast path (all earlier tests in this
    file, which return instantly) must remain byte-identical."""

    def _arm_slow_backend(self, tools, monkeypatch, sleep_s, reply):
        import time

        monkeypatch.setattr(goethe.PlannerMixin, "_PLANNER_INLINE_WAIT_S", 1)

        def fake(task, context="", no_think=False):
            time.sleep(sleep_s)
            return reply

        monkeypatch.setattr(tools, "_call_node_planner", fake)

    def test_slow_backend_detaches_and_lands_in_place(self, tools, monkeypatch):
        import re
        import time

        self._arm_slow_backend(tools, monkeypatch, 3, json.dumps(ENV_NEW))
        t0 = time.monotonic()
        r = tools.planner("migrate DNS to pi-hole")
        elapsed = time.monotonic() - t0
        assert elapsed < 2.5, (
            f"detach must return within the 1s threshold, took {elapsed:.1f}s"
        )
        assert "PLAN IN PROGRESS" in r
        assert "task_resume(" in r
        tid = re.search(r"task_id=([0-9a-f]{8})", r).group(1)
        # in-progress row: open, marker plan text, no steps yet
        conn = tools._tasks_db()
        row = conn.execute(
            "SELECT status, plan, steps_json FROM task_blocks WHERE task_id=?",
            (tid,),
        ).fetchone()
        conn.close()
        assert row[0] == "open"
        assert "PLANNING IN PROGRESS" in row[1]
        assert row[2] is None
        # worker lands the final plan in the SAME row (poll up to 15s)
        deadline = time.monotonic() + 15
        landed = False
        while time.monotonic() < deadline:
            conn = tools._tasks_db()
            row = conn.execute(
                "SELECT steps_json FROM task_blocks WHERE task_id=?", (tid,)
            ).fetchone()
            conn.close()
            if row[0] is not None:
                landed = True
                break
            time.sleep(0.2)
        assert landed, "worker never landed steps_json in the in-progress row"
        b = read_block(tools, tid)
        assert b["status"] == "open"
        assert "PLANNING IN PROGRESS" not in b["plan"]
        assert [s["status"] for s in b["steps"]] == ["pending", "pending"]
        assert "STEP 1 ONLY" in b["next_prompt"]

    def test_slow_backend_failure_lands_in_row(self, tools, monkeypatch):
        import re
        import time

        self._arm_slow_backend(tools, monkeypatch, 2, '{"intent": "plan"}')
        r = tools.planner("migrate DNS to pi-hole")
        assert "PLAN IN PROGRESS" in r
        tid = re.search(r"task_id=([0-9a-f]{8})", r).group(1)
        # two-attempt retry loop (2 x 2s) -> poll up to 30s for the failure
        deadline = time.monotonic() + 30
        row = None
        while time.monotonic() < deadline:
            conn = tools._tasks_db()
            row = conn.execute(
                "SELECT findings, next_prompt FROM task_blocks WHERE task_id=?",
                (tid,),
            ).fetchone()
            conn.close()
            if row[0] and "detached planner worker failed" in row[0]:
                break
            time.sleep(0.3)
        assert row[0] and "detached planner worker failed" in row[0]
        assert "PLANNER FAILED" in row[1]
        assert "default budgets" in row[1]
