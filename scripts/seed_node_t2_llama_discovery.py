#!/usr/bin/env python3
"""
Seed T2 challenge: node3090 llama.cpp Discovery & Launch Configuration.

Goal: LSE finds the llama-server binary on node3090, verifies CUDA 13.x
availability, calculates optimal launch flags for RTX 3090 24GB + 80K context
window with Qwen3.6-27B-Q4_K_M, and writes the recommended start command to KB.

This is a READ-ONLY analysis challenge — no service is started.
It prepares the ground truth for node-t3-003 (server start + validation).

Changes from v1:
  - a3: plausible-range bounds (model 14-22GB, KV 3-12GB, total = sum ≤ 26GB)
        prevents model from fabricating fits_in_24gb=True without real arithmetic.
  - a4: added --cache-type-k as required flag.
        added --n-gpu-layers value > 0 check (presence alone was insufficient).
        KB verify changed from existence-only to content check (>=10 lines,
        contains 'llama-server') — prevents trivial pass on pre-existing file.

Usage:
    python3 scripts/seed_node_t2_llama_discovery.py
"""

import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/opt/local-se/challenges.db"
CREATED_AT = datetime.now(timezone.utc).isoformat()

CHALLENGE = dict(
    id="node-t2-001",
    title="node3090 llama.cpp Discovery & Launch Configuration",
    description=(
        "llama.cpp is installed on node3090 (192.168.5.41, Ubuntu 24.04, "
        "RTX 3090 24GB, Intel Core i9-9900K 8c/16t, 32GB RAM) but the binary "
        "location is unknown. The target model is Qwen3.6-27B-Q4_K_M with an "
        "80K (81920 token) context window. "
        "\n\n"
        "Your tasks (all via SSH as lse-admin):\n"
        "1. Locate the llama-server binary.\n"
        "2. Confirm the CUDA driver version via nvidia-smi (driver 13.x expected).\n"
        "3. Calculate the VRAM budget: model weights + KV cache at q8_0 must fit "
        "within 24GB. Show your working.\n"
        "4. Determine the optimal llama-server launch flags: GPU layers, context "
        "size, KV cache type, thread count for the i9-9900K, host/port for "
        "multi-agent access from LUCIFER (192.168.1.x).\n"
        "5. Write the recommended start command and VRAM breakdown to the LSE KB.\n"
        "\n"
        "Return a JSON object with: "
        "llama_server_path (str), "
        "cuda_version (str, e.g. '13.2' — from nvidia-smi CUDA Version line), "
        "cuda_13_3_available (bool — True if driver major >= 13), "
        "model_vram_gb (float), "
        "kv_cache_vram_gb (float), "
        "total_vram_gb (float), "
        "fits_in_24gb (bool), "
        "recommended_command (str — full llama-server invocation), "
        "kb_entry_written (bool)."
    ),
    domain="node",
    discipline="infrastructure",
    tier=2,
    mode="read_only",
    starting_state=json.dumps({
        "target_node": "node3090",
        "target_ip": "192.168.5.41",
        "ssh_user": "lse-admin",
        "gpu": "RTX 3090 24GB VRAM",
        "cpu": "Intel Core i9-9900K (8 cores / 16 threads)",
        "ram_gb": 32,
        "os": "Ubuntu 24.04",
        "model": "Qwen3.6-27B-Q4_K_M",
        "target_ctx": 81920,
        "target_port": 8080,
        "cuda_target": "13.x (driver CUDA API — check nvidia-smi, NOT nvcc)",
        "notes": (
            "Step 1 — find binary: "
            "execute_command('ssh lse-admin@192.168.5.41 "
            "\"which llama-server 2>/dev/null || "
            "find /usr /opt /home -name llama-server -type f 2>/dev/null | head -5\"'). "
            "\n"
            "Step 2 — CUDA check: "
            "execute_command('ssh lse-admin@192.168.5.41 \"nvidia-smi\"') to get driver version; "
            "execute_command('ssh lse-admin@192.168.5.41 \"nvcc --version 2>/dev/null || "
            "cat /usr/local/cuda/version.txt 2>/dev/null || "
            "ls /usr/local/ | grep cuda\"') for toolkit version. "
            "CUDA 13.3 requires driver >= 575. "
            "\n"
            "Step 3 — VRAM budget: "
            "Qwen3.6-27B-Q4_K_M weights: compute from Q4_K_M bitrate (~4.83 bits/param). "
            "KV cache at q8_0 for 81920 ctx: use model architecture "
            "(num_hidden_layers=46, num_key_value_heads=8, head_dim=128) to compute "
            "2 * layers * kv_heads * head_dim * ctx_len bytes. "
            "Report both components separately. total_vram_gb must equal their sum. "
            "\n"
            "Step 4 — flags: must include "
            "--n-gpu-layers <N> (all layers on GPU, N > 0), "
            "--ctx-size 81920, "
            "--cache-type-k q8_0, "
            "--threads <cpu_threads> (recommend 8 for i9-9900K during GPU inference), "
            "--host 0.0.0.0 (accessible from LUCIFER), "
            "--port 8080, "
            "--flash-attn on (if supported by build). "
            "Check llama-server --help or --version for supported flags before including. "
            "\n"
            "Step 5 — KB: write findings to "
            "/opt/local-se/kb/node3090-llama-launch.md via write_file. "
            "File must be at least 10 lines and include the llama-server command."
        )
    }),
    success_criteria=json.dumps({
        "assertions": [
            {
                "id": "a1",
                "points": 1,
                "code": (
                    "assert llama_server_path is not None "
                    "and len(llama_server_path) > 0 "
                    "and 'llama-server' in llama_server_path"
                ),
                "description": "llama-server binary located on node3090",
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": (
                        "which llama-server 2>/dev/null || "
                        "find /usr /opt /home -name llama-server -type f 2>/dev/null | head -1"
                    ),
                    "parse": (
                        "llama_server_path = stdout.strip() if stdout.strip() else None"
                    ),
                }
            },
            {
                "id": "a2",
                "points": 1,
                "code": (
                    "assert cuda_driver_major >= 13 "
                    "and cuda_version is not None"
                ),
                "description": "CUDA 13.x driver confirmed on node3090 (nvidia-smi)",
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": "nvidia-smi 2>/dev/null | grep -i 'cuda version'",
                    "parse": (
                        "_m = re.search(r'CUDA Version:\\s*([0-9]+)\\.([0-9]+)', stdout, re.IGNORECASE) if stdout else None; "
                        "cuda_driver_major = int(_m.group(1)) if _m else 0; "
                        "cuda_driver_minor = int(_m.group(2)) if _m else 0; "
                        "cuda_version = f'{cuda_driver_major}.{cuda_driver_minor}' if _m else None; "
                        "cuda_13_3_available = cuda_driver_major >= 13"
                    ),
                }
            },
            {
                "id": "a3",
                "points": 1,
                # Plausible-range check forces real VRAM math, not a bare fits_in_24gb=True claim.
                # Qwen3-27B-Q4_K_M weights: ~14-22 GB depending on overhead.
                # KV cache q8_0 at 81920 ctx (46 layers, 8 KV heads, 128 head_dim): ~5-12 GB.
                # total = sum constraint catches fabricated totals that don't match components.
                "code": (
                    "assert 14.0 <= model_vram_gb <= 22.0 "
                    "and 3.0 <= kv_cache_vram_gb <= 12.0 "
                    "and -0.2 <= total_vram_gb - model_vram_gb - kv_cache_vram_gb <= 0.2 "
                    "and total_vram_gb <= 26.0"
                ),
                "description": (
                    "VRAM budget computed with real arithmetic: model 14-22 GB, "
                    "KV cache 3-12 GB, total within 0.2 GB of sum, total <= 26 GB. "
                    "Prevents fabricating fits_in_24gb=True without decomposed calculation."
                ),
                # No verify_ssh: grounded by a1 (real GPU node) + a2 (real GPU confirmed).
                # Bounds + sum constraint verify genuine calculation, not recitation.
            },
            {
                "id": "a4",
                "points": 1,
                "code": (
                    "assert recommended_command is not None "
                    "and '--ctx-size' in recommended_command "
                    "and '81920' in recommended_command "
                    "and '--n-gpu-layers' in recommended_command "
                    "and '--cache-type-k' in recommended_command "
                    "and '--host' in recommended_command "
                    "and '--port' in recommended_command "
                    "and '8080' in recommended_command "
                    "and int(recommended_command.split('--n-gpu-layers')[1].strip().split()[0]) > 0 "
                    "and kb_file_exists is True"
                ),
                "description": (
                    "Command has all required flags (--ctx-size 81920, --n-gpu-layers N>0, "
                    "--cache-type-k, --host, --port 8080) and KB file has >=10 lines "
                    "containing 'llama-server' (content check, not just existence)."
                ),
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    # Line count + grep match count — two numbers on stdout
                    "cmd": (
                        "wc -l /opt/local-se/kb/node3090-llama-launch.md 2>/dev/null | awk '{print $1}'; "
                        "grep -c 'llama-server' /opt/local-se/kb/node3090-llama-launch.md 2>/dev/null || echo 0"
                    ),
                    "parse": (
                        "_parts = stdout.strip().split(); "
                        "_lines = int(_parts[0]) if _parts else 0; "
                        "_hits = int(_parts[1]) if len(_parts) > 1 else 0; "
                        "kb_file_exists = (_lines >= 10 and _hits > 0)"
                    ),
                }
            }
        ]
    }),
    failure_modes=json.dumps({
        "0/4": "Binary not found or SSH access failed.",
        "1/4": "Binary found but CUDA driver < 13.x or nvidia-smi unreachable.",
        "2/4": "Binary + CUDA confirmed but VRAM math outside plausible bounds "
               "(model must be 14-22 GB, KV 3-12 GB, total within 0.2 GB of sum).",
        "3/4": "VRAM OK but command missing --cache-type-k, --n-gpu-layers <= 0, "
               "or KB file has fewer than 10 lines or lacks llama-server reference.",
        "4/4": "Binary located, CUDA 13.x confirmed, VRAM computed with real arithmetic, "
               "command has all required flags with valid values, KB written with content."
    }),
    kb_target="node3090/llama-launch-config",
    rollback_defined=0,
    requires_human_approval=0,
    discipline_multiplier=1.3,
    max_attempts=3,
    claude_only_override=0,
    auto_generated=0,
    parent_episode_id=None,
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
          f"{CHALLENGE['discipline_multiplier']}x  |  read_only")
    print(f"       Assertions: {len(json.loads(CHALLENGE['success_criteria'])['assertions'])}")
    print(f"       Max points: "
          f"{len(json.loads(CHALLENGE['success_criteria'])['assertions']) * 5 * CHALLENGE['discipline_multiplier']:.1f}")
    print(f"       Next: node-t3-003 — start llama-server with discovered config")
