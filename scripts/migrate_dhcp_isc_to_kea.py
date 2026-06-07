#!/usr/bin/env python3
"""
migrate_dhcp_isc_to_kea.py — pfSense ISC DHCP → Kea DHCP reservation migrator

Usage:
  python3 scripts/migrate_dhcp_isc_to_kea.py --export
      Write dhcp_reservations.json from embedded KB data (32 mappings, 3 interfaces)

  python3 scripts/migrate_dhcp_isc_to_kea.py --discover
      Probe pfSense REST API for Kea/DHCP endpoint paths (run after backend switch)

  python3 scripts/migrate_dhcp_isc_to_kea.py --apply [--interface LAN|OPT1|OPT2] [--dry-run]
      POST reservations to Kea DHCP API
      --interface OPT1   staged migration (OPT1 first)
      --dry-run          print payloads without touching pfSense

Env vars:
  PFSENSE_API_KEY   pfSense REST API key (Vaultwarden: LSE-pfsense_API_key → password)

pfSense interface ID notes (CONFIRMED 2026-06-07):
  LAN  → API id: lan
  OPT1 → API id: opt4   !! NOT opt1 — display name ≠ API id !!
  OPT2 → API id: opt2

Non-DHCP devices (static ARP entries, NOT migrated):
  192.168.1.1  GT-BE19000  (router gateway — not a DHCP client)
  192.168.5.2  netgear     (dumb switch — static ARP, no DHCP)
  192.168.10.2 ksem        (Kostal meter — static ARP, no DHCP)
"""

import argparse
import json
import os
import re
import sys

import requests
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
PFSENSE_BASE      = "https://pfsense.home.arpa/api/v2"
API_KEY_ENV       = "PFSENSE_API_KEY"
TLS_VERIFY        = False
RESERVATIONS_FILE = os.path.join(os.path.dirname(__file__), "dhcp_reservations.json")

# Confirm via --discover after switching backend to Kea.
# Will be 404 while ISC DHCP is active — activates post-migration.
KEA_RESERVATION_ENDPOINT = "/services/dhcp_server/static_mapping"

