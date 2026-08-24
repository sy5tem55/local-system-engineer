#!/usr/bin/env python3
"""
goethe_planner.py — planner/ledger execution loop, extracted from goethe.py
============================================================================
D7 (2026-07-31): third mixin extraction of the 2026-07-31 refactor, per
docs/D7-MIXIN-EXTRACTION-PLAN.md Step 9. This is the largest group and the
core operational-rigor differentiator (planner -> execute -> plan_step_done,
task_checkpoint/task_resume for crash recovery).

`Tools` in goethe.py inherits `PlannerMixin` alongside `KBMixin`,
`NetSecMixin`, `NodeLifecycleMixin`; goethe_mcp discovers tools via
dir(instance), so the exposed MCP tool list is unchanged. Follows the
goethe_kb.KBMixin shape: a plain class with no __init__ and no Valves
declaration, using self.valves / self._log / self.search_kb (KBMixin, via
MRO) from the host Tools class. This module must never import goethe.py —
import direction is one-way, goethe.py imports this file.

MEMBERSHIP METHODOLOGY (2026-07-31): the D7 plan's own coupling table
estimated "18 methods" for this group, derived from a coarse keyword-prefix
scan. That scan undercounted three times over: it missed backend-dispatch
functions (_resolve_backend_name, _call_planner_backend, _call_claude_planner,
_call_chatgpt_planner, _call_rest_planner, _openai_style_call, the two OAuth
token readers) and it missed helpers with no matching name prefix at all
(_load_ledger_for_revise, _synthesize_packaged_prompt, _plan_step_prompt).
Rather than keep patching by hand, membership here was computed as the call
closure reachable from the four public entry points (planner, plan_step_done,
task_checkpoint, task_resume) via BOTH direct calls (self.foo()) and bare
references (self.foo passed as a value, e.g. to ThreadPoolExecutor.submit -
this is how _augment_context_with_kb_inner is actually invoked and a
call-only scan misses it). The reverse check was also run: no method OUTSIDE
this closure references anything inside it, except self._log (which
correctly stays on Tools, shared by every group) - confirming zero coupling
breakage from this extraction.

_read_claude_oauth_token is included despite having zero callers: it is
documented dead code, deliberately retained for reference inside
_call_claude_planner's docstring ("retained above for reference but is
deliberately no longer called by anything. Do not re-wire it.") - it belongs
with the group it documents, not deleted (unlike search_rfc, which really
was unreachable dead weight and was removed outright on 2026-07-31).

Methods and constants moved verbatim (2026-07-31, from tools/goethe.py @
dd315c4, 29 methods + 5 class attributes, full list and line ranges in the
Step 9 commit message):
  _PLANNER_CONTRACT, _GEMMA_MODELS, _try_forced_planner_endpoint,
  _post_chat_completion, _call_node_planner, _resolve_backend_name,
  _call_planner_backend, _openai_style_call, _read_codex_oauth_token,
  _read_claude_oauth_token, _call_rest_planner, _call_chatgpt_planner,
  _call_claude_planner, _planner_task_class, _planner_free_vram_mb,
  _planner_gemma_select, _spawn_gemma_server, _stop_gemma_server, _tasks_db,
  task_checkpoint, task_resume, plan_step_done, _parse_planner_envelope,
  _load_ledger_for_revise, _synthesize_packaged_prompt, _normalize_plan_steps,
  _request_plan_envelope, _PLANNER_KB_CHAR_BUDGET, _PLANNER_KB_MAX_DOCS,
  _PLANNER_KB_TIMEOUT_S, _augment_context_with_kb,
  _augment_context_with_kb_inner, planner, _plan_step_prompt

No logic, docstring, or formatting changes were made during the move — this
is a pure relocation. Behavior is pinned by the full test suite (including
tests/test_planner_ledger.py, which monkeypatches _call_node_planner and
_augment_context_with_kb by name on the instance - verified to keep working
under MRO, not assumed) plus the runtime proof in
docs/D7-MIXIN-EXTRACTION-PLAN.md Step 9: the pinned STACK-MAP grounding
(_augment_context_with_kb) is exercised end-to-end through the extracted
code path, not just import-checked.
"""


import json
import os
import subprocess
import urllib.error
import threading
import urllib.request
from datetime import datetime
from typing import Optional

from goethe_constants import _LOOPBACK, _LSE_BASE_PATH


