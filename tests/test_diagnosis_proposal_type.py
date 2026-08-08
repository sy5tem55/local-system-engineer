#!/usr/bin/env python3
"""SPEC-diagnosis-proposal-type-2026-08 -- routing, structural validation,
provenance boundary, and Console rendering for the `diagnosis` proposal type.

No live ES needed here (test_kb_contracts.py::TestRecordErrorDiagnosisFields
covers record_error against a real throwaway lse-errors-test index for
spec tests 1, 2, 6). This file covers:

  Test 3 -- error-cluster emits `diagnosis` for a triggered-failure cluster.
  Test 4 -- a genuine repeatable procedure can still emit `skill-candidate`
            (LOAD-BEARING: routing works both ways, not a wholesale replacement).
  Test 5 -- a diagnosis missing `interpretation` is rejected; missing
            `anti_response` is allowed (LOAD-BEARING).
  Test 7 -- pass-written diagnoses are distinguishable from dream-infra
            crash records (record_crash_error's own provenance="dream-infra"
            tag never appears on a record_error-created doc).
  Test 8 -- the Console renders record_error with a readable action line.

Plus: the error-cluster prompt explicitly asks for anti_response (the model
will not volunteer it -- Hazard B), and KNOWN_PROPOSAL_TYPES/tool-count
invariants (record_error extended in place, no new tool).

Run on LUCIFER:
    /home/sy5/owui/bin/python3 -m pytest tests/test_diagnosis_proposal_type.py -v
"""

import inspect
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_apply as da  # noqa: E402
import dream_runner as dr  # noqa: E402
import goethe  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))


# -- FakeES: minimal in-memory double, same convention as
#    test_dream_crash_discipline.py's FakeES (one-fixture-per-file) --------

class FakeES:
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

    def search(self, *, index, body=None, **kw):
        # record_error's KNN dedup search -- always "no match" in this fake,
        # so every call takes the create-new-doc path (test 7 needs two
        # independently-created docs, not a merge).
        self.calls.append(("search", index))
        return {"hits": {"hits": []}}


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
        pass_name="error-cluster",
        dry_run=True,
    )
    base.update(overrides)
    return dr.DreamConfig(**base)


def _episode_members(n=3, sessions=2):
    """n occurrences spanning `sessions` distinct sessions -- enough to
    clear ERROR_CLUSTER_MIN_OCCURRENCES/MIN_SESSIONS."""
    members = []
    for i in range(n):
        members.append({
            "key": f"sess{i % sessions}@t{i}",
            "session_id": f"sess{i % sessions}",
            "ts": f"2026-08-0{i + 1}T00:00:00Z",
            "tool": "execute_command",
            "exit_class": "timeout",
            "result_truncated": "MCP error -32001: request timed out",
            "embed_text": "execute_command: MCP error -32001",
            "source": "episode",
        })
    return members


# == Test 3 -- error-cluster emits `diagnosis` for a triggered failure =====

