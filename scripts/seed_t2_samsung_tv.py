#!/usr/bin/env python3
"""
Seed T2 challenge: Samsung TV Traffic Analysis.

Parent finding: Multiple T1 challenges flagged Samsung S90C (192.168.1.90,
MAC 1c:af:4a:04:5f:b6) for: DHCP requests every 1-2 min and unblocked WAN access.

Usage:
    python3 scripts/seed_t2_samsung_tv.py
"""

import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/opt/local-se/challenges.db"
CREATED_AT = datetime.now(timezone.utc).isoformat()

CHALLENGE = dict(
    id="net-t2-011",
    title="Samsung TV Traffic Analysis",
    description=(
        "Samsung S90C TV at 192.168.1.90 (MAC 1c:af:4a:04:5f:b6) was flagged during "
        "T1 challenges for two behaviours: (1) DHCP requests every 1-2 minutes "
        "(abnormally high frequency — normal devices renew every hours/days), and "
        "(2) unblocked WAN access (TV is phoning home). "
        "Investigate both using pfSense data: "
        "confirm the TV has an active DHCP lease, "
        "check firewall logs for WAN traffic sourced from 192.168.1.90, "
        "identify the top WAN destinations the TV is reaching, "
        "and check whether DHCP logs confirm the hammering behaviour. "
        "Use pfsense_log_summary() for the firewall log picture. "
        "Use pfsense_query('/api/v2/dhcp/server/lease') for the lease table. "
        "Return a JSON object with: "
        "dhcp_lease_found (bool), "
        "dhcp_lease_expiry (str — ISO timestamp or 'unknown'), "
        "wan_traffic_found (bool — True if 192.168.1.90 appears in WAN pass logs), "
        "top_wan_destinations (list of str — IPs or domains TV is calling), "
        "risk_summary (str — one paragraph assessment of the TV's behaviour)."
    ),
    domain="network",
    discipline="security",
    tier=2,
    mode="read_only",
    starting_state=json.dumps({
        "target_ip": "192.168.1.90",
        "target_mac": "1c:af:4a:04:5f:b6",
        "target_device": "Samsung S90C TV",
        "known_behaviours": [
            "DHCP requests every 1-2 minutes (observed in syslog T1 sessions)",
            "WAN access unblocked — TV has outbound internet access"
        ],
        "notes": (
            "DHCP lease endpoint: pfsense_query('/api/v2/dhcp/server/lease'). "
            "Firewall logs: pfsense_log_summary(hours=24). "
            "For WAN traffic from TV specifically, filter firewall logs by src=192.168.1.90. "
            "DHCP log endpoint (if available): pfsense_query('/api/v2/status/logs/dhcp'). "
            "The TV's DHCP hammer was visible in syslog as repeated DISCOVER/REQUEST cycles "
            "from MAC 1c:af:4a:04:5f:b6."
        )
    }),
    success_criteria=json.dumps({
        "assertions": [
            {
                "id": "a1", "points": 1,
                "code": "assert dhcp_lease_found is True",
                "description": "Samsung TV has an active DHCP lease on 192.168.1.0/24"
            },
            {
                "id": "a2", "points": 1,
                "code": "assert wan_traffic_found is True",
                "description": "WAN traffic sourced from 192.168.1.90 confirmed in firewall logs"
            },
            {
                "id": "a3", "points": 1,
                "code": (
                    "assert isinstance(risk_summary, str) and len(risk_summary) >= 30 "
                    "and isinstance(top_wan_destinations, list)"
                ),
                "description": "Risk assessment produced with WAN destination list"
            }
        ]
    }),
    failure_modes=json.dumps({
        "0/3": "pfSense API unreachable or lease table empty — no data.",
        "1/3": "Lease found but no firewall log analysis performed.",
        "2/3": "Lease + WAN traffic confirmed but no destination list or risk assessment.",
        "3/3": "Full picture: lease confirmed, WAN traffic identified with destinations, risk assessed."
    }),
    kb_target="network-security/samsung-tv-traffic-profile",
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
    print(f"  ✅  {CHALLENGE['id']}  {CHALLENGE['title']}")
    print(f"       Tier: {CHALLENGE['tier']}  |  {CHALLENGE['discipline']} {CHALLENGE['discipline_multiplier']}×")
    print(f"       Assertions: {len(json.loads(CHALLENGE['success_criteria'])['assertions'])}/3")
