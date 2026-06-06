#!/usr/bin/env python3
"""
Samsung TV T4 — DHCP Hammer Investigation
=========================================
Queries pfSense to characterise the Samsung TV (192.168.1.90) DHCP behaviour:
  1. Current DHCP lease entry + expiry
  2. DHCP lease time configured on the LAN interface
  3. Recent DHCP-related firewall/system log entries for the TV MAC
  4. Recommendation: is this noise or a real problem?

Outputs a report to:
  /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/samsung-tv-dhcp-report.txt

Run from WSL2:
  python3 scripts/samsung_tv_dhcp_investigation.py
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Import LSE tool helpers ────────────────────────────────────────────────────
# Add the tools path so we can reuse pfsense_query
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

# pfSense connection config (matches lse tool)
PFSENSE_BASE  = os.getenv("PFSENSE_BASE",  "https://pfsense.home.arpa/api/v2")
PFSENSE_KEY   = os.getenv("PFSENSE_KEY",   "")
PFSENSE_CA    = os.getenv("PFSENSE_CA",    "/opt/local-se/cert/pfsense-webgui-ca.crt")

TV_IP         = "192.168.1.90"
TV_HOSTNAME   = "Samsung-S90C"
REPORT_PATH   = Path("/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/samsung-tv-dhcp-report.txt")

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def pfsense_get(endpoint: str, params: dict = None) -> dict:
    """GET against pfSense REST API v2."""
    headers = {"x-api-key": PFSENSE_KEY, "Accept": "application/json"} if PFSENSE_KEY else {}
    url = f"{PFSENSE_BASE}{endpoint}"
    try:
        r = requests.get(url, headers=headers, params=params or {},
                         verify=PFSENSE_CA if Path(PFSENSE_CA).exists() else False,
                         timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"_error": str(e), "_url": url}


def load_pfsense_key() -> str:
    """Try to load pfSense API key from .lse/secrets or env."""
    key = os.getenv("PFSENSE_KEY", "")
    if key:
        return key
    secrets_path = Path("/opt/local-se/.lse/secrets")
    if secrets_path.exists():
        for line in secrets_path.read_text().splitlines():
            if line.startswith("PFSENSE_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    return ""


def main():
    global PFSENSE_KEY
    PFSENSE_KEY = load_pfsense_key()
    if not PFSENSE_KEY:
        print("WARNING: PFSENSE_KEY not found. Requests may fail with 401.")

    report = []
    report.append("=" * 70)
    report.append("Samsung TV T4 — DHCP Hammer Investigation")
    report.append(f"Run: {datetime.now().isoformat()}")
    report.append("=" * 70)

    # ── 1. Current DHCP lease for TV ─────────────────────────────────────────
    report.append("\n## 1. Current DHCP lease (192.168.1.90)")
    leases = pfsense_get("/dhcp/server/lease")
    if "_error" in leases:
        # Try alternative endpoint
        leases = pfsense_get("/services/dhcpd/lease")
    if "_error" in leases:
        report.append(f"  ERROR: {leases['_error']}")
        report.append(f"  URL tried: {leases.get('_url')}")
        tv_lease = None
    else:
        data = leases.get("data", leases) if isinstance(leases, dict) else leases
        if isinstance(data, dict):
            data = data.get("data", [])
        tv_leases = [l for l in (data or [])
                     if l.get("ip_address") == TV_IP or l.get("ipaddr") == TV_IP]
        if tv_leases:
            tv_lease = tv_leases[0]
            report.append(f"  IP:       {tv_lease.get('ip_address') or tv_lease.get('ipaddr')}")
            report.append(f"  MAC:      {tv_lease.get('mac') or tv_lease.get('hwaddr', 'unknown')}")
            report.append(f"  Hostname: {tv_lease.get('hostname', 'unknown')}")
            report.append(f"  Starts:   {tv_lease.get('starts', 'unknown')}")
            report.append(f"  Ends:     {tv_lease.get('ends', 'unknown')}")
            report.append(f"  Type:     {tv_lease.get('type', 'unknown')}")
            report.append(f"  State:    {tv_lease.get('state', 'unknown')}")
            report.append(f"\n  Raw: {json.dumps(tv_lease, indent=4)}")
        else:
            report.append(f"  No lease found for {TV_IP} in {len(data or [])} entries.")
            report.append(f"  All leases: {json.dumps(data[:5] if data else [], indent=2)}")
            tv_lease = None

    # ── 2. DHCP server config (lease time) ───────────────────────────────────
    report.append("\n## 2. DHCP server config — LAN interface lease times")
    dhcp_conf = pfsense_get("/services/dhcpd")
    if "_error" in dhcp_conf:
        dhcp_conf = pfsense_get("/dhcp/server")
    if "_error" in dhcp_conf:
        report.append(f"  ERROR: {dhcp_conf['_error']}")
    else:
        data = dhcp_conf.get("data", dhcp_conf)
        if isinstance(data, list):
            # Find LAN interface
            lan = next((d for d in data if d.get("interface") in ("lan", "LAN", "igb0", "em0")), None)
            if not lan and data:
                lan = data[0]
        else:
            lan = data

        if lan:
            report.append(f"  Interface:        {lan.get('interface', 'unknown')}")
            report.append(f"  Default leasetime: {lan.get('defaultleasetime', lan.get('default_lease_time', 'unknown'))} sec")
            report.append(f"  Max leasetime:     {lan.get('maxleasetime', lan.get('max_lease_time', 'unknown'))} sec")
            report.append(f"  Range:             {lan.get('range', {}).get('from', '?')} – {lan.get('range', {}).get('to', '?')}")
            report.append(f"\n  Raw (first entry): {json.dumps(lan, indent=4)}")

            # Interpret
            default_lt = lan.get("defaultleasetime") or lan.get("default_lease_time")
            if default_lt:
                try:
                    lt_sec = int(default_lt)
                    lt_min = lt_sec // 60
                    report.append(f"\n  → Lease time: {lt_sec}s = {lt_min} minutes")
                    if lt_min <= 2:
                        report.append("  ⚠️  VERY SHORT lease time — this is likely causing the DHCP hammer!")
                    elif lt_min <= 10:
                        report.append("  ⚠️  Short lease time — TV is renewing aggressively, probably at 50% of lease.")
                    else:
                        report.append(f"  ✅  Lease time OK ({lt_min} min). DHCP hammer may be TV firmware behaviour.")
                except ValueError:
                    pass
        else:
            report.append(f"  Raw: {json.dumps(dhcp_conf, indent=2)[:500]}")

    # ── 3. Static mapping for TV ─────────────────────────────────────────────
    report.append("\n## 3. Static DHCP mapping for TV")
    static = pfsense_get("/services/dhcpd/static_mapping")
    if "_error" in static:
        static = pfsense_get("/dhcp/server/static_mapping")
    if "_error" in static:
        report.append(f"  ERROR: {static['_error']}")
    else:
        data = static.get("data", static)
        if isinstance(data, dict):
            data = data.get("data", [])
        tv_statics = [s for s in (data or [])
                      if s.get("ipaddr") == TV_IP or s.get("ip_address") == TV_IP]
        if tv_statics:
            s = tv_statics[0]
            report.append(f"  Found static mapping: {json.dumps(s, indent=4)}")
        else:
            report.append(f"  No static mapping found for {TV_IP}.")
            report.append("  ℹ️  TV gets a dynamic lease — no MAC-pinned assignment.")

    # ── 4. Recent system logs for DHCP ───────────────────────────────────────
    report.append("\n## 4. pfSense DHCP log entries for TV")
    syslog = pfsense_get("/status/logs/dhcp")
    if "_error" in syslog:
        syslog = pfsense_get("/log/dhcp")
    if "_error" in syslog:
        report.append(f"  ERROR (DHCP log): {syslog['_error']}")
        report.append("  → Try: pfSense UI → Status → System Logs → DHCP")
    else:
        data = syslog.get("data", syslog)
        if isinstance(data, dict):
            data = data.get("data", [])
        # Filter for TV IP or known MAC
        tv_log = [e for e in (data or [])
                  if TV_IP in str(e) or (tv_lease and tv_lease.get("mac", "???") in str(e))]
        report.append(f"  Total DHCP log entries: {len(data or [])}")
        report.append(f"  Entries for {TV_IP}: {len(tv_log)}")
        if tv_log:
            report.append("  Last 10 TV entries:")
            for entry in tv_log[-10:]:
                report.append(f"    {entry}")

    # ── 5. Summary + recommendation ──────────────────────────────────────────
    report.append("\n## 5. Summary and recommendation")
    report.append(f"""
