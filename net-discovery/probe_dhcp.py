"""
probe_dhcp.py — L1 Base probe
Queries pfSense REST API for DHCP static mappings and ARP table across all
active subnets. Populates snapshot devices with MAC, IP, hostname, interface,
and lease metadata.

pfSense API endpoints used (confirmed working on pfSense Plus 26.03.1):

  GET /api/v2/services/dhcp_server/static_mapping?parent_id=<iface>&id=<n>
      ISC DHCP static mappings. Iterate child id 1..N until 404.
      Known parent_ids with DHCP servers: lan, opt2, opt3, opt4, opt6
      !! pfSense display name ≠ API id — see PFSENSE_DHCP_IFACES below !!

  GET /api/v2/diagnostics/arp_table
      Live ARP cache (MAC + IP + interface). Catches dynamic DHCP clients
      and any device not in static mappings.

Auth: x-api-key header (NOT Authorization: Bearer)
"""

import os
import logging
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List

log = logging.getLogger(__name__)

# ── Interface ID mappings ─────────────────────────────────────────────────────
# pfSense API uses internal IDs that differ from the Web UI display names.
# CONFIRMED 2026-06-07: OPT1 display name = opt4 API id (NOT opt1).
# Order determines probe sequence — process larger subnets first.
PFSENSE_DHCP_IFACES = ["lan", "opt4", "opt2", "opt3", "opt6"]

# Map pfSense API interface id → config.json subnet interface name.
# Needed to correlate API data with config["subnets"][].interface values.
PFSENSE_TO_CONFIG_IFACE = {
    "lan":  "lan",
    "opt4": "opt1",    # Web UI: OPT1 (192.168.5.0/24) — API calls it opt4
    "opt2": "opt2",    # Web UI: OPT2 (192.168.10.0/24)
    "opt3": "opt3",    # Web UI: WLAN — not yet in config.json
    "opt6": "igc1.55", # Web UI: IoT VLAN 55 — inactive in config.json
}

# Max static mapping IDs to scan per interface before giving up.
# LAN has 18, OPT1 has 13. 50 gives headroom for growth without runaway loops.
_MAX_STATIC_MAPPING_ID = 50


def _pfsense_get(base_url: str, path: str, params: dict,
                 api_key: str, tls_verify: bool) -> Any:
    """Single pfSense REST GET with query params. Returns parsed body or raises."""
    url = f"{base_url}{path}"
    headers = {"X-API-Key": api_key}
    r = requests.get(url, headers=headers, params=params,
                     verify=tls_verify, timeout=(5, 10))
    if r.status_code == 404:
        return None  # Sentinel: resource not found (end of iteration)
    r.raise_for_status()
    body = r.json()
    if "data" not in body:
        raise ValueError(f"Unexpected response from {path}: {list(body.keys())}")
    return body["data"]


def _normalize_mac(mac: str) -> str:
    """Lowercase colon-separated MAC. Handles various input formats."""
    mac = mac.strip().lower().replace("-", ":").replace(".", ":")
    if len(mac) == 12 and ":" not in mac:
        mac = ":".join(mac[i:i+2] for i in range(0, 12, 2))
    return mac


def _fetch_static_mappings(base_url: str, api_key: str,
                           tls_verify: bool) -> List[Dict]:
    """
    Iterate /services/dhcp_server/static_mapping for all known DHCP interfaces.
    Returns list of dicts, each with a '_pf_iface' key added for interface tracking.
    Stops per-interface iteration on first 404 (IDs are sequential from 1).
    """
    results = []
    for pf_iface in PFSENSE_DHCP_IFACES:
        count = 0
        for child_id in range(1, _MAX_STATIC_MAPPING_ID + 1):
            try:
                data = _pfsense_get(
                    base_url,
                    "/services/dhcp_server/static_mapping",
                    {"parent_id": pf_iface, "id": child_id},
                    api_key, tls_verify
                )
            except Exception as e:
                log.warning(f"probe_dhcp: static_mapping {pf_iface}/{child_id}: {e}")
                break
            if data is None:  # 404 — no more mappings for this interface
                break
            data["_pf_iface"] = pf_iface
            results.append(data)
            count += 1
        if count:
            log.debug(f"probe_dhcp: {pf_iface} → {count} static mappings")
    return results


def _subnet_for_interface(pf_iface: str, subnet_map: Dict[str, str]) -> str | None:
    """Map pfSense API interface id to CIDR via config.json subnet map."""
    config_iface = PFSENSE_TO_CONFIG_IFACE.get(pf_iface, pf_iface)
    return subnet_map.get(config_iface)


