"""
probe_mdns.py — L2 mDNS / Zeroconf service discovery enrichment
Browses local mDNS service types and resolves service records.
Enriches snapshot devices with service name, port, and TXT records.

PRE-INSTALL RULE: zeroconf is ALREADY installed.
  Check: pip show zeroconf
  DO NOT reinstall.

Limitations:
  - mDNS is link-local (multicast 224.0.0.251). Only reaches devices on the
    same L2 segment as the probe host (LUCIFER's LAN interface).
  - OPT1 (192.168.5.x) and Z WiFi clients behind Teltonika are NOT reachable
    via mDNS from LUCIFER unless a mDNS repeater is configured on pfSense.
  - IoT VLAN 55 is disabled — mDNS unreachable there too.
  - Run time: BROWSE_TIMEOUT_S per service type. With 8 types = ~32s extra.

Service types discovered (extend SERVICE_TYPES to add more):
  _http._tcp.local.       Web servers (OpenWebUI, dashboards, APIs)
  _https._tcp.local.      HTTPS services
  _ssh._tcp.local.        SSH daemons (most Linux hosts)
  _sftp-ssh._tcp.local.   SFTP
  _smb._tcp.local.        Samba / Windows shares
  _printer._tcp.local.    Network printers
  _ipp._tcp.local.        IPP print servers
  _workstation._tcp.local. Avahi workstation announcements (most Ubuntu/Debian)

Usage:
  Called by discovery_engine.py as optional L2 probe.
  Can also run standalone: python3 probe_mdns.py [--timeout 4] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------
def _check_pkg(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


if not _check_pkg("zeroconf"):
    print(
        "ERROR: 'zeroconf' not importable.\n"
        "Check first: pip show zeroconf\n"
        "Install only if missing: pip install zeroconf --break-system-packages",
        file=sys.stderr,
    )
    sys.exit(1)

from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BROWSE_TIMEOUT_S: float = 4.0   # time to wait per service type

SERVICE_TYPES: List[str] = [
    "_http._tcp.local.",
    "_https._tcp.local.",
    "_ssh._tcp.local.",
    "_sftp-ssh._tcp.local.",
    "_smb._tcp.local.",
    "_workstation._tcp.local.",
    "_printer._tcp.local.",
    "_ipp._tcp.local.",
]


# ---------------------------------------------------------------------------
# Listener — collects discovered services
# ---------------------------------------------------------------------------
class _Listener:
    def __init__(self) -> None:
        # {service_type: [{name, ip, port, txt}]}
        self.records: List[Dict[str, Any]] = []

    def add_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        try:
            info: Optional[ServiceInfo] = zc.get_service_info(service_type, name, timeout=2000)
            if info is None:
                return

            # Resolve IP — prefer IPv4
            ip: Optional[str] = None
            for addr_bytes in info.addresses:
                try:
                    ip = socket.inet_ntoa(addr_bytes)
                    break
                except Exception:
                    pass

            txt: Dict[str, str] = {}
            if info.properties:
                for k, v in info.properties.items():
                    key = k.decode("utf-8", errors="replace") if isinstance(k, bytes) else str(k)
                    val = v.decode("utf-8", errors="replace") if isinstance(v, bytes) else (str(v) if v else "")
                    txt[key] = val

            record = {
                "service_type": service_type.rstrip("."),
                "service_name": name,
                "ip": ip,
                "port": info.port,
                "txt": txt,
                "server": info.server,
            }
            self.records.append(record)
            log.debug("mDNS: %s @ %s:%s", name, ip, info.port)

        except Exception as exc:
            log.debug("mDNS: failed to resolve %s: %s", name, exc)

    def remove_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        pass  # not needed for snapshot enrichment

    def update_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Main probe function
# ---------------------------------------------------------------------------
def _browse_services(
    service_types: List[str],
    timeout_s: float,
) -> List[Dict[str, Any]]:
    """Browse all service types in parallel using one Zeroconf instance."""
    zc = Zeroconf()
    listener = _Listener()
    browsers = []

    try:
        for stype in service_types:
            browsers.append(ServiceBrowser(zc, stype, listener))
        time.sleep(timeout_s)
    finally:
        for b in browsers:
            try:
                b.cancel()
            except Exception:
                pass
        zc.close()

    return listener.records


def _enrich_snapshot(
    records: List[Dict[str, Any]],
    snapshot: Dict[str, Any],
) -> None:
    """
    Match discovered mDNS records to snapshot devices by IP.
    Adds/updates dev['mdns'] with a list of service records.
    """
    # Build IP → device lookup
    devices = snapshot.get("devices", {})

    # devices may be dict (internal) or list (normalised) — handle both
    if isinstance(devices, dict):
        ip_to_dev = {dev.get("ip"): dev for dev in devices.values() if dev.get("ip")}
    else:
        ip_to_dev = {dev.get("ip"): dev for dev in devices if dev.get("ip")}

    enriched = 0
    for record in records:
        ip = record.get("ip")
        if not ip:
            continue

        dev = ip_to_dev.get(ip)
        if dev is None:
            log.debug("mDNS record for unknown IP %s (not in snapshot) — skipping", ip)
            continue

        # Accumulate service records
        if not isinstance(dev.get("mdns"), list):
            dev["mdns"] = []

        # Deduplicate by (service_type, service_name)
        existing_keys = {(r["service_type"], r["service_name"]) for r in dev["mdns"]}
        key = (record["service_type"], record["service_name"])
        if key not in existing_keys:
            dev["mdns"].append({
                "service_type": record["service_type"],
                "service_name": record["service_name"],
                "port": record["port"],
                "txt": record["txt"],
                "server": record.get("server"),
            })
            enriched += 1

        # Append to sources if not already there
        sources = dev.get("sources") or dev.get("source") or []
        if "probe_mdns" not in sources:
            sources.append("probe_mdns")
        dev["sources"] = sources

    log.info("probe_mdns: matched %d mDNS records to snapshot devices", enriched)


# ---------------------------------------------------------------------------
# Entry point (called by discovery_engine.py)
# ---------------------------------------------------------------------------
def run(config: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    """
    Entry point called by discovery_engine.py.
    Mutates snapshot['devices'] in place.
    """
    probe_cfg = config.get("probe_config", {})
    timeout_s = float(probe_cfg.get("mdns_timeout_s", BROWSE_TIMEOUT_S))

    log.info(
        "probe_mdns: browsing %d service types (%.1fs timeout each, ~%.0fs total)",
        len(SERVICE_TYPES), timeout_s, timeout_s,
    )

    records = _browse_services(SERVICE_TYPES, timeout_s)
    log.info("probe_mdns: found %d mDNS service records", len(records))

    if records:
        _enrich_snapshot(records, snapshot)


# ---------------------------------------------------------------------------
# Standalone CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="mDNS probe — discover LAN services")
    parser.add_argument("--timeout", type=float, default=BROWSE_TIMEOUT_S,
                        help=f"Browse timeout in seconds per type (default: {BROWSE_TIMEOUT_S})")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    records = _browse_services(SERVICE_TYPES, args.timeout)

    if not records:
        print("No mDNS services found on local network.")
        return

    # Group by IP for readable output
    by_ip: Dict[str, List[Dict]] = {}
    for r in records:
        ip = r.get("ip", "unknown")
        by_ip.setdefault(ip, []).append(r)

    print(f"\nFound {len(records)} mDNS service records on {len(by_ip)} hosts:\n")
    for ip, recs in sorted(by_ip.items()):
        print(f"  {ip}")
        for r in recs:
            txt_str = ", ".join(f"{k}={v}" for k, v in r.get("txt", {}).items())
            print(f"    {r['service_type']}  port={r['port']}  name={r['service_name']}"
                  + (f"  [{txt_str}]" if txt_str else ""))
    print()


if __name__ == "__main__":
    main()