class TestDiagnosisEmission:
    def test_draft_emits_diagnosis_for_triggered_cluster(self, monkeypatch):
        def fake_envelope(system_prompt, user_content, cfg, **_kwargs):
            return {
                "diagnoses": [{
                    "error_text": "MCP error -32001",
                    "context": "running a long execute_command inline",
                    "interpretation": (
                        "the MCP request timeout is shorter than the "
                        "command's real runtime, not a sign of a hang"
                    ),
                    "resolution": "background it with nohup ... & disown, then poll the log",
                    "anti_response": "do not retry the same blocking call expecting it to finish faster",
                    "why": "seen across 2+ sessions, always the same signature",
                }],
                "skill_candidates": [],
            }, None

        monkeypatch.setattr(dr, "request_dream_envelope", fake_envelope)
        cfg = _cfg()
        diagnoses, skills, note = dr._draft_error_cluster_proposals(
            cfg, _episode_members(), []
        )
        assert note is None
        assert skills == []
        assert len(diagnoses) == 1
        d = diagnoses[0]
        assert d["type"] == "diagnosis"
        assert d["call"] == "record_error"
        assert d["args"]["error_text"] == "MCP error -32001"
        assert d["args"]["interpretation"].startswith("the MCP request timeout")
        assert d["args"]["anti_response"].startswith("do not retry")
        assert set(d["args"]) == {
            "error_text", "context", "interpretation", "resolution", "anti_response",
        }

    def test_run_pass_error_cluster_produces_diagnosis_type(self, monkeypatch, tmp_path):
        def fake_envelope(system_prompt, user_content, cfg, **_kwargs):
            return {
                "diagnoses": [{
                    "error_text": "MCP error -32001",
                    "context": "running pytest inline",
                    "interpretation": "timeout is shorter than the suite runtime",
                    "resolution": "background it",
                    "anti_response": "",
                    "why": "recurring",
                }],
                "skill_candidates": [],
            }, None

        monkeypatch.setattr(dr, "request_dream_envelope", fake_envelope)
        monkeypatch.setattr(dr, "embed_items", lambda cfg, items: {
            it["key"]: [0.1, 0.2, 0.3] for it in items
        })
        monkeypatch.setattr(dr, "cluster_by_similarity", lambda embeddings, threshold: [
            list(embeddings.keys())
        ])
        cfg = _cfg()
        sessions = [{"session_id": "sess0"}, {"session_id": "sess1"}]
        # 3 distinct occurrences (distinct ts -> distinct collect_episode_
        # error_occurrences keys) across 2 sessions -- clears both
        # ERROR_CLUSTER_MIN_OCCURRENCES (3) and ERROR_CLUSTER_MIN_SESSIONS (2).
        episodes_by_session = {
            "sess0": [
                {"exit_class": "timeout", "result_truncated": "MCP error -32001",
                 "tool": "execute_command", "ts": "2026-08-01T00:00:00Z"},
                {"exit_class": "timeout", "result_truncated": "MCP error -32001",
                 "tool": "execute_command", "ts": "2026-08-01T00:05:00Z"},
            ],
            "sess1": [
                {"exit_class": "timeout", "result_truncated": "MCP error -32001",
                 "tool": "execute_command", "ts": "2026-08-02T00:00:00Z"},
            ],
        }
        proposals, narrative, null_record = dr.run_pass_error_cluster(
            cfg, sessions, episodes_by_session, [], []
        )
        assert null_record is None
        assert any(p["type"] == "diagnosis" for p in proposals)
        assert "diagnosis" in narrative or "diagnoses" in narrative


# == Test 4 (LOAD-BEARING) -- routing works both ways ======================

class TestSkillCandidateStillRoutable:
    def test_genuine_procedure_still_emits_skill_candidate(self, monkeypatch):
        """A cluster whose evidence yields a real repeatable multi-step fix
        must still be able to emit skill-candidate -- diagnosis is additive
        routing, not a wholesale replacement (spec §4 item 6)."""
        def fake_envelope(system_prompt, user_content, cfg, **_kwargs):
            return {
                "diagnoses": [],
                "skill_candidates": [{
                    "task": "clear stale llama-server GPU lock after a crash",
                    "trigger": "llama-server fails to bind port 8080 with 'address in use'",
                    "occupation": "Local System Engineer",
                    "procedure": "pkill -f llama-server; rm /tmp/llama.lock; restart the service",
                    "verification": "curl localhost:8080/health returns 200",
                    "preconditions": "",
                    "failure_modes": "",
                    "why": "repeated 3x this week, always the same fix",
                }],
            }, None

        monkeypatch.setattr(dr, "request_dream_envelope", fake_envelope)
        cfg = _cfg()
        diagnoses, skills, note = dr._draft_error_cluster_proposals(
            cfg, _episode_members(), []
        )
        assert note is None
        assert diagnoses == []
        assert len(skills) == 1
        s = skills[0]
        assert s["type"] == "skill-candidate"
        assert s["call"] == "skill_record"
        assert "WHEN THIS HAPPENS" in s["args"]["procedure"]
        assert "FIX:" in s["args"]["procedure"]

    def test_both_can_be_emitted_from_the_same_envelope(self, monkeypatch):
        """Routing is per-cluster in the model's judgment, not all-or-nothing
        at the pass level -- one call can return both arrays populated."""
        def fake_envelope(system_prompt, user_content, cfg, **_kwargs):
            return {
                "diagnoses": [{
                    "error_text": "err A", "context": "ctx A",
                    "interpretation": "interp A", "resolution": "res A",
                    "anti_response": "", "why": "why A",
                }],
                "skill_candidates": [{
                    "task": "task B", "trigger": "trigger B", "occupation": "sre",
                    "procedure": "step 1; step 2", "verification": "verify B",
                    "preconditions": "", "failure_modes": "", "why": "why B",
                }],
            }, None

        monkeypatch.setattr(dr, "request_dream_envelope", fake_envelope)
        diagnoses, skills, note = dr._draft_error_cluster_proposals(
            _cfg(), _episode_members(), []
        )
        assert len(diagnoses) == 1 and len(skills) == 1