class PlannerMixin:
    """Planner/ledger execution-loop tool methods (planner, plan_step_done,
    task_checkpoint, task_resume) plus their full backend-dispatch and
    KB-grounding machinery, mixed into goethe.Tools. Uses self.valves,
    self._log, and self.search_kb (from KBMixin via MRO) from the host class.
    """

    _PLANNER_CONTRACT = (
        "You are a task planner. Given a task, ATOMIZE it and return ONLY "
        "a single JSON object — no prose, no markdown fences, no explanation.\n\n"
        "JSON envelope schema (v=2):\n"
        "{\n"
        '  "intent": "plan",\n'
        '  "correlation_id": "<from request header>",\n'
        '  "goal_summary": "<one line — what done looks like>",\n'
        '  "sessions_estimate": <int: 1 if one context window suffices, 2+ for multi-day>,\n'
        '  "single_session": <bool>,\n'
        '  "confidence": "low" | "medium" | "high",\n'
        '  "abort_criteria": "<specific condition to stop and report instead of continuing>",\n'
        '  "steps": [\n'
        '    {"n": 1, "what": "<ONE action>", "depends_on": [<step numbers>], '
        '"inputs": "<artifacts/facts needed, naming which step produced them>", '
        '"output": "<the single artifact/fact this step produces>", '
        '"web_calls": <int>, "tool_calls": <int>, '
        '"verify": "<concrete check command/observation — NEVER NONE>", '
        '"packaged_prompt": "<self-contained brief for a fresh agent executing ONLY '
        "this step: goal one-liner, this step's inputs (with values or where to read "
        'them), the action, the verify check, and STOP-AFTER instruction>"},\n'
        "    ...\n"
        "  ]\n"
        "}\n\n"
        "ATOMIZATION RULES (v2 — the reason this contract exists):\n"
        "- Each step is ONE tightly scoped unit: <=5 tool calls, ONE verifiable "
        "outcome. If an action needs more, SPLIT it.\n"
        "- Each step must be executable by a fresh agent with ZERO memory of other "
        "steps, given only its packaged_prompt plus a short ledger summary. Never "
        "write 'as before' or 'continue' in a packaged_prompt.\n"
        "- Declare every dependency: depends_on lists the step numbers whose output "
        "this step consumes; inputs names those artifacts explicitly.\n"
        "- Order steps so each depends only on EARLIER steps (topological order — "
        "they must fall into place naturally).\n"
        "- Prefer more, smaller steps over fewer, bigger ones: the executing model "
        "performs best tightly scoped, and each step runs in a fresh context window.\n"
        "- verify is mandatory per step: a command to run or observation to make "
        "whose output proves the step's output exists/works.\n"
        "Rules:\n"
        "- Return ONLY the JSON object. No prose before or after it.\n"
        "- abort_criteria: be specific (e.g. 'Stop if 3 searches return no new data').\n"
        "- web_calls / tool_calls: budget estimates only, not hard limits.\n"
        "- single_session=true if the task fits in one ~8k-token context window.\n"
        "- confidence: 'high' if the plan is complete; 'low' if key unknowns remain.\n"
        "- BACKUP RULE (hard, no exceptions): any step that modifies or overwrites a file "
        "must begin with a timestamped backup: "
        "cp <file> <bkp_dir>/<filename>_$(date +%Y%m%d_%H%M%S). "
        "State the backup command explicitly in that step's 'what' field AND in that "
        "step's packaged_prompt. No file may be overwritten without a backup copy first.\n"
        "- REVISION MODE: if the user message contains a LEDGER section with completed/"
        "failed steps, re-plan ONLY the remaining work. Do not re-emit completed steps; "
        "number new steps continuing after the highest completed step number.\n"
    )

    _GEMMA_MODELS: dict = {
        "E4B": {
            "gguf":    "gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q4_K_M.gguf",
            "mmproj":  "gemma-4-E4B-it-GGUF/mmproj-gemma-4-E4B-it-BF16.gguf",
            "vram_mb": 5200,   # 4.97 GB model + ~946 MB mmproj + headroom
        },
        "26B": {
            "gguf":    "gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-Q4_K_M.gguf",
            "mmproj":  "gemma-4-26B-A4B-it-GGUF/mmproj-gemma-4-26B-A4B-it-BF16.gguf",
            "vram_mb": 17200,  # 15.6 GB model + 1.1 GB mmproj + headroom
        },
        "31B": {
            "gguf":    "gemma-4-31B-it-GGUF/gemma-4-31B-it-Q4_K_M.gguf",
            "mmproj":  "gemma-4-31B-it-GGUF/mmproj-gemma-4-31B-it-BF16.gguf",
            "vram_mb": 19100,  # 17.4 GB model + 1.1 GB mmproj + headroom
        },
    }

    def _try_forced_planner_endpoint(
        self, task: str, context: str = "", no_think: bool = False
    ) -> str | None:
        """Try the forced planner endpoint if configured and healthy.

        Returns the LLM result string if successful, None to continue cascade.
        """
        import json as _json
        import urllib.request as _ureq  # noqa: PLC0415
        force_url = (self.valves.PLANNER_FORCE_URL or "").strip().rstrip("/")
        if not force_url:
            return None
        force_ok = False
        try:
            with _ureq.urlopen(f"{force_url}/health", timeout=3) as r:
                force_ok = r.status == 200
        except urllib.error.URLError:
            force_ok = False
        if force_ok:
            self._log(f"NODE-PLAN: PLANNER_FORCE_URL healthy → {force_url}")
            messages = [{"role": "system", "content": self._PLANNER_CONTRACT}]
            user_content = task.strip()
            if context:
                user_content = f"CONTEXT:\n{context.strip()}\n\nTASK:\n{user_content}"
            if no_think:
                user_content += " /no_think"
            messages.append({"role": "user", "content": user_content})
            payload_obj: dict = {
                "messages": messages,
                "max_tokens": 8192,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                # v0.4.8: STREAM. See _read_sse_stream for the measurement -
                # a non-streaming call idles the TCP connection for the whole
                # generation and gets reaped past ~4 minutes.
                "stream": True,
            }
            payload_obj.update(self._planner_no_think_payload())
            fm = self.valves.PLANNER_FORCE_MODEL
            if fm:
                payload_obj["model"] = fm
            payload = _json.dumps(payload_obj).encode()
            result = self._post_chat_completion(force_url, payload, 180)
            if not result.startswith("ERROR:"):
                return result
            self._log(
                f"NODE-PLAN: forced endpoint failed ({result[:80]}), "
                "falling back to cascade"
            )
        else:
            self._log(f"NODE-PLAN: PLANNER_FORCE_URL down ({force_url}) — cascade")
        return None

    def _planner_no_think_payload(self) -> dict:
        """Per-request reasoning kill-switch for llama.cpp planner calls.

        2026-08-24 (measured on node3090, llama.cpp build b10106): the field
        this replaces — "thinking_budget_tokens": 0 — is NOT part of the
        llama.cpp API. Unknown body keys are silently dropped, so every
        planner call since v0.3.3 has run with reasoning FULLY ENABLED
        despite the kill-switch appearing to be set. "reasoning_effort":
        "none" is ignored the same way. Only chat_template_kwargs reaches the
        Jinja chat template and actually suppresses the <think> block:
            thinking_budget_tokens=0  -> 37 completion tokens, 112 reasoning chars
            reasoning_effort="none"   -> 37 completion tokens, 112 reasoning chars
            enable_thinking=False     ->  6 completion tokens,   0 reasoning chars

        Why this was fatal, not merely wasteful: on a reasoning model the
        <think> trace is billed against max_tokens, and llama.cpp routes it
        to message.reasoning_content — NOT message.content, which is all
        _post_chat_completion returns. A hard planner task therefore spent
        the entire 8192-token budget thinking, came back
        finish_reason="length" with content="", and surfaced downstream as
        "JSON parse failed" / "PLANNER UNAVAILABLE". Raising the ceiling only
        buys a longer, more expensive way to fail.

        Measured with this fix (real contract, 24k-char context, 8 steps):
        4822/8192 completion tokens, 211.5s, finish_reason="stop",
        reasoning_chars=0, envelope parses clean.

        SCOPE — this is deliberately a PER-REQUEST body parameter, not a
        server flag. node3090's llama-server is shared (llama-ui, chat_bridge,
        other consumers); nothing here changes server state or affects any
        other client's reasoning behaviour. It is applied ONLY to the two
        llama.cpp planner paths, never to _openai_style_call: the rest and
        chatgpt backends talk to remote OpenAI-compatible APIs that reject
        unrecognised body keys outright rather than ignoring them.
        """
        return {"chat_template_kwargs": {"enable_thinking": False}}

    def _read_sse_stream(self, resp) -> tuple:
        """Reassemble an OpenAI-style SSE stream.

        Returns (content, reasoning_content, finish_reason, completion_tokens).

        v0.4.8: the planner's node3090 call is STREAMED, and this is why.
        A non-streaming POST holds a TCP connection carrying ZERO bytes in
        either direction for the entire generation. Measured 2026-08-24 on the
        LUCIFER -> pfSense (192.168.1.50) -> node3090 path: requests whose
        generation ran past roughly four minutes had their connection reaped
        mid-flight. llama-server then wrote a complete, untruncated response
        into a socket the client no longer owned, and the client blocked to its
        full timeout receiving nothing.

        Matched evidence, same server and model:
            non-streaming, 248s generation -> client got 0 bytes, timed out
                (server task 88240: eval 243756.95 ms / 5806 tokens,
                 release n_tokens=13174, truncated=0 -- a CLEAN completion)
            streaming,     270.5s generation -> 6579 chunks, complete
        Successes were 79s / 126s / 154s / 211s; failures 248s / ~353s / ~353s.
        The cliff tracks elapsed time, not truncation, not reasoning, not the
        health probe -- which is why hard planner tasks failed reproducibly
        while short ones always worked.

        Streaming keeps bytes flowing continuously, so the connection is never
        idle and nothing reaps it. It also makes PLANNER_LOCAL_TIMEOUT_S a
        backstop rather than the thing standing between a finished plan and
        the caller.
        """
        import json as _json  # noqa: PLC0415

        content_parts: list = []
        reasoning_parts: list = []
        finish_reason = None
        used = "?"
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                event = _json.loads(body)
            except ValueError:
                # a partial/keepalive frame is not fatal - keep reading
                continue
            choices = event.get("choices") or [{}]
            choice = choices[0] if choices else {}
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
            usage = event.get("usage") or {}
            if usage.get("completion_tokens") is not None:
                used = usage["completion_tokens"]
        return (
            "".join(content_parts), "".join(reasoning_parts), finish_reason, used,
        )

    def _post_chat_completion(
        self, base_url: str, payload: bytes, timeout: int
    ) -> str:
        """POST payload to /v1/chat/completions. Returns content or 'ERROR: ...'"""
        import json as _json
        import urllib.request as _ureq
        import urllib.error as _uerr

        req = _ureq.Request(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            _streaming = False
            try:
                _streaming = bool(_json.loads(payload.decode()).get("stream"))
            except (ValueError, UnicodeDecodeError):
                _streaming = False
            with _ureq.urlopen(req, timeout=timeout) as resp:
                if _streaming:
                    content, reasoning, _finish, used = self._read_sse_stream(resp)
                else:
                    data = _json.loads(resp.read().decode())
                    choice = data["choices"][0]
                    msg = choice.get("message") or {}
                    content = msg.get("content") or ""
                    reasoning = msg.get("reasoning_content") or ""
                    _finish = choice.get("finish_reason")
                    used = data.get("usage", {}).get("completion_tokens", "?")
                # v0.4.5: finish_reason was discarded, so a reply cut off at
                # max_tokens was indistinguishable from a malformed one. The
                # envelope parser then reported it as "JSON parse failed",
                # pointing at model formatting when the real cause was the
                # token budget. Surface it explicitly instead.
                if _finish == "length":
                    self._log(
                        "NODE-PLAN: reply TRUNCATED at max_tokens "
                        f"(completion_tokens={used}, reasoning_chars={len(reasoning)}) "
                        "— the JSON will not parse. This is a budget problem, not a "
                        "model formatting problem."
                    )
                    # v0.4.6: was `return content`. A truncated reply is a
                    # FAILURE and must be reported as one: returning the
                    # partial string let it travel on as if it were a plan,
                    # so the caller's `result.startswith("ERROR:")` guard saw
                    # success, skipped the cascade fallback, and the real
                    # cause resurfaced downstream as "JSON parse failed".
                    return (
                        f"ERROR: reply truncated at max_tokens "
                        f"(completion_tokens={used}, reasoning_chars={len(reasoning)})"
                    )
                if not content.strip():
                    # v0.4.6: empty content with a populated reasoning_content
                    # is the reasoning-runaway signature — the model spent the
                    # budget in <think> and never emitted the envelope.
                    self._log(
                        "NODE-PLAN: empty content "
                        f"(reasoning_chars={len(reasoning)}, "
                        f"finish_reason={_finish})"
                    )
                    return (
                        "ERROR: model returned empty content "
                        f"(reasoning_chars={len(reasoning)})"
                    )
                return content
        except _uerr.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            return f"ERROR: HTTP {exc.code} — {body}"
        except (
            _uerr.URLError, json.JSONDecodeError, KeyError, TimeoutError,
        ) as exc:
            # v0.4.6: TimeoutError (== socket.timeout) was MISSING here. It is
            # a sibling of URLError under OSError, NOT a subclass, so a read
            # timeout escaped this handler entirely instead of returning the
            # "ERROR: ..." string this function's contract promises. That is
            # the literal `worker crashed: timed out` seen on 2026-08-24 - and
            # because no ERROR string was ever returned, the documented
            # cascade fallback could not fire either.
            return f"ERROR: {type(exc).__name__}: {exc}"

    def _call_node_planner(
        self, task: str, context: str = "", no_think: bool = False
    ) -> str:
        """INTERNAL — Hermes replacement (v0.2.7).

        Cascade:
          1. Health-probe node3090 llama-server (NODE3090_LLM_URL/health, 3s timeout).
             If healthy → POST /v1/chat/completions with _PLANNER_CONTRACT as system
             message. Qwen 27B GPU path — best quality.
          2. If probe fails or LLM call errors → fall back to Ollama CPU on node3090
             (NODE3090_OLLAMA_URL) with NODE3090_PLANNER_FALLBACK_MODEL (qwen3:4b).
             Always-available, zero GPU contention.

        Returns the model's raw reply string, or "ERROR: <reason>" on both paths failing.
        """
        import json as _json
        import time as _time
        import urllib.request as _ureq
        import urllib.error as _uerr

        def _llm_call(base_url: str, model: str, timeout: int) -> str:
            """POST /v1/chat/completions to base_url. Returns content or 'ERROR: ...'"""
            messages = [{"role": "system", "content": self._PLANNER_CONTRACT}]
            user_content = task.strip()
            if context:
                user_content = f"CONTEXT:\n{context.strip()}\n\nTASK:\n{user_content}"
            if no_think:
                user_content += " /no_think"
            messages.append({"role": "user", "content": user_content})

            payload_obj: dict = {
                "messages": messages,
                # v0.3.3: 2048 was truncating v2 envelopes (per-step packaged
                # prompts) — the dominant "PLANNER UNAVAILABLE" root cause.
                "max_tokens": 8192,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                # v0.4.8: STREAM - see _read_sse_stream.
                "stream": True,
            }
            payload_obj.update(self._planner_no_think_payload())
            if model:
                payload_obj["model"] = model
            payload = _json.dumps(payload_obj).encode()
            return self._post_chat_completion(base_url, payload, timeout)

        # ── Step 0: forced endpoint (v0.3.2 — cross-family planner experiments) ─
        # Health-probed: the valve can stay set permanently (e.g. the Gemma-31B
        # swap port on node3090) — used when up, silently skipped when down.
        result = self._try_forced_planner_endpoint(task, context=context, no_think=no_think)
        if result is not None:
            return result

        # ── Step 1: probe node3090 llama-server ──────────────────────────────
        llm_url = self.valves.NODE3090_LLM_URL.rstrip("/")
        # v0.4.7: was a SINGLE urlopen with timeout=3 and a bare
        # `except URLError: probe_ok = False` that logged NOTHING on failure.
        # node3090 is the only working planner path (Ollama removed v0.4.5,
        # Gemma is host-local and absent on LUCIFER), so that 3-second probe
        # was the sole gate on the whole planner — and a transient blip
        # silently routed the call into a fallback that cannot succeed.
        # Observed 2026-08-24 20:16:03: no probe line at all in
        # agent_commands.log, then PLANNER-GEMMA exactly 3s later; node3090
        # answered /health in 4-17ms over six tries three minutes afterwards.
        # Now: N attempts with linear backoff, every failure logged WITH the
        # exception, and TimeoutError caught explicitly (it is a sibling of
        # URLError under OSError, not a subclass — a read-phase timeout would
        # otherwise escape this handler entirely, the same defect fixed in
        # _post_chat_completion).
        _probe_attempts = int(os.environ.get("PLANNER_PROBE_ATTEMPTS", "3"))
        _probe_timeout = int(os.environ.get("PLANNER_PROBE_TIMEOUT_S", "5"))
        probe_ok = False
        _probe_err = ""
        for _attempt in range(1, _probe_attempts + 1):
            try:
                with _ureq.urlopen(f"{llm_url}/health", timeout=_probe_timeout) as r:
                    if r.status == 200:
                        probe_ok = True
                        break
                    _probe_err = f"HTTP {r.status}"
            except (_uerr.URLError, TimeoutError, OSError) as exc:
                _probe_err = f"{type(exc).__name__}: {exc}"
            if _attempt < _probe_attempts:
                self._log(
                    f"NODE-PLAN: probe attempt {_attempt}/{_probe_attempts} failed "
                    f"({_probe_err}) — retrying"
                )
                _time.sleep(_attempt)
        if not probe_ok:
            self._log(
                f"NODE-PLAN: llama-server probe FAILED after {_probe_attempts} "
                f"attempt(s) → {llm_url} ({_probe_err or 'unknown'}) — node3090 is "
                "the only working planner backend; check it is awake and serving"
            )

        if probe_ok:
            # v0.4.5: /health is LIVENESS, not READINESS — llama-server answers
            # {"status":"ok"} whenever a model is loaded, even with every slot
            # busy. A probe-OK request can still queue behind an in-flight
            # generation and spend its budget waiting. Queueing is acceptable
            # (that is what the timeout is for), so this does not gate the call
            # — it just makes the wait explainable after the fact.
            try:
                with _ureq.urlopen(f"{llm_url}/slots", timeout=3) as _r:
                    _slots = _json.loads(_r.read().decode())
                _busy = [s for s in _slots if s.get("is_processing")]
                if _busy and len(_busy) == len(_slots):
                    self._log(
                        f"NODE-PLAN: {llm_url} live but all {len(_slots)} slot(s) "
                        "busy — this call will queue before it generates"
                    )
            except (_uerr.URLError, json.JSONDecodeError) as _exc:
                self._log(f"NODE-PLAN: /slots unreadable ({_exc}) — trusting /health")
            self._log(f"NODE-PLAN: llama-server probe OK → {llm_url}")
            # v0.4.5: was 120s. v0.3.3 raised max_tokens 2048→8192 to stop
            # envelope truncation but left this at 120s, which at the measured
            # ~42 tok/s on node3090 (Qwen3.6-27B-Q4_K_M) caps delivery at
            # ~5,000 tokens. Any envelope between ~5k and the 8,192 the request
            # permits was structurally impossible to return: the model finished
            # (finish_reason=stop) and the client hung up anyway. Measured: a
            # complete 8-step plan = 5,231 tokens / 125.3s. 8192/42 ≈ 196s, so
            # 240s covers the full permitted envelope plus prompt and margin.
            # This is a ceiling, not a cost — short plans still return in ~20s.
            # 2026-08-24 E2E (task b2094f80): the 240s envelope math above
            # is invalidated by the live node3090 model (Qwen3.8-27B UD
            # Q4_K_XL 131K, measured 23.6 t/s - not 42) plus a 14.4k-token
            # uncached planner prompt: generation ran ~400s and was
            # cancelled at n_decoded=5530. Default raised to 600s; env
            # PLANNER_LOCAL_TIMEOUT_S overrides. With detach-on-slow this
            # ceiling no longer risks the MCP client (the call detaches at
            # _PLANNER_INLINE_WAIT_S) - it only bounds GPU hold time.
            _local_timeout = int(os.environ.get("PLANNER_LOCAL_TIMEOUT_S", "600"))
            result = _llm_call(llm_url, model="", timeout=_local_timeout)
            if not result.startswith("ERROR:"):
                return result
            self._log(f"NODE-PLAN: llama-server call failed ({result[:80]}), trying Ollama")

        # ── Step 2: (removed v0.4.5) Ollama CPU fallback ──────────────────────
        # Was: _llm_call(NODE3090_OLLAMA_URL, qwen3:4b, timeout=300).
        # Removed on evidence: every invocation in the audit log failed with
        # "timed out" — 2026-07-08, 07-12 (x2), 07-14, 07-21. Zero successes.
        # A 4B model on CPU cannot emit an 8k-token JSON envelope inside 300s,
        # so this stage only added five minutes to every failure and pushed the
        # total cascade (3+120+300+60+180 = 663s) far past the MCP transport
        # timeout — which is why the caller saw a bare "Request timed out" while
        # the informative NODE-PLAN log lines were still being written.
        # The valves NODE3090_OLLAMA_URL / NODE3090_PLANNER_FALLBACK_MODEL are
        # left defined so existing configs keep loading; they are now unused.

        # ── Step 3: Gemma GGUF local spawn (VRAM-aware, v0.2.8) ──────────────
        vision = any(
            kw in task.lower()
            for kw in ("image", "screenshot", "photo", "visual",
                       "png", "jpg", "jpeg", "picture")
        )
        gguf, mmproj, model_key = self._planner_gemma_select(task, vision=vision)
        if gguf is None:
            # v0.4.7: the old message named three paths as if each had been
            # genuinely attempted and blamed VRAM/model files generically,
            # which sent readers hunting for a VRAM problem when the real
            # cause was a failed node3090 probe. Report what actually
            # happened on each leg.
            _md = self.valves.PLANNER_MODEL_DIR.rstrip("/")
            _gemma_why = (
                f"PLANNER_MODEL_DIR {_md!r} does not exist on this host"
                if not os.path.isdir(_md)
                else "no Gemma model fits free VRAM, or its files are missing"
            )
            return (
                "ERROR: all planner paths exhausted. "
                f"node3090 llama-server: {_probe_err or 'probe failed'}. "
                "Ollama: removed in v0.4.5. "
                f"Gemma local spawn: {_gemma_why}. "
                "node3090 is the only working planner path — verify it is "
                "awake and serving, then retry."
            )
        planner_port = self.valves.PLANNER_PORT
        proc = self._spawn_gemma_server(gguf, mmproj, planner_port)
        if proc is None:
            return f"ERROR: Gemma server (model_key={model_key}) failed to start within 60s"
        try:
            self._log(f"NODE-PLAN: Gemma path — model_key={model_key} vision={vision}")
            return _llm_call(f"http://{_LOOPBACK}:{planner_port}", model="", timeout=180)
        finally:
            self._stop_gemma_server(proc)

    def _resolve_backend_name(self, backend: str = "") -> str:
        """backend override → PLANNER_BACKEND valve default → 'local'. Shared
        by _call_planner_backend (to route the call) and planner() (to
        record which backend actually produced a plan, for the ledger's
        'backend' column and the Console's status panel) so the two never
        drift apart."""
        explicit = (backend or "").strip().lower()
        if explicit:
            return explicit
        # A Console selection (goethe_planner_state) outranks the valve
        # default; the valve stays the deployment default for when nothing
        # has been chosen. Import is local and guarded so a missing state
        # module degrades to the old behaviour rather than breaking planner().
        try:
            import goethe_planner_state as _pstate  # noqa: PLC0415

            return _pstate.selected_backend(self.valves.PLANNER_BACKEND or "local")
        except ImportError:
            self._log("PLANNER-BACKEND: goethe_planner_state unavailable")
            return (self.valves.PLANNER_BACKEND or "local").strip().lower()

    def _call_planner_backend(
        self, task: str, context: str = "", no_think: bool = False, backend: str = ""
    ) -> str:
        """Route a planner LLM call to the selected backend.

        This is now the ONLY entry point planner()/_request_plan_envelope()
        call — _call_node_planner itself is unchanged and untouched, just no
        longer called directly from planner(). Same return contract every
        backend function here has always had: the model's raw reply string,
        or 'ERROR: <reason>' on failure.

        backend: '' → use the PLANNER_BACKEND valve's default. Otherwise one
        of 'local' | 'chatgpt' | 'claude' | 'rest'.
        """
        b = self._resolve_backend_name(backend)
        if b == "local":
            return self._call_node_planner(task, context=context, no_think=no_think)
        if b == "rest":
            return self._call_rest_planner(task, context=context, no_think=no_think)
        if b == "chatgpt":
            return self._call_chatgpt_planner(task, context=context, no_think=no_think)
        if b == "claude":
            return self._call_claude_planner(task, context=context, no_think=no_think)
        return (
            f"ERROR: unknown planner backend {b!r} — must be one of "
            "local | chatgpt | claude | rest"
        )

    def _openai_style_call(
        self, base_url: str, model: str, api_key: str,
        task: str, context: str, no_think: bool, timeout: int,
    ) -> str:
        """Shared POST /v1/chat/completions body-building + call, used by the
        'rest' and 'chatgpt' backends (both speak the OpenAI chat-completions
        shape; they differ only in URL/credential-sourcing). Anthropic does
        NOT use this — its Messages API has a different envelope entirely,
        see _call_claude_planner.

        api_key, if non-empty, is sent as 'Authorization: Bearer <key>'.
        """
        import json as _json  # noqa: PLC0415
        import urllib.error as _uerr  # noqa: PLC0415
        import urllib.request as _ureq  # noqa: PLC0415

        messages = [{"role": "system", "content": self._PLANNER_CONTRACT}]
        user_content = task.strip()
        if context:
            user_content = f"CONTEXT:\n{context.strip()}\n\nTASK:\n{user_content}"
        if no_think:
            user_content += " /no_think"
        messages.append({"role": "user", "content": user_content})

        payload_obj: dict = {
            "messages": messages,
            "max_tokens": 8192,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }
        if model:
            payload_obj["model"] = model
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = _ureq.Request(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            data=_json.dumps(payload_obj).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with _ureq.urlopen(req, timeout=timeout) as resp:
                data = _json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"]
        except _uerr.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            return f"ERROR: HTTP {exc.code} — {body}"
        except (
            _uerr.URLError, json.JSONDecodeError, KeyError, TimeoutError,
        ) as exc:
            # v0.4.6: same missing-TimeoutError defect as
            # _post_chat_completion - see the note there. Applies to the rest
            # and chatgpt backends.
            return f"ERROR: {type(exc).__name__}: {exc}"

    def _read_codex_oauth_token(self) -> Optional[str]:
        """Best-effort read of an existing Codex CLI (`codex login`) OAuth
        session — see PLANNER_CODEX_AUTH_PATHS for the documented caveat
        that this file format is not an OpenAI-published spec. Tries each
        candidate path in order; returns the first usable token found, or
        None if nothing is found/parseable (never raises — a broken or
        missing credentials file must degrade to the API-key fallback, not
        crash the planner call)."""
        import json as _json  # noqa: PLC0415

        for raw in (self.valves.PLANNER_CODEX_AUTH_PATHS or "").split(":"):
            p = os.path.expanduser(raw.strip())
            if not p or not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    data = _json.load(f)
                tok = (
                    (data.get("tokens") or {}).get("access_token")
                    or data.get("access_token")
                    or data.get("OPENAI_API_KEY")
                )
                if tok:
                    return tok
            except (OSError, json.JSONDecodeError) as e:
                self._log(f"PLANNER-BACKEND: codex auth file {p} unreadable: {e}")
        return None

    def _read_claude_oauth_token(self) -> Optional[str]:
        """Best-effort read of an existing Claude Code (`claude login`) OAuth
        session — see PLANNER_CLAUDE_AUTH_PATHS for the same undocumented-
        format caveat as _read_codex_oauth_token. Never raises; returns None
        if nothing usable is found."""
        import json as _json  # noqa: PLC0415

        for raw in (self.valves.PLANNER_CLAUDE_AUTH_PATHS or "").split(":"):
            p = os.path.expanduser(raw.strip())
            if not p or not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    data = _json.load(f)
                oauth = data.get("claudeAiOauth") or {}
                tok = (
                    oauth.get("accessToken")
                    or data.get("accessToken")
                    or data.get("access_token")
                )
                if tok:
                    return tok
            except (OSError, json.JSONDecodeError) as e:
                self._log(f"PLANNER-BACKEND: claude auth file {p} unreadable: {e}")
        return None

    def _call_rest_planner(self, task: str, context: str = "", no_think: bool = False) -> str:
        """backend='rest' — any OpenAI-compatible /v1/chat/completions server.
        The 'almost universally compatible' option: OpenRouter, Groq,
        Together, a LAN vLLM/LM Studio/text-generation-webui instance, or
        anything else that speaks this shape works here unmodified, just by
        setting PLANNER_REST_URL (+ optionally _MODEL / _API_KEY)."""
        url = (self.valves.PLANNER_REST_URL or "").strip()
        if not url:
            return "ERROR: backend='rest' requires the PLANNER_REST_URL valve to be set"
        return self._openai_style_call(
            url, self.valves.PLANNER_REST_MODEL, self.valves.PLANNER_REST_API_KEY,
            task, context, no_think, timeout=120,
        )

    def _call_chatgpt_planner(self, task: str, context: str = "", no_think: bool = False) -> str:
        """backend='chatgpt'. Order of attempts:
          1. Codex CLI OAuth session, if `codex login` has been run on this
             machine (_read_codex_oauth_token). CAVEAT, stated plainly rather
             than papered over: this token is normally scoped to ChatGPT's
             own apps, not the general pay-per-token API — whether it's
             accepted by api.openai.com depends on your account. If it's
             REJECTED, this reports that clearly instead of silently trying
             something else, since silently switching auth mechanisms after
             a real auth failure would hide what actually happened.
          2. PLANNER_OPENAI_API_KEY — used only when no OAuth session was
             found at all (not on OAuth rejection), since that's a distinct,
             separately-billed credential and switching to it automatically
             after an explicit auth failure could surprise-charge the user.
        """
        oauth_tok = self._read_codex_oauth_token()
        if oauth_tok:
            self._log("PLANNER-BACKEND: chatgpt — using Codex CLI OAuth session")
            result = self._openai_style_call(
                "https://api.openai.com", self.valves.PLANNER_OPENAI_MODEL,
                oauth_tok, task, context, no_think, timeout=120,
            )
            if not result.startswith("ERROR:"):
                return result
            return (
                result + " — a Codex CLI OAuth session was found but "
                "api.openai.com rejected it. ChatGPT subscription-login "
                "tokens are usually scoped to ChatGPT's own apps, not the "
                "general API. Set PLANNER_OPENAI_API_KEY to a real OpenAI "
                "API key, or use backend='rest' with an OpenAI-compatible "
                "gateway instead."
            )
        api_key = self.valves.PLANNER_OPENAI_API_KEY or ""
        if not api_key:
            return (
                "ERROR: backend='chatgpt' found no Codex CLI OAuth session "
                f"(checked PLANNER_CODEX_AUTH_PATHS={self.valves.PLANNER_CODEX_AUTH_PATHS!r}) "
                "and PLANNER_OPENAI_API_KEY is not set. Run `codex login`, "
                "or set PLANNER_OPENAI_API_KEY to an OpenAI API key."
            )
        self._log("PLANNER-BACKEND: chatgpt — using PLANNER_OPENAI_API_KEY")
        return self._openai_style_call(
            "https://api.openai.com", self.valves.PLANNER_OPENAI_MODEL,
            api_key, task, context, no_think, timeout=120,
        )

    def _call_claude_planner(self, task: str, context: str = "", no_think: bool = False) -> str:
        """backend='claude' — runs the plan through the Claude Agent SDK via
        the `claude -p` CLI (non-interactive mode), authenticated by whatever
        session `claude login` established.

        WHY THE CLI AND NOT A DIRECT CALL TO api.anthropic.com (v1.14.0)
          The previous implementation read Claude Code's OAuth access token
          out of ~/.claude/.credentials.json and replayed it as a Bearer
          token against /v1/messages. That is not what the credential
          authorises, and it is the pattern Anthropic enforced against
          between January and April 2026:

            Consumer Terms section 3(7) permits automated access "via an
            Anthropic API Key or where we otherwise explicitly permit it".
            Agent SDK and `claude -p` usage on a subscription IS that
            explicit permission — see support.claude.com article 15036540,
            which counts third-party app usage against subscription limits.
            Hand-rolled token replay is not: Claude Code's legal-and-
            compliance page states OAuth is "intended exclusively for ...
            ordinary use of Claude Code and other native Anthropic
            applications".

          Going through the CLI reaches the same subscription-funded
          planning the OAuth path was after, through the supported door,
          and stops depending on an undocumented credential-file format
          that has already changed once.

          _read_claude_oauth_token() is retained above for reference but is
          deliberately no longer called by anything. Do not re-wire it.

        CREDENTIAL PRECEDENCE
          1. Whatever `claude login` established — the subscription path,
             and the default. Nothing needs configuring here.
          2. PLANNER_ANTHROPIC_API_KEY, if set, is exported to the child as
             ANTHROPIC_API_KEY, switching this same code path to billed
             pay-as-you-go. It WINS when set — treated as the operator's
             deliberate choice, not a fallback, because someone who sets an
             API key means it.

        The binary is `claude` on PATH; GOETHE_PLANNER_CLAUDE_CLI overrides,
        same GOETHE_<FIELD> convention goethe_mcp.py uses for valves.
        """
        import shutil as _shutil  # noqa: PLC0415
        import subprocess as _sp  # noqa: PLC0415

        cli = os.environ.get("GOETHE_PLANNER_CLAUDE_CLI", "").strip() or "claude"
        resolved = _shutil.which(cli)
        if not resolved:
            return (
                f"ERROR: backend='claude' needs the Claude Code CLI ({cli!r}) "
                "on PATH and it was not found. Install it with "
                "`npm install -g @anthropic-ai/claude-code`, then run "
                "`claude login` once to authenticate against your "
                "subscription. Set GOETHE_PLANNER_CLAUDE_CLI if it lives "
                "somewhere off PATH."
            )

        user_content = task.strip()
        if context:
            user_content = f"CONTEXT:\n{context.strip()}\n\nTASK:\n{user_content}"
        prompt = f"{self._PLANNER_CONTRACT}\n\n{user_content}"
        if no_think:
            prompt += "\n\n(Respond directly — no extended thinking needed.)"

        cmd = [
            resolved, "-p",
            "--output-format", "text",
            "--model", self.valves.PLANNER_ANTHROPIC_MODEL,
        ]

        env = dict(os.environ)
        # ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN redirect the CLI at a
        # custom LLM gateway instead of Anthropic. LUCIFER's ~/.bashrc
        # exports exactly that (http://localhost:8082, found 2026-07-29),
        # and while the gateway process does not source .bashrc today, that
        # is an accident of how it is launched, not a guarantee. If those
        # ever reached this process the planner would answer from somewhere
        # other than Anthropic — or hang when that endpoint is down — while
        # the ledger recorded backend='claude'. A wrong plan attributed to
        # the wrong model is worse than a failed one, so strip them in both
        # credential modes.
        for _redirect in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
                          "ANTHROPIC_API_URL",
                          "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"):
            env.pop(_redirect, None)
        api_key = (self.valves.PLANNER_ANTHROPIC_API_KEY or "").strip()
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
            self._log("PLANNER-BACKEND: claude — CLI, PLANNER_ANTHROPIC_API_KEY (billed)")
        else:
            # Do not let an unrelated ambient ANTHROPIC_API_KEY leak into the
            # child and silently bill a key the operator did not choose here.
            env.pop("ANTHROPIC_API_KEY", None)
            self._log("PLANNER-BACKEND: claude — CLI on the `claude login` session")

        try:
            proc = _sp.run(
                cmd, input=prompt, capture_output=True, text=True,
                timeout=int(self.valves.PLANNER_CLI_TIMEOUT_S), env=env,
            )
        except _sp.TimeoutExpired:
            return (f"ERROR: backend='claude' timed out after "
                    f"{int(self.valves.PLANNER_CLI_TIMEOUT_S)}s")
        except OSError as exc:
            return f"ERROR: backend='claude' could not run {cli!r}: {exc}"

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:300]
            low = err.lower()
            hint = ""
            if any(k in low for k in ("login", "auth", "unauthor", "401", "403")):
                hint = (" — run `claude login` to (re)authenticate, or set "
                        "PLANNER_ANTHROPIC_API_KEY to use a Claude Platform "
                        "API key instead")
            return f"ERROR: claude CLI exited {proc.returncode}: {err}{hint}"

        out = (proc.stdout or "").strip()
        if not out:
            return "ERROR: claude CLI returned empty output"

        # The CLI exits 0 when unauthenticated and prints a notice to stdout
        # rather than stderr — verified against 2.1.220 on 2026-07-29:
        #     $ echo hi | claude -p ; echo $?
        #     Not logged in · Please run /login
        #     0
        # Exit-code checking alone therefore hands that notice back to
        # planner() as though it were a plan, and the ledger records a
        # "successful" run. Detect it from the output instead. Length-capped
        # so a genuine plan that happens to discuss /login cannot trip it.
        if len(out) < 200:
            low = out.lower()
            if "not logged in" in low or "please run /login" in low:
                return (
                    "ERROR: backend='claude' — the Claude Code CLI is installed "
                    "but not authenticated. Run `claude login` as the same user "
                    "the gateway runs as, then retry. (The CLI exits 0 in this "
                    "state, so this is detected from its output, not its exit "
                    "code.)"
                )
        return out

    def _planner_task_class(self, task: str) -> str:
        """Classify task size for Gemma model selection: 'small' / 'medium' / 'large'."""
        n = len(task)
        if n < 400:
            return "small"
        if n < 1500:
            return "medium"
        return "large"

    def _planner_free_vram_mb(self) -> int:
        """Return the largest free VRAM (MiB) across all GPUs via nvidia-smi, or 0 on error."""
        import subprocess as _sp2  # noqa: PLC0415

        try:
            r = _sp2.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [ln.strip() for ln in r.stdout.strip().splitlines() if ln.strip()]
            if lines:
                return max(int(ln) for ln in lines)
        except (subprocess.SubprocessError, OSError, ValueError):
            pass
        return 0

    def _planner_gemma_select(self, task: str, vision: bool = False) -> tuple:
        """
        Select the best-fit Gemma GGUF from PLANNER_MODEL_DIR given available VRAM.

        Preference order by task class:
          small  → E4B  → 26B → 31B
          medium → 26B  → 31B → E4B
          large  → 31B  → 26B → E4B
        Skips any model whose vram_mb gate exceeds free VRAM or whose files are absent.

        Returns (gguf_path, mmproj_path_or_None, model_key), or (None, None, None)
        if no model fits.
        """
        import os as _os2  # noqa: PLC0415

        model_dir = self.valves.PLANNER_MODEL_DIR.rstrip("/")
        # v0.4.7: check the directory BEFORE probing VRAM. Path 3 spawns a
        # server on THIS host, but PLANNER_MODEL_DIR's default
        # (/opt/models/lmstudio-community) is documented "Verified on
        # node3090" and does not exist on LUCIFER — recorded as broken in KB
        # 3fba06e7639ce58d on 2026-07-30. Without this guard the pass logged
        # three misleading "skip <size> — need N MB, have M" VRAM lines and
        # blamed VRAM, when no amount of free VRAM could ever have helped.
        if not _os2.path.isdir(model_dir):
            self._log(
                f"PLANNER-GEMMA: PLANNER_MODEL_DIR {model_dir!r} does not exist on "
                "this host — local Gemma spawn is unavailable here "
                "(KB 3fba06e7639ce58d). Skipping Path 3."
            )
            return None, None, None

        free = self._planner_free_vram_mb()
        self._log(f"PLANNER-GEMMA: free VRAM={free} MB")

        tc = self._planner_task_class(task)
        order = (
            ["E4B", "26B", "31B"] if tc == "small"
            else ["26B", "31B", "E4B"] if tc == "medium"
            else ["31B", "26B", "E4B"]
        )

        for key in order:
            m = self._GEMMA_MODELS[key]
            if free < m["vram_mb"]:
                self._log(
                    f"PLANNER-GEMMA: skip {key} — need {m['vram_mb']} MB, have {free}"
                )
                continue
            gguf = f"{model_dir}/{m['gguf']}"
            mmproj = f"{model_dir}/{m['mmproj']}" if vision else None
            if not _os2.path.isfile(gguf):
                self._log(f"PLANNER-GEMMA: skip {key} — gguf missing: {gguf}")
                continue
            if vision and mmproj and not _os2.path.isfile(mmproj):
                self._log(f"PLANNER-GEMMA: skip {key} — mmproj missing: {mmproj}")
                continue
            self._log(f"PLANNER-GEMMA: selected {key} (task_class={tc}, vision={vision})")
            return gguf, mmproj, key

        return None, None, None

    def _spawn_gemma_server(self, gguf_path: str, mmproj_path, port: int):
        """
        Spawn a transient llama-server on 127.0.0.1:<port> for Path 3 planning.

        Polls GET /health every 2 s for up to 60 s. Returns the Popen object when
        the server reports healthy, or None if it does not become healthy in time.
        The caller is responsible for calling _stop_gemma_server(proc) when done.
        """
        import subprocess as _sp3  # noqa: PLC0415
        import time as _tm3  # noqa: PLC0415
        import urllib.request as _ur3  # noqa: PLC0415

        llama_bin = self.valves.PLANNER_LLAMA_BIN
        cmd = [
            llama_bin,
            "--model", gguf_path,
            "--port", str(port),
            "--host", _LOOPBACK,
            "--n-gpu-layers", "99",
            "--ctx-size", "4096",
            "--threads", "4",
        ]
        if mmproj_path:
            cmd += ["--mmproj", mmproj_path]
        self._log(
            f"PLANNER-GEMMA: spawn {llama_bin} model=...{gguf_path[-40:]} port={port}"
        )
        try:
            proc = _sp3.Popen(cmd, stdout=_sp3.DEVNULL, stderr=_sp3.DEVNULL)
        except OSError as exc:
            self._log(f"PLANNER-GEMMA: Popen failed: {exc}")
            return None

        deadline = _tm3.time() + 60
        while _tm3.time() < deadline:
            _tm3.sleep(2)
            try:
                with _ur3.urlopen(
                    f"http://{_LOOPBACK}:{port}/health", timeout=2
                ) as r:
                    if r.status == 200:
                        self._log("PLANNER-GEMMA: server healthy")
                        return proc
            except urllib.error.URLError:
                pass

        self._log("PLANNER-GEMMA: health timeout (60 s) — killing proc")
        proc.kill()
        return None

    def _stop_gemma_server(self, proc) -> None:
        """Kill and reap a spawned Gemma llama-server process."""
        try:
            proc.kill()
            proc.wait(timeout=5)
            self._log("PLANNER-GEMMA: server stopped")
        except Exception:  # noqa: BLE001 (cleanup must not crash)
            pass

    # ── v1.14.x detach-on-slow helpers (ff7dd9bc, 2026-08-24) ────────────────
    # planner() runs its heavy half in a worker thread and returns immediately
    # when it exceeds _PLANNER_INLINE_WAIT_S, leaving an in-progress ledger row
    # that the worker finalizes in place. See planner() for the race notes.
    _PLANNER_INLINE_WAIT_S = int(os.environ.get("PLANNER_INLINE_WAIT_S", "120"))

    def _planner_inline_wait_s(self) -> int:
        """Inline-wait threshold (seconds) before planner() detaches to a
        background worker. 120s default: above historical 90-170s planning
        times (most calls stay inline), below the 300s llama-ui MCP client
        ceiling (operator-verified 2026-08-24). Env PLANNER_INLINE_WAIT_S
        overrides for testing."""
        return self._PLANNER_INLINE_WAIT_S

    def _planner_write_in_progress(
        self, tid, task, backend, prior_done_steps, corr
    ) -> None:
        """Ledger row for a detached planner run: status stays 'open' so
        task_resume() finds it; the worker overwrites the SAME row in place
        when the envelope lands (or _planner_mark_detached_failed lands the
        failure)."""
        goal = task.strip()[:300]
        done_lines = "; ".join(
            f"step {s['n']}: {s['what']}" for s in prior_done_steps
        )
        started = datetime.now().astimezone().isoformat()
        self.task_checkpoint(
            goal=goal,
            plan=(
                "PLANNING IN PROGRESS — background worker generating atomized "
                f"steps (backend={backend or 'default'}, started {started})"
            ),
            done=done_lines,
            findings=(
                f"planner detached after {self._planner_inline_wait_s()}s inline "
                f"wait; correlation_id={corr}"
            ),
            next_prompt=(
                f"Planner worker still running for task {tid}. Call "
                f"task_resume('{tid}') to check — this block updates in place "
                "when the plan lands (status stays open). Do NOT call planner() "
                "again for this task."
            ),
            unverified="",
            status="open",
            task_id=tid,
        )

    def _planner_mark_detached_failed(self, tid, error) -> None:
        """Land a detached worker's failure in its in-progress row: stays
        'open' (task_resume finds it) and points the next session at the
        standard fallback."""
        self.task_checkpoint(
            goal=f"(detached planner failed) {tid}",
            plan="(plan never materialized — background worker failed)",
            done="",
            findings=f"detached planner worker failed: {str(error)[:400]}",
            next_prompt=(
                f"PLANNER FAILED for task {tid} (detached worker): "
                f"{str(error)[:400]} Proceed WITHOUT a plan — default budgets "
                "apply, checkpoint early. Do NOT retry planner() for this task."
            ),
            unverified="",
            status="open",
            task_id=tid,
        )

    def _planner_finalize(
        self, env, mode, prior_done_steps, effective_backend, tid, corr, task
    ) -> tuple:
        """Envelope -> ledger write -> return string. Extracted verbatim from
        planner()'s former tail (v1.14.x detach-on-slow) so the fast path and
        the detached worker share ONE finalizer. Returns (result, None) or
        (None, error)."""
        raw_steps = env.get("steps") or []
        legacy_packaged = str(env.get("packaged_prompt", "")).strip()
        goal = str(env.get("goal_summary") or task.strip()[:300])
        # Normalize steps into ledger entries; per-step packaged_prompt is v2 —
        # synthesize a defensive fallback when the model omitted it.
        new_steps = self._normalize_plan_steps(raw_steps, goal, legacy_packaged)
        if not new_steps:
            return None, (
                "PLANNER UNAVAILABLE — no usable steps in envelope. "
                "Proceed with default budgets, checkpoint early."
            )
        # revise: keep completed history in front of the re-planned remainder
        all_steps = prior_done_steps + new_steps
        all_steps.sort(key=lambda s: s.get("n", 0))
        plan_lines = "; ".join(
            f"step {s['n']}: {s['what']} "
            f"(web={s.get('web_calls', 0)}, tools={s.get('tool_calls', 0)}, "
            f"verify: {s.get('verify') or 'NONE'})"
            for s in new_steps
        )
        done_lines = "; ".join(
            f"step {s['n']}: {s['what']}" for s in prior_done_steps
        )
        first = new_steps[0]
        next_prompt = self._plan_step_prompt(goal, all_steps, first)
        ck = self.task_checkpoint(
            goal=goal,
            plan=plan_lines,
            done=done_lines,
            findings="",
            next_prompt=next_prompt,
            unverified="all planner estimates (sessions, budgets) — plan, not fact",
            status="open",
            task_id=tid,
        )
        resolved_backend = self._resolve_backend_name(effective_backend)
        try:
            conn = self._tasks_db()
            with conn:
                conn.execute(
                    "UPDATE task_blocks SET steps_json=?, backend=? WHERE task_id=?",
                    (json.dumps(all_steps), resolved_backend, tid),
                )
            conn.close()
        except Exception as e:  # noqa: BLE001 (DB via _tasks_db helper)
            return None, f"planner: ledger steps write failed: {e}"
        return (
            (
                f"PLAN ENVELOPE accepted ({mode}): task_id={tid} | correlation_id={corr} "
                f"| backend={resolved_backend}\n"
                f"sessions_estimate={env.get('sessions_estimate', '?')} | "
                f"single_session={env.get('single_session', '?')} | "
                f"confidence={env.get('confidence', '?')} | "
                f"steps={len(new_steps)} atomized"
                f"{f' (+{len(prior_done_steps)} already done)' if prior_done_steps else ''}\n"
                f"STEPS: {plan_lines}\n"
                f"ABORT CRITERIA: "
                f"{env.get('abort_criteria', '(none given — budget gate is the only stop)')}\n"
                f"{ck}\n"
                "EXECUTE ONLY THE STEP BELOW, run its verify check, then call "
                f"plan_step_done('{tid}', {first['n']}, evidence=<verify output>) "
                "to strike it and receive the next step. Estimates are NOT facts (P2).\n"
                f"---\n{next_prompt}"
            ),
            None,
        )

    def _tasks_db(self):
        """SQLite handle for the task-block store (auto-creates schema).
        v0.3.2: adds steps_json column (structured per-step plan ledger).
        v1.13.0: adds backend column (which planner backend produced/last
        touched this task's plan — see planner()'s backend param)."""
        import sqlite3  # noqa: PLC0415

        conn = sqlite3.connect(self.valves.TASKS_DB, timeout=5)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS task_blocks ("
            "task_id TEXT PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL, "
            "plan TEXT, done_steps TEXT, findings TEXT, unverified TEXT, "
            "next_prompt TEXT, checkpoints INTEGER DEFAULT 0, "
            "created_at TEXT, updated_at TEXT)"
        )
        cols = [r[1] for r in conn.execute("PRAGMA table_info(task_blocks)")]
        if "steps_json" not in cols:
            conn.execute("ALTER TABLE task_blocks ADD COLUMN steps_json TEXT")
        if "backend" not in cols:
            conn.execute("ALTER TABLE task_blocks ADD COLUMN backend TEXT")
        return conn

    def task_checkpoint(
        self,
        goal: str,
        plan: str,
        done: str,
        findings: str,
        next_prompt: str,
        unverified: str = "",
        status: str = "open",
        task_id: str = "",
    ) -> str:
        """
        Save a progress checkpoint for work that may outlive this session's context.

        CHECKPOINT RULE — mandatory:
          Call this (1) after completing each major step of a multi-step task,
          (2) IMMEDIATELY when any tool result contains a SEARCH BUDGET warning or
          BUDGET EXHAUSTED notice, and (3) with status="done" when a multi-session
          task finishes. Ending a complex task without a final status="done"
          checkpoint is a protocol violation.

        GATE: only for tasks needing more than ~3 tool calls. Do NOT checkpoint
        trivial single-answer lookups.

        FINDINGS vs UNVERIFIED — keep them separate:
          GOOD: findings="quote is in Wilhelm Meisters Wanderjahre (confirmed via
                Gutenberg #5851)", unverified="German wording from memory, not
                checked against source"   ← verified and unverified separated
          BAD:  findings includes a quotation you reconstructed from memory
                ← unverified claims in findings poison the next session, which
                will treat them as established. Protocol violation.

        next_prompt is the single most important field: write the exact prompt a
        fresh session should start from — context, what is done, what remains,
        where to look next. Trust the return value — do NOT call task_resume to
        verify the write.

        Args:
            goal:        One-line statement of the overall task.
            plan:        Remaining steps, ';'-separated.
            done:        Completed steps, ';'-separated.
            findings:    VERIFIED results so far (sources included).
            next_prompt: Exact starting prompt for the next session.
            unverified:  Claims still needing verification, ';'-separated.
            status:      'open' (default), 'done', or 'abandoned'.
            task_id:     Omit on first checkpoint (generated); pass the returned
                         id on every later checkpoint of the same task.
        """
        import hashlib  # noqa: PLC0415

        self._log(f"TASK-CHECKPOINT: status={status} goal={goal[:80]}")
        if status not in ("open", "done", "abandoned"):
            return "ERROR: status must be 'open', 'done', or 'abandoned'."
        if not next_prompt.strip() and status == "open":
            return (
                "CHECKPOINT rejected: next_prompt is required for open tasks — "
                "write the exact prompt the next session should start from."
            )
        now = datetime.now().astimezone().isoformat()
        tid = task_id.strip() or hashlib.sha256(goal.encode()).hexdigest()[:8]
        try:
            conn = self._tasks_db()
            with conn:
                row = conn.execute(
                    "SELECT checkpoints, created_at, steps_json FROM task_blocks "
                    "WHERE task_id=?",
                    (tid,),
                ).fetchone()
                n = (row[0] + 1) if row else 1
                created = row[1] if row else now
                steps_json = row[2] if row else None  # carry the v0.3.2 step ledger
                conn.execute(
                    "INSERT OR REPLACE INTO task_blocks "
                    "(task_id, goal, status, plan, done_steps, findings, unverified, "
                    "next_prompt, checkpoints, created_at, updated_at, steps_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        tid,
                        goal,
                        status,
                        plan,
                        done,
                        findings,
                        unverified,
                        next_prompt,
                        n,
                        created,
                        now,
                        steps_json,
                    ),
                )
            conn.close()
            return (
                f"CHECKPOINT saved: task_id={tid} | status={status} | "
                f"checkpoint #{n}. Resume in a later session with "
                f"task_resume('{tid}')."
            )
        except Exception as e:  # noqa: BLE001 (DB via _tasks_db helper)
            self._log(f"TASK-CHECKPOINT ERROR: {e}")
            return f"CHECKPOINT error: {e}"

    def task_resume(self, task_id: str = "") -> str:
        """
        Load the task block to continue work from a previous session.

        GATE: call ONCE, as your FIRST tool call, when the user says "continue",
        "resume", "where were we", or references unfinished prior work. NEVER
        call mid-task, and never call when the user gives a fresh, self-contained
        task. Calling this more than once per session is a protocol violation.

        AFTER LOADING:
          Treat next_prompt as your working plan. Treat every item in UNVERIFIED
          as NOT established — re-verify before using. Checkpoint progress with
          task_checkpoint(task_id=...) as you work.

        Args:
            task_id: Specific block id. Empty = most recently updated open block.
        """
        self._log(f"TASK-RESUME: {task_id or '(latest open)'}")
        try:
            # v0.3.3: explicit column list — SELECT * broke on the steps_json
            # migration (12 columns vs 11-value unpack), killing resume for ALL
            # blocks. Columns are pinned here; new columns never leak in.
            _COLS = (
                "task_id, goal, status, plan, done_steps, findings, unverified, "
                "next_prompt, checkpoints, created_at, updated_at"
            )
            conn = self._tasks_db()
            if task_id.strip():
                row = conn.execute(
                    f"SELECT {_COLS} FROM task_blocks WHERE task_id=?",
                    (task_id.strip(),),
                ).fetchone()
            else:
                row = conn.execute(
                    f"SELECT {_COLS} FROM task_blocks WHERE status='open' "
                    "ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
            open_count = conn.execute(
                "SELECT COUNT(*) FROM task_blocks WHERE status='open'"
            ).fetchone()[0]
            conn.close()
            if not row:
                return (
                    "No matching task block. Either the id is wrong or there is "
                    "no open carried-over work — ask the user what to do next."
                )
            (
                tid,
                goal,
                status,
                plan,
                done,
                findings,
                unverified,
                next_prompt,
                n,
                created,
                updated,
            ) = row
            return (
                f"TASK BLOCK {tid} [{status}] — checkpoint #{n}, updated {updated}\n"
                f"GOAL: {goal}\n"
                f"DONE: {done or '(none)'}\n"
                f"REMAINING PLAN: {plan or '(none)'}\n"
                f"VERIFIED FINDINGS: {findings or '(none)'}\n"
                f"UNVERIFIED (re-verify before use): {unverified or '(none)'}\n"
                f"NEXT PROMPT: {next_prompt}\n"
                f"(open blocks total: {open_count})"
            )
        except Exception as e:  # noqa: BLE001 (DB via _tasks_db helper)
            self._log(f"TASK-RESUME ERROR: {e}")
            return f"TASK resume error: {e}"

    def plan_step_done(
        self,
        task_id: str,
        step_n: int,
        evidence: str,
        failed: bool = False,
    ) -> str:
        """
        Strike a completed plan step in the ledger and receive the NEXT step's
        packaged prompt (v0.3.2 — the planner↔agent loop for atomized plans).

        EVIDENCE GATE — mandatory:
          evidence must be the step's ACTUAL verify-check output (>=20 chars of
          command output / probe result), not a claim. Same gate as skill_outcome:
          "it worked" is rejected. The evidence is stored on the step for
          forensics and shown in later ledger summaries.
          GOOD: evidence="dig @192.168.1.5 pfsense.home.arpa → 192.168.1.50; 12/12 NOERROR"
                ← the verify command AND its output
          BAD:  evidence="step completed successfully"  ← claim, rejected

        LOOP DISCIPLINE:
          - Call this after executing exactly ONE step from a planner() plan.
          - The return value contains the next step's fresh-context prompt —
            execute ONLY that, then call this again.
          - Never skip ahead, never mark steps you did not execute.
          - Trust the return value — do NOT call task_resume mid-loop to
            re-check the ledger (task_resume is for fresh sessions only).

        CONTEXT HANDOFF — mandatory:
          If context usage is high (>70% or any context-monitor warning), do
          NOT execute the next step in this session. The ledger already
          persists — tell the user to start a fresh session, where
          task_resume returns the next step's prompt with the ledger summary.
          Grinding to the context ceiling mid-step loses work; the handoff
          costs nothing. Continuing past a context warning is a protocol
          violation.

        ON FAILURE:
          failed=True records the step as FAILED with your evidence and tells you
          to call planner(task, mode="revise", task_id=...) — the planner re-plans
          the remaining work with the failure in its ledger context. Do NOT keep
          executing subsequent steps after a failed dependency.

        Args:
            task_id: The ledger id returned by planner().
            step_n:  The step number just executed.
            evidence: Verbatim verify-check output (>=20 chars).
            failed:  True if the step's verify check did NOT pass.
        """
        import json as _json  # noqa: PLC0415

        self._log(f"PLAN-STEP-DONE: {task_id} step={step_n} failed={failed}")
        evidence = (evidence or "").strip()[:500]
        if len(evidence) < 20:
            return (
                "plan_step_done rejected: evidence too thin (<20 chars). Paste the "
                "step's actual verify-check output, not a claim."
            )
        try:
            now = datetime.now().astimezone().isoformat()
            conn = self._tasks_db()
            row = conn.execute(
                "SELECT goal, steps_json, checkpoints FROM task_blocks WHERE task_id=?",
                (task_id.strip(),),
            ).fetchone()
            if not row:
                conn.close()
                return (
                    f"plan_step_done: no task block '{task_id}'. Use the id "
                    "returned by planner()."
                )
            goal, steps_raw, ckpts = row[0], row[1], row[2] or 0
            steps = _json.loads(steps_raw) if steps_raw else []
            if not steps:
                conn.close()
                return (
                    f"plan_step_done: task block '{task_id}' has no step ledger — "
                    "it predates planner v2. Use task_checkpoint instead."
                )
            target = next((s for s in steps if s.get("n") == int(step_n)), None)
            if target is None:
                conn.close()
                ns = ", ".join(str(s.get("n")) for s in steps)
                return f"plan_step_done: no step {step_n} in plan (steps: {ns})."
            if target.get("status") == "done":
                conn.close()
                return f"plan_step_done: step {step_n} is already struck. No change."
            target["status"] = "failed" if failed else "done"
            target["evidence"] = evidence
            target["done_at"] = now
            pending = [s for s in steps if s.get("status") == "pending"]
            done = [s for s in steps if s.get("status") == "done"]
            done_lines = "; ".join(f"step {s['n']}: {s['what']}" for s in done)
            plan_lines = "; ".join(f"step {s['n']}: {s['what']}" for s in pending)
            if failed:
                next_prompt = (
                    f"Step {step_n} FAILED. Call planner(task=<original goal>, "
                    f"mode='revise', task_id='{task_id}') to re-plan the remaining "
                    "work before executing anything else."
                )
                status = "open"
            elif pending:
                next_prompt = self._plan_step_prompt(goal, steps, pending[0])
                status = "open"
            else:
                next_prompt = "(all steps complete)"
                status = "done"
            with conn:
                conn.execute(
                    "UPDATE task_blocks SET steps_json=?, done_steps=?, plan=?, "
                    "next_prompt=?, status=?, checkpoints=?, updated_at=? "
                    "WHERE task_id=?",
                    (
                        _json.dumps(steps),
                        done_lines,
                        plan_lines,
                        next_prompt,
                        status,
                        ckpts + 1,
                        now,
                        task_id.strip(),
                    ),
                )
            conn.close()
            if failed:
                return (
                    f"Step {step_n} recorded as FAILED ❌ (evidence stored).\n"
                    f"{next_prompt}"
                )
            if status == "done":
                return (
                    f"Step {step_n} struck ✔ — ALL {len(steps)} STEPS COMPLETE. "
                    f"Task block {task_id} closed (status=done). Report the "
                    "final outcome to the user with the collected evidence."
                )
            return (
                f"Step {step_n} struck ✔ ({len(done)}/{len(steps)} done, "
                f"{len(pending)} remaining).\n"
                "EXECUTE ONLY THE STEP BELOW, run its verify check, then call "
                f"plan_step_done('{task_id}', {pending[0]['n']}, "
                "evidence=<verify output>).\n"
                f"---\n{next_prompt}"
            )
        except Exception as e:  # noqa: BLE001 (DB via _tasks_db helper)
            self._log(f"PLAN-STEP-DONE ERROR: {e}")
            return f"plan_step_done error: {e}"

    def _parse_planner_envelope(self, reply: str) -> tuple[dict | None, str]:
        """Parse planner reply into JSON envelope.

        Strips thinking blocks and code fences, finds and parses the first
        JSON object, validates it has a 'steps' array.

        Returns (envelope_dict, "") on success, (None, fail_reason) on failure.
        """
        # Strip Qwen3 / DeepSeek thinking blocks before JSON extraction.
        import re as _re  # noqa: PLC0415
        import json as _json  # noqa: PLC0415
        clean = _re.sub(r"<think>.*?</think>", "", reply, flags=_re.DOTALL).strip()
        # Strip markdown code fences (```json ... ```) some models wrap JSON in.
        clean = _re.sub(r"^```[a-z]*\n?", "", clean).rstrip("`").strip()
        # raw_decode parses the FIRST valid JSON object, stopping cleanly at
        # its closing brace regardless of trailing prose or garbage.
        idx = clean.find("{")
        if idx == -1:
            return None, f"no JSON object in reply. RAW: {clean[:200]!r}"
        try:
            env_c, _ = _json.JSONDecoder().raw_decode(clean, idx)
            if env_c.get("steps"):
                return env_c, ""
            return None, "envelope has no 'steps' array"
        except json.JSONDecodeError as _exc:
            return None, (
                f"JSON parse failed ({_exc}). "
                f"RAW: {clean[idx : idx + 200]!r}"
            )

    def _load_ledger_for_revise(
        self, task_id: str, context: str
    ) -> tuple[list, str, Optional[str]] | str:
        """Load ledger history for revise mode.

        Returns (prior_done_steps, updated_context, stored_backend) on
        success, or an error string on failure. stored_backend is whichever
        backend the task was last planned/revised with (None for task
        blocks written before v1.13.0's backend column existed) — planner()
        uses it as the revise-mode default so you don't have to re-specify
        backend='claude' etc. on every follow-up call for the same task_id.
        """
        import json as _json  # noqa: PLC0415
        if not task_id.strip():
            return "planner: mode='revise' requires task_id from the original plan."
        try:
            conn = self._tasks_db()
            row = conn.execute(
                "SELECT goal, steps_json, backend FROM task_blocks WHERE task_id=?",
                (task_id.strip(),),
            ).fetchone()
            conn.close()
        except Exception as e:  # noqa: BLE001 (DB via _tasks_db helper)
            return f"planner revise: ledger read failed: {e}"
        if not row:
            return f"planner revise: no task block '{task_id}' in the ledger."
        old_steps = _json.loads(row[1]) if row[1] else []
        stored_backend = row[2] or None
        prior_done_steps = [s for s in old_steps if s.get("status") == "done"]
        ledger_lines = []
        for s in old_steps:
            st = s.get("status", "pending")
            mark = {"done": "COMPLETED", "failed": "FAILED"}.get(st, "pending")
            line = f"step {s.get('n')}: [{mark}] {s.get('what', '')}"
            if st in ("done", "failed") and s.get("evidence"):
                line += f" | evidence: {str(s['evidence'])[:150]}"
            ledger_lines.append(line)
        context = (
            (context + "\n\n" if context else "")
            + "LEDGER (completed/failed steps of the existing plan — re-plan "
            "ONLY the remaining work, number new steps after the highest "
            "completed step):\n" + "\n".join(ledger_lines)
        )
        return prior_done_steps, context, stored_backend

    def _synthesize_packaged_prompt(
        self,
        is_first_step: bool,
        goal: str,
        step_n: int,
        what: str,
        step_data: dict,
        legacy_packaged: str,
    ) -> str:
        """Generate a packaged_prompt when the planner omitted one.

        Uses the legacy packaged prompt for the first step (if available),
        otherwise synthesizes a defensive prompt from goal + step metadata.
        """
        if is_first_step and legacy_packaged:
            return legacy_packaged
        return (
            f"GOAL: {goal}\n"
            f"YOU ARE EXECUTING STEP {step_n} ONLY: {what}\n"
            f"INPUTS: {step_data.get('inputs', '(see ledger summary)')}\n"
            f"VERIFY: {step_data.get('verify', '')}\n"
            "STOP after this step and report the verify output."
        )

    def _normalize_plan_steps(self, raw_steps: list, goal: str, legacy_packaged: str) -> list:
        """Normalize raw planner steps into ledger entries.

        Synthesizes a defensive packaged_prompt fallback when the model
        omitted it. Returns a list of step dicts ready for the ledger.
        """
        new_steps = []
        for s in raw_steps:
            n = s.get("n")
            what = str(s.get("what", "")).strip()
            if n is None or not what:
                continue
            pkg = str(s.get("packaged_prompt", "")).strip()
            if not pkg:
                pkg = self._synthesize_packaged_prompt(
                    is_first_step=len(new_steps) == 0,
                    goal=goal,
                    step_n=n,
                    what=what,
                    step_data=s,
                    legacy_packaged=legacy_packaged,
                )
            new_steps.append(
                {
                    "n": int(n),
                    "what": what,
                    "depends_on": s.get("depends_on") or [],
                    "inputs": str(s.get("inputs", "")),
                    "output": str(s.get("output", "")),
                    "web_calls": s.get("web_calls", 0),
                    "tool_calls": s.get("tool_calls", 0),
                    "verify": str(s.get("verify", "")),
                    "packaged_prompt": pkg,
                    "status": "pending",
                    "evidence": "",
                    "done_at": None,
                }
            )
        return new_steps

    def _request_plan_envelope(
        self, task: str, context: str, backend: str = ""
    ) -> tuple[dict | None, str | None]:
        """Fetch plan envelope from the selected planner backend with
        two-attempt retry.

        backend: '' → PLANNER_BACKEND valve default, else 'local' |
        'chatgpt' | 'claude' | 'rest' — passed straight through to
        _call_planner_backend, same resolution _resolve_backend_name() uses.

        Returns (envelope_dict, None) on success,
        or (None, error_message) on failure.
        """
        env = None
        fail_reason = ""
        plan_ctx = context
        for attempt in (1, 2):
            reply = self._call_planner_backend(
                task, context=plan_ctx, no_think=True, backend=backend
            )
            if not reply or reply.startswith("ERROR:"):
                return None, (
                    "PLANNER UNAVAILABLE — proceed with default budgets, "
                    f"checkpoint early. ({(reply or 'no reply')[:160]})"
                )
            env, fail_reason = self._parse_planner_envelope(reply)
            if env is not None:
                break
            self._log(f"NODE-PLAN: attempt {attempt} rejected — {fail_reason[:120]}")
            plan_ctx = (
                (context + "\n\n" if context else "")
                + "PREVIOUS REPLY REJECTED: " + fail_reason[:200]
                + "\nReturn ONLY the v2 JSON envelope object — no thinking, no "
                "prose, no code fences. Keep each packaged_prompt under 80 words."
            )
        if env is None:
            return None, (
                f"PLANNER UNAVAILABLE — {fail_reason} (after retry). "
                "Proceed with default budgets, checkpoint early."
            )
        return env, None

    _PLANNER_KB_CHAR_BUDGET = 24000

    _PLANNER_KB_MAX_DOCS = 3

    _PLANNER_KB_TIMEOUT_S = 15

    def _augment_context_with_kb(self, task: str, context: str = "") -> str:
        """Time-bounded wrapper around _augment_context_with_kb_inner.

        search_kb reaches Elasticsearch. When ES is down, slow, or absent (CI,
        a fresh checkout, a stopped container) it can block far longer than a
        planner call should tolerate. Enrichment is a nice-to-have; planning is
        not. On timeout or any failure this returns the caller's context
        unchanged, so the worst case is the old behaviour rather than a hang.
        """
        import concurrent.futures as _cf  # noqa: PLC0415

        pool = _cf.ThreadPoolExecutor(max_workers=1)
        try:
            fut = pool.submit(self._augment_context_with_kb_inner, task, context)
            return fut.result(timeout=self._PLANNER_KB_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 (ThreadPool + KB black-box)
            self._log(
                f"PLANNER-KB: enrichment abandoned after "
                f"{self._PLANNER_KB_TIMEOUT_S}s or error ({type(exc).__name__}); "
                "planning on caller context only"
            )
            return context
        finally:
            # wait=False so a stuck ES read cannot hold the planner hostage.
            pool.shutdown(wait=False)

    def _augment_context_with_kb_inner(self, task: str, context: str = "") -> str:
        """Append the task's top KB matches to the planner context, in full.

        WHY THIS EXISTS (2026-07-29). planner(context=) relied on the caller to
        decide what the planner was allowed to see — which meant the weaker
        model curated input for the stronger one. Measured: the caller read a
        7,300-char KB document in full, then passed a 450-char summary. The
        resulting plan omitted a mkdir, an open-handle check, and a mandatory
        post-reload systemctl restart, all of which were in the dropped text,
        and every step's verify still passed because each verified against its
        own flawed premise.

        Summarising is now structurally impossible for KB material: whatever
        the caller passes, the source documents are attached anyway.

        Reads full document bodies via the `source:` path when a search hit
        exposes one, because search_kb truncates. Never raises — degrades to
        returning the caller's context unchanged, since a planner that fails
        because its optional enrichment failed is worse than one planning on
        less.
        """
        try:
            hits = self.search_kb(task, max_results=self._PLANNER_KB_MAX_DOCS)
        except Exception as exc:  # noqa: BLE001 (KB search black-box)
            self._log(f"PLANNER-KB: search failed, continuing without: {exc}")
            return context
        if not isinstance(hits, str) or not hits.strip():
            return context

        import os as _os  # noqa: PLC0415
        import re as _re2  # noqa: PLC0415

        chunks: list = []
        used = 0
        # Pinned ground truth (2026-07-30): always attach the stack map first
        # so plans cannot cite decommissioned components (the OpenWebUI
        # reference that stalled plan e264ed19). Missing/unreadable file
        # degrades silently to the previous behaviour.
        _PINNED = _os.path.join(_LSE_BASE_PATH, "kb", "STACK-MAP.md")
        try:
            if _os.path.isfile(_PINNED):
                with open(_PINNED, encoding="utf-8", errors="replace") as fh:
                    _pin = fh.read()[: self._PLANNER_KB_CHAR_BUDGET // 4]
                chunks.append(
                    f"--- KB SOURCE (PINNED GROUND TRUTH): {_PINNED} ---\n{_pin}"
                )
                used += len(_pin)
        except OSError:
            pass
        _pinned_n = len(chunks)
        # Prefer full file bodies over truncated search snippets.
        for path in _re2.findall(r"source:\s*(\S+\.md)", hits):
            if used >= self._PLANNER_KB_CHAR_BUDGET:
                break
            for cand in (path, _os.path.join(_LSE_BASE_PATH, path),
                         _os.path.join(_LSE_BASE_PATH, "kb",
                                       _os.path.basename(path))):
                try:
                    if not _os.path.isfile(cand):
                        continue
                    with open(cand, encoding="utf-8", errors="replace") as fh:
                        body = fh.read()
                except OSError:
                    continue
                room = self._PLANNER_KB_CHAR_BUDGET - used
                if len(body) > room:
                    body = body[:room] + "\n[...truncated at planner KB budget]"
                chunks.append(f"--- KB SOURCE: {cand} ---\n{body}")
                used += len(body)
                break

        if len(chunks) == _pinned_n:
            # No readable semantic source; fall back to the search output itself,
            # truncated snippets and all — still better than nothing.
            chunks.append(f"--- KB SEARCH RESULTS ---\n{hits[:self._PLANNER_KB_CHAR_BUDGET]}")

        self._log(
            f"PLANNER-KB: attached {len(chunks)} source(s), {used} chars "
            f"(caller context was {len(context)} chars)"
        )
        header = (
            "=== AUTO-ATTACHED KB MATERIAL (verbatim, appended by planner()) ===\n"
            "Treat this as authoritative operational detail for this system. "
            "It was NOT summarised. If it contradicts the caller context below, "
            "say so explicitly in the plan rather than silently choosing.\n"
        )
        joined = header + "\n\n".join(chunks)
        return f"{context}\n\n{joined}" if context.strip() else joined

    def planner(
        self,
        task: str,
        context: str = "",
        mode: str = "new",
        task_id: str = "",
        backend: str = "",
    ) -> str:
        """
        SPEC: Get an ATOMIZED execution plan for a multi-step task. Writes to the
        tasks.db ledger; you execute ONE step, then call plan_step_done().

        MANDATORY TRIGGER — the user asked for a plan:
        If the request contains "plan", "get a plan", "how should we approach",
        or assigns a multi-phase audit/migration/overhaul, calling planner() is
        REQUIRED. NEVER hand-write a plan in prose. NEVER create plan.md.

        GATE — planner comes before EXECUTION, not before reading:
        Information gathering does NOT close the planning window. search_kb,
        skill_search, and read-only probes BEFORE planner are correct — KB-FIRST
        still applies — and their findings belong in context= VERBATIM, not
        summarised. The window closes when you start CHANGING state or producing
        deliverables.

        THIS CALL USUALLY BLOCKS for 90-170s while the plan is generated;
        wait for it, do NOT retry it, and do NOT start writing a plan
        yourself while it runs. Calling planner() a second time for the same
        task is a protocol violation.

        SLOW-CALL BEHAVIOUR (detach-on-slow): if the plan has not landed
        within the inline threshold (120s default, env PLANNER_INLINE_WAIT_S)
        the call returns "PLAN IN PROGRESS: task_id=..." immediately and the
        plan finishes in the background. Poll with task_resume('<task_id>') —
        the block updates in place when the plan lands (status stays open).
        Do NOT call planner() again for that task while the worker runs.

        DO NOT call for single-fact lookups, procedures under 3 steps (execute
        directly), or resuming carried-over work (that is task_resume).

        AFTER A PLAN IS RETURNED — mandatory step loop:
        1. Execute ONLY the step in the packaged prompt at the END of planner().
        2. Run that step's verify check and call
           plan_step_done(task_id, step_n, evidence=<verify output>).
        3. plan_step_done returns the NEXT step's packaged prompt — repeat.
        Do NOT look ahead, do NOT execute multiple steps from one prompt.
        On a FAILED step: plan_step_done(..., failed=True), then
        planner(task, mode="revise", task_id=<id>) to re-plan the remainder.
        Planner estimates are ESTIMATES, not established facts: never copy
        them into findings, never raise skill/KB quality from a plan (P2).
        Ignoring the abort criteria is a protocol violation.

        ON "PLANNER UNAVAILABLE": proceed WITHOUT a plan: default budgets apply,
        checkpoint early. Do NOT retry planner more than once per task.

        Planner backend — pick with backend= or the PLANNER_BACKEND valve
        (default 'local'):
          'local'   (default) node3090 llama-server :8080 (Qwen 27B, GPU) —
                    primary. Falls back to VRAM-aware local Gemma GGUF spawn.
          'chatgpt' OpenAI, via Codex CLI OAuth or PLANNER_OPENAI_API_KEY.
          'claude'  Anthropic, via Claude Code OAuth or PLANNER_ANTHROPIC_API_KEY.
          'rest'    Any OpenAI-compatible /v1/chat/completions server.

        Args:
            task:    The user's task, verbatim or lightly cleaned.
            context: Source material — VERBATIM, never a summary. Paste actual
                     text: KB bodies, command output, config contents. Do NOT
                     compress into a précis. THIS IS THE #1 CAUSE OF BAD PLANS.
                     Length is not a concern. When in doubt, paste more.
                     planner() also auto-attaches top KB matches for the task.
            mode:    "new" (default) or "revise". Revise loads the ledger for
                     task_id and replaces only the remaining steps.
            task_id: Required for mode="revise".
            backend: '' (default) uses the valve; or 'local'|'chatgpt'|'claude'|'rest'.

        NOTES:
        AUTO-KB: planner() runs its own search_kb on the task and appends top
        matches to whatever context you pass. You do not need to paste KB content
        you already found — but pasting live probe output is still essential.
        DETACH-ON-SLOW: see SLOW-CALL BEHAVIOUR above — slow plans land in the
        ledger via a background worker; task_resume() is the only follow-up.
        """
        import hashlib  # noqa: PLC0415

        self._log(f"NODE-PLAN: mode={mode} {task[:80]}")
        corr = hashlib.sha256((task + datetime.now().isoformat()).encode()).hexdigest()[
            :12
        ]
        # ── v0.3.2 revise mode: feed the ledger back to the planner ──────────
        prior_done_steps: list = []
        stored_backend: Optional[str] = None
        if mode == "revise":
            result = self._load_ledger_for_revise(task_id, context)
            if isinstance(result, str):
                return result
            prior_done_steps, context, stored_backend = result
        elif mode != "new":
            return "planner: mode must be 'new' or 'revise'."
        # v1.13.0: an explicit backend= wins; otherwise a revise call reuses
        # whatever backend the task was last planned with; a brand-new task
        # falls through to the PLANNER_BACKEND valve inside
        # _resolve_backend_name/_call_planner_backend.
        effective_backend = backend or stored_backend or ""
        # v0.3.3: NEVER trust a model-supplied task_id — live smoke showed the
        # model copying the schema example ("a1b2c3d4") verbatim, which would
        # collide every plan onto one ledger row. corr already hashes task+now.
        # Computed here, before the worker starts, so the detach path's
        # in-progress row uses the same id.
        tid = task_id.strip() if mode == "revise" else corr[:8]
        # ── v1.14.x detach-on-slow (ff7dd9bc, 2026-08-24) ─────────────────────
        # The heavy half (KB augmentation + two-attempt envelope loop) runs in
        # a worker thread. Lands within _PLANNER_INLINE_WAIT_S -> returned
        # inline, byte-identical to the pre-detach behaviour. Slower -> an
        # in-progress ledger row is left behind and this call returns
        # immediately; the worker finalizes the SAME row in place when the
        # envelope lands (or records the failure). task_resume() finds the row
        # in either state. This bounds the MCP tool call itself so a slow
        # backend can no longer outlive the client ceiling (llama-ui MCP
        # request timeout = 300s, operator-verified 2026-08-24) — the durable
        # fix for bare "timed out" planner failures.
        #
        # Race note: `gate` makes the fast/slow hand-off atomic. The worker is
        # the sole ledger finalizer on the slow path; on the fast path it has
        # already finished when `ready` is observed and the main thread
        # finalizes. Exactly one finalizer runs in every interleaving, so the
        # row can never be stranded "PLANNING IN PROGRESS".
        inline_wait = self._planner_inline_wait_s()
        state = {"env": None, "error": None, "ready": False, "detached": False}
        gate = threading.Lock()

        def _finalize() -> tuple:
            if state["error"]:
                return None, state["error"]
            return self._planner_finalize(
                state["env"], mode, prior_done_steps, effective_backend, tid, corr, task
            )

        def _worker():
            try:
                ctx = self._augment_context_with_kb(task, context)
                env, error = self._request_plan_envelope(
                    task, ctx, backend=effective_backend
                )
            except Exception as e:  # noqa: BLE001 (worker must not die silently)
                env, error = None, f"PLANNER UNAVAILABLE — worker crashed: {e}"
            with gate:
                state["env"], state["error"] = env, error
                state["ready"] = True
                if state["detached"]:
                    # Slow path: land the outcome in the in-progress row.
                    _, ferr = _finalize()
                    if ferr:
                        self._log(
                            f"NODE-PLAN: detached worker FAILED task_id={tid}: "
                            f"{ferr[:200]}"
                        )
                        self._planner_mark_detached_failed(tid, ferr)
                    else:
                        self._log(f"NODE-PLAN: detached worker landed task_id={tid}")

        w = threading.Thread(target=_worker, name=f"planner-{tid}", daemon=True)
        w.start()
        w.join(inline_wait)
        with gate:
            if state["ready"]:
                # Fast path: worker landed within the inline threshold.
                out, ferr = _finalize()
                return ferr if ferr else out
            state["detached"] = True
        self._log(f"NODE-PLAN: slow (>={inline_wait}s) — detaching task_id={tid}")
        self._planner_write_in_progress(tid, task, effective_backend, prior_done_steps, corr)
        return (
            f"PLAN IN PROGRESS: task_id={tid} | correlation_id={corr} | "
            f"backend={effective_backend or 'default'}\n"
            f"Plan generation exceeded the {inline_wait}s inline threshold and "
            f"continues in the background. Call task_resume('{tid}') to check "
            "— the block updates in place when the plan lands (status stays "
            "open). Do NOT call planner() again for this task and do NOT retry "
            "while the worker runs."
        )

    def _plan_step_prompt(self, goal: str, all_steps: list, step: dict) -> str:
        """Build the fresh-context prompt for ONE plan step: compact ledger
        summary + the step's own packaged prompt (v0.3.2 context-ceiling tool)."""
        done = [s for s in all_steps if s.get("status") == "done"]
        pending = [s for s in all_steps if s.get("status") == "pending"]
        ledger = []
        for s in done[-8:]:  # cap ledger growth — oldest strikes fall away
            ev = str(s.get("evidence", ""))[:120]
            ledger.append(f"  ✔ step {s['n']}: {s['what']}" + (f" — {ev}" if ev else ""))
        remaining = ", ".join(str(s["n"]) for s in pending)
        header = (
            f"[PLAN {goal[:120]}]\n"
            f"LEDGER — completed:\n" + ("\n".join(ledger) or "  (none yet)") + "\n"
            f"REMAINING steps: {remaining or '(this is the last one)'}\n"
            f"YOU ARE EXECUTING STEP {step['n']} ONLY. Do not look ahead.\n"
            "---\n"
        )
        return header + step["packaged_prompt"]