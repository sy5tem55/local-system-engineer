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
            "api_base": "https://192.168.1.50/api/v2",
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
            "api_base": "https://192.168.1.50/api/v2",
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
            "api_base": "https://192.168.1.50/api/v2",
            "endpoints": [
                "GET /api/v2/services/unbound/host_override",
                "GET /api/v2/services/unbound/domain_override"
            ],
            "ssh_fallback": "ssh admin@192.168.1.50 'cat /cf/conf/config.xml'",
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
            "api_base": "https://192.168.1.50/api/v2",
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
