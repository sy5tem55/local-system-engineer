#!/usr/bin/env python3
"""
goethe_node.py — GPU node lifecycle, extracted from goethe.py
============================================================================
D7 (2026-07-31): second mixin extraction of the 2026-07-31 refactor, per
docs/D7-MIXIN-EXTRACTION-PLAN.md Step 8. Extracted after NetSecMixin (the
pilot) proved the pattern; NodeLifecycle has the next-lowest external
coupling (self._log, self._live_node_profile).

`Tools` in goethe.py inherits `NodeLifecycleMixin` alongside `KBMixin` and
`NetSecMixin`; goethe_mcp discovers tools via dir(instance), so the exposed
MCP tool list is unchanged. Follows the goethe_kb.KBMixin shape: a plain
class with no __init__ and no Valves declaration, using self.valves /
self._log / self._live_node_profile from the host Tools class. This module
must never import goethe.py — import direction is one-way, goethe.py
imports this file.

Methods and constants moved verbatim (2026-07-31, from tools/goethe.py @
10b6b50, lines 4022-4066, 4068-4210, 4212-4308, 4319-4330, 4398-4465,
4467-4605, 4607-4649, 4651-4738):
  _NODE_REGISTRY, _PROFILE_FLAGS, wake_node, query_node_agent,
  check_node_agent_drift, start_node_agent, stop_node_agent, shutdown_node

DELIBERATELY LEFT ON Tools (not moved): `_parse_llama_cmdline` and
`_live_node_profile`. The D7 plan named `_live_node_profile` as an external
dependency to leave in place; auditing its call graph during this extraction
found `_parse_llama_cmdline` is called ONLY by `_live_node_profile` (never
directly by any NodeLifecycle method), so it travels with its sole caller
rather than with this mixin. Both stay co-located on Tools and are called
via self, exactly as `_live_node_profile` already is from
check_node_agent_drift and start_node_agent.

No logic, docstring, or formatting changes were made during the move — this
is a pure relocation. Behavior is pinned by the full test suite plus the
runtime proof recorded in docs/D7-MIXIN-EXTRACTION-PLAN.md Step 8, which
explicitly checks self._NODE_REGISTRY["node3090"]["hostname"] resolves via
MRO — the D6 sweep rewired the reddit-fallback path in goethe.py to read
this attribute through self, so a broken move here would silently break
browser rendering with zero test coverage.
"""


import os
import subprocess