# == Test 5 (LOAD-BEARING) -- interpretation required, anti_response optional =

class TestDiagnosisStructuralValidation:
    def _diagnosis_proposal(self, **arg_overrides):
        args = {
            "error_text": "PermissionError",
            "context": "writing to /var/lib/docker",
            "interpretation": "the service user changed after a host rebuild",
            "resolution": "chown the socket to the service user",
            "anti_response": "do not chmod 777 the socket",
        }
        args.update(arg_overrides)
        return {
            "type": "diagnosis",
            "call": "record_error",
            "args": args,
            "why": "recurring across sessions",
        }

    def test_valid_diagnosis_passes_structural_validation(self):
        p = self._diagnosis_proposal()
        assert dr.validate_proposal_shape(p) is None

    def test_missing_anti_response_is_allowed(self):
        """The model may legitimately have no obvious wrong move to warn
        against -- anti_response empty must NOT be rejected."""
        p = self._diagnosis_proposal(anti_response="")
        assert dr.validate_proposal_shape(p) is None

    def test_missing_interpretation_is_rejected(self):
        """LOAD-BEARING: interpretation is the value a diagnosis exists to
        record (spec §1) -- missing it must be rejected as an incomplete draft."""
        p = self._diagnosis_proposal(interpretation="")
        reason = dr.validate_proposal_shape(p)
        assert reason is not None
        assert "interpretation" in reason

    def test_whitespace_only_interpretation_is_also_rejected(self):
        p = self._diagnosis_proposal(interpretation="   ")
        reason = dr.validate_proposal_shape(p)
        assert reason is not None
        assert "interpretation" in reason

    def test_prove_the_guard_actually_fires(self):
        """WORKFLOW-thread-handover.md §5: 'prove a guard fails before
        trusting it to pass' -- break it, confirm red, this test IS that
        proof captured permanently rather than a one-off manual check."""
        broken = self._diagnosis_proposal(interpretation="")
        assert dr.validate_proposal_shape(broken) is not None
        fixed = self._diagnosis_proposal()
        assert dr.validate_proposal_shape(fixed) is None

    def test_diagnosis_type_known(self):
        assert "diagnosis" in dr.KNOWN_PROPOSAL_TYPES

    def test_draft_skips_incomplete_diagnosis_missing_interpretation(self, monkeypatch):
        """The drafting filter (pre-validator, at generation time) must also
        drop an incomplete diagnosis -- same discipline as skill-candidate's
        existing task/trigger/procedure/verification/why filter."""
        def fake_envelope(system_prompt, user_content, cfg, **_kwargs):
            return {
                "diagnoses": [{
                    "error_text": "err", "context": "ctx",
                    "interpretation": "",  # missing -- must be dropped
                    "resolution": "res", "anti_response": "", "why": "why",
                }],
                "skill_candidates": [],
            }, None

        monkeypatch.setattr(dr, "request_dream_envelope", fake_envelope)
        diagnoses, skills, note = dr._draft_error_cluster_proposals(
            _cfg(), _episode_members(), []
        )
        assert diagnoses == []


# == Test 7 -- distinguishable from dream-infra crash records ==============

