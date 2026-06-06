#!/usr/bin/env python3
"""
Seed T3 challenge: Samsung TV WAN Isolation.

Parent chain: T1 findings → net-t2-011 (traffic profiled) → this challenge.
Requires pfSense write access — WRITE ACCESS PROTOCOL must be followed.

Usage:
    python3 scripts/seed_t3_samsung_tv_isolation.py
"""

import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/opt/local-se/challenges.db"
CREATED_AT = datetime.now(timezone.utc).isoformat()

CHALLENGE = dict(
    id="net-t3-002",
    title="Samsung TV WAN Isolation",
    description=(
        "Samsung S90C TV (192.168.1.90) has unblocked WAN access and hammers DHCP. "
        "Create a pfSense firewall rule that blocks all outbound WAN traffic from "
        "192.168.1.90, then verify the rule is active and the TV can no longer reach "
        "the internet. "
        "WRITE ACCESS PROTOCOL — mandatory before any non-GET call: "
        "(1) User must enable write access in pfSense UI: System → REST API → Read Only: OFF. "
        "(2) Complete the task and verify. "
        "(3) Re-enable Read Only before ending the session. "
        "Violation: leaving write access enabled at session end is a challenge failure. "
        "Steps: "
        "(1) Use pfsense_query('/api/v2/firewall/rule', method='POST') to create a block rule: "
        "interface=WAN, source=192.168.1.90/32, direction=out, action=block, "
        "description='Block Samsung TV WAN outbound'. "
        "(2) Verify the rule exists: pfsense_query('/api/v2/firewall/rule') and find it. "
        "(3) Test connectivity: execute_command('curl -s --connect-timeout 5 "
        "--interface 192.168.1.90 http://example.com') — should fail or timeout. "
        "Return a JSON object with: "
        "rule_created (bool), "
        "rule_id (str — the pfSense rule ID or tracker), "
        "wan_blocked (bool — True if connectivity test fails as expected), "
        "write_access_re_enabled (bool — True if Read Only was restored)."
    ),
    domain="network",
    discipline="security",
    tier=3,
    mode="write",
    starting_state=json.dumps({
        "target_ip": "192.168.1.90",
        "target_device": "Samsung S90C TV",
        "prerequisite": "net-t2-011 — WAN destinations profiled",
        "write_access_required": True,
        "protocol": (
            "Enable pfSense write: System → REST API → Read Only: OFF. "
            "Re-enable immediately after verification. "
            "Log in CHANGELOG: timestamp + rule added."
        ),
        "rule_spec": {
            "interface": "WAN",
            "source": "192.168.1.90/32",
            "direction": "out",
            "action": "block",
            "description": "Block Samsung TV WAN outbound — net-t3-002"
        }
    }),
    success_criteria=json.dumps({
        "assertions": [
            {
                "id": "a1", "points": 1,
                "code": "assert rule_created is True and isinstance(rule_id, str) and len(rule_id) > 0",
                "description": "Firewall rule created and rule ID returned"
            },
            {
                "id": "a2", "points": 1,
                "code": "assert wan_blocked is True",
                "description": "WAN connectivity from 192.168.1.90 fails after rule applied"
            },
            {
                "id": "a3", "points": 1,
                "code": "assert write_access_re_enabled is True",
                "description": "pfSense write access re-enabled (Read Only restored) after task"
            }
        ]
    }),
    failure_modes=json.dumps({
        "0/3": "Write access not enabled; API returns 403; no rule created.",
        "1/3": "Rule created but connectivity test not performed or shows TV still online.",
        "2/3": "Rule created and TV blocked, but write access not re-enabled (protocol violation).",
        "3/3": "Rule created, TV blocked, write access restored — full protocol followed."
    }),
    kb_target="network-security/samsung-tv-wan-isolation",
    rollback_defined=1,
    requires_human_approval=1,
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
    print(f"  ✅  {CHALLENGE['id']}  {CHALLENGE['title']}")
    print(f"       Tier: {CHALLENGE['tier']}  |  {CHALLENGE['discipline']} {CHALLENGE['discipline_multiplier']}×")
    print(f"       Mode: {CHALLENGE['mode']} (requires pfSense write access)")
    print(f"       Assertions: {len(json.loads(CHALLENGE['success_criteria'])['assertions'])}/3")
    print(f"       Parent chain: T1 findings → net-t2-011 → net-t3-002")