def run(config: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    """
    Entry point called by discovery_engine.py.
    Mutates snapshot['devices'] in place.
    """
    gw = config["gateway"]
    base_url = gw["base_url"]
    api_key  = os.environ.get(gw["api_key_env"], "")
    tls_verify = gw.get("tls_verify", True)

    if not api_key:
        raise EnvironmentError(f"Environment variable {gw['api_key_env']} is not set")

    # Build config interface → CIDR map from active subnets
    subnet_map = {
        s["interface"]: s["cidr"]
        for s in config["subnets"]
        if s.get("active", True)
    }

    devices = snapshot.setdefault("devices", {})

    # ── DHCP Static Mappings ──────────────────────────────────────────────────
    log.info("probe_dhcp: fetching static mappings")
    try:
        mappings = _fetch_static_mappings(base_url, api_key, tls_verify)
        log.info(f"probe_dhcp: got {len(mappings)} static mappings across all interfaces")

        for m in mappings:
            # pfSense REST API v2 field names for static_mapping resource
            mac = m.get("mac") or m.get("mac_addr") or m.get("macaddr") or ""
            if not mac:
                continue
            mac = _normalize_mac(mac)

            ip       = m.get("ipaddr") or m.get("ip_addr") or m.get("ip") or None
            hostname = m.get("hostname") or m.get("host") or None
            descr    = m.get("descr") or m.get("description") or ""
            pf_iface = m.get("_pf_iface", "")

            dev = devices.setdefault(mac, {
                "mac": mac, "status": "unknown", "source": [], "labels": [],
                "dhcp": None, "wifi": None, "icmp": None, "mdns": None
            })

            if ip:
                dev["ip"] = ip
            if hostname and not dev.get("hostname"):
                dev["hostname"] = hostname
            if descr and not dev.get("description"):
                dev["description"] = descr

            config_iface = PFSENSE_TO_CONFIG_IFACE.get(pf_iface, pf_iface)
            dev["interface"] = config_iface
            dev["subnet"]    = _subnet_for_interface(pf_iface, subnet_map)

            dev["dhcp"] = {
                "binding_type": "static",
                "lease_start": None,
                "lease_end":   None,
            }

            if "probe_dhcp" not in dev["source"]:
                dev["source"].append("probe_dhcp")

    except Exception as e:
        log.error(f"probe_dhcp: static mappings failed: {e}")
        snapshot.setdefault("meta", {}).setdefault("probes_failed", []).append("dhcp_static")

    # ── ARP Table ────────────────────────────────────────────────────────────
    # Catches dynamic DHCP clients, guests, and any device not in static mappings.
    # Endpoint confirmed: /diagnostics/arp_table (NOT /diagnostics/arp)
    log.info("probe_dhcp: fetching ARP table")
    try:
        arp_data = _pfsense_get(base_url, "/diagnostics/arp_table", {},
                                api_key, tls_verify)
        arp_entries = arp_data if isinstance(arp_data, list) else []
        log.info(f"probe_dhcp: got {len(arp_entries)} ARP entries")

        for entry in arp_entries:
            mac = entry.get("mac") or entry.get("mac_address") or ""
            if not mac or mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
                continue
            mac = _normalize_mac(mac)

            ip       = entry.get("ip") or entry.get("ip_address") or None
            iface    = entry.get("interface") or entry.get("if") or ""
            hostname = entry.get("hostname") or None

            dev = devices.setdefault(mac, {
                "mac": mac, "status": "unknown", "source": [], "labels": [],
                "dhcp": None, "wifi": None, "icmp": None, "mdns": None
            })

            # ARP fills gaps — don't overwrite richer static mapping data
            if not dev.get("ip") and ip:
                dev["ip"] = ip
            if hostname and not dev.get("hostname"):
                dev["hostname"] = hostname

            # ARP interface is the pfSense API id (opt4, not opt1)
            if not dev.get("interface") and iface:
                dev["interface"] = PFSENSE_TO_CONFIG_IFACE.get(iface.lower(), iface.lower())
            if not dev.get("subnet") and iface:
                dev["subnet"] = _subnet_for_interface(iface.lower(), subnet_map)

            # ARP presence confirms device is (or recently was) active
            if dev["status"] == "unknown":
                dev["status"] = "up"

            if "probe_arp" not in dev["source"]:
                dev["source"].append("probe_arp")

    except Exception as e:
        log.error(f"probe_dhcp: ARP table failed: {e}")
        snapshot.setdefault("meta", {}).setdefault("probes_failed", []).append("dhcp_arp")

    log.info(f"probe_dhcp: complete — {len(devices)} devices in snapshot")
