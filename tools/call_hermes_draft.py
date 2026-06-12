"""
Draft call_hermes tool function — for docstring audit before merging into openwebui-tool.
"""

def call_hermes(self, task: str, context: str = "", no_think: bool = True) -> str:
    """
    Delegate a task to the Hermes Agent on node3090 (http://192.168.5.41:8642).
    Hermes runs Qwen3.6-27B locally and can autonomously execute tasks on node3090
    using its own tool set (shell, file, browser, image generation).

    GATE — call only when ALL of the following are true:
      1. The task requires autonomous multi-step execution on node3090.
      2. A single SSH command cannot answer or complete it.
      3. llama-server AND hermes-gateway are confirmed running on node3090.
    Do NOT call for facts answerable with one SSH command.
    Do NOT call if either service is down — diagnose first, then call.

    GOOD: call_hermes("Check disk usage on all mountpoints and alert if any > 85%")
          ← multi-step: df + parsing + conditional logic, Hermes handles autonomously
    BAD:  call_hermes("What is the hostname of node3090?")
          ← single fact; use execute_command('ssh lse-admin@192.168.5.41 hostname')

    GOOD: call_hermes("Rotate the nginx logs and restart the service", no_think=False)
          ← complex + risky; use no_think=False so Hermes reasons before acting
    BAD:  call_hermes("Rotate the nginx logs and restart the service")
          ← no_think=True skips reasoning on a service-affecting task

    THINKING MODE:
      no_think=True  (default) — fast, no reasoning chain. Use for read-only tasks.
      no_think=False — Hermes reasons before acting. Use for write/destructive tasks.
      Skipping no_think=False on destructive tasks is a protocol violation.

    CONTEXT: pass relevant KB entries, prior command output, or constraints in context.
      GOOD: call_hermes("Update pfsense firewall rule", context=read_file("/opt/local-se/kb/pfsense-firewall-rules-api.md"))
      BAD:  call_hermes("Update pfsense firewall rule")  ← no context, Hermes will guess

    AFTER CALLING: check that the returned string does not start with "ERROR:".
    If it does, report the error and do not treat the task as complete.
    Treating an ERROR: response as success is a protocol violation.

    Returns the Hermes agent response as a plain string.
    Returns "ERROR: <reason>" on connection failure, timeout, or API error.
    """
    import urllib.request
    import json as _json

    api_url = getattr(self.valves, "HERMES_API_URL", "http://192.168.5.41:8642")
    api_key = getattr(self.valves, "HERMES_API_KEY", "")

    content = task.strip()
    if context:
        content = f"CONTEXT:\n{context.strip()}\n\nTASK:\n{content}"
    if no_think:
        content += " /no_think"

    payload = _json.dumps({
        "model": "default",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2048,
    }).encode()

    req = urllib.request.Request(
        f"{api_url}/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = _json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        return f"ERROR: HTTP {exc.code} from Hermes — {body}"
    except Exception as exc:
        return f"ERROR: Hermes call failed — {exc}"
