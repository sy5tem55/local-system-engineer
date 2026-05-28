# Network Engineer Agent — Bootstrap Guide

**Written:** 2026-05-28  
**Based on:** LSE project lessons learned (runs 1–5, 47 tracked tasks)  
**Purpose:** Start the NE agent project with all LSE traps already known. Skip the rediscovery phase.

---

## Hardware Target

| Component | Spec |
|---|---|
| CPU | Intel Core i9-9900K (8c/16t) |
| RAM | 32 GB |
| GPU | NVIDIA RTX 3090 (24 GB GDDR6X) |
| OS | Ubuntu Pro 24.04 (native, not WSL2) |

**Why this machine is the right choice:**
- RTX 3090 has same 24 GB VRAM as the LSE's RTX 4090 — same model family works
- Ubuntu Pro native eliminates the entire WSL2 networking complexity class (Docker bridge gymnastics, gateway IP routing, relay proxies) that consumed significant time in the LSE project
- Agent should run on the machine whose network it manages — correct failure domain
- No resource contention with the LSE running on LUCIFER

---

## Model Recommendation

**Primary:** `Qwen3.6-27B-Q5_K_M` — same as LSE, proven on technical tasks  
**Alternative:** `Qwen3.6-27B-Q4_K_M` — if VRAM headroom is needed for 64k sessions  

VRAM budget on RTX 3090 (24 GB):
- Q5_K_M weights: ~19.4 GB
- 32k q8_0 KV cache: ~0.5 GB  
- Overhead: ~1.5 GB
- Total: ~21.4 GB → ~2.6 GB headroom (tighter than 4090 due to slightly different memory architecture)

The 9900K is slower than modern CPUs for CPU-offloaded operations. Keep `ngl` set to fully GPU-loaded (all layers on GPU). For MTP (speculative decoding), test carefully — MTP draft model adds VRAM pressure.

**Do not use:** `iq4_nl` KV quant — causes prefill collapse at 64k context. `q4_0` KV quant — causes multilingual drift on Qwen models.

---

## Stack (start here, proven on LSE)

```
llama-server  (inference, port 8080, started with --metrics)
OpenWebUI     (frontend, port 3000, native process)
SearxNG       (web search, port 8088, Docker)
Prometheus    (metrics, port 9090, Docker)
Grafana       (dashboards + alerts, port 3002→3000, Docker)
```

**Do not use WSL2.** Native Ubuntu means:
- systemd works correctly (no WSL2 systemd hacks)
- Docker networking is simpler (no bridge gateway gymnastics)
- Network tools (`ip`, `ss`, `netstat`, `tcpdump`) have full access to the real network stack

---

## Docker Network — Do This First

Create a dedicated Docker network before starting any containers. Putting everything on the default bridge means containers cannot reach each other by name — learned this the hard way on LSE.

```bash
docker network create ne-net

# Start all containers with --network ne-net
# Then containers can use http://prometheus:9090 etc.
```

Verify after starting:
```bash
docker network inspect ne-net --format '{{range .Containers}}{{.Name}} {{end}}'
```

---

## Prometheus Metric Names — Critical

**This burned the LSE project significantly.**

This version of llama.cpp exports metrics with the `llamacpp:` prefix, NOT the `llama_` prefix:

```
llamacpp:n_tokens_max          ← current KV cache tokens used
llamacpp:prompt_tokens_seconds ← prompt throughput
llamacpp:predicted_tokens_seconds ← generation throughput
```

There is NO `llama_kv_cache_usage_ratio` metric. You must compute it yourself via the context exporter (see below). Do not write any code or Grafana queries assuming `llama_` prefix metrics.

**Verify on first run:**
```bash
curl -s http://localhost:8080/metrics | grep -v "^#" | sort
```

---

## Context Alert Pipeline (build this before first eval)

Do not put context monitoring inside the model. All LSE versions (v1.0–v1.3 filter) failed — the model always prioritises task completion over meta-monitoring. Use the external Grafana pipeline instead.

Copy from LSE and adapt:

**1. Context exporter** (`/opt/local-ne/llama-context-exporter.py`, port 9836):
- Queries `/slots` → gets `n_ctx` (dynamic: 32768 or 65536)
- Queries `/metrics` → gets `llamacpp:n_tokens_max`
- Exposes `llama_kv_cache_usage_ratio` and `llama_context_size`
- Runs as systemd service

**2. Grafana-OpenWebUI adapter** (`/opt/local-ne/grafana-owui-adapter.py`, port 9837):
- Receives Grafana webhook JSON (Grafana sends its own format, not `{"content":"..."}`)
- Converts to OpenWebUI channel webhook format
- Runs as systemd service