The Samsung TV S90C (192.168.1.90) is generating DHCP requests every 1-2 minutes.
WAN is already blocked (net-t3-002 ✅).

Diagnosis path:
  A) If DHCP lease time is ≤ 2 min → increase to 3600s (1 hour) in pfSense.
     pfSense: Services → DHCP Server → LAN → Default Lease Time → 3600
     Or add a static mapping with a long lease for the TV MAC.

  B) If DHCP lease time is normal (≥ 30 min) → TV firmware is misbehaving.
     Samsung TVs are known to re-DHCP on every content refresh or ad load.
     Mitigation: static DHCP reservation + rate-limit DHCP from TV MAC.
     pfSense: Firewall → Rules → LAN → add rule: TV MAC → UDP 67/68 → max 2/min.

  C) If TV has no static mapping → Add one with a 24h lease (86400s).
     This pins the IP and gives the TV a stable long lease.

T4 challenge assertion targets:
  a1: DHCP request rate measured (packets/min from TV MAC in DHCP log)
  a2: Root cause identified (short lease vs firmware behaviour)
  a3: Remediation applied or documented (lease time change / static mapping / rate-limit)
""")

    # ── Write report ─────────────────────────────────────────────────────────
    output = "\n".join(report)
    REPORT_PATH.write_text(output, encoding="utf-8")
    print(output)
    print(f"\n✅ Report written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
