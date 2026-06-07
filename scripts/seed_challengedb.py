#!/usr/bin/env python3
"""
Seed ChallengeDB with T1 challenges from network-topology.md.

Usage (on LUCIFER WSL2):
    python3 scripts/seed_challengedb.py                  # create + insert
    python3 scripts/seed_challengedb.py --dry-run        # print SQL only
    python3 scripts/seed_challengedb.py --reset          # drop + recreate + insert

Database path: /opt/local-se/challenges.db
"""

import sqlite3
import json
import argparse
from datetime import datetime, timezone

DB_PATH = "/opt/local-se/challenges.db"
CREATED_AT = datetime.now(timezone.utc).isoformat()

# ── Schema (from arena doc §11) ───────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS challenges (
    id                      TEXT PRIMARY KEY,
    title                   TEXT NOT NULL,
    description             TEXT NOT NULL,
    domain                  TEXT NOT NULL,
    discipline              TEXT NOT NULL,
    tier                    INTEGER NOT NULL,
    mode                    TEXT NOT NULL,
    starting_state          TEXT,
    success_criteria        TEXT NOT NULL,
    failure_modes           TEXT NOT NULL,
    kb_target               TEXT,
    rollback_defined        INTEGER DEFAULT 0,
    requires_human_approval INTEGER DEFAULT 0,
    discipline_multiplier   REAL NOT NULL,
    max_attempts            INTEGER DEFAULT 3,
    claude_only_override    INTEGER DEFAULT 0,
    created_at              TEXT,
    version                 INTEGER DEFAULT 1,
    auto_generated          INTEGER DEFAULT 0,
    parent_episode_id       INTEGER,
    status                  TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS episodes (
    id                          TEXT PRIMARY KEY,
    challenge_id                TEXT REFERENCES challenges(id),
    model_id                    TEXT NOT NULL,
    attempt_count               INTEGER,
    convergence_triggered       INTEGER DEFAULT 0,
    kb_assisted                 INTEGER DEFAULT 0,
    escalated                   INTEGER DEFAULT 0,
    escalation_context_quality  TEXT,
    sandbox_pass                INTEGER,
    human_approved              INTEGER,
    deployed                    INTEGER DEFAULT 0,
    base_points                 INTEGER,
    bonus_points                INTEGER,
    total_points                REAL,
    started_at                  TEXT,
    completed_at                TEXT
);
"""

# ── T1 Challenges ─────────────────────────────────────────────────────────────

CHALLENGES = [

    dict(
        id="pf-t1-001",
        title="LAN Device Map",
        description=(
            "Enumerate all active devices on 192.168.1.0/24 with hostname, MAC address, "
            "and vendor. Use the pfSense DHCP lease table (GET /api/v2/dhcp/server/lease) "
            "combined with an ARP scan from LUCIFER WSL2. Produce a structured inventory "
            "of all known devices including pfSense (192.168.1.50) and LUCIFER (192.168.1.57)."
        ),
        domain="pfsense",
        discipline="sysadmin",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "api_base": "https://pfsense.home.arpa/api/v2",
            "auth": "vaultwarden:PFSENSE_API_KEY",
            "api_mode": "read_only",
            "snapshot_required": False,
            "notes": "Direct production query. WSL2 mirrored networking confirmed."
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": 'assert "192.168.1.50" in [d["ip"] for d in devices]',
                    "description": "pfSense gateway found at 192.168.1.50"
                },
                {
                    "id": "a2", "points": 1,
                    "code": 'assert "192.168.1.57" in [d["ip"] for d in devices]',
                    "description": "LUCIFER host found at 192.168.1.57"
                },
                {
                    "id": "a3", "points": 1,
                    "code": 'assert len([d for d in devices if d.get("mac")]) >= 5',
                    "description": "At least 5 devices with MAC address resolved"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "Model fails to query pfSense DHCP API or ARP table; returns no device list.",
            "1/3": "DHCP lease table retrieved, pfSense + LUCIFER found; no ARP scan, MAC vendor not resolved; a3 fails.",
            "2/3": "pfSense and LUCIFER confirmed, MACs listed, but fewer than 5 entries; ARP scan incomplete.",
            "3/3": "Full inventory — all known devices, hostnames, MACs, vendors; all 3 assertions pass."
        }),
        kb_target="network-topology/lan-device-inventory",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.0, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="pf-t1-002",
        title="NAS Subnet Map",
        description=(
            "Enumerate 192.168.5.0/24. Confirm the TS-419P II NAS is present, identify "
            "all listening ports via nmap top-1000 scan, and flag any unexpected open ports "
            "beyond NFS (2049), SMB (445), and QNAP web (8080/443). Verify the subnet is "
            "reachable from LUCIFER WSL2 via pfSense inter-subnet routing."
        ),
        domain="pfsense",
        discipline="security",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "tool": "nmap --top-ports 1000",
            "from": "lucifer-wsl2",
            "target": "192.168.5.0/24",
            "snapshot_required": False,
            "notes": "Requires WSL2 mirrored networking + pfSense inter-subnet routing to 192.168.5.0/24."
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert nas_subnet_reachable is True",
                    "description": "192.168.5.0/24 reachable from LUCIFER WSL2"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert any(2049 in h.get('ports', []) for h in hosts)",
                    "description": "NFS port 2049 found on at least one host"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert unexpected_ports == [] or unexpected_ports is not None",
                    "description": "Unexpected port analysis performed (list produced, may be empty)"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "WSL2 → 192.168.5.0/24 routing fails; subnet unreachable; no results.",
            "1/3": "Subnet reachable (ping sweep only), NAS found, but no port scan; NFS assertion fails.",
            "2/3": "NFS confirmed, NAS identified; unexpected port analysis not performed or missing.",
            "3/3": "Full scan — NAS found, all ports listed, unexpected findings analysed; all 3 pass."
        }),
        kb_target="network-topology/nas-subnet-inventory",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.3, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="pf-t1-003",
        title="pfSense Firewall Log Baseline",
        description=(
            "Parse pfSense firewall logs from the last 24 hours. Produce: (1) top 10 "
            "blocked source IPs ranked by frequency, (2) top blocked destination ports, "
            "(3) pass/block ratio per interface. "
            "IMPORTANT: use pfsense_log_summary() — do NOT call the raw logs API directly. "
            "pfsense_log_summary() returns: log_count (int), top_blocked_ips (list), "
            "top_blocked_ports (list), interface_ratios (dict with block_ratio key), anomalies (str). "
            "Return log_count as an integer, not a list."
        ),
        domain="pfsense",
        discipline="security",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "syslog_host": "lucifer-wsl2", "syslog_port": 514, "syslog_status": "live",
            "api_fallback": "GET /api/v2/status/logs/firewall",
            "infra_prereq": "syslog_collector_container",
            "snapshot_required": False,
            "notes": "Syslog collector container must be running. nc listener is temporary — not usable here."
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert int(log_count) >= 100",
                    "description": "At least 100 log entries parsed (log_count is an integer — use pfsense_log_summary())"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert len(top_blocked_ips) >= 5",
                    "description": "Top blocked source IPs ranked (at least 5)"
                },
                {
                    "id": "a3", "points": 1,
                    "code": 'assert "block_ratio" in summary and summary["block_ratio"] > 0',
                    "description": "Pass/block ratio computed per interface"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "Model cannot reach syslog or pfSense log API; returns no data.",
            "1/3": "Logs parsed, count >= 100 confirmed, but no ranking of blocked IPs; a2 fails.",
            "2/3": "Top blocked IPs produced; pass/block ratio missing or not per-interface.",
            "3/3": "Top 10 blocked IPs, top blocked destination ports, pass/block ratio per interface."
        }),
        kb_target="pfsense/log-baseline",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.3, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="ha-t1-004",
        title="Home Assistant Inventory",
        description=(
            "Enumerate all Home Assistant entities, devices, integrations, and installed "
            "add-ons on the production Pi 4 instance. Identify the Pi hardware model and "
            "available RAM via the Supervisor API (GET /api/hassio/host/info). Requires a "
            "long-lived access token — create in HA profile → Security → Long-lived tokens."
        ),
        domain="homeassistant",
        discipline="sysadmin",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "api_base": "http://homeassistant.home.arpa:8123/api",
            "auth": "vaultwarden:HA_TOKEN",
            "supervisor_api": "GET /api/hassio/host/info",
            "snapshot_required": False,
            "prereq": "HA long-lived token — STATUS UNKNOWN, create before running"
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert len(entities) >= 10",
                    "description": "At least 10 entities found"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert ha_version is not None",
                    "description": "HA version string retrieved"
                },
                {
                    "id": "a3", "points": 1,
                    "code": 'assert system_info.get("board") is not None or system_info.get("total_ram_mb") is not None',
                    "description": "Pi hardware model or RAM identified via Supervisor API"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "No HA token; authentication fails; no data returned.",
            "1/3": "Entities listed (>=10), HA version retrieved; Supervisor API not called; hardware missing.",
            "2/3": "Entities + version + add-on list retrieved; Pi hardware/RAM not identified.",
            "3/3": "Full inventory — entities, devices, integrations, add-ons, Pi model, memory."
        }),
        kb_target="home-assistant/entity-inventory",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.0, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="nas-t1-005",
        title="NAS Service Inventory",
        description=(
            "Enumerate running services and shares on the QNAP TS-419P II at 192.168.5.x. "
            "Identify all NFS exports, SMB shares, and available disk space. Confirm no "
            "Container Station is installed (ARMv5 Kirkwood — Docker not supported). "
            "Use QNAP QTS API if credentials available; fallback: nmap + showmount -e."
        ),
        domain="sysadmin",
        discipline="sysadmin",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "target": "192.168.5.45",
            "auth": "QNAP_ADMIN_CREDENTIALS — STATUS UNKNOWN — try default admin/admin or admin/password",
            "fallback": "nmap + showmount -e <nas-ip> from lucifer-wsl2",
            "snapshot_required": False,
            "notes": "Obtain QNAP admin credentials from QNAP web UI or SSH before running."
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert len(nfs_exports) >= 1",
                    "description": "At least one NFS export found"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert len(smb_shares) >= 1",
                    "description": "At least one SMB share found"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert disk_free_gb > 0",
                    "description": "Available disk space retrieved"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "192.168.5.x unreachable from WSL2; no results (routing or credential issue).",
            "1/3": "NAS reached via nmap, ports confirmed (2049/445), but showmount blocked; NFS not enumerated.",
            "2/3": "NFS exports found; SMB shares or disk space not retrieved.",
            "3/3": "NFS exports, SMB shares, disk space retrieved; no Container Station confirmed."
        }),
        kb_target="nas/service-inventory",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.0, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="pf-t1-006",
        title="pfSense Firewall Rule Map",
        description=(
            "Retrieve all pfSense firewall rules via GET /api/v2/firewall/rule. Map rules "
            "governing inter-subnet routing between 192.168.1.0/24 (LAN) and 192.168.5.0/24 "
            "(NAS subnet). Identify any rules with any/any source/destination and flag them "
            "as security risks."
        ),
        domain="pfsense",
        discipline="security",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "api_base": "https://pfsense.home.arpa/api/v2",
            "endpoint": "GET /api/v2/firewall/rule",
            "auth": "vaultwarden:PFSENSE_API_KEY",
            "api_mode": "read_only",
            "snapshot_required": False,
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert len(lan_rules) > 0",
                    "description": "LAN interface rules retrieved"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert inter_subnet_rules is not None",
                    "description": "Rules governing .1.x <-> .5.x identified (list, may be empty)"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert any_any_checked is True",
                    "description": "any/any source/destination analysis performed and result reported"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "API returns rules but model does not parse or categorize by interface; raw dump only.",
            "1/3": "LAN rules listed; inter-subnet rules not specifically extracted; a2 fails.",
            "2/3": "Inter-subnet rules mapped; any/any check not performed or not explicitly flagged.",
            "3/3": "All rules retrieved, inter-subnet categorized, any/any flagged as security risk."
        }),
        kb_target="pfsense/firewall-rule-map",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.3, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="pf-t1-007",
        title="pfSense DNS Resolver Audit",
        description=(
            "Retrieve the pfSense Unbound DNS resolver configuration. List all custom host "
            "overrides and domain overrides via GET /api/v2/services/unbound/host_override "
            "and GET /api/v2/services/unbound/domain_override. Verify no override entries "
            "point to public (non-RFC1918) IP addresses. SSH fallback: cat /cf/conf/config.xml. "
            "Note: cisco.lan stale entry was removed 2026-06-03 — audit should show clean state."
        ),
        domain="pfsense",
        discipline="security",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "api_base": "https://pfsense.home.arpa/api/v2",
            "endpoints": [
                "GET /api/v2/services/unbound/host_override",
                "GET /api/v2/services/unbound/domain_override"
            ],
            "ssh_fallback": "ssh admin@pfsense.home.arpa 'cat /cf/conf/config.xml'",
            "known_state": "cisco.lan stale entry removed 2026-06-03 — audit should show clean state",
            "snapshot_required": False,
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert dns_resolver_running is True",
                    "description": "Unbound service confirmed running"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert isinstance(host_overrides, list)",
                    "description": "Host override list retrieved (may be empty)"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert all(is_rfc1918(o['ip']) for o in host_overrides)",
                    "description": "All override IPs are RFC1918 — no public IPs in DNS overrides"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "DNS config not retrieved (API error or SSH not used as fallback).",
            "1/3": "Resolver status confirmed running; override list not retrieved.",
            "2/3": "Overrides listed (may be empty); IP public/private analysis not performed.",
            "3/3": "Resolver confirmed, all overrides listed, public IP entries flagged or absent."
        }),
        kb_target="pfsense/dns-resolver-config",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.3, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="ha-t1-008",
        title="HA Automation Audit",
        description=(
            "List all Home Assistant automations via GET /api/states filtered to automation.* "
            "entities. For each automation retrieve: trigger type, last_triggered timestamp, "
            "and enabled/disabled status (state: on/off). Flag any automation that has not "
            "fired in the last 30 days OR has last_triggered=null (never fired). "
            "Requires HA long-lived access token."
        ),
        domain="homeassistant",
        discipline="sysadmin",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "api_base": "http://homeassistant.home.arpa:8123/api",
            "endpoint": "GET /api/states",
            "filter": "automation.*",
            "auth": "vaultwarden:HA_TOKEN",
            "notes": "last_triggered=null means never fired, treat as stale. Token required."
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert len(automations) >= 1",
                    "description": "At least one automation exists"
                },
                {
                    "id": "a2", "points": 1,
                    "code": 'assert all("last_triggered" in a["attributes"] for a in automations)',
                    "description": "last_triggered attribute retrieved for all automations"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert stale_automations is not None",
                    "description": "Stale automation list produced (list, may be empty)"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "No HA access (token missing/invalid); no data returned.",
            "1/3": "Automations listed (>=1), but last_triggered not extracted from attributes.",
            "2/3": "Timestamps present; stale filter (30-day or null) not applied; a3 fails.",
            "3/3": "All automations listed with trigger type, enabled status, last_triggered; stale flagged."
        }),
        kb_target="home-assistant/automation-audit",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.0, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="ha-t2-002",
        title="HA Template Sensor Misconfiguration Audit",
        description=(
            "Home Assistant is logging: 'Configuring the template integration by adding "
            "platform: template under the sensor: key is not supported.' "
            "Use the HA REST API to: (1) confirm the error in /api/error_log, "
            "(2) enumerate all sensor.* entities to identify which are template-based, "
            "(3) retrieve their current state values and attributes. "
            "Produce a migration report: list each affected sensor name, its current "
            "value_template expression (from attributes), and the corrected template: YAML block."
        ),
        domain="homeassistant",
        discipline="sysadmin",
        tier=2,
        mode="read_only",
        starting_state=json.dumps({
            "api_base": "http://homeassistant.home.arpa:8123/api",
            "auth": "vaultwarden:HA_TOKEN",
            "error_log_endpoint": "GET /api/error_log",
            "states_endpoint": "GET /api/states",
            "known_issue": "platform: template under sensor: key — deprecated since HA 2023.4",
            "fix_target": "Migrate to template: key in configuration.yaml",
            "prereq": "HA long-lived token — CONFIRMED LIVE (2026-06-05)"
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": 'assert "platform" in error_log and ("template" in error_log or "unsupported" in error_log.lower())',
                    "description": "Template misconfiguration error confirmed in HA error log"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert len(template_sensors) >= 1",
                    "description": "At least one affected template sensor entity identified by name"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert migration_yaml is not None and 'template:' in migration_yaml",
                    "description": "Correct migration YAML produced with template: key format"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "HA token missing or API unreachable; no data retrieved.",
            "1/3": "Error log confirms the issue but no sensor entities identified.",
            "2/3": "Sensors identified and current states retrieved; migration YAML not produced.",
            "3/3": "Error confirmed, all affected sensors identified, correct migration YAML generated."
        }),
        kb_target="home-assistant/template-migration",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.3, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="ha-t3-001",
        title="HA Template Sensor Migration — Apply Fix",
        description=(
            "Apply the template sensor migration identified in ha-t2-002. "
            "Steps: (1) Read current configuration.yaml from the Pi via SSH from LUCIFER "
            "(ssh pi@homeassistant.home.arpa cat /homeassistant/configuration.yaml), "
            "(2) generate the corrected YAML replacing sensor: platform: template with "
            "the template: key format, (3) write the updated file back via SSH, "
            "(4) validate config via POST /api/config/core/check_config, "
            "(5) restart HA via POST /api/services/homeassistant/restart, "
            "(6) confirm /api/error_log no longer contains the template migration warning. "
            "Requires human approval before writing to Pi filesystem."
        ),
        domain="homeassistant",
        discipline="sysadmin",
        tier=3,
        mode="read_write",
        starting_state=json.dumps({
            "api_base": "http://homeassistant.home.arpa:8123/api",
            "auth": "vaultwarden:HA_TOKEN",
            "config_file": "/homeassistant/configuration.yaml",
            "ssh_target": "pi@homeassistant.home.arpa",
            "config_check_endpoint": "POST /api/config/core/check_config",
            "restart_endpoint": "POST /api/services/homeassistant/restart",
            "verify_endpoint": "GET /api/error_log",
            "prereq": "ha-t2-002 solved — migration YAML in KB. infra-t3-002 must be solved first (SSH key auth required for non-interactive file edit)",
            "rollback": "SSH cp /homeassistant/configuration.yaml.bak /homeassistant/configuration.yaml + restart"
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": 'assert config_check_result.get("result") == "valid"',
                    "description": "HA config check passes after YAML edit"
                },
                {
                    "id": "a2", "points": 1,
                    "code": 'assert restart_status_code == 200',
                    "description": "HA restart triggered successfully via REST API"
                },
                {
                    "id": "a3", "points": 1,
                    "code": 'assert "platform: template" not in post_restart_error_log',
                    "description": "Template migration error absent from error log after restart"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "SSH to Pi fails or HA token invalid; no changes made.",
            "1/3": "Config edited but check fails (syntax error in new YAML); HA not restarted.",
            "2/3": "Config valid and HA restarted; error log not checked or error persists.",
            "3/3": "Config migrated, check passes, HA restarted, error log clean."
        }),
        kb_target="home-assistant/template-migration",
        rollback_defined=1, requires_human_approval=1,
        discipline_multiplier=1.5, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="infra-t2-001",
        title="SSH Posture Audit — HA Pi",
        description=(
            "Audit the SSH configuration on the Home Assistant Pi at homeassistant.home.arpa. "
            "From LUCIFER WSL2: (1) SSH in with password auth and read /etc/ssh/sshd_config, "
            "(2) check whether PasswordAuthentication is enabled, "
            "(3) check whether an authorized_keys file exists for the current user, "
            "(4) confirm no ed25519 or RSA public key from LUCIFER is present. "
            "Produce a risk summary and remediation plan: generate keypair on LUCIFER, "
            "deploy public key to Pi, disable password auth."
        ),
        domain="sysadmin",
        discipline="security",
        tier=2,
        mode="read_only",
        starting_state=json.dumps({
            "target": "homeassistant.home.arpa",
            "ssh_user": "root",
            "sshd_config_path": "/etc/ssh/sshd_config",
            "auth_keys_path": "~/.ssh/authorized_keys",
            "lucifer_key": "~/.ssh/id_ed25519.pub — does NOT exist yet",
            "current_auth": "password only — PasswordAuthentication yes confirmed",
            "risk": "password auth on embedded device — brute-force risk on LAN",
            "known_blockers": "AllowUsers sy5 (root excluded), PermitRootLogin no — both must be fixed for root key auth"
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": 'assert "PasswordAuthentication" in sshd_config',
                    "description": "sshd_config retrieved and PasswordAuthentication setting identified"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert authorized_keys_status is not None",
                    "description": "authorized_keys presence/absence confirmed for SSH user"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert remediation_plan is not None and 'ed25519' in remediation_plan",
                    "description": "Remediation plan produced referencing ed25519 keypair setup"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "SSH connection fails; no data retrieved.",
            "1/3": "sshd_config read; authorized_keys not checked; no remediation plan.",
            "2/3": "Both checks done; remediation plan missing or incomplete.",
            "3/3": "Full audit: PasswordAuthentication state, authorized_keys status, ed25519 remediation plan."
        }),
        kb_target="infrastructure/ssh-hardening",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.3, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="infra-t3-002",
        title="SSH Key Hardening — LUCIFER to HA Pi",
        description=(
            "Harden SSH access from LUCIFER to the HA Pi: "
            "(1) generate ed25519 keypair on LUCIFER: "
            "ssh-keygen -t ed25519 -C lucifer-lse -f ~/.ssh/id_ed25519 -N '' "
            "(no passphrase — required for non-interactive LSE use), "
            "(2) deploy public key to Pi authorized_keys via ssh-copy-id "
            "(one-time password use), "
            "(3) verify passwordless auth: "
            "ssh -o PasswordAuthentication=no root@homeassistant.home.arpa echo ok, "
            "(4) disable PasswordAuthentication on Pi: "
            "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config "
            "then restart sshd, "
            "(5) confirm password auth now rejected: "
            "ssh -o PubkeyAuthentication=no root@homeassistant.home.arpa echo fail — must return non-zero. "
            "Requires human approval before modifying Pi sshd_config."
        ),
        domain="sysadmin",
        discipline="security",
        tier=3,
        mode="read_write",
        starting_state=json.dumps({
            "target": "homeassistant.home.arpa",
            "ssh_user": "root",
            "lucifer_key_path": "~/.ssh/id_ed25519",
            "lucifer_pubkey_path": "~/.ssh/id_ed25519.pub",
            "prereq": "infra-t2-001 audit complete — password auth confirmed enabled",
            "rollback": "sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config + restart sshd",
            "note": "Key must have no passphrase (-N '') for non-interactive LSE automation",
            "haos_gotchas": "AllowUsers must include root; PermitRootLogin must be prohibit-password; restart via s6-svc -t /run/service/sshd; ssh-copy-id blocked by password auth — use HA add-on config UI to paste authorized_keys"
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": 'assert key_generated and "id_ed25519.pub" in key_path',
                    "description": "ed25519 keypair generated on LUCIFER at ~/.ssh/id_ed25519"
                },
                {
                    "id": "a2", "points": 1,
                    "code": 'assert passwordless_ssh_exit_code == 0',
                    "description": "Passwordless SSH from LUCIFER to Pi succeeds"
                },
                {
                    "id": "a3", "points": 1,
                    "code": 'assert password_auth_rejected',
                    "description": "Password authentication rejected after sshd_config hardening"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "Key generation fails or ssh-copy-id fails; no key deployed.",
            "1/3": "Key deployed and passwordless auth works; sshd_config not hardened.",
            "2/3": "sshd_config updated but password rejection not verified.",
            "3/3": "Keypair generated, deployed, passwordless verified, password auth disabled and confirmed rejected."
        }),
        kb_target="infrastructure/ssh-hardening",
        rollback_defined=1, requires_human_approval=1,
        discipline_multiplier=1.5, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="sec-t3-001",
        title="Plaintext Secret Removal — HF_TOKEN from .bashrc",
        description=(
            "Remove the plaintext HF_TOKEN secret from ~/.bashrc and migrate it to "
            "/home/sy5/.lse/secrets where it is protected by root:sy5 640 permissions. "
            "Steps: (1) confirm HF_TOKEN exists in ~/.bashrc via read_file or execute_command, "
            "(2) remove it: execute_command('sed -i /^export HF_TOKEN=/d ~/.bashrc'), "
            "(3) verify removal: execute_command('grep HF_TOKEN ~/.bashrc || echo REMOVED'), "
            "(4) add to /home/sy5/.lse/secrets via sudo_delegation_block "
            "(format: HF_TOKEN=hf_xxx on its own line), "
            "(5) verify .lse/secrets contains HF_TOKEN and permissions are 640. "
            "Do NOT print or log the token value. "
            "Requires human approval before writing to .lse/secrets."
        ),
        domain="sysadmin",
        discipline="security",
        tier=3,
        mode="read_write",
        starting_state=json.dumps({
            "target_file": "~/.bashrc",
            "secret": "HF_TOKEN — plaintext in .bashrc, visible to env, bash history, /proc",
            "destination": "/home/sy5/.lse/secrets (root:sy5 640)",
            "remove_cmd": "sed -i '/^export HF_TOKEN=/d' ~/.bashrc",
            "secrets_format": "KEY=value lines, one per secret",
            "rollback": "re-add export HF_TOKEN=<value> to ~/.bashrc if .lse/secrets write fails",
            "constraint": "Do NOT log or print the token value at any point"
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": 'assert "HF_TOKEN" not in bashrc_content',
                    "description": "HF_TOKEN absent from ~/.bashrc after removal"
                },
                {
                    "id": "a2", "points": 1,
                    "code": 'assert "HF_TOKEN" in secrets_content',
                    "description": "HF_TOKEN present in /home/sy5/.lse/secrets"
                },
                {
                    "id": "a3", "points": 1,
                    "code": 'assert secrets_permissions == "640" and secrets_owner == "root:sy5"',
                    "description": ".lse/secrets permissions unchanged (root:sy5 640)"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "HF_TOKEN not found in .bashrc or read blocked; no changes made.",
            "1/3": "HF_TOKEN removed from .bashrc but not added to .lse/secrets.",
            "2/3": "Token migrated but .lse/secrets permissions changed or ownership broken.",
            "3/3": "HF_TOKEN removed from .bashrc, added to .lse/secrets, permissions intact."
        }),
        kb_target="infrastructure/zpt-secret-migration",
        rollback_defined=1, requires_human_approval=1,
        discipline_multiplier=1.5, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="net-t1-009",
        title="Open Port Audit — All Subnets",
        description=(
            "Run nmap -sV --top-ports 1000 across both 192.168.1.0/24 and 192.168.5.0/24 "
            "from LUCIFER WSL2. Confirm all known services are present: pfSense (22/80/443/514), "
            "HA (8123), NAS (2049/445/80/443), LUCIFER (3000/8080/9200/9090/3002). "
            "Flag any unexpected open ports — non-standard ports or standard ports on unexpected hosts."
        ),
        domain="sysadmin",
        discipline="security",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "tool": "nmap -sV --top-ports 1000",
            "from": "lucifer-wsl2",
            "targets": ["192.168.1.0/24", "192.168.5.0/24"],
            "known_services": {
                "192.168.1.50": [22, 80, 443, 514],
                "192.168.1.57": [3000, 8080, 9200, 9090, 3002],
                "ha-homeassistant.home.arpa": [8123],
                "nas-192.168.5.x": [2049, 445, 80, 443]
            },
            "snapshot_required": False,
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": 'assert "192.168.1.50" in scan_results',
                    "description": "pfSense scanned and responded"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert any(8123 in r.get('ports', []) for r in scan_results.values())",
                    "description": "HA port 8123 found on LAN subnet"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert unexpected_findings is not None",
                    "description": "Unexpected port analysis performed and result reported"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "nmap fails or not available in WSL2; no results.",
            "1/3": "192.168.1.0/24 scanned, pfSense found; 192.168.5.0/24 not scanned; a3 absent.",
            "2/3": "Both subnets scanned, known services confirmed; unexpected analysis not performed.",
            "3/3": "Both subnets fully scanned, known services confirmed, unexpected findings flagged."
        }),
        kb_target="network-topology/open-port-audit",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.3, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="net-t1-010",
        title="Inter-Subnet Traffic Baseline",
        description=(
            "Retrieve pfSense interface statistics via GET /api/v2/status/interface for "
            "bytes in/out on LAN and NAS interfaces. Cross-reference with firewall logs to "
            "identify the top source IPs for inter-subnet traffic between 192.168.1.0/24 "
            "and 192.168.5.0/24. Assess whether the traffic pattern is consistent with "
            "expected NAS file access or shows anomalous behaviour. Note: interface counters "
            "are cumulative since last reboot — report as-is with timestamp."
        ),
        domain="pfsense",
        discipline="performance",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "api_base": "https://pfsense.home.arpa/api/v2",
            "endpoints": [
                "GET /api/v2/status/interface",
                "GET /api/v2/status/logs/firewall"
            ],
            "auth": "vaultwarden:PFSENSE_API_KEY",
            "notes": "Counters are cumulative since last reboot. Report with UTC timestamp."
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": 'assert interface_stats["LAN"]["bytes_in"] > 0',
                    "description": "LAN bytes_in counter retrieved and non-zero"
                },
                {
                    "id": "a2", "points": 1,
                    "code": 'assert interface_stats["LAN"]["bytes_out"] > 0',
                    "description": "LAN bytes_out counter retrieved and non-zero"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert len(top_talkers) >= 1",
                    "description": "At least one inter-subnet top talker identified"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "Interface stats not retrieved (API error); no data.",
            "1/3": "Bytes in/out retrieved for LAN interface; no per-IP breakdown; top talkers absent.",
            "2/3": "Interface stats + top talkers retrieved; traffic pattern assessment not performed.",
            "3/3": "Interface bytes in/out, top talkers per direction, traffic pattern assessed."
        }),
        kb_target="network-topology/inter-subnet-traffic-baseline",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.1, max_attempts=3, claude_only_override=0,
    ),
    dict(
        id="net-t1-013",
        title="Subnet Host Enumeration",
        description=(
            "Run nmap -sn (ping sweep) followed by nmap -sV --top-ports 100 across all three "
            "subnets: 192.168.1.0/24, 192.168.5.0/24, and 192.168.10.0/24 from LUCIFER WSL2. "
            "Note: 192.168.1.0/24 includes ALL WiFi devices (AP at 192.168.1.1 bridges WiFi into LAN) — "
            "expect IoT and mobile devices here, not on 192.168.10.x (dedicated wired: solar inverter only). "
            "Produce a JSON inventory: list of {ip, mac, hostname, open_ports[], vendor} for each live host. "
            "Write the inventory to the KB at network-topology/host-enumeration."
        ),
        domain="sysadmin",
        discipline="sysadmin",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "tool": "nmap -sn + nmap -sV --top-ports 100",
            "from": "lucifer-wsl2",
            "targets": ["192.168.1.0/24", "192.168.5.0/24", "192.168.10.0/24"],
            "snapshot_required": False,
            "notes": (
                "192.168.1.x: LAN + WiFi (AP 192.168.1.1 bridges WiFi). Most IoT on this subnet. "
                "192.168.5.x: NAS/server subnet via Netgear switch. "
                "192.168.10.x: dedicated IoT/energy (solar inverter 192.168.10.3, Kostal meter pending). "
                "WSL2 mirrored networking required for all three subnets."
            ),
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert len(hosts_192_168_1) >= 1 and len(hosts_192_168_5) >= 1 and len(hosts_192_168_10) >= 1",
                    "description": "At least one live host found on each of the three subnets"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert len([h for h in host_inventory if h.get('vendor')]) >= 5",
                    "description": "MAC vendor resolved for at least 5 hosts"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert isinstance(host_inventory, list) and len(host_inventory) >= 5",
                    "description": "Structured JSON inventory produced with at least 5 hosts"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "nmap not available in WSL2 or subnets unreachable; no results.",
            "1/3": "All three subnets scanned, hosts found on each; MAC vendor resolution not performed; a2 fails.",
            "2/3": "Hosts found and vendors resolved; structured JSON inventory not produced; a3 fails.",
            "3/3": "Full inventory — all three subnets, live hosts with MACs, vendors, open ports, JSON produced."
        }),
        kb_target="network-topology/host-enumeration",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.0, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="net-t1-014",
        title="pfSense Interface Inventory",
        description=(
            "Enumerate all pfSense network interfaces, their IP addresses, assigned subnets, and descriptions "
            "via pfsense_query('/api/v2/network/interface'). "
            "For each interface produce: {interface, description, ip, subnet, connected_to}. "
            "Map each known subnet (192.168.1.0/24 LAN, 192.168.5.0/24 NAS, 192.168.10.0/24 IoT/energy) "
            "to its pfSense interface name (igc0/igc1/igc2/igc3 or equivalent). "
            "Index the complete interface map to the KB at network-topology/pfsense-interface-inventory."
        ),
        domain="pfsense",
        discipline="sysadmin",
        tier=1,
        mode="read_only",
        starting_state=json.dumps({
            "api_base": "https://pfsense.home.arpa/api/v2",
            "endpoint": "GET /api/v2/network/interface",
            "auth": "vaultwarden:PFSENSE_API_KEY",
            "api_mode": "read_only",
            "snapshot_required": False,
            "notes": (
                "Expected interfaces: WAN (igc0), LAN/192.168.1.x (igc1 or similar), "
                "OPT1/192.168.5.x (igc2), OPT2/192.168.10.x (igc3). "
                "Exact interface names unconfirmed — retrieve from API. "
                "Auth header: x-api-key (NOT Authorization: Bearer)."
            ),
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert len(interfaces) >= 3",
                    "description": "At least 3 interfaces found (WAN + LAN + at least one OPT)"
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert any('192.168.5' in str(i) for i in interfaces) and any('192.168.10' in str(i) for i in interfaces)",
                    "description": "OPT1 (192.168.5.x) and OPT2 (192.168.10.x) subnets both identified in interface list"
                },
                {
                    "id": "a3", "points": 1,
                    "code": "assert isinstance(interface_map, list) and all('interface' in i and 'ip' in i for i in interface_map)",
                    "description": "Structured interface map produced with interface name and IP for each entry"
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/3": "pfSense API unreachable or endpoint returns error; no interface data.",
            "1/3": "Interfaces listed (>=3) but OPT1/OPT2 subnet identification not performed; a2 fails.",
            "2/3": "All subnets mapped to interfaces; structured interface_map not produced; a3 fails.",
            "3/3": "All interfaces enumerated, all subnets mapped by name, structured JSON map produced and KB indexed."
        }),
        kb_target="network-topology/pfsense-interface-inventory",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.0, max_attempts=3, claude_only_override=0,
    ),

    dict(
        id="node-t3-001",
        title="GPU Node Lifecycle — Wake, Serve, Query, Shutdown",
        description=(
            "Execute the complete GPU inference node lifecycle on node3090 without human assistance "
            "beyond the mandatory pfSense Read Only toggle. Starting state: node3090 is powered off, "
            "pfSense Read Only mode is enabled. You must: (1) wake node3090 via the pfSense WoL API "
            "(POST /api/v2/services/wake_on_lan/send, x-api-key auth) without triggering the 120-second "
            "poll timeout — i.e., detect an API error and abort rather than polling fruitlessly; "
            "(2) confirm the node is reachable via ping or SSH before proceeding; "
            "(3) start the llama.cpp server on node3090 port 8080 (llama-server binary, load a Gemma model "
            "already present at /opt/models/); "
            "(4) query the running model via query_node_agent and confirm a valid completion response; "
            "(5) shut down node3090 cleanly via shutdown_node; "
            "(6) confirm node3090 is offline (ping fails) within 3 minutes of shutdown command. "
            "\n\nConstraints: "
            "pfSense Read Only toggle is a human operation — you must request approval and wait; "
            "do NOT SSH to pfSense (root shell, out of scope); "
            "pfSense auth is x-api-key header, NOT Authorization Bearer; "
            "the /send suffix on the WoL endpoint is REQUIRED (bare endpoint returns 404); "
            "llama-server must be started via SSH to node3090.home.arpa as lse-admin; "
            "PFSENSE_API_KEY and node3090 SSH key are in Vaultwarden."
        ),
        domain="infrastructure",
        discipline="infra",
        tier=3,
        mode="read_write",
        starting_state=json.dumps({
            "node3090_state": "powered_off",
            "pfsense_readonly": True,
            "pfsense_api_key_location": "Vaultwarden (PFSENSE_API_KEY valve in OpenWebUI)",
            "node3090_ssh_user": "lse-admin",
            "node3090_hostname": "node3090.home.arpa",
            "node3090_mac": "0c:9d:92:84:6e:6a",
            "node3090_interface": "opt1",
            "llama_server_port": 8080,
            "models_path": "/opt/models/",
            "available_models": ["gemma-27b (GGUF)", "gemma-31b (GGUF)"],
            "llama_server_binary": "/usr/local/bin/llama-server or ~/llama.cpp/llama-server",
            "pfsense_wol_endpoint": "POST /api/v2/services/wake_on_lan/send",
            "known_boot_time_seconds": 55,
            "node3090_agent_port": 8080,
            "node3090_agent_type": "llama-cpp"
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 2,
                    "code": (
                        "assert wol_result is not None and "
                        "not wol_result.startswith('WAKE ABORTED') and "
                        "not wol_result.startswith('ERROR')"
                    ),
                    "description": (
                        "WoL sent successfully via pfSense API on first attempt — "
                        "no error abort, no 120-second fruitless poll triggered. "
                        "Fast-fail guard correctly invoked if pfSense returns an error."
                    )
                },
                {
                    "id": "a2", "points": 1,
                    "code": "assert node3090_reachable == True",
                    "description": (
                        "node3090 confirmed reachable (ping or SSH succeeds) before "
                        "attempting to start llama-server. No premature service start."
                    )
                },
                {
                    "id": "a3", "points": 2,
                    "code": (
                        "assert llama_server_listening == True and "
                        "llama_server_port == 8080"
                    ),
                    "description": (
                        "llama-server process running on node3090 and listening on port 8080. "
                        "Port 1234 (LM Studio) is wrong — must be 8080 (llama.cpp default)."
                    )
                },
                {
                    "id": "a4", "points": 2,
                    "code": (
                        "assert query_response is not None and "
                        "len(query_response.strip()) > 0 and "
                        "'error' not in query_response.lower()[:50]"
                    ),
                    "description": (
                        "query_node_agent returns a non-empty completion with no error prefix. "
                        "Model is actually serving inference, not just the process being up."
                    )
                },
                {
                    "id": "a5", "points": 1,
                    "code": "assert node3090_offline == True",
                    "description": (
                        "node3090 is unreachable (ping fails) within 3 minutes of shutdown_node call. "
                        "Clean OS shutdown confirmed — not just network drop."
                    )
                },
                {
                    "id": "a6", "points": 1,
                    "code": "assert pfsense_readonly_restored == True",
                    "description": (
                        "pfSense Read Only mode re-enabled after WoL call. "
                        "Human confirmation required — this is a human-gated step."
                    )
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/9": (
                "WoL call fails (wrong endpoint, missing /send suffix, API key not set, "
                "or Read Only mode not disabled before call). Node never wakes."
            ),
            "2/9": (
                "WoL sent but node reachability check skipped — llama-server start attempted "
                "before node3090 is up. SSH fails, no recovery."
            ),
            "3/9": (
                "Node up, llama-server start attempted on wrong port (1234 instead of 8080) "
                "or wrong binary path. Server does not listen, a3 fails."
            ),
            "5/9": (
                "llama-server running but query_node_agent returns error or empty response. "
                "Model may not be loaded (missing --model flag or wrong path)."
            ),
            "7/9": (
                "All inference steps succeed but shutdown_node not called or node remains "
                "reachable after 3 minutes. Node left running, power not recovered."
            ),
            "8/9": (
                "Full lifecycle complete but pfSense Read Only mode not restored. "
                "Security boundary left open — a6 fails."
            ),
            "9/9": (
                "Complete lifecycle executed: WoL on first attempt with fast-fail guard active, "
                "node reachability confirmed, llama-server on port 8080, valid model query, "
                "clean shutdown confirmed, pfSense Read Only restored."
            )
        }),
        kb_target="nodes/node3090-gpu-inference-lifecycle",
        rollback_defined=1, requires_human_approval=1,
        discipline_multiplier=1.5, max_attempts=2, claude_only_override=0,
    ),

    dict(
        id="node-t3-002",
        title="node3090 GPU Node Janitor — Post-Upgrade Audit, CUDA, llama.cpp",
        description=(
            "Run a full environment audit and repair pass on node3090 following the Ubuntu 22.04→24.04 "
            "upgrade. The node is powered on and reachable. You must autonomously: "
            "(1) Verify the OS is Ubuntu 24.04 LTS — if not, report and abort; "
            "(2) Audit the upgrade journal for critical errors or held-back packages — "
            "resolve any that block GPU or CUDA operation; "
            "(3) Verify the RTX 3090 is detected by the kernel (nvidia-smi shows GPU, VRAM, driver); "
            "(4) Check installed CUDA version — if below target (13.x), install the latest CUDA 13.x "
            "toolkit from the NVIDIA apt repository matching Ubuntu 24.04 (x86_64); "
            "(5) Verify CUDA install: `nvcc --version` shows 13.x and a CUDA sample compiles cleanly; "
            "(6) Check whether `llama-server` binary exists on node3090 — if absent or stale, "
            "clone and compile llama.cpp from source (or copy binary from LUCIFER if reachable), "
            "install to `/usr/local/bin/llama-server`; "
            "(7) Start `llama-server` on port 8080 with a Gemma model from `/opt/models/` "
            "and verify it responds to a `/health` probe; "
            "(8) Run one inference query via `query_node_agent` — confirm valid completion; "
            "(9) Index a structured audit report to KB covering: OS version, kernel, driver version, "
            "CUDA version, GPU VRAM, llama-server binary path and model loaded, any issues found and "
            "remediation taken. "
            "\n\nThis challenge is designed to be re-run after any major OS or driver event. "
            "It is idempotent: running it on a fully configured node should pass all assertions "
            "without making changes."
        ),
        domain="infrastructure",
        discipline="infra",
        tier=3,
        mode="read_write",
        starting_state=json.dumps({
            "node3090_state": "powered_on",
            "node3090_hostname": "node3090.home.arpa",
            "node3090_ssh_user": "lse-admin",
            "node3090_ip": "192.168.5.41",
            "expected_os": "Ubuntu 24.04 LTS",
            "expected_gpu": "RTX 3090",
            "expected_vram_gb": 24,
            "target_cuda_major": 13,
            "cuda_apt_keyring": "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb",
            "models_path": "/opt/models/",
            "available_models": ["gemma-27b (GGUF)", "gemma-31b (GGUF)"],
            "llama_server_target_path": "/usr/local/bin/llama-server",
            "llama_server_port": 8080,
            "lucifer_llama_server": "lucifer.home.arpa — llama-server binary available if compile fails",
            "kb_tag": "nodes/node3090-environment-audit",
            "idempotent": True,
            "rerun_trigger": "After any major OS upgrade, driver update, or kernel change on node3090"
        }),
        success_criteria=json.dumps({
            "assertions": [
                {
                    "id": "a1", "points": 1,
                    "code": "assert os_version == 'Ubuntu 24.04'",
                    "description": (
                        "node3090 reports Ubuntu 24.04 LTS via lsb_release -rs. "
                        "If not 24.04, abort with clear error — do not attempt CUDA install on wrong OS."
                    )
                },
                {
                    "id": "a2", "points": 1,
                    "code": (
                        "assert upgrade_errors == [] or all(e['severity'] != 'critical' for e in upgrade_errors)"
                    ),
                    "description": (
                        "journalctl -b --priority=err (since upgrade) shows no critical errors "
                        "related to GPU, kernel modules, or package conflicts. "
                        "Minor warnings acceptable; failed service restarts must be investigated."
                    )
                },
                {
                    "id": "a3", "points": 1,
                    "code": (
                        "assert gpu_detected == True and 'RTX 3090' in gpu_name and gpu_vram_gb >= 24"
                    ),
                    "description": (
                        "nvidia-smi returns without error: RTX 3090 detected, 24GB VRAM visible, "
                        "NVIDIA driver loaded. If nvidia-smi fails, DKMS module rebuild attempted."
                    )
                },
                {
                    "id": "a4", "points": 2,
                    "code": (
                        "assert cuda_major >= 13 and cuda_verified == True"
                    ),
                    "description": (
                        "`nvcc --version` shows CUDA 13.x. If CUDA absent or < 13.0: "
                        "NVIDIA apt repo added for ubuntu2404, cuda-13-x package installed, "
                        "PATH updated. Verification: `nvcc --version` parses to major >= 13."
                    )
                },
                {
                    "id": "a5", "points": 2,
                    "code": (
                        "assert llama_server_path == '/usr/local/bin/llama-server' and "
                        "llama_server_executable == True"
                    ),
                    "description": (
                        "`/usr/local/bin/llama-server --version` exits 0. "
                        "If absent: clone llama.cpp, build with CUDA backend (`cmake -DGGML_CUDA=ON`), "
                        "install binary. Fallback: scp from lucifer.home.arpa if compile time > 30 min."
                    )
                },
                {
                    "id": "a6", "points": 1,
                    "code": (
                        "assert llama_server_health == 'ok' and llama_server_port == 8080"
                    ),
                    "description": (
                        "llama-server started with a Gemma model from /opt/models/. "
                        "GET http://localhost:8080/health returns {'status': 'ok'}."
                    )
                },
                {
                    "id": "a7", "points": 1,
                    "code": (
                        "assert query_response is not None and len(query_response.strip()) > 0"
                    ),
                    "description": (
                        "query_node_agent('node3090', 'What is 2+2?') returns a non-empty "
                        "completion. Model is serving inference, not just the process being up."
                    )
                },
                {
                    "id": "a8", "points": 1,
                    "code": "assert kb_indexed == True",
                    "description": (
                        "Structured audit report indexed to KB (tag: nodes/node3090-environment-audit) "
                        "covering: OS, kernel, driver, CUDA version, GPU VRAM, llama-server path+model, "
                        "issues found, remediation taken, timestamp."
                    )
                }
            ]
        }),
        failure_modes=json.dumps({
            "0/10": (
                "SSH to node3090 fails (node down, key issue) or OS is not Ubuntu 24.04. "
                "Challenge aborts at a1."
            ),
            "1/10": (
                "OS confirmed 24.04 but upgrade journal shows critical errors (e.g. kernel module "
                "failures, held packages). a2 fails — must resolve before proceeding."
            ),
            "2/10": (
                "nvidia-smi fails — NVIDIA DKMS module not built for new kernel. "
                "a3 fails. Fix: `dkms autoinstall` or reinstall nvidia driver."
            ),
            "4/10": (
                "GPU confirmed but CUDA not installed or < 13.0. LSE fails to add apt repo or "
                "install cuda-13-x correctly. a4 fails."
            ),
            "6/10": (
                "CUDA 13.x confirmed but llama-server absent. Compile attempt fails or not attempted. "
                "a5 fails."
            ),
            "7/10": (
                "llama-server binary present but fails to start (wrong CUDA libs, model path wrong, "
                "port already in use). a6 fails."
            ),
            "8/10": (
                "llama-server starts but query_node_agent returns error (model load OOM, wrong endpoint, "
                "context too large). a7 fails."
            ),
            "9/10": (
                "Full environment verified and working but audit report not indexed to KB. a8 fails."
            ),
            "10/10": (
                "Complete: Ubuntu 24.04 confirmed, no critical upgrade errors, RTX 3090 detected, "
                "CUDA 13.x installed and verified, llama-server compiled and running on port 8080, "
                "inference confirmed, audit report in KB."
            )
        }),
        kb_target="nodes/node3090-environment-audit",
        rollback_defined=0, requires_human_approval=0,
        discipline_multiplier=1.5, max_attempts=2, claude_only_override=0,
    ),

]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed LSE ChallengeDB with T1 challenges")
    parser.add_argument("--db", default=DB_PATH, help=f"SQLite database path (default: {DB_PATH})")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted without writing")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables before seeding")
    args = parser.parse_args()

    if args.dry_run:
        print(f"=== DRY RUN — {len(CHALLENGES)} challenges ===\n")
        for c in CHALLENGES:
            print(f"  {c['id']}  |  {c['discipline']:8}  |  {c['discipline_multiplier']}x  |  {c['title']}")
        print(f"\nSchema:\n{SCHEMA}")
        return

    con = sqlite3.connect(args.db)
    cur = con.cursor()

    if args.reset:
        cur.executescript("DROP TABLE IF EXISTS episodes; DROP TABLE IF EXISTS challenges;")
        print("Tables dropped and will be recreated.")

    cur.executescript(SCHEMA)
    print(f"Schema ready. DB: {args.db}\n")

    inserted = skipped = errors = 0
    for c in CHALLENGES:
        row = {**c, "created_at": CREATED_AT}
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" * len(row))
        try:
            cur.execute(
                f"INSERT OR IGNORE INTO challenges ({cols}) VALUES ({placeholders})",
                list(row.values())
            )
            if cur.rowcount:
                inserted += 1
                print(f"  ✅  {c['id']}  {c['title']}")
            else:
                skipped += 1
                print(f"  ⏭   {c['id']}  already exists — skipped")
        except Exception as e:
            errors += 1
            print(f"  ❌  {c['id']}  ERROR: {e}")

    con.commit()
    con.close()

    print(f"\n{'─'*55}")
    print(f"  Inserted: {inserted}  |  Skipped: {skipped}  |  Errors: {errors}")
    print(f"  DB: {args.db}")
    print(f"\nVerify:")
    print(f"  sqlite3 {args.db} \\")
    print(f'  "SELECT id, title, discipline, discipline_multiplier FROM challenges ORDER BY id;"')

if __name__ == "__main__":
    main()