**3. Grafana alert:** `llama_kv_cache_usage_ratio > 0.8`, for=1m → contact point → adapter → OpenWebUI channel

The bridge gateway IP (Docker → host) on native Ubuntu is typically `172.17.0.1`. Verify with:
```bash
docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}'
```

Contact point URL in Grafana: `http://172.17.0.1:9837`

---

## Launcher

On native Ubuntu there is no Windows Terminal. Use a tmux session or a simple shell script that starts each service in a named tmux window. No PowerShell, no Authenticode signing, no strip-sig workflow.

Suggested tmux layout:
```
window 0: llama-server  (red prompt)
window 1: OpenWebUI logs
window 2: shell (general work)
```

Start script (`/opt/local-ne/start-stack.sh`):
```bash
#!/bin/bash
tmux new-session -d -s ne -n llama
tmux send-keys -t ne:llama "/home/ne/llama.cpp/build/bin/llama-server \
  --model /home/ne/models/Qwen3.6-27B-Q5_K_M.gguf \
  --ctx-size 32768 --n-gpu-layers 99 --port 8080 \
  --metrics --mtp-draft-max-ngram-size 0" Enter
```

---

## Permission Boundary — Network Engineering Scope

The NE agent has a different permission model than LSE. It needs to read and interpret network state but must be conservative about modifying it.

**Read freely:**
```
ip addr show
ip route show
ss -tlnp
netstat -tlnp
ping -c 4 <host>
traceroute <host>
nmap -sn <subnet>   (host discovery only)
cat /etc/netplan/*.yaml
cat /etc/hosts
cat /etc/resolv.conf
cat /etc/network/interfaces
journalctl -u NetworkManager -n 50
```

**Delegate via sudo_delegation_block (never run autonomously):**
```
ip link set
ip addr add/del
ip route add/del
netplan apply
iptables -A / -I / -D
ufw allow/deny
systemctl restart networking
```

**Block permanently (no exceptions):**
```
iptables -F          ← flushes all rules, instant lockout
ip link delete       ← destroys network interfaces
ip addr flush        ← removes all addresses from interface
route del default    ← removes default gateway
```

**Add to denylist in the tool docstring** — these are the network equivalent of LSE's `mkfs` / `fdisk`.

---

## Tool Design — Reuse LSE v1.5.7 as Base

Start from `tools/openwebui-tool-v1.5.7.py` and adapt:

1. **Keep:** `execute_command`, `read_file`, `write_file`, `sudo_delegation_block`, `search_web`, `get_context_status`
2. **Replace denylist** in `execute_command` with network-appropriate blocked commands
3. **Replace privileged paths** with network config paths (`/etc/netplan/`, `/etc/iptables/`, etc.)
4. **Add write paths** for `/etc/hosts`, `/tmp/ne/` as appropriate
5. **Consider adding:** `ping_host(host)`, `resolve_hostname(name)` as safe read-only helpers

**Do not add a Python REPL tool** — it bypasses all safety controls.

---

## Prompt Design — Start Lean (v0.5.4 pattern)

Start with the v0.5.4 structure (lean, no CONTEXT HANDOVER). Key sections:

```
IDENTITY      — observe, reason, act. READ → PLAN → ACT → VERIFY
ENVIRONMENT   — hostname, model version, ports
PERMISSION BOUNDARY — read paths, write paths, BLOCKED list, LIVE SERVICE RULE
TOOLS         — one-liner per tool, no verbose explanations
OUTPUT RULES  — no preamble, short answers, confirm before destructive action
KNOWLEDGE BASE — /etc/netplan/ /etc/hosts /etc/resolv.conf etc.
```

**Do not include CONTEXT HANDOVER** — it has never worked reliably. Use the Grafana pipeline.

**LIVE SERVICE RULE is essential** — before any `systemctl restart networking` or `netplan apply`, check what's running. For the NE agent, add: if the agent itself is being managed by a network interface that will be affected by the change, HARD STOP and delegate.

---

## Eval Framework — Build Before First Session

Build the eval suite before running any real sessions. Lessons from LSE:

**Category structure (adapt from LSE v3.5):**
- **P** (Permission boundary) — blocked commands, privilege escalation attempts
- **M** (Mandatory delegation) — sudo operations that must use sudo_delegation_block
- **W** (Web search) — announce before searching, single call rule
- **A** (Awareness) — context fill, tool availability, state questions
- **L** (Live service) — pgrep check before any service modification
- **N** (Network-specific) — read-only vs destructive network ops

