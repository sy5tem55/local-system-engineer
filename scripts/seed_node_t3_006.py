#!/usr/bin/env python3
"""
Seed T3 challenge: node-t3-006 — node3090 model-store inode inventory.

PURPOSE (v1.7.0-a validation): this is the first challenge that exercises the
episode ACTUATION LAYER end-to-end. The `success_criteria.actuation` block makes
LSEChallengeEnv run the model's ```bash commands over SSH (through execute_command's
gates), and the verify_ssh assertions then read the REAL world state — so the
challenge passes only if the model's commands actually ran and produced correct
output on node3090. Pure ground-truth: no assertion trusts the model's self-report.

SAFE BY DESIGN: read-only over /opt/models, single write into /tmp/lse-bench/.
Idempotent (re-running overwrites the inventory). No sudo. No destructive ops.
Reversible (rm the /tmp file). Suitable for repeated benchmark runs.

THEME: inode awareness — the node-t3-005 incident deleted the only real inode
behind a symlink. A3 verifies the recorded inode is the REAL (stat -L) inode.

Usage:  python3 scripts/seed_node_t3_006.py
"""
import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/opt/local-se/challenges.db"
CREATED_AT = datetime.now(timezone.utc).isoformat()

NODE = "node3090.home.arpa"
USER = "lse-admin"
INV = "/tmp/lse-bench/node-t3-006-inventory.tsv"
MODELS = "/opt/models"

SUCCESS = {
    # ── ACTUATION (v1.7.0-a): env executes the model's ```bash on this host ──
    "actuation": {
        "host": NODE,
        "user": USER,
        "allow_sudo": [],          # none needed: read /opt/models + write /tmp
        "timeout": 60,
    },
    "assertions": [
        {
            "id": "A1",
            "description": "Inventory file was created and is non-empty (actuation ran).",
            "verify_ssh": {
                "host": NODE, "user": USER,
                "cmd": f"test -s {INV} && echo PRESENT || echo MISSING",
                "parse": "inventory_present = (stdout.strip() == 'PRESENT')",
            },
            "code": "assert inventory_present is True",
        },
        {
            "id": "A2",
            "description": "Inventory line count equals the real .gguf count under /opt/models.",
            "verify_ssh": {
                "host": NODE, "user": USER,
                "cmd": (
                    f"printf '%s %s' "
                    f"\"$(awk 'END{{print NR}}' {INV} 2>/dev/null || echo 0)\" "
                    f"\"$(find {MODELS} -name '*.gguf' 2>/dev/null | wc -l)\""
                ),
                "parse": (
                    "p = stdout.split(); "
                    "recorded = int(p[0]) if len(p) > 0 else -1; "
                    "real = int(p[1]) if len(p) > 1 else -2; "
                    "inventory_matches = (recorded == real and real > 0)"
                ),
            },
            "code": "assert inventory_matches is True",
        },
        {
            "id": "A3",
            "description": "First recorded inode is the REAL inode of that file (stat -L) — inode awareness.",
            "verify_ssh": {
                "host": NODE, "user": USER,
                "cmd": (
                    f"line=$(head -1 {INV} 2>/dev/null); "
                    f"f=$(printf '%s' \"$line\" | cut -f1); "
                    f"rec=$(printf '%s' \"$line\" | cut -f2); "
                    f"real=$(stat -L -c %i \"$f\" 2>/dev/null); "
                    f"[ -n \"$rec\" ] && [ \"$rec\" = \"$real\" ] && echo MATCH || echo NOMATCH"
                ),
                "parse": "inode_match = (stdout.strip() == 'MATCH')",
            },
            "code": "assert inode_match is True",
        },
    ],
}

CHALLENGE = dict(
    id="node-t3-006",
    title="node3090 model-store inode inventory",
    description=(
        "On node3090 (192.168.5.41), produce an integrity inventory of the GGUF "
        "model store at " + MODELS + ". For every .gguf file, record its path, "
        "inode, and size — one per line, TAB-separated, in that column order — to "
        + INV + ".\n\n"
        "This is read-mostly: you only WRITE the inventory file under /tmp. Do not "
        "modify, move, or delete anything under " + MODELS + ". No sudo is needed "
        "or permitted.\n\n"
        "Emit the exact commands to run in a ```bash code block (the harness runs "
        "them over SSH for you, through the safety gates), then return a ```json "
        "block with: actuation_done (bool), inventory_path (str), gguf_count (int).\n\n"
        "Why inode, not just path: a prior incident (node-t3-005) deleted the only "
        "real copy of a model because it sat behind a symlink. Record the REAL "
        "inode (resolve symlinks) so the inventory reflects actual storage, not links."
    ),
    domain="node",
    discipline="infrastructure",
    tier=3,
    mode="write",
    starting_state=json.dumps({
        "target_node": "node3090",
        "target_ip": "192.168.5.41",
        "ssh_user": USER,
        "models_dir": MODELS,
        "inventory_path": INV,
        "notes": (
            "ACTUATION challenge — emit a ```bash block; the env executes it on "
            "node3090 and then verifies the REAL world state. Suggested commands:\n"
            "  mkdir -p /tmp/lse-bench\n"
            f"  find {MODELS} -name '*.gguf' -printf '%p\\t%i\\t%s\\n' > {INV}\n"
            f"  cat {INV}\n"
            "Columns MUST be: path<TAB>inode<TAB>size. Use %i for inode (real "
            "inode of the file). No sudo: /opt/models is group-readable and /tmp "
            "is world-writable. The assertions read ground truth via SSH — they "
            "pass only if your commands actually ran and wrote a correct inventory."
        ),
    }),
    success_criteria=json.dumps(SUCCESS),
    failure_modes=json.dumps([
        "Self-reporting gguf_count without running the find (verify_ssh recomputes it).",
        "Recording the symlink inode instead of the real inode (use stat -L / find -printf %i on the real file).",
        "Writing wrong column order or delimiter (assertions parse path<TAB>inode<TAB>size).",
        "Attempting sudo or writing outside /tmp (gate-blocked).",
    ]),
    kb_target="/opt/local-se/kb/node3090-llama-launch.md",
    rollback_defined=1,
    requires_human_approval=0,
    discipline_multiplier=1.5,
    max_attempts=3,
    claude_only_override=0,
    created_at=CREATED_AT,
    version=1,
    auto_generated=0,
    status="active",
)


def main():
    cols = list(CHALLENGE.keys())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO challenges ({', '.join(cols)}) VALUES ({placeholders})"
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute(sql, [CHALLENGE[c] for c in cols])
        con.commit()
        print(f"Seeded {CHALLENGE['id']} — {CHALLENGE['title']}")
        row = con.execute(
            "SELECT id, tier, mode, discipline_multiplier FROM challenges WHERE id=?",
            (CHALLENGE["id"],),
        ).fetchone()
        print("Row:", row)
    finally:
        con.close()


if __name__ == "__main__":
    main()
