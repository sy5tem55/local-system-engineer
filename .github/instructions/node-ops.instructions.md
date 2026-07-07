---
description: "Apply for tasks involving node3090 or node5090: SSH operations, model serving, wake/sleep, remote service management, or any cross-node workflow."
applyTo: "**"
---
# Node Operations

## Node Registry

| Node     | FQDN                    | IP             | GPU            | llama-server port | SSH user  |
|----------|-------------------------|----------------|----------------|-------------------|-----------|
| node3090 | node3090.home.arpa      | 192.168.5.41   | RTX 3090 24GB  | 8080              | lse-admin |
| node5090 | node5090.home.arpa      | TBD            | —              | 8081 (LMStudio)   | sy5       |

**Always SSH via FQDN. Never bare hostname or IP.**

```
GOOD: ssh lse-admin@node3090.home.arpa
BAD:  ssh 192.168.5.41
BAD:  ssh node3090
```

## Wake / Wake-on-LAN

Before attempting to wake node3090:
1. Call `search_kb("node3090 wake")` — wake procedure may have changed
2. Use the LSE `wake_node` tool if available — do not guess the WoL MAC from training

If the node is unreachable and wake fails: call `search_kb("node3090 WOL troubleshoot")` before escalating.

## Remote llama-server (node3090)

- Endpoint: `http://node3090.home.arpa:8080/v1`
- Model: Qwen3.6-35B-A3B (110k context, speculative decoding with 0.5B draft model)
- Hermes gateway: `http://node3090.home.arpa:8642` (alternate access)
- Context budget: 110k tokens — prefer this node for large-codebase tasks, architecture review, 100k context refactors

**Before switching inference to node3090:**
1. Verify node is reachable: `curl -s -o /dev/null -w "%{http_code}" http://node3090.home.arpa:8080/health`
2. Expected: `200`. If `000` → node is off or unreachable — run wake sequence.

## Remote Service Management (SSH)

All remote shell operations must be in a single `execute_command` call with `&&` chaining.

```
GOOD: execute_command("ssh lse-admin@node3090.home.arpa 'pgrep -a llama-server && nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader'")
BAD:  Two separate execute_command calls
```

Privileged operations on node3090 (service restart, config changes) must use the same
`sudo_delegation_block` convention as LUCIFER: emit the block, one echo line, stop.
Never attempt `sudo` in an SSH command string.

## node3090 VRAM (RTX 3090, 24 GB)

| Used     | State                                         |
|----------|-----------------------------------------------|
| < 1 GB   | llama-server not loaded                       |
| 18–22 GB | 35B model loaded, 32k–64k ctx                 |
| > 23 GB  | Near capacity — warn before adding load       |

## Cross-Node Port Isolation

| Service               | Host               | Port  |
|-----------------------|--------------------|-------|
| llama-server (LUCIFER)| localhost (WSL)    | 8080  |
| llama-server (node3090)| node3090.home.arpa | 8080  |
| Hermes (node3090)     | node3090.home.arpa | 8642  |
| SearxNG (LUCIFER)     | localhost          | 8088  |

SearxNG and llama-server share port 8080 in name only — on different hosts.
Never route LUCIFER SearxNG traffic to node3090 or vice versa.

## Security

- node3090 llama-server is LAN-only — never expose it beyond 192.168.5.0/24
- SSH key must be loaded in agent: `ssh-add ~/.ssh/id_ed25519` before remote commands
- If SSH times out, check node3090 reachability: `ping -c 2 node3090.home.arpa`
