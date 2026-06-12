#!/usr/bin/env python3
"""
Seed T3 challenge: node3090 llama-server Production Cutover.

Goal: LSE normalises llama-server on node3090 to the canonical state
defined in the KB (/opt/local-se/kb/node3090-llama-launch.md):
  - binary:        /usr/local/bin/llama-server
  - ctx-size:      81920
  - n-gpu-layers:  129
  - cache-type-k:  q8_0
  - host:          0.0.0.0, port: 8080

Prerequisite: node-t2-001 completed (KB entry exists and is verified).

This is a WRITE challenge — llama-server will be restarted if not at
canonical state. Requires Hermes coordination pre and post restart.

Protocol enforced by docstring:
  - KB-FIRST: read KB before any SSH action
  - No call_hermes between stop and health-ok (inference backend is down)
  - Hermes requests context= responses if it asks for data

Changes from initial design:
  - a4 verifies Hermes gateway + socat proxy (full call path), not just
    gateway alone — socat (hermes-socat.service) is required for LUCIFER
    to reach Hermes at 192.168.5.41:8643.

Usage:
    python3 scripts/seed_node_t3_llama_cutover.py
"""

import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/opt/local-se/challenges.db"
CREATED_AT = datetime.now(timezone.utc).isoformat()

CHALLENGE = dict(
    id="node-t3-003",
    title="node3090 llama-server Production Cutover",
    description=(
        "llama-server is running on node3090 (192.168.5.41, RTX 3090 24GB) "
        "but may not be in the canonical state. The KB entry at "
        "/opt/local-se/kb/node3090-llama-launch.md defines the correct "
        "configuration: ctx-size 81920, n-gpu-layers 129, cache-type-k q8_0, "
        "host 0.0.0.0, port 8080, binary /usr/local/bin/llama-server.\n\n"
        "Your tasks:\n"
        "1. Read the KB entry first (KB-FIRST rule — mandatory).\n"
        "2. Notify Hermes of the upcoming operation via call_hermes (no_think=True).\n"
        "3. Check current llama-server state via SSH (ps aux).\n"
        "4. If not at canonical state: stop llama-server, restart with KB command.\n"
        "   If already correct: verify and confirm without restarting.\n"
        "5. Poll localhost:8080/health via SSH until ok (timeout 3 min, every 10s).\n"
        "6. Confirm Hermes is back online via call_hermes (no_think=True).\n\n"
        "Return a JSON object with: "
        "kb_read (bool), "
        "hermes_notified (bool), "
        "restart_required (bool), "
        "ctx_size (int), "
        "n_gpu_layers (int), "
        "health_ok (bool), "
        "hermes_confirmed (bool)."
    ),
    domain="node",
    discipline="infrastructure",
    tier=3,
    mode="write",
    starting_state=json.dumps({
        "target_node": "node3090",
        "target_ip": "192.168.5.41",
        "ssh_user": "lse-admin",
        "kb_file": "/opt/local-se/kb/node3090-llama-launch.md",
        "canonical_ctx_size": 81920,
        "canonical_n_gpu_layers": 129,
        "canonical_binary": "/usr/local/bin/llama-server",
        "canonical_model": "/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf",
        "hermes_url": "http://192.168.5.41:8643",
        "notes": (
            "KB-FIRST — mandatory before any SSH action:\n"
            "  search_kb('node3090 llama-server launch', topic_filter='node3090')\n"
            "  OR read_file('/opt/local-se/kb/node3090-llama-launch.md')\n"
            "  Proceeding without reading the KB is a protocol violation.\n"
            "\n"
            "Step 2 — notify Hermes (llama-server still up at this point):\n"
            "  call_hermes('LSE is checking llama-server state on node3090. "
            "Will restart if ctx-size != 81920 or n-gpu-layers != 129. "
            "Acknowledge and report current ctx-size from ps aux.', no_think=True)\n"
            "\n"
            "Step 3 — check current state:\n"
            "  execute_command('ssh lse-admin@192.168.5.41 "
            "\"pgrep -af llama-server | grep -v grep\"')\n"
            "  Extract --ctx-size and --n-gpu-layers. "
            "If both match canonical, skip steps 4-5.\n"
            "\n"
            "Step 4a — stop (only if restart needed):\n"
            "  execute_command('ssh lse-admin@192.168.5.41 \"pkill -f llama-server\"')\n"
            "  Wait 3s. Verify: pgrep -f llama-server || echo stopped\n"
            "\n"
            "Step 4b — start with canonical KB command:\n"
            "  execute_command('ssh lse-admin@192.168.5.41 \"nohup /usr/local/bin/llama-server "
            "--model /home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/"
            "Qwen3.6-27B-Q4_K_M.gguf --ctx-size 81920 --n-gpu-layers 129 "
            "--flash-attn on --cache-type-k q8_0 --reasoning-budget 3072 "
            "--n-predict 8192 --jinja --metrics --host 0.0.0.0 --port 8080 "
            "--threads 8 </dev/null > /home/lse-admin/llama-server.log 2>&1 &\"')\n"
            "\n"
            "Step 5 — poll health (timeout 3 min, every 10s):\n"
            "  execute_command('ssh lse-admin@192.168.5.41 "
            "\"for i in $(seq 1 18); do "
            "curl -s http://localhost:8080/health | grep -q ok "
            "&& echo ready && break; "
            "echo attempt $i... && sleep 10; done\"')\n"
            "\n"
            "Step 6 — confirm with Hermes (only AFTER health ok):\n"
            "  call_hermes('llama-server is back. Confirm you are online and "
            "report ctx-size and n-gpu-layers from ps aux.', no_think=True)\n"
            "\n"
            "CRITICAL: Do NOT call call_hermes between stop and health-ok.\n"
            "Hermes inference backend IS llama-server. While it is stopped,\n"
            "Hermes cannot generate responses. Protocol violation if called early."
        )
    }),
    success_criteria=json.dumps({
        "assertions": [
            {
                "id": "a1",
                "points": 1,
                "code": (
                    "assert llama_server_running is True "
                    "and ctx_size == 81920"
                ),
                "description": "llama-server running with ctx-size exactly 81920",
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": "pgrep -af llama-server | grep -v grep | head -1",
                    "parse": (
                        "_line = stdout.strip(); "
                        "llama_server_running = len(_line) > 0; "
                        "_m = re.search(r'--ctx-size\\s+(\\d+)', _line) if _line else None; "
                        "ctx_size = int(_m.group(1)) if _m else 0"
                    ),
                }
            },
            {
                "id": "a2",
                "points": 1,
                "code": (
                    "assert n_gpu_layers == 129 "
                    "and binary_correct is True"
                ),
                "description": "n-gpu-layers exactly 129, canonical binary /usr/local/bin/llama-server",
                # pgrep -af may show just the binary name (not full path) depending on how
                # the process was invoked. Use /proc/PID/exe (readlink) for the real path.
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": (
                        "_pid=$(pgrep -f llama-server | head -1); "
                        "readlink -f /proc/$_pid/exe 2>/dev/null; "
                        "echo '---'; "
                        "pgrep -af llama-server | grep -v grep | head -1"
                    ),
                    "parse": (
                        "_parts = stdout.strip().split('---'); "
                        "_binary = _parts[0].strip() if _parts else ''; "
                        "binary_correct = _binary == '/usr/local/bin/llama-server'; "
                        "_line = _parts[1].strip() if len(_parts) > 1 else ''; "
                        "_m = re.search(r'--n-gpu-layers\\s+(\\d+)', _line) if _line else None; "
                        "n_gpu_layers = int(_m.group(1)) if _m else 0"
                    ),
                }
            },
            {
                "id": "a3",
                "points": 1,
                "code": (
                    "assert health_ok is True "
                    "and cache_type_correct is True"
                ),
                "description": "Health endpoint returns ok and --cache-type-k q8_0 in command",
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": (
                        "curl -s http://localhost:8080/health; "
                        "echo '---'; "
                        "pgrep -af llama-server | grep -v grep | head -1"
                    ),
                    "parse": (
                        "_parts = stdout.split('---'); "
                        "health_ok = 'ok' in _parts[0].lower() if _parts else False; "
                        "_line = _parts[1].strip() if len(_parts) > 1 else ''; "
                        "cache_type_correct = 'cache-type-k' in _line and 'q8_0' in _line"
                    ),
                }
            },
            {
                "id": "a4",
                "points": 1,
                "code": (
                    "assert hermes_gateway_active is True "
                    "and socat_listening is True"
                ),
                "description": (
                    "Hermes gateway active (hermes-gateway.service) and socat proxy "
                    "listening on 0.0.0.0:8643 (hermes-socat.service) — "
                    "confirms full LSE→Hermes call path available post-restart."
                ),
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": (
                        "systemctl is-active hermes-gateway 2>/dev/null; "
                        "echo '---'; "
                        "ss -tlnp | grep ':8643' | wc -l"
                    ),
                    "parse": (
                        "_parts = stdout.strip().split('---'); "
                        "hermes_gateway_active = _parts[0].strip() == 'active' if _parts else False; "
                        "_n = _parts[1].strip() if len(_parts) > 1 else '0'; "
                        "socat_listening = _n.isdigit() and int(_n) > 0"
                    ),
                }
            }
        ]
    }),
    failure_modes=json.dumps({
        "0/4": "llama-server not running or wrong binary after operation.",
        "1/4": "Running with ctx-size 81920 but n-gpu-layers wrong or wrong binary.",
        "2/4": "Binary and layers correct but health endpoint not responding or cache-type-k missing.",
        "3/4": "llama-server healthy but Hermes gateway or socat proxy not active (call path broken).",
        "4/4": "llama-server at canonical state (ctx-size 81920, n-gpu-layers 129, q8_0 cache, "
               "health ok) and full Hermes call path verified (gateway + socat)."
    }),
    kb_target="node3090/llama-server-production-state",
    rollback_defined=0,
    requires_human_approval=0,
    discipline_multiplier=1.3,
    max_attempts=3,
    claude_only_override=0,
    auto_generated=0,
    parent_episode_id="node-t2-001",
    status="active",
)

INSERT_SQL = """
INSERT OR REPLACE INTO challenges (
    id, title, description, domain, discipline, tier, mode,
    starting_state, success_criteria, failure_modes, kb_target,
    rollback_defined, requires_human_approval, discipline_multiplier,
    max_attempts, claude_only_override, auto_generated, parent_episode_id,
    status, created_at
) VALUES (
    :id, :title, :description, :domain, :discipline, :tier, :mode,
    :starting_state, :success_criteria, :failure_modes, :kb_target,
    :rollback_defined, :requires_human_approval, :discipline_multiplier,
    :max_attempts, :claude_only_override, :auto_generated, :parent_episode_id,
    :status, :created_at
)
"""

if __name__ == "__main__":
    row = dict(CHALLENGE, created_at=CREATED_AT)
    con = sqlite3.connect(DB_PATH)
    con.execute(INSERT_SQL, row)
    con.commit()
    con.close()
    print(f"  ✅  {CHALLENGE['id']}  —  {CHALLENGE['title']}")
    print(f"       Tier: {CHALLENGE['tier']}  |  {CHALLENGE['discipline']} "
          f"{CHALLENGE['discipline_multiplier']}x  |  {CHALLENGE['mode']}")
    print(f"       Assertions: {len(json.loads(CHALLENGE['success_criteria'])['assertions'])}")
    print(f"       Max points: "
          f"{len(json.loads(CHALLENGE['success_criteria'])['assertions']) * 5 * CHALLENGE['discipline_multiplier']:.1f}")
    print(f"       Parent: {CHALLENGE['parent_episode_id']}")
    print(f"       Next: verify Hermes call path + inference under realistic conditions")
