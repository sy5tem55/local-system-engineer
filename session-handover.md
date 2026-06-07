# Session Handover — 2026-06-07

## State at end of session

### Infrastructure
- **LUCIFER** (node4090): Qwen3.6-27B-Q4_K_M running on port 8080 via llama-server (Worker + Verifier)
- **node3090**: Gemma-4-26B-A4B-it running via LM Studio on port 1234 (Planner)
- **echarts_topology.py**: running on port 8766, HTML at `/`, JSON at `/topology` and `/data.json`, CORS enabled
- **Grafana "Network Topology" dashboard**: LIVE at http://localhost:3002/d/net-topology/network-topology, 30s refresh
- **lse_task.sh**: Planner=192.168.5.41:1234, Worker/Verifier=localhost:8080, SHUTDOWN_AFTER=false

### What was fixed this session
- LM Studio on node3090 used as Planner (port 1234) — bypasses broken llama-server build `6b80c74` that crashes on Gemma-4 MoE CUDA tensors
- lse_task.sh: PLANNER_URL updated to port 1234, SHUTDOWN_AFTER flipped to false
- echarts_topology.py: rewritten with CORS headers, duplicate node ID bug fixed (all_ips guard)
- Grafana topology panel: `await fetch` → sync XHR (ECharts panel v7.2.5 doesn't support async getOption)
- Grafana provisioned topology.json is inside the container — update via `docker cp`

### Pending commits (from WSL terminal)
- `lse_agent.py`
- `lse_task.sh`
- `net-discovery/echarts_topology.py`
- `net-discovery/push_topology_dashboard.py`
- `kb/session-learnings.md`

### Pending KB entry
Add to `kb/session-learnings.md`:
- LM Studio as drop-in llama-server replacement (port 1234, OpenAI-compatible)
- Grafana provisioned dashboards can't be deleted via API — use `docker cp` to update inside container
- ECharts panel v7.2.5 doesn't support `await` in getOption — use sync XMLHttpRequest
- Duplicate node IDs in ECharts graph crash with "can't access property dataIndex" — guard with `ip in all_ips` not `ip in tier_ips`

---

## Primary next task: Upgrade PLANNER_SYSTEM in lse_agent.py

### Why
Current Planner has one generic schema (IPs, ports, tier_nodes). Works for network queries, fails silently on code tasks — produces empty JSON so Worker runs blind. Upgrading to task-type-aware makes the pipeline load-bearing for code repair, feature additions, config changes, and shell tasks.

### Replace PLANNER_SYSTEM (lse_agent.py line 149) with:

```python
PLANNER_SYSTEM = """\
You are the Planner in a three-stage AI pipeline (Planner -> Worker -> Verifier).
Your job: read the task and files, classify the task type, then output a structured
JSON brief that the Worker can execute WITHOUT re-reading the raw files.

Output ONLY valid JSON - no markdown fences, no prose, no preamble.

## Task types and schemas

### "code_repair" - file broken, truncated, crashing, missing sections
{
  "type": "code_repair",
  "target_file": "<path>",
  "language": "<python|bash|js|...>",
  "broken_section": "<what is missing or wrong>",
  "expected_behaviour": "<what it should do when fixed>",
  "constraints": ["<must preserve X>", "<must not use Y>"],
  "key_constants": { "<NAME>": "<value>" },
  "write_method": "heredoc"
}

### "code_feature" - adding new functionality to a working file
{
  "type": "code_feature",
  "target_file": "<path>",
  "language": "<python|bash|js|...>",
  "feature": "<what to add>",
  "insertion_point": "<after function X / at end of file>",
  "constraints": ["<must preserve X>"],
  "key_constants": { "<NAME>": "<value>" },
  "write_method": "heredoc|string_replace"
}

### "network_query" - questions about devices, IPs, hostnames, topology
{
  "type": "network_query",
  "question": "<normalized question>",
  "ips": ["<ip>"],
  "hostnames": { "<ip>": "<hostname>" },
  "subnets": ["<cidr>"],
  "ports": { "<ip>": [<port>] },
  "topology": { "<child_ip>": "<parent_ip>" }
}

### "config_change" - modifying yaml, toml, ini, json, bash config files
{
  "type": "config_change",
  "target_file": "<path>",
  "format": "<yaml|toml|ini|json|bash>",
  "changes": [
    { "key": "<key>", "old": "<current>", "new": "<desired>", "reason": "<why>" }
  ],
  "constraints": ["<do not restart X>", "<backup first>"]
}

### "shell_task" - operational: start/stop services, copy files, check status
{
  "type": "shell_task",
  "steps": [
    { "action": "<description>", "command": "<exact bash or null>" }
  ],
  "success_check": "<verification command>"
}

## Rules
- Output ONLY valid JSON. Nothing else.
- Pick the PRIMARY type if the task spans multiple.
- Extract ALL constants (IPs, ports, paths) from files - the Worker must not guess them.
- If a file is truncated, set broken_section to "FILE TRUNCATED - last readable line: <N>".
- If task type is unclear: {"type": "unknown", "reason": "<why>"}
"""
```

### Also update run_planner() signature and user message

Add `task` parameter:
```python
def run_planner(file_contents: dict, url: str, model: str | None, task: str = "") -> dict:
```

Change user message from generic to task-aware:
```python
{"role": "user", "content": (
    f"Task: {task}\n\n"
    f"Files:\n\n{files_text}\n\n"
    "Classify the task type and output the JSON brief. /no_think"
)},
```

Update the call in main():
```python
facts = run_planner(file_contents, p_url, p_model, task=args.task)
```

---

## Three-node architecture (node5090 as Worker)
- node5090 (RTX 5090) -> Worker (largest model, best output quality)
- LUCIFER (node4090) -> Verifier (Qwen3.6, independent check)
- node3090 -> Planner (Gemma via LM Studio, lightweight)

To wire: set LLM_URL to node5090 IP/port in lse_task.sh. Add --verifier-url if Verifier stays on LUCIFER.

---

## Key facts

| Item | Value |
|------|-------|
| Grafana password | LSEgrafana2026 |
| Grafana port | 3002 |
| Topology API port | 8766 |
| Worker (Qwen3.6) | localhost:8080 |
| Planner (Gemma/LM Studio) | 192.168.5.41:1234 |
| node3090 IP | 192.168.5.41 |
| Topology JSON in container | /etc/grafana/provisioning/dashboards/topology.json |
| Update it | docker cp /tmp/topology.json grafana:/etc/grafana/provisioning/dashboards/topology.json |
| Python >100 lines on NTFS | heredoc from WSL only, never Edit tool |
| Git commits | WSL terminal only |

## Backlog
- Better device icons in topology map (ECharts supports SVG path symbols and image URLs)
- Discovery engine on 60s loop for near-real-time device state
- node5090 wired as Worker
- Verifier checklist: verify Worker used Planner key_constants, not hallucinated values
