#!/usr/bin/env python3
"""
Seed T3 challenge: node3090 llama-server Model Path Repair.

Goal: LSE ensures llama-server on node3090 is running with the canonical
model path from the KB. Current state: process is running with
/opt/models/... (wrong path). Canonical path:
/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf

This is a follow-up to node-t3-003 (ctx-size + binary verified).
node-t3-004 adds model path as a verified assertion and keeps all
other canonical parameters (ctx-size 81920, n-gpu-layers 129,
cache-type-k q8_0, host 0.0.0.0, port 8080).

Protocol:
  - KB-FIRST: read KB before any SSH action
  - Hermes pre-notification + post-confirmation
  - No call_hermes between stop and health-ok
  - Use /proc/PID/exe for binary check (pgrep may omit full path)

Usage:
    python3 scripts/seed_node_t3_llama_model_path.py
"""

import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/opt/local-se/challenges.db"
CREATED_AT = datetime.now(timezone.utc).isoformat()

CANONICAL_MODEL = (
    "/home/sy5/.lmstudio/models/lmstudio-community/"
    "Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf"
)

CHALLENGE = dict(
    id="node-t3-004",
    title="node3090 llama-server Model Path Repair",
    description=(
        "llama-server is running on node3090 (192.168.5.41) but with the wrong "
        "model path: /opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf. "
        "The canonical path from the KB is: "
        "/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf.\n\n"
        "All other parameters must remain at canonical values: "
        "ctx-size 81920, n-gpu-layers 129, cache-type-k q8_0, "
        "host 0.0.0.0, port 8080.\n\n"
        "Your tasks:\n"
        "1. Read the KB entry to confirm the canonical launch command.\n"
        "2. Notify Hermes of the upcoming restart via call_hermes (no_think=True).\n"
        "3. Check current --model path via SSH (ps aux / pgrep).\n"
        "4. Stop llama-server and restart with the canonical model path.\n"
        "5. Poll localhost:8080/health until ok (timeout 3 min, every 10s).\n"
        "6. Confirm with Hermes post-restart via call_hermes (no_think=True).\n\n"
        "Return a JSON object with: "
        "kb_read (bool), "
        "hermes_notified (bool), "
        "model_path (str), "
        "model_path_correct (bool), "
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
        "wrong_model_path": "/opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf",
        "canonical_model_path": CANONICAL_MODEL,
        "canonical_ctx_size": 81920,
        "canonical_n_gpu_layers": 129,
        "canonical_binary": "/usr/local/bin/llama-server",
        "notes": (
            "KB-FIRST — mandatory before any SSH action:\n"
            "  search_kb('node3090 llama-server launch', topic_filter='node3090')\n"
            "  OR read_file('/opt/local-se/kb/node3090-llama-launch.md')\n"
            "\n"
            "Step 2 — notify Hermes (llama-server still up at this point):\n"
            "  call_hermes('LSE is restarting llama-server on node3090 to fix "
            "the model path. Current: /opt/models/... Canonical: "
            "/home/sy5/.lmstudio/models/... Will be offline ~90s. "
            "Acknowledge.', no_think=True)\n"
            "\n"
            "Step 3 — verify current model path:\n"
            "  execute_command('ssh lse-admin@192.168.5.41 "
            "\"pgrep -af llama-server | grep -v grep | head -1\"')\n"
            "  Extract --model value. Confirm it does NOT match canonical.\n"
            "\n"
            "Step 4a — stop:\n"
            "  execute_command('ssh lse-admin@192.168.5.41 \"pkill -f llama-server\"')\n"
            "  Wait 3s. Verify: pgrep -f llama-server || echo stopped\n"
            "\n"
            "Step 4b — start with canonical model path (COPY EXACTLY):\n"
            "  execute_command('ssh lse-admin@192.168.5.41 "
            "\"nohup /usr/local/bin/llama-server "
            "--model /home/sy5/.lmstudio/models/lmstudio-community/"
            "Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf "
            "--ctx-size 81920 --n-gpu-layers 129 "
            "--flash-attn on --cache-type-k q8_0 "
            "--reasoning-budget 3072 --n-predict 8192 "
            "--jinja --metrics --host 0.0.0.0 --port 8080 --threads 8 "
            "</dev/null > /home/lse-admin/llama-server.log 2>&1 &\"')\n"
            "\n"
            "Step 5 — poll health (timeout 3 min, every 10s):\n"
            "  execute_command('ssh lse-admin@192.168.5.41 "
            "\"for i in $(seq 1 18); do "
            "curl -s http://localhost:8080/health | grep -q ok "
            "&& echo ready && break; "
            "echo attempt $i... && sleep 10; done\"')\n"
            "\n"
            "Step 6 — confirm with Hermes (ONLY after health ok):\n"
            "  call_hermes('llama-server restarted. Confirm online and report "
            "--model path from ps aux.', no_think=True)\n"
            "\n"
            "CRITICAL: Do NOT call call_hermes between stop and health-ok.\n"
            "Hermes inference backend IS llama-server — offline while stopped."
        )
    }),
    success_criteria=json.dumps({
        "assertions": [
            {
                "id": "a1",
                "points": 1,
                # Model path is checked FIRST so the model cannot pass a1 without
                # actually fixing the path. Moving it here prevents the model from
                # satisfying a1-a3 on the existing (wrong-path) process and stopping.
                "code": (
                    "assert llama_server_running is True "
                    "and model_path_correct is True"
                ),
                "description": (
                    "llama-server running AND model path is canonical "
                    "/home/sy5/.lmstudio/... (not /opt/models/...). "
                    "RESTART IS REQUIRED — do not skip even if other params appear correct."
                ),
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": "pgrep -af llama-server | grep -v grep | head -1",
                    "parse": (
                        "_line = stdout.strip(); "
                        "llama_server_running = len(_line) > 0; "
                        "_m = re.search(r'--model\\s+(\\S+)', _line) if _line else None; "
                        "model_path = _m.group(1) if _m else ''; "
                        "model_path_correct = model_path == "
                        "'/home/sy5/.lmstudio/models/lmstudio-community/"
                        "Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf'"
                    ),
                }
            },
            {
                "id": "a2",
                "points": 1,
                "code": (
                    "assert ctx_size == 81920 "
                    "and n_gpu_layers == 129"
                ),
                "description": "ctx-size exactly 81920 and n-gpu-layers exactly 129 after restart",
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": "pgrep -af llama-server | grep -v grep | head -1",
                    "parse": (
                        "_line = stdout.strip(); "
                        "_mc = re.search(r'--ctx-size\\s+(\\d+)', _line) if _line else None; "
                        "ctx_size = int(_mc.group(1)) if _mc else 0; "
                        "_mg = re.search(r'--n-gpu-layers\\s+(\\d+)', _line) if _line else None; "
                        "n_gpu_layers = int(_mg.group(1)) if _mg else 0"
                    ),
                }
            },
            {
                "id": "a3",
                "points": 1,
                "code": (
                    "assert binary_correct is True "
                    "and cache_type_correct is True"
                ),
                "description": "Binary is /usr/local/bin/llama-server (via /proc/exe) and --cache-type-k q8_0",
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
                        "cache_type_correct = 'cache-type-k' in _line and 'q8_0' in _line"
                    ),
                }
            },
            {
                "id": "a4",
                "points": 1,
                "code": (
                    "assert health_ok is True"
                ),
                "description": "Health endpoint returns ok post-restart",
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": "curl -s http://localhost:8080/health",
                    "parse": (
                        "health_ok = 'ok' in stdout.lower()"
                    ),
                }
            },
        ]
    }),
    failure_modes=json.dumps({
        "0/4": "llama-server not running or model path still /opt/models/... (restart not performed).",
        "1/4": "Canonical model path confirmed but ctx-size != 81920 or n-gpu-layers != 129.",
        "2/4": "Path and params correct but binary not /usr/local/bin/llama-server or cache-type-k missing.",
        "3/4": "All parameters correct but health endpoint not responding.",
        "4/4": "llama-server restarted with canonical model path, ctx-size 81920, "
               "n-gpu-layers 129, binary correct, q8_0 cache, health ok."
    }),
    kb_target="node3090/llama-server-model-path",
    rollback_defined=0,
    requires_human_approval=0,
    discipline_multiplier=1.3,
    max_attempts=3,
    claude_only_override=0,
    auto_generated=0,
    parent_episode_id="node-t3-003",
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
    print(f"       Canonical model: {CANONICAL_MODEL}")