class NodeLifecycleMixin:
    """GPU node lifecycle tool methods (wake/query/drift-check/start/stop/
    shutdown) mixed into goethe.Tools. Uses self.valves, self._log, and
    self._live_node_profile (which remains on the host class) from Tools.
    """

    # ── Node Registry ─────────────────────────────────────────────────────────
    _NODE_REGISTRY: dict = {
        "node3090": {
            "mac": "0c:9d:92:84:6e:6a",
            "hostname": "node3090.home.arpa",
            "interface": "opt1",
            "agent_port": 8080,
            "agent_type": "llama-cpp",
            "os": "linux",
            "ssh_user": "lse-admin",
            "agent_profile": {
                "model": "/opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf",
                "ctx_size": 131072,
                "gpu_layers": 99,
                "flash_attn": True,
                "cache_type_k": "q4_0",
                "cache_type_v": "q4_0",
                "parallel": 1,
                "threads": 16,
                "threads_batch": 16,
                "reasoning_format": "none",
                "reasoning_budget": 16000,
                "n_predict": 8192,
                "jinja": True,
                "metrics": True,
            },
        },
        # STALE — NOT MIGRATED (flagged 2026-07-29). LM Studio was
        # decommissioned across the fleet in favour of llama-server; node3090
        # was migrated in v1.5.23 but this entry never was. agent_port 8081 /
        # agent_type "lmstudio" describe software that no longer runs. The
        # node was asleep at time of writing, so the live configuration could
        # not be read to correct it. Do NOT treat these values as current:
        # run check_node_agent_drift("node5090") once the node is awake and
        # set them from what is actually there.
        "node5090": {
            "mac": "a0:ad:9f:84:d5:bf",
            "hostname": "node5090.home.arpa",
            "interface": "lan",
            "agent_port": 8081,
            "agent_type": "lmstudio",
            "os": "windows",
            "ssh_user": "sy5",
            "_stale": "unmigrated from LM Studio; verify before use (2026-07-29)",
        },
    }

    _PROFILE_FLAGS = {
        "model": "--model",
        "ctx_size": "--ctx-size",
        "gpu_layers": "--n-gpu-layers",
        "cache_type_k": "--cache-type-k",
        "cache_type_v": "--cache-type-v",
        "parallel": "--parallel",
        "threads": "--threads",
        "threads_batch": "--threads-batch",
        "reasoning_format": "--reasoning-format",
        "reasoning_budget": "--reasoning-budget",
        "n_predict": "--n-predict",
    }

    def wake_node(self, node: str) -> str:
        """
        Wake a GPU node: ping first (skip WoL if already up), consult KB for
        current procedure, then send WoL via pfSense and poll until pingable.

        WORKFLOW
          Step 1 — Ping: if the node already responds, return immediately.
          Step 2 — KB lookup: search_kb for the node's current wake procedure.
                   Surface any KB notes before proceeding (interface changes,
                   known boot quirks, updated timeouts).
          Step 3 — WoL: POST magic packet via pfSense REST API.
          Step 4 — Poll ping for up to 120s; return once the node is up.

        WRITE ACCESS NOTE:
          WoL is a POST to pfSense (/api/v2/services/wake_on_lan/send). It sends
          a UDP magic packet only — it does NOT modify pfSense config. Still
          requires pfSense read-only mode to be disabled before calling.
          After waking: re-enable read-only before ending the session.

        FULL LIFECYCLE — call in order:
          1. wake_node(node)           — this tool
          2. query_node_agent(node, …) — delegate work to the GPU node's AI agent
          3. shutdown_node(node)       — shut down when done

        Args:
            node: "node3090" or "node5090"

        Returns:
            Status string: already-up / booted with elapsed time / error.
        """
        import time, subprocess  # noqa: PLC0415
        import json as _json  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        hostname = reg["hostname"]

        # ── Step 1: ping — skip WoL entirely if the node is already up ─────────
        self._log(f"WAKE-NODE: pinging {node} ({hostname}) to check current state")
        ping_check = subprocess.run(
            ["ping", "-c", "1", "-W", "2", hostname],
            capture_output=True,
        )
        if ping_check.returncode == 0:
            self._log(f"WAKE-NODE: {node} is already up — WoL skipped")
            return (
                f"{node} is already up (ping OK — WoL skipped).\n"
                f"Agent: http://{hostname}:{reg['agent_port']}/v1/\n"
                f"Next: call query_node_agent('{node}', prompt)"
            )

        # ── Step 2: KB lookup — surface any updated procedure or known quirks ───
        self._log(f"WAKE-NODE: checking KB for '{node} wake procedure'")
        kb_notes = ""
        try:
            kb_result = self.search_kb(f"{node} wake procedure")
            if kb_result and "no results" not in kb_result.lower():
                kb_notes = f"\nKB notes for {node}:\n{kb_result}\n"
                self._log(f"WAKE-NODE: KB returned notes ({len(kb_result)} chars)")
            else:
                self._log("WAKE-NODE: no KB notes found — proceeding with registry defaults")
        except Exception as exc:  # noqa: BLE001 (KB is black-box)
            self._log(f"WAKE-NODE: KB lookup failed ({exc}) — continuing anyway")

        # ── Step 3: send WoL magic packet via pfSense ────────────────────────────
        self._log(
            f"WAKE-NODE: sending WoL for {node} ({reg['mac']}) on {reg['interface']}"
        )
        # Direct pfSense call, not self.pfsense_query() -- pfsense_query now lives
        # in a separate module/instance (lse/skills/pfsense/tools.py, loaded via
        # `--also`), so it is not reachable as a method on this goethe.py Tools
        # instance. This is a self-contained inline POST instead of a byte-for-byte
        # copy of pfsense_query's full machinery (log guard / confirmed gate /
        # response cap) because none of that applies here: this is a single fixed,
        # non-log, non-persistent-config endpoint (a UDP magic packet, not a
        # config write), and the explicit wake_node(node) call by name is itself
        # the user's confirmation to wake that node. PFSENSE_URL/API_KEY/CA_CERT
        # valves are intentionally still defined on this Tools class (unlike the
        # vault extraction, which removed BW_* entirely) precisely because of
        # this one remaining direct dependency.
        import requests as _wol_req  # noqa: PLC0415

        wol_key = self.valves.PFSENSE_API_KEY.strip()
        wol_cert = self.valves.PFSENSE_CA_CERT.strip()
        wol_verify = wol_cert if (wol_cert and os.path.isfile(wol_cert)) else False
        try:
            wol_resp = _wol_req.post(
                self.valves.PFSENSE_URL.rstrip("/") + "/api/v2/services/wake_on_lan/send",
                headers={"X-API-Key": wol_key, "Content-Type": "application/json"},
                json={"interface": reg["interface"], "mac": reg["mac"]},
                verify=wol_verify,
                timeout=15,
            )
            try:
                wol_result = f"[HTTP {wol_resp.status_code}] {_json.dumps(wol_resp.json())}"
            except Exception:  # noqa: BLE001 (WoL JSON parse fallback)
                wol_result = f"[HTTP {wol_resp.status_code}] {wol_resp.text[:500]}"
            if wol_resp.status_code >= 400:
                wol_result = "ERROR: " + wol_result
        except _wol_req.RequestException as exc:
            wol_result = f"ERROR: WoL request to pfSense failed: {exc}"
        self._log(f"WAKE-NODE: pfSense response: {wol_result[:120]}")

        # Fast-fail: if the API call itself failed, do not waste 120s polling
        if wol_result.startswith("ERROR") or wol_result.startswith("[HTTP"):
            return (
                f"WAKE ABORTED — pfSense WoL API error (not starting poll):\n"
                f"{wol_result[:300]}\n"
                f"{kb_notes}"
                "Common causes:\n"
                "  • PFSENSE_API_KEY valve not set\n"
                "  • pfSense Read Only mode still enabled\n"
                "  • Endpoint mismatch (correct: POST /api/v2/services/wake_on_lan/send)"
            )

        # ── Step 4: poll ping — up to 120s ───────────────────────────────────────
        start = time.time()
        for attempt in range(60):
            time.sleep(2)
            if attempt % 5 == 0:
                self._log(f"WAKE-NODE: waiting for {node}... {attempt*2}s elapsed")
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "2", hostname],
                capture_output=True,
            )
            if r.returncode == 0:
                elapsed = int(time.time() - start)
                self._log(f"WAKE-NODE: {node} up in {elapsed}s")
                return (
                    f"{node} is up — boot took {elapsed}s.\n"
                    f"{kb_notes}"
                    f"Agent: http://{hostname}:{reg['agent_port']}/v1/\n"
                    f"Next: call query_node_agent('{node}', prompt)"
                )

        return (
            f"TIMEOUT: {node} did not respond to ping after 120s.\n"
            f"WoL was sent (pfSense: {wol_result[:80]}).\n"
            f"{kb_notes}"
            "Check pfSense OPT1 interface selection and node power state."
        )

    def query_node_agent(
        self,
        node: str,
        prompt: str,
        model: str = "",
        max_tokens: int = 2000,
        system_prompt: str = "",
    ) -> str:
        """
        Send a prompt to the model served by a GPU node's llama-server.

        THE NODE HAS NO TOOLS. This posts to llama-server's OpenAI-compatible
        /v1/chat/completions and returns text. The node cannot run commands,
        read files, or change anything. If the reply proposes an action, YOU
        must carry it out via execute_command / ssh_run after reviewing it.
        A tool-call block in the response means the model hallucinated one —
        nothing ran. This is enforced, not advisory: a no-tools system prompt
        is injected on every call and tool-call output is flagged on return.

        Endpoint comes from _NODE_REGISTRY[node]["agent_port"], NOT a fixed
        port. Do not assume 8081 — that was LM Studio, decommissioned in
        favour of llama-server across all nodes (registry migrated in
        v1.5.23; this docstring corrected in v1.14.0, having outlived the
        change by long enough to cause a live misdiagnosis).

        NOT the node's Goethe gateway. node3090 also runs goethe_mcp on 9700,
        which DOES have tools and which llama-ui calls directly from the
        browser. This function deliberately does not touch it — see
        docs/11-node-agent-delegation.md for why that separation is load-
        bearing rather than an oversight.

        Node must already be awake — call wake_node() first if needed.
        Response is returned directly — do not re-summarise unless needed.

        Args:
            node:          A key of _NODE_REGISTRY (currently "node3090" or
                           "node5090"). Note node4090 is an alias for LUCIFER
                           itself, is not a remote node, and is not routable
                           here.
            prompt:        User message to send to the node's model.
            model:         Model name override. Empty uses whatever model
                           llama-server was started with.
            max_tokens:    Max tokens for the response (default 2000).
            system_prompt: Optional system prompt. The no-tools instruction is
                           appended to it, never replaced by it.

        Returns:
            The model's response text, or an error string beginning "Cannot
            reach" / "query_node_agent error:".
        """
        import requests as _req  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        url = f"http://{reg['hostname']}:{reg['agent_port']}/v1/chat/completions"
        _no_tools = (
            "You have NO tools, functions, or command execution on this node. "
            "Reply in plain text only. Never emit <tool_call>, <function=...>, "
            "or JSON function-call blocks. If action is needed, describe the "
            "exact command for the operator to run instead."
        )
        _sys = (system_prompt + "\n\n" + _no_tools) if system_prompt else _no_tools
        messages = [{"role": "system", "content": _sys}]
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        if model:
            payload["model"] = model

        self._log(f"QUERY-NODE-AGENT: POST {url} ({len(prompt)} chars)")
        try:
            resp = _req.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            self._log(f"QUERY-NODE-AGENT: got {len(content)} chars from {node}")
            if "<tool_call>" in content or "<function=" in content:
                content += (
                    "\n\n[goethe note: the node agent emitted a tool-call block "
                    "above, but node agents have NO tools -- NOTHING was "
                    "executed on the node. Treat it as a suggested command: "
                    "review it, then run it yourself via execute_command or "
                    "ssh_run if appropriate.]"
                )
            return content
        except _req.exceptions.ConnectionError:
            return (
                f"Cannot reach {node} at {url}. "
                "Is the node awake? Call wake_node() first."
            )
        except _req.RequestException as exc:
            return f"query_node_agent error: {exc}"

    def check_node_agent_drift(self, node: str) -> str:
        """
        Compare a GPU node's CANONICAL agent_profile against the llama-server
        actually running on it, and report every discrepancy.

        Call this before start_node_agent() or stop_node_agent() on a node that
        may already be serving, and whenever a node's behaviour does not match
        what the registry claims it should be.

        Reports three distinct kinds of drift, which need different responses:
          CHANGED    — canonical and live disagree on a value. Decide which is
                       right, then either fix the registry or restart the node.
          MISSING    — canonical sets something the live server is not running.
          UNMODELLED — the live server runs flags agent_profile cannot express,
                       so a restart WOULD SILENTLY DROP THEM. This is the one
                       that loses work.

        Read-only: SSH plus pgrep, no state change. Safe to call freely.

        Args:
            node: A key of _NODE_REGISTRY ("node3090" / "node5090").

        Returns:
            A drift report, or "no drift" when canonical and live agree.
        """
        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"
        canon = reg.get("agent_profile")
        if not canon:
            return f"No agent_profile defined for '{node}' — nothing to compare."

        live, err = self._live_node_profile(node)
        if err:
            return f"Could not read live profile for {node}: {err}"
        if live is None:
            return (f"{node}: no llama-server running — nothing to compare. "
                    f"Canonical profile is the only description that exists.")

        changed, missing = [], []
        for key, want in canon.items():
            if key not in live:
                missing.append(f"  MISSING    {key}: canonical={want!r}, not set on live server")
                continue
            got = live[key]
            if str(want) != str(got):
                changed.append(f"  CHANGED    {key}: canonical={want!r} -> live={got!r}")

        unmodelled = live.get("_unmodelled") or []
        lines = [f"Agent profile drift for {node} (canonical _NODE_REGISTRY vs live server):"]
        lines += changed or []
        lines += missing or []
        if unmodelled:
            lines.append(
                f"  UNMODELLED live flags agent_profile cannot express "
                f"({len(unmodelled)}): {' '.join(unmodelled)}"
            )
            lines.append(
                "             A start_node_agent() restart would DROP these."
            )
        if not changed and not missing and not unmodelled:
            return f"{node}: no drift — canonical profile matches the live server."
        lines.append(
            "ACTION: decide which side is authoritative. If live is correct, "
            "update _NODE_REGISTRY[\"" + node + "\"][\"agent_profile\"] to match "
            "before any restart."
        )
        return "\n".join(lines)

    def start_node_agent(self, node: str, force: bool = False) -> str:
        """
        Start the llama-cpp inference server on a GPU node using its CANONICAL
        registered agent_profile.

        REFUSES BY DEFAULT IF A SERVER IS ALREADY RUNNING. This is not
        politeness. The previous version launched unconditionally: the second
        process failed to bind the port, but the /health poll then answered
        from the FIRST server and this function reported success. A restart
        that silently did nothing looked identical to one that worked.

        When a server is already up, this runs check_node_agent_drift() and
        returns the report instead of launching. Read it before overriding —
        drift means the live server is NOT what agent_profile describes, and
        force=True will restart it into the canonical configuration, dropping
        any live setting the profile cannot express.

        Launches via SSH with nohup so the server persists after the SSH
        session ends. Logs to /home/<ssh_user>/llama-server.log on the node.
        Polls /health for up to 120s.

        Node must be awake — call wake_node() first if needed.
        To stop: stop_node_agent(node).

        SUDO EXEMPTION: server runs as lse-admin, no sudo required.

        Args:
            node:  A key of _NODE_REGISTRY ("node3090" / "node5090").
            force: Restart even if a server is already running. Requires the
                   operator to have seen the drift report first.

        Returns:
            Confirmation with PID and endpoint, a drift report, or an error.
        """
        import subprocess as _sp  # noqa: PLC0415
        import time as _time  # noqa: PLC0415
        import requests as _req  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        profile = reg.get("agent_profile")
        if not profile:
            return f"No agent_profile defined for '{node}'. Update _NODE_REGISTRY."

        # Pre-flight: never relaunch over a running server. See the docstring
        # for why the old unconditional launch reported false success.
        _live, _err = self._live_node_profile(node)
        if _live is not None and not force:
            return (
                f"{node} already has a llama-server running — NOT relaunching.\n\n"
                + self.check_node_agent_drift(node)
                + "\n\nIf you intend to restart it into the canonical profile, "
                  "call stop_node_agent() first, or start_node_agent(node, "
                  "force=True). Review the drift report above before doing so."
            )

        hostname = reg["hostname"]
        user = reg["ssh_user"]
        port = reg["agent_port"]
        log_path = f"/home/{user}/llama-server.log"

        # Build CLI args from profile dict
        parts = ["llama-server"]
        parts += ["--model", profile["model"]]
        parts += ["--port", str(port)]
        parts += ["--host", "0.0.0.0"]
        parts += ["--ctx-size", str(profile["ctx_size"])]
        parts += ["--n-gpu-layers", str(profile["gpu_layers"])]
        if profile.get("flash_attn"):
            parts += ["--flash-attn", "on"]
        if profile.get("cache_type_k"):
            parts += ["--cache-type-k", profile["cache_type_k"]]
        if profile.get("cache_type_v"):
            parts += ["--cache-type-v", profile["cache_type_v"]]
        if profile.get("parallel"):
            parts += ["--parallel", str(profile["parallel"])]
        if profile.get("threads"):
            parts += ["--threads", str(profile["threads"])]
        if profile.get("threads_batch"):
            parts += ["--threads-batch", str(profile["threads_batch"])]
        if profile.get("reasoning_format"):
            parts += ["--reasoning-format", profile["reasoning_format"]]
        if profile.get("reasoning_budget"):
            parts += ["--reasoning-budget", str(profile["reasoning_budget"])]
        if profile.get("n_predict"):
            parts += ["--n-predict", str(profile["n_predict"])]
        if profile.get("jinja"):
            parts.append("--jinja")
        if profile.get("metrics"):
            parts.append("--metrics")

        cmd_str = " ".join(parts)
        # Background via nohup; stdin from /dev/null so SSH exits cleanly
        remote_cmd = f"nohup {cmd_str} </dev/null >{log_path} 2>&1 & echo PID:$!"

        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            f"{user}@{hostname}",
            remote_cmd,
        ]

        self._log(f"START-NODE-AGENT: launching llama-server on {node}")
        try:
            r = _sp.run(ssh_cmd, capture_output=True, text=True, timeout=20)
            if r.returncode != 0:
                return f"SSH failed (exit {r.returncode}): {r.stderr.strip()}"
            pid_line = r.stdout.strip()
        except subprocess.SubprocessError as exc:
            return f"start_node_agent SSH error: {exc}"

        # Poll /health — model load takes 30-90s
        health_url = f"http://{hostname}:{port}/health"
        self._log(f"START-NODE-AGENT: polling {health_url}")
        deadline = _time.time() + 120
        while _time.time() < deadline:
            _time.sleep(5)
            try:
                resp = _req.get(health_url, timeout=3)
                if resp.status_code == 200:
                    elapsed = round(_time.time() - (deadline - 120))
                    return (
                        f"{node} agent ready ({pid_line}) — loaded in ~{elapsed}s\n"
                        f"Endpoint: http://{hostname}:{port}/v1/\n"
                        f"Log: ssh {user}@{hostname} tail -f {log_path}\n"
                        f"Stop: call stop_node_agent('{node}')"
                    )
            except Exception:  # noqa: BLE001 (health poll cleanup)
                pass

        return (
            f"Timeout: llama-server started ({pid_line}) but /health not responding after 120s. "
            f"Check: ssh {user}@{hostname} tail {log_path}"
        )

    def stop_node_agent(self, node: str) -> str:
        """
        Stop the llama-cpp inference server on a GPU node via SSH pkill.

        SAFETY: confirm no active inference jobs before calling.
        GPU VRAM is released immediately on stop.

        SUDO EXEMPTION: pkill runs as lse-admin, no sudo required.

        Args:
            node: "node3090" or "node5090"

        Returns:
            Confirmation or error string.
        """
        import subprocess as _sp  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        hostname = reg["hostname"]
        user = reg["ssh_user"]

        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            f"{user}@{hostname}",
            "pkill -f llama-server && echo stopped || echo no_process",
        ]

        self._log(f"STOP-NODE-AGENT: pkill llama-server on {node}")
        try:
            r = _sp.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            output = r.stdout.strip() or r.stderr.strip()
            return f"{node} agent: {output}"
        except subprocess.SubprocessError as exc:
            return f"stop_node_agent error: {exc}"

    def shutdown_node(self, node: str, confirmed: bool = False) -> str:
        """
        Gracefully shut down a GPU node via SSH.

        CONFIRMATION REQUIRED — two-step call protocol:
          1. Call shutdown_node(node) — returns a confirmation prompt. STOP.
             Show the prompt to the user and wait for explicit approval.
          2. Only after the user says yes: call shutdown_node(node, confirmed=True).
          Never pass confirmed=True on the first call. Never assume consent.

        SAFETY RULES — mandatory before calling:
          - Confirm all GPU workloads on the node are complete.
          - Confirm query_node_agent() has returned its final response.

        SUDO EXEMPTION — do NOT call sudo_delegation_block for this function:
          The sudo runs remotely on the target node via SSH, not on LUCIFER.
          node3090 is configured with NOPASSWD sudoers for /sbin/shutdown (lse-admin).
          This is a pre-approved, pre-configured remote operation — call execute_command
          directly. Invoking sudo_delegation_block here is a protocol violation.

        SSH requirements:
          - LUCIFER lse-admin SSH key authorised on target node (no password prompt).
          - node3090 (Linux): /etc/sudoers.d/lse-shutdown grants NOPASSWD for shutdown.
          - node5090 (Windows): sy5 SSH session — SSH server must be enabled.

        Args:
            node:      "node3090" or "node5090"
            confirmed: Must be explicitly set to True by the user. Default False
                       returns a confirmation prompt without taking any action.

        Returns:
            Confirmation prompt (confirmed=False) or shutdown result (confirmed=True).
        """
        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        hostname = reg["hostname"]
        user = reg["ssh_user"]
        os_type = reg["os"]

        # ── Confirmation gate — always return prompt unless user explicitly approved ──
        if not confirmed:
            shutdown_cmd = "sudo shutdown -h now" if os_type == "linux" else "shutdown /s /t 30"
            return (
                f"⚠️  SHUTDOWN CONFIRMATION REQUIRED\n"
                f"  Node:    {node} ({hostname})\n"
                f"  OS:      {os_type}\n"
                f"  Command: {shutdown_cmd} (via SSH as {user})\n\n"
                f"This will power off the node immediately. All running workloads will be lost.\n\n"
                f"Reply 'yes' to confirm, then I will call shutdown_node('{node}', confirmed=True)."
            )

        # ── Confirmed — proceed with SSH shutdown ─────────────────────────────────
        if os_type == "linux":
            cmd = (
                f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "
                f"-o BatchMode=yes {user}@{hostname} sudo shutdown -h now"
            )
        else:  # windows
            cmd = (
                f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "
                f"-o BatchMode=yes {user}@{hostname} shutdown /s /t 30"
            )

        self._log(f"SHUTDOWN-NODE: confirmed=True — executing: {cmd}")
        # Use subprocess directly — execute_command blocks commands containing "sudo"
        # even when sudo runs remotely over SSH. This is a pre-approved remote operation.
        import subprocess as _sp  # noqa: PLC0415

        try:
            r = _sp.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=15,
            )
            # exit 255 = SSH closed mid-session as OS shuts down — this is success
            if r.returncode in (0, 255):
                return f"{node} shutdown command accepted (exit {r.returncode}). Node powering off."
            return (
                f"Shutdown may have failed (exit {r.returncode}). "
                f"stdout={r.stdout.strip()!r} stderr={r.stderr.strip()!r}"
            )
        except _sp.TimeoutExpired:
            return "SSH timeout — node may already be shutting down or unreachable."
        except subprocess.SubprocessError as exc:
            return f"shutdown_node error: {exc}"