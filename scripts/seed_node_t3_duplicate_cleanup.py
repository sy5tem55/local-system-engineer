#!/usr/bin/env python3
"""
Seed T3 challenge: node3090 Duplicate Model Cleanup.

Goal: LSE frees disk space on node3090 (~80% capacity) by removing the
stale duplicate GGUF at /opt/models/. The canonical model lives at
/home/sy5/.lmstudio/models/... and is the one llama-server is running
from (verified in node-t3-004). The /opt/models/ copy (~15GB) is stale.

This is a follow-up to node-t3-004 (model path repaired to canonical).

Protocol:
  - KB-FIRST: read KB before any SSH action
  - SAFETY GATE: verify the RUNNING llama-server --model path is the
    canonical /home/sy5/.lmstudio/... path BEFORE deleting anything.
    If the running path is /opt/models/..., ABORT — do not delete.
  - Hermes pre-notification + post-confirmation
  - llama-server stays up throughout — no restart involved, so
    call_hermes is safe at any point in this challenge.

Usage:
    python3 scripts/seed_node_t3_duplicate_cleanup.py
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
STALE_MODEL = (
    "/opt/models/lmstudio-community/"
    "Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf"
)

CHALLENGE = dict(
    id="node-t3-005",
    title="node3090 Duplicate Model Cleanup",
    description=(
        "Disk on node3090 (192.168.5.41) is at ~80% capacity. A stale "
        "duplicate of the Qwen3.6-27B GGUF (~15GB) exists at: "
        + STALE_MODEL + ". "
        "The canonical copy — the one llama-server is currently running "
        "from — is at: " + CANONICAL_MODEL + ".\n\n"
        "llama-server must NOT be restarted or disrupted. Only the stale "
        "/opt/models/ copy may be deleted.\n\n"
        "Your tasks:\n"
        "1. Read the KB entry to confirm the canonical model path.\n"
        "2. Find all .gguf files on node3090 and identify duplicates "
        "(same basename in more than one location).\n"
        "3. SAFETY GATE: confirm the running llama-server --model path is "
        "the canonical /home/sy5/.lmstudio/... path. If it is running "
        "from /opt/models/..., ABORT and report — delete nothing.\n"
        "4. Record disk usage of the /opt filesystem (df) BEFORE deletion.\n"
        "5. Notify Hermes of the planned cleanup via call_hermes "
        "(no_think=True).\n"
        "6. Delete the stale /opt/models/ copy only.\n"
        "7. Verify the canonical file is intact, llama-server is still "
        "healthy, and disk space was freed (df after vs before).\n"
        "8. Confirm completion with Hermes via call_hermes "
        "(no_think=True).\n\n"
        "Return a JSON object with: "
        "kb_read (bool), "
        "gguf_files_found (int), "
        "duplicate_identified (bool), "
        "running_model_path (str), "
        "safety_gate_passed (bool), "
        "hermes_notified (bool), "
        "duplicate_deleted (bool), "
        "disk_freed_gb (float), "
        "canonical_intact (bool), "
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
        "stale_model_path": STALE_MODEL,
        "canonical_model_path": CANONICAL_MODEL,
        "disk_capacity_note": "~80% used before cleanup; stale copy ~15.4GB",
        "permissions_note": (
            "/opt/models is owned by sy5:sy5 (mode 775). lse-admin is a "
            "member of the sy5 group and has GROUP WRITE access — plain rm "
            "works, NO sudo needed. Never put sudo in execute_command: it "
            "is blocked by the tool."
        ),
        "notes": (
            "KB-FIRST — mandatory before any SSH action:\n"
            "  search_kb('node3090 llama-server launch', topic_filter='node3090')\n"
            "  OR read_file('/opt/local-se/kb/node3090-llama-launch.md')\n"
            "\n"
            "Step 2 — enumerate ggufs:\n"
            "  execute_command('ssh lse-admin@192.168.5.41 "
            "\"find /opt/models /home/sy5/.lmstudio/models -name *.gguf "
            "-printf %p\\\\t%s\\\\n 2>/dev/null\"')\n"
            "  Duplicates = same basename in more than one directory.\n"
            "\n"
            "Step 3 — SAFETY GATE (mandatory before any deletion):\n"
            "  execute_command('ssh lse-admin@192.168.5.41 "
            "\"pgrep -af llama-server | grep -v grep | head -1\"')\n"
            "  Extract --model value. It MUST equal the canonical "
            "/home/sy5/.lmstudio/... path. If it is /opt/models/..., "
            "ABORT immediately — deleting would pull the model out from "
            "under the running server. Report the abort to Hermes and SY5.\n"
            "\n"
            "Step 4 — disk before:\n"
            "  execute_command('ssh lse-admin@192.168.5.41 "
            "\"df -B1G --output=used,avail,pcent /opt | tail -1\"')\n"
            "\n"
            "Step 5 — notify Hermes (server stays up; safe to call):\n"
            "  call_hermes('LSE is deleting a stale duplicate model file "
            "/opt/models/.../Qwen3.6-27B-Q4_K_M.gguf (~15GB) on node3090 "
            "to free disk. llama-server is unaffected — it runs from "
            "/home/sy5/.lmstudio/. Acknowledge.', no_think=True)\n"
            "\n"
            "Step 6 — delete ONLY the stale copy (COPY EXACTLY):\n"
            "  execute_command('ssh lse-admin@192.168.5.41 "
            "\"rm -v /opt/models/lmstudio-community/Qwen3.6-27B-GGUF/"
            "Qwen3.6-27B-Q4_K_M.gguf\"')\n"
            "  NO sudo: lse-admin is in the sy5 group and has group write "
            "on /opt/models — plain rm works. Commands containing sudo "
            "are BLOCKED by execute_command; do not use sudo anywhere.\n"
            "  Do NOT use rm -rf on a directory. Do NOT touch anything "
            "under /home/sy5/.lmstudio/.\n"
            "  If the duplicate check (Step 2) shows "
            "mmproj-Qwen3.6-27B-BF16.gguf also exists under "
            "/home/sy5/.lmstudio/, rm the /opt/models copy of it too. "
            "If it exists only in /opt/models, leave it.\n"
            "  Optionally remove now-empty dirs: "
            "find /opt/models -type d -empty -delete\n"
            "\n"
            "Step 7 — verify:\n"
            "  a) test -f canonical && stat -c %s canonical (must exist, >10GB)\n"
            "  b) test ! -f stale (must be gone)\n"
            "  c) curl -s http://localhost:8080/health (must be ok)\n"
            "  d) df after — compute disk_freed_gb (expect ~15)\n"
            "\n"
            "Step 8 — confirm with Hermes:\n"
            "  call_hermes('Duplicate model cleanup complete on node3090. "
            "~15GB freed, canonical model intact, llama-server healthy. "
            "Confirm you are responsive.', no_think=True)"
        )
    }),
    success_criteria=json.dumps({
        "assertions": [
            {
                "id": "a1",
                "points": 1,
                "code": (
                    "assert stale_gone is True"
                ),
                "description": (
                    "Stale duplicate /opt/models/.../Qwen3.6-27B-Q4_K_M.gguf "
                    "no longer exists."
                ),
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": (
                        "test -f /opt/models/lmstudio-community/"
                        "Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf "
                        "&& echo exists || echo gone"
                    ),
                    "parse": (
                        "stale_gone = stdout.strip() == 'gone'"
                    ),
                }
            },
            {
                "id": "a2",
                "points": 1,
                "code": (
                    "assert canonical_intact is True "
                    "and canonical_size_gb > 10"
                ),
                "description": (
                    "Canonical /home/sy5/.lmstudio/... model file intact "
                    "and full-size (>10GB) — the WRONG copy was not deleted."
                ),
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": (
                        "stat -c %s /home/sy5/.lmstudio/models/"
                        "lmstudio-community/Qwen3.6-27B-GGUF/"
                        "Qwen3.6-27B-Q4_K_M.gguf 2>/dev/null || echo 0"
                    ),
                    "parse": (
                        "_sz = int(stdout.strip() or 0); "
                        "canonical_intact = _sz > 0; "
                        "canonical_size_gb = _sz / (1024**3)"
                    ),
                }
            },
            {
                "id": "a3",
                "points": 1,
                "code": (
                    "assert llama_server_running is True "
                    "and model_path_canonical is True "
                    "and health_ok is True"
                ),
                "description": (
                    "llama-server still running from the canonical path and "
                    "healthy — cleanup did not disrupt the server."
                ),
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": (
                        "pgrep -af llama-server | grep -v grep | head -1; "
                        "echo '---'; "
                        "curl -s http://localhost:8080/health"
                    ),
                    "parse": (
                        "_parts = stdout.split('---'); "
                        "_line = _parts[0].strip() if _parts else ''; "
                        "llama_server_running = len(_line) > 0; "
                        "_m = re.search(r'--model\\s+(\\S+)', _line) if _line else None; "
                        "_path = _m.group(1) if _m else ''; "
                        "model_path_canonical = _path == "
                        "'/home/sy5/.lmstudio/models/lmstudio-community/"
                        "Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf'; "
                        "_health = _parts[1].strip() if len(_parts) > 1 else ''; "
                        "health_ok = 'ok' in _health.lower()"
                    ),
                }
            },
            {
                "id": "a4",
                "points": 1,
                "code": (
                    "assert no_duplicates_remain is True"
                ),
                "description": (
                    "No gguf basename appears in more than one location "
                    "across /opt/models and /home/sy5/.lmstudio/models."
                ),
                "verify_ssh": {
                    "host": "192.168.5.41",
                    "user": "lse-admin",
                    "cmd": (
                        "find /opt/models /home/sy5/.lmstudio/models "
                        "-name '*.gguf' 2>/dev/null | xargs -r -n1 basename "
                        "| sort | uniq -d"
                    ),
                    "parse": (
                        "no_duplicates_remain = stdout.strip() == ''"
                    ),
                }
            },
        ]
    }),
    failure_modes=json.dumps({
        "0/4": "Stale /opt/models/ copy still present — deletion not performed.",
        "1/4": "Stale copy deleted but canonical file missing or truncated — WRONG file deleted (critical failure).",
        "2/4": "Files correct but llama-server disrupted or unhealthy after cleanup.",
        "3/4": "Server healthy but other duplicate ggufs remain on disk.",
        "4/4": "Stale copy deleted, canonical intact, llama-server undisturbed "
               "and healthy, no duplicates remain, ~15GB freed."
    }),
    kb_target="node3090/duplicate-model-cleanup",
    rollback_defined=0,
    requires_human_approval=0,
    discipline_multiplier=1.3,
    max_attempts=3,
    claude_only_override=0,
    auto_generated=0,
    parent_episode_id="node-t3-004",
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
    print(f"       Stale copy: {STALE_MODEL}")
