#!/usr/bin/env python3
"""
Seed T3 challenge: NAS Anonymous Access Hardening Verification.

Parent chain: pf-t1-002 → nas-t2-001 (FTP anon + SMB anon found)
Fix applied:  setcfg global "restrict anonymous" "2" + FTP anon disabled.
This challenge verifies the fix is in place and effective.

Usage:
    python3 scripts/seed_t3_nas_anon_hardening.py
"""

import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/opt/local-se/challenges.db"
CREATED_AT = datetime.now(timezone.utc).isoformat()

CHALLENGE = dict(
    id="nas-t3-001",
    title="NAS Anonymous Access Hardening Verification",
    description=(
        "Following the T2 discovery that FTP anonymous login and SMB anonymous "
        "enumeration were both enabled on n45.home.arpa (192.168.5.45), fixes were "
        "applied: `setcfg global 'restrict anonymous' '2'` for SMB and FTP anonymous "
        "login disabled via QNAP Control Panel. "
        "Verify both fixes are in place and effective from LUCIFER WSL2. "
        "IMPORTANT — QNAP QTS 4.x regenerates smb.conf on every SMB restart. "
        "Do NOT check smb.conf directly for `map to guest` — that is the generated "
        "artifact. The authoritative source is the `restrict anonymous` value in the "
        "[global] section of /etc/config/smb.conf (set via setcfg, persists across restarts). "
        "Return a JSON object with: "
        "smb_anonymous_blocked (bool — True if NT_STATUS_LOGON_FAILURE returned), "
        "restrict_anonymous_value (str — the current value from setcfg/smb.conf), "
        "ftp_anonymous_blocked (bool — True if anonymous FTP login is rejected), "
        "hardening_complete (bool — True only if BOTH SMB and FTP anonymous are blocked)."
    ),
    domain="nas",
    discipline="security",
    tier=3,
    mode="read_only",
    starting_state=json.dumps({
        "target": "n45.home.arpa",
        "ip": "192.168.5.45",
        "smb_fix_applied": "setcfg global 'restrict anonymous' '2' -f /etc/config/smb.conf",
        "ftp_fix_applied": "QNAP Control Panel → FTP Service → anonymous login disabled",
        "kb_doc_id": "7ac7c02c1d118662",
        "notes": (
            "Check SMB: execute_command('smbclient -L //n45.home.arpa -N 2>&1 | head -5'). "
            "Expect: NT_STATUS_LOGON_FAILURE. "
            "Check FTP: execute_command('curl -v --connect-timeout 5 ftp://192.168.5.45 2>&1 | head -10'). "
            "Expect: 530 Login incorrect or 530 Not logged in. "
            "Check restrict_anonymous source value via SSH: "
            "execute_command(\"ssh admin@n45.home.arpa 'grep -i restrict /etc/config/smb.conf'\")"
        )
    }),
    success_criteria=json.dumps({
        "assertions": [
            {
                "id": "a1", "points": 1,
                "code": "assert smb_anonymous_blocked is True",
                "description": "SMB anonymous enumeration blocked (NT_STATUS_LOGON_FAILURE)"
            },
            {
                "id": "a2", "points": 1,
                "code": "assert ftp_anonymous_blocked is True",
                "description": "FTP anonymous login rejected (530 error)"
            },
            {
                "id": "a3", "points": 1,
                "code": (
                    "assert hardening_complete is True "
                    "and restrict_anonymous_value == '2'"
                ),
                "description": "Both vectors blocked AND source setting confirms restrict anonymous = 2"
            }
        ]
    }),
    failure_modes=json.dumps({
        "0/3": "SMB or FTP still allows anonymous access — fix not applied or reverted.",
        "1/3": "One vector blocked but not both; or restrict_anonymous value not checked.",
        "2/3": "Both blocked but restrict_anonymous source value not confirmed (fix may not survive reboot).",
        "3/3": "Both vectors blocked, source setting confirmed at 2 — fix is persistent."
    }),
    kb_target="network-security/nas-anonymous-hardening",
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
    print(f"       Parent chain: pf-t1-002 → nas-t2-001 → nas-t3-001")
