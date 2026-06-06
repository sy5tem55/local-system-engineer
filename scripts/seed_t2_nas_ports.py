#!/usr/bin/env python3
"""
Seed T2 challenge: NAS Unexpected Port Investigation.

Parent finding: pf-t1-002 / net-t1-009 — ports 21, 22, 80, 139 found open
on 192.168.5.45 (nas.home.arpa) beyond the expected NFS/SMB/QNAP-web set.

Usage:
    python3 scripts/seed_t2_nas_ports.py
"""

import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/opt/local-se/challenges.db"
CREATED_AT = datetime.now(timezone.utc).isoformat()

CHALLENGE = dict(
    id="nas-t2-001",
    title="NAS Unexpected Port Investigation",
    description=(
        "During T1 scans, ports 21 (FTP), 22 (SSH), 80 (HTTP), and 139 (NetBIOS) "
        "were found open on 192.168.5.45 (nas.home.arpa) beyond the expected "
        "NFS (2049), SMB (445), and QNAP web (8080/443) services. "
        "Investigate each unexpected port: confirm the service is live, identify "
        "what is listening, classify the security risk (high/medium/low), and "
        "determine whether each port should be firewalled or left open. "
        "Use nmap_summary() for the scan — do NOT use raw execute_command('nmap ...'). "
        "Return a JSON object with: "
        "unexpected_ports (list of {port, service, risk, verdict}), "
        "ftp_anonymous_allowed (bool), "
        "recommendation (str — one concrete action to take). "
    ),
    domain="nas",
    discipline="security",
    tier=2,
    mode="read_only",
    starting_state=json.dumps({
        "target": "192.168.5.45",
        "known_unexpected_ports": [21, 22, 80, 139],
        "expected_ports": [445, 2049, 443, 8080],
        "notes": (
            "NAS is a QNAP TS-419P II at 192.168.5.45 / nas.home.arpa. "
            "Reachable from LUCIFER WSL2 via pfSense inter-subnet routing. "
            "Use nmap_summary() with known_services JSON to isolate unexpected ports. "
            "For FTP (21): check anonymous login with: "
            "execute_command('curl -v --connect-timeout 5 ftp://192.168.5.45 2>&1 | head -20')"
        )
    }),
    success_criteria=json.dumps({
        "assertions": [
            {
                "id": "a1", "points": 1,
                "code": (
                    "assert isinstance(unexpected_ports, list) and len(unexpected_ports) >= 3 "
                    "and all('port' in p and 'risk' in p for p in unexpected_ports)"
                ),
                "description": "At least 3 unexpected ports analysed with port + risk fields"
            },
            {
                "id": "a2", "points": 1,
                "code": (
                    "assert isinstance(ftp_anonymous_allowed, bool)"
                ),
                "description": "FTP anonymous login status explicitly determined (True or False)"
            },
            {
                "id": "a3", "points": 1,
                "code": (
                    "assert isinstance(recommendation, str) and len(recommendation) >= 20"
                ),
                "description": "Concrete remediation recommendation provided (>=20 chars)"
            }
        ]
    }),
    failure_modes=json.dumps({
        "0/3": "nmap_summary() fails or model calls raw nmap; no structured output.",
        "1/3": "Ports listed but no risk classification; FTP check skipped.",
        "2/3": "Ports + risk present; FTP status determined; no recommendation.",
        "3/3": "Full investigation — all unexpected ports classified, FTP auth tested, "
               "concrete recommendation produced."
    }),
    kb_target="network-security/nas-unexpected-ports",
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