# ── Embedded reservation data ─────────────────────────────────────────────────
# 32 DHCP static mappings confirmed via live pfSense API (2026-06-07).
# Excludes 3 static ARP entries: GT-BE19000 (1.1), netgear (5.2), ksem (10.2).
# pfsense_interface = pfSense REST API id (opt4 for OPT1, NOT opt1).
KB_DATA = {
    "exported_at": "2026-06-07",
    "source": "pfSense REST API live export (P17 Cowork session)",
    "interfaces": {
        "LAN": {
            "subnet": "192.168.1.0/24",
            "pfsense_interface": "lan",
            "reservations": [
                {"mac": "d8:3a:dd:0e:1c:38", "ip": "192.168.1.5",   "hostname": "sy5berry",            "descr": "PiHole DNS server"},
                {"mac": "a0:ad:9f:84:d5:bf", "ip": "192.168.1.55",  "hostname": "1BL15",               "descr": "NODE1 / node5090"},
                {"mac": "58:11:22:bf:80:02", "ip": "192.168.1.57",  "hostname": "LUCIFER",             "descr": "ROG MAXIMUS Z790 APEX 14900K 64GB 4090"},
                {"mac": "00:17:88:62:58:bc", "ip": "192.168.1.65",  "hostname": "philipshue",          "descr": "Philips Hue"},
                {"mac": "b0:4a:39:4f:c8:39", "ip": "192.168.1.70",  "hostname": "roborock-vacuum-a70", "descr": "Roborock Vacuum"},
                {"mac": "cc:44:63:e8:00:3d", "ip": "192.168.1.75",  "hostname": "ipad",                "descr": "iPad Pro 12.9 inch"},
                {"mac": "36:89:34:c5:0e:57", "ip": "192.168.1.76",  "hostname": "fedeiphone",          "descr": "Fede iPhone"},
                {"mac": "d8:3a:dd:2e:fc:1b", "ip": "192.168.1.80",  "hostname": "homeassistant",       "descr": "Home Assistant Supervised OS"},
                {"mac": "b8:13:32:8e:07:aa", "ip": "192.168.1.88",  "hostname": "x1",                  "descr": "Bambu Lab X1 Carbon (WiFi X)"},
                {"mac": "1c:af:4a:04:5f:b6", "ip": "192.168.1.90",  "hostname": "samsungtv",           "descr": "Samsung S90C"},
                {"mac": "f8:b9:5a:ec:e1:d0", "ip": "192.168.1.95",  "hostname": "lgtv",                "descr": "LG OLED55CX"},
                {"mac": "d8:3a:dd:2e:fc:1c", "ip": "192.168.1.115", "hostname": "spider",              "descr": "Spider Robot"},
                {"mac": "02:42:c0:a8:01:7d", "ip": "192.168.1.125", "hostname": "homebridge",          "descr": "Homebridge docker"},
                {"mac": "00:09:b0:13:ae:ab", "ip": "192.168.1.210", "hostname": "p10w",                "descr": "Pioneer AV receiver (WiFi)"},
                {"mac": "00:09:b0:4f:69:8d", "ip": "192.168.1.211", "hostname": "p10",                 "descr": "Pioneer AV receiver (Ethernet)"},
                {"mac": "d8:44:89:4b:ef:34", "ip": "192.168.1.220", "hostname": "P100",                "descr": "JVC Subwoofer Smart Plug"},
                {"mac": "d8:44:89:4b:ef:32", "ip": "192.168.1.221", "hostname": "P100tvsam",           "descr": "Samsung TV plug"},
                {"mac": "d4:ad:fc:93:52:9c", "ip": "192.168.1.222", "hostname": "goveeledstrip01",     "descr": "Govee LED strip"},
            ]
        },
        "OPT1": {
            "subnet": "192.168.5.0/24",
            "pfsense_interface": "opt4",   # pfSense API id for OPT1 display name
            "reservations": [
                {"mac": "00:1e:42:61:75:c0", "ip": "192.168.5.3",   "hostname": "teltonika",        "descr": "Teltonika RUTX50"},
                {"mac": "b8:13:32:8e:07:aa", "ip": "192.168.5.6",   "hostname": "x1Carbon",         "descr": "Bambu Lab X1 Carbon (WiFi Z)"},
                {"mac": "0c:9d:92:84:6e:6a", "ip": "192.168.5.41",  "hostname": "node3090",         "descr": "NODE3 Ubuntu 22.04 3090"},
                {"mac": "00:08:9b:cd:1c:43", "ip": "192.168.5.44",  "hostname": "n45",              "descr": "QNAP TS-419P II (NIC 1)"},
                {"mac": "00:08:9b:cd:1c:42", "ip": "192.168.5.45",  "hostname": "n45",              "descr": "QNAP TS-419P II (NIC 2)"},
                {"mac": "64:e2:20:1f:d4:80", "ip": "192.168.5.55",  "hostname": "mercedes",         "descr": "Mercedes C Class W206"},
                {"mac": "da:41:bd:bd:d4:34", "ip": "192.168.5.75",  "hostname": "ipad",             "descr": "iPad Pro 12.9 inch (Z WiFi)"},
                {"mac": "10:2c:b1:13:8d:22", "ip": "192.168.5.88",  "hostname": "roofTop",          "descr": "Eufy security camera"},
                {"mac": "d8:44:89:4b:f0:76", "ip": "192.168.5.95",  "hostname": "x1plug",           "descr": "Smart Plug (X1 Carbon)"},
                {"mac": "c4:5b:be:81:33:c4", "ip": "192.168.5.100", "hostname": "goechargerhouse",  "descr": "go-eCharger HOUSE"},
                {"mac": "e0:e2:e6:7e:a0:64", "ip": "192.168.5.101", "hostname": "goechargershed",   "descr": "go-eCharger SHED"},
                {"mac": "c8:60:00:02:13:ed", "ip": "192.168.5.155", "hostname": "developer",        "descr": "1080Ti dev machine"},
                {"mac": "84:2a:fd:a5:46:e9", "ip": "192.168.5.205", "hostname": "hp",               "descr": "HP Laserjet M118"},
            ]
        },
        "OPT2": {
            "subnet": "192.168.10.0/24",
            "pfsense_interface": "opt2",
            # NOTE: ksem (10.2) is a static ARP entry — NOT a DHCP reservation.
            # Only helios (10.3) has a DHCP static mapping.
            "reservations": [
                {"mac": "a4:06:e9:25:ae:3a", "ip": "192.168.10.3", "hostname": "helios", "descr": "Kostal Solar Power Inverter"},
            ]
        }
    }
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_api_key():
    key = os.environ.get(API_KEY_ENV)
    if not key:
        sys.exit(f"ERROR: {API_KEY_ENV} not set.\n"
                 f"       export {API_KEY_ENV}=<key>   "
                 f"(Vaultwarden: LSE-pfsense_API_key → password field)")
    return key

def api_get(path, params, api_key):
    return requests.get(
        f"{PFSENSE_BASE}{path}",
        headers={"x-api-key": api_key},
        params=params,
        verify=TLS_VERIFY, timeout=10
    )

def api_post(path, body, api_key):
    return requests.post(
        f"{PFSENSE_BASE}{path}",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json=body, verify=TLS_VERIFY, timeout=10
    )

# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_export():
    with open(RESERVATIONS_FILE, "w") as f:
        json.dump(KB_DATA, f, indent=2)
    total = sum(len(v["reservations"]) for v in KB_DATA["interfaces"].values())
    print(f"Wrote {total} reservations → {RESERVATIONS_FILE}")
    for iface, data in KB_DATA["interfaces"].items():
        pf = data["pfsense_interface"]
        print(f"  {iface:6} (pf_id={pf:5}, {data['subnet']:18}): "
              f"{len(data['reservations'])} reservations")


def cmd_discover():
    """Find live Kea endpoints — run this AFTER switching backend to Kea."""
    api_key = get_api_key()
    print(f"Fetching OpenAPI spec from {PFSENSE_BASE}/schema/openapi.json ...")
    r = api_get("/schema/openapi.json", {}, api_key)
    if r.status_code == 200:
        try:
            spec = r.json()
            matches = [
                (p, sorted(spec["paths"][p].keys()))
                for p in spec.get("paths", {})
                if re.search(r"kea|reservation|dhcp|arp|lease", p, re.I)
            ]
            if matches:
                print(f"Found {len(matches)} relevant paths:")
                for p, methods in sorted(matches):
                    print(f"  {str(methods):30}  {p}")
            return
        except Exception as e:
            print(f"  Spec parse error: {e}")
    else:
        print(f"  Spec endpoint → HTTP {r.status_code}")

    print("\nCandidate endpoint probe (404 = Kea not yet active):")
    candidates = [
        "/services/kea_dhcp4/reservation",
        "/services/kea_dhcp4/lease",
        "/services/kea_dhcp/reservation",
        "/services/dhcp_server/static_mapping",
        "/diagnostics/arp_table",
    ]
    for c in candidates:
        rc = api_get(c, {}, api_key)
        mark = "✓" if rc.status_code < 400 else "✗"
        print(f"  {mark} {rc.status_code}  {c}")


def cmd_apply(interface_filter, dry_run):
    if not os.path.exists(RESERVATIONS_FILE):
        sys.exit(f"ERROR: {RESERVATIONS_FILE} not found. Run --export first.")

    api_key = get_api_key() if not dry_run else "dry-run"

    with open(RESERVATIONS_FILE) as f:
        data = json.load(f)

    prefix = "[DRY RUN] " if dry_run else ""
    ok = err = skipped = 0

    for iface, idata in data["interfaces"].items():
        if interface_filter and iface != interface_filter.upper():
            skipped += len(idata["reservations"])
            continue

        pf_iface = idata["pfsense_interface"]
        count    = len(idata["reservations"])
        print(f"\n{prefix}── {iface} (pf={pf_iface}, {idata['subnet']}) — {count} reservations ──")

        for res in idata["reservations"]:
            body = {
                "mac":       res["mac"],
                "ipaddr":    res["ip"],
                "hostname":  res["hostname"],
                "descr":     res["descr"],
                "parent_id": pf_iface,
            }
            if dry_run:
                print(f"  POST {KEA_RESERVATION_ENDPOINT}  {res['ip']:18}  "
                      f"{res['mac']}  {res['hostname']}")
                ok += 1
                continue

            resp = api_post(KEA_RESERVATION_ENDPOINT, body, api_key)
            if resp.status_code in (200, 201):
                print(f"  ✓ {resp.status_code}  {res['ip']:18}  {res['hostname']}")
                ok += 1
            else:
                print(f"  ✗ {resp.status_code}  {res['ip']:18}  {res['hostname']}")
                print(f"    {resp.text[:200]}")
                err += 1

    print(f"\n{'='*55}")
    print(f"Result: {ok} ok  |  {err} errors  |  {skipped} skipped (filtered)")
    if err:
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="pfSense ISC DHCP → Kea DHCP reservation migrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    ap.add_argument("--export",    action="store_true",
                    help="Write dhcp_reservations.json from embedded data")
    ap.add_argument("--discover",  action="store_true",
                    help="Probe pfSense API for Kea endpoint paths")
    ap.add_argument("--apply",     action="store_true",
                    help="POST reservations to Kea API (run after backend switch)")
    ap.add_argument("--interface", choices=["LAN", "OPT1", "OPT2"], metavar="IFACE",
                    help="--apply: restrict to one interface")
    ap.add_argument("--dry-run",   action="store_true",
                    help="--apply: print payloads without sending")
    args = ap.parse_args()

    if args.export:
        cmd_export()
    elif args.discover:
        cmd_discover()
    elif args.apply:
        cmd_apply(args.interface, args.dry_run)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