**A1 test design lesson:** Make A1 questions unfakeable from model training knowledge. Use live system state: current PID of a process, current IP of an interface, current routing table entry. The model must call a tool to answer — it cannot fake it.

**Precondition rule:** every test must verify the precondition before scoring. If the test assumes a file exists, check it exists. If it assumes a service is running, check it's running. Violated preconditions invalidate the test, not the model.

---

## Eval Infrastructure — Reuse LSE Skills

The following LSE skills transfer directly:
- `lse:eval-runner` → copy and rename to `ne:eval-runner`
- `lse:docstring-optimizer` → reuse as-is (checks docstring patterns that apply to any agent)
- `lse:stack-health-check` → adapt service list for NE stack
- `lse:session-debrief` → reuse as-is
- `lse:version-manager` → reuse as-is

---

## Prometheus Scrape Config — On Native Ubuntu

On native Ubuntu, Prometheus in Docker can reach the host at the bridge gateway IP (typically `172.17.0.1`). Add these jobs to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "llama-server"
    static_configs:
      - targets: ["172.17.0.1:8080"]
    metrics_path: "/metrics"
    scrape_interval: 15s

  - job_name: "llama-context-exporter"
    static_configs:
      - targets: ["172.17.0.1:9836"]
    scrape_interval: 15s

  - job_name: "node-exporter"
    static_configs:
      - targets: ["node-exporter:9100"]
    scrape_interval: 15s
```

**Prometheus reload:** On native Ubuntu with `--web.enable-lifecycle` flag set, `curl -X POST http://localhost:9090/-/reload` works without a container restart. Add this flag to the Prometheus Docker run command.

---

## Traps to Avoid (Learned on LSE)

| Trap | What happens | Fix |
|---|---|---|
| Assume `llama_` metric prefix | No metrics found, alert never fires | Use `llamacpp:` prefix; verify with `curl http://localhost:8080/metrics` |
| Put context monitoring in the model | Model ignores it; task always wins | Use Grafana pipeline |
| Default Docker bridge for all containers | Containers can't reach each other by name | Create named network, connect all containers |
| Prometheus reload without `--web.enable-lifecycle` | `curl -X POST /-/reload` returns 404 | Add flag, or use `docker restart prometheus` |
| Grafana webhook → OpenWebUI directly | 422 Unprocessable Entity (format mismatch) | Use the adapter script on port 9837 |
| `iq4_nl` KV quant at 64k context | Prefill collapses from ~120 to ~45 tok/s | Use `q8_0`; `q4_0` also causes multilingual drift |
| Edit signed PS1 file directly | SIG block corrupts file | N/A on native Ubuntu — no Authenticode |
| `[ref]$errors` without pre-declaration in PS7 | InvalidOperation exception | N/A on native Ubuntu |
| Grafana API key scope | 401 on some endpoints | Use service account with Admin role |
| CONTEXT HANDOVER in prompt | Model ignores it when busy | Remove entirely; use Grafana alert |

---

## First Session Checklist

Before the first NE agent session:

- [ ] llama-server running with `--metrics` flag
- [ ] `curl http://localhost:8080/metrics | grep llamacpp` returns data
- [ ] Context exporter running: `curl http://localhost:9836/metrics`
- [ ] Prometheus scraping both jobs: check Targets page at `http://localhost:9090/targets`
- [ ] Grafana alert rule created and contact point tested
- [ ] OpenWebUI channel `ne-alerts` created with webhook
- [ ] Adapter service running: `systemctl status grafana-owui-adapter`
- [ ] Tool uploaded to OpenWebUI Admin → Tools
- [ ] Prompt pasted to OpenWebUI Admin → Models → NE model
- [ ] Smoke test: send a blocked command, verify refusal; send a sudo command, verify delegation block

---

## Repository Structure (suggested)

```
network-engineer/
├── README.md
├── ROADMAP.md
├── VERSION.md
├── docs/
│   ├── 01-model-evaluation.md
│   ├── 02-tool-design.md
│   ├── 03-network-permission-model.md
│   ├── 04-context-management.md       ← Grafana pipeline only, no in-model approach
│   └── 05-operations-runbook.md
├── prompts/
│   ├── CHANGELOG.md
│   └── v0.1-baseline.md               ← start lean, expand only when eval shows gaps
├── tools/
│   └── openwebui-tool-v1.0.0.py       ← adapted from LSE v1.5.7
└── eval/
    ├── test-suite-v1.0.md
    └── eval-runner/
```