class TestDreamInfraBoundary:
    def test_record_error_diagnosis_never_carries_dream_infra_provenance(self, monkeypatch):
        es = FakeES()
        monkeypatch.setattr(dr, "es_client", lambda cfg: es)
        cfg = _cfg(dry_run=False)

        # A real dream-infra crash record (Hazard C's existing boundary).
        crash_msg = dr.record_crash_error(cfg, "KeyError: 'foo'", context="dream-runner")
        assert "created" in crash_msg
        crash_docs = [d for (idx, _id), d in es.store.items() if idx == "lse-errors-1024"]
        assert len(crash_docs) == 1
        assert crash_docs[0]["provenance"] == "dream-infra"

        # A pass-written diagnosis via the SAME lse-errors-1024 index, same
        # ES double, applied through goethe.Tools.record_error (the only
        # call a diagnosis proposal ever makes).
        t = goethe.Tools()
        monkeypatch.setattr(t, "_es", lambda: es)
        monkeypatch.setattr(t, "_embed", lambda text: [0.0] * 8)
        diag_msg = t.record_error(
            "TimeoutError: node3090 unreachable", "SSH connectivity check",
            "verify node3090 is powered on before retrying",
            interpretation="the node is asleep (WoL-managed), not the network being down",
            anti_response="do not assume the network is broken",
        )
        assert diag_msg.startswith("Error KB created")

        all_docs = [d for (idx, _id), d in es.store.items() if idx == "lse-errors-1024"]
        assert len(all_docs) == 2  # two independent docs, never merged
        diag_docs = [d for d in all_docs if d.get("interpretation")]
        assert len(diag_docs) == 1
        # The load-bearing distinguishing fact: a record_error-created
        # diagnosis never carries provenance="dream-infra" -- that value is
        # hardcoded ONLY inside record_crash_error, a completely separate
        # function record_error never calls and never shares state with.
        assert diag_docs[0].get("provenance") != "dream-infra"
        assert diag_docs[0]["interpretation"].startswith("the node is asleep")


# == Test 8 -- Console renders record_error with a readable action line ====

class TestConsoleRendering:
    def test_dashboard_proposal_action_handles_record_error(self):
        with open(
            os.path.join(_HERE, "..", "tools", "goethe_dashboard.html"),
            encoding="utf-8",
        ) as f:
            html = f.read()
        assert 'if(call==="record_error")' in html
        assert '"Record diagnosis"' in html
        assert "a.error_text" in html

    def test_dream_apply_render_group_has_a_record_error_block(self):
        source = inspect.getsource(da.render_group)
        assert 'call == "record_error"' in source
        assert '"interpretation"' in source
        assert '"anti_response"' in source


# == Hazard B -- the prompt asks for anti_response explicitly ==============

class TestErrorClusterPromptAsksForAntiResponse:
    def test_prompt_names_anti_response_explicitly(self):
        prompt = dr._ERROR_CLUSTER_SYSTEM_PROMPT
        assert "anti_response" in prompt
        # not just present in the schema -- the model must be told WHY /
        # that it will not volunteer this on its own (Hazard B's whole point)
        assert "will not volunteer" in prompt

    def test_prompt_states_both_routing_tests(self):
        prompt = dr._ERROR_CLUSTER_SYSTEM_PROMPT
        assert "decide" in prompt.lower() or "choose" in prompt.lower()
        assert "interpretation" in prompt.lower()
        assert "diagnosis" in prompt.lower()
        assert "skill" in prompt.lower()


# == Anti-goals / invariants ================================================

class TestAntiGoals:
    def test_record_error_signature_backward_compatible(self):
        sig = inspect.signature(goethe.Tools.record_error)
        params = list(sig.parameters.values())
        names = [p.name for p in params]
        assert names[:4] == ["self", "error_text", "context", "resolution"]
        assert "interpretation" in names and "anti_response" in names
        # both new params optional -- old 3-positional-arg callers unaffected
        assert sig.parameters["interpretation"].default == ""
        assert sig.parameters["anti_response"].default == ""

    def test_no_new_tool_added_for_diagnosis(self):
        """D7 pinned the public tool surface at 39; a diagnosis proposal
        must route through record_error, never a new method."""
        source = inspect.getsource(dr._draft_error_cluster_proposals)
        assert '"call": "record_error"' in source
        assert "record_error" in inspect.getsource(da.apply_group)

    def test_skill_record_untouched_by_this_change(self):
        # sanity: skill_record's own signature is unaffected by this work
        sig = inspect.signature(goethe.Tools.skill_record)
        assert "trigger" not in sig.parameters
