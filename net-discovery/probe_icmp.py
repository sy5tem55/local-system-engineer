"""
probe_icmp.py — L1 Base probe
nmap ping sweep across all active subnets.
Confirms liveness, catches static IPs not in DHCP, updates status and RTT.

Uses nmap -sn (no port scan) with --unprivileged (no raw sockets needed).
Runs subnets in parallel threads for speed.

Requirements: nmap installed on probe host
  apt install nmap   (Ubuntu/Debian)
"""

import logging
import subprocess
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, Any

log = logging.getLogger(__name__)


def _run_nmap(cidr: str, nmap_args: str, timeout_s: int) -> str:
    """Run nmap on a subnet, return XML output string."""
    cmd = ["nmap", "-oX", "-"] + nmap_args.split() + [cidr]
    log.info(f"probe_icmp: nmap {' '.join(cmd[1:])}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s * 10  # generous timeout for full subnet sweep
        )
        if result.returncode not in (0, 1):  # nmap returns 1 for "hosts not found"
            log.warning(f"probe_icmp: nmap exited {result.returncode}: {result.stderr[:200]}")
        return result.stdout
    except subprocess.TimeoutExpired:
        log.error(f"probe_icmp: nmap timed out on {cidr}")
        return ""
    except FileNotFoundError:
        log.error("probe_icmp: nmap not found — install with: apt install nmap")
        return ""


def _parse_nmap_xml(xml_str: str) -> list[Dict[str, Any]]:
    """Parse nmap XML output into list of host dicts."""
    if not xml_str.strip():
        return []
    hosts = []
    try:
        root = ET.fromstring(xml_str)
        for host in root.findall("host"):
            if host.find("status") is None:
                continue
            status = host.find("status").get("state", "down")

            ip = None
            mac = None
            vendor = None

            for addr in host.findall("address"):
                addrtype = addr.get("addrtype")
                if addrtype == "ipv4":
                    ip = addr.get("addr")
                elif addrtype == "mac":
                    mac = addr.get("addr", "").lower()
                    vendor = addr.get("vendor")

            # RTT from host timing
            rtt_ms = None
            times = host.find("times")
            if times is not None:
                srtt = times.get("srtt")  # in microseconds
                if srtt:
                    rtt_ms = round(int(srtt) / 1000, 2)

            hosts.append({
                "ip": ip,
                "mac": mac,
                "vendor": vendor,
                "status": "up" if status == "up" else "down",
                "rtt_ms": rtt_ms
            })
    except ET.ParseError as e:
        log.error(f"probe_icmp: XML parse error: {e}")
    return hosts


def _normalize_mac(mac: str) -> str:
    if not mac:
        return ""
    return mac.strip().lower().replace("-", ":").replace(".", ":")


def _sweep_subnet(subnet_cfg: Dict, probe_cfg: Dict) -> list[Dict]:
    """Sweep one subnet, return parsed host list."""
    cidr = subnet_cfg["cidr"]
    nmap_args = probe_cfg.get("nmap_args", "-sn --unprivileged")
    timeout_s = probe_cfg.get("icmp_timeout_s", 2)
    xml_out = _run_nmap(cidr, nmap_args, timeout_s)
    return _parse_nmap_xml(xml_out)


def run(config: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    """
    Entry point called by discovery_engine.py.
    Mutates snapshot['devices'] in place.
    """
    active_subnets = [s for s in config["subnets"] if s.get("active", True)]
    probe_cfg = config.get("probe_config", {})
    max_workers = min(len(active_subnets), probe_cfg.get("icmp_parallel", 4))
    now_iso = datetime.now(timezone.utc).isoformat()
    devices = snapshot.setdefault("devices", {})

    results_by_subnet: Dict[str, list] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_sweep_subnet, s, probe_cfg): s
            for s in active_subnets
        }
        for future in as_completed(futures):
            subnet_cfg = futures[future]
            try:
                hosts = future.result()
                results_by_subnet[subnet_cfg["name"]] = hosts
                log.info(f"probe_icmp: {subnet_cfg['name']} — {len(hosts)} hosts found")
            except Exception as e:
                log.error(f"probe_icmp: sweep of {subnet_cfg['name']} failed: {e}")
                snapshot.setdefault("meta", {}).setdefault("probes_failed", []).append(
                    f"icmp_{subnet_cfg['name']}"
                )

    # Merge results into snapshot
    for subnet_name, hosts in results_by_subnet.items():
        subnet_cfg = next(s for s in active_subnets if s["name"] == subnet_name)
        for host in hosts:
            ip = host.get("ip")
            mac = _normalize_mac(host.get("mac") or "")

            # Find existing device by MAC, or fall back to IP match
            dev = None
            if mac:
                dev = devices.get(mac)
            if dev is None and ip:
                # Search by IP — device may not have MAC yet (e.g. across VLANs)
                for existing in devices.values():
                    if existing.get("ip") == ip:
                        dev = existing
                        break

            if dev is None:
                # New device — only seen by ICMP, not in DHCP/ARP
                if not mac:
                    # No MAC visible (cross-subnet ping) — key by IP
                    mac = f"ip:{ip}"
                dev = devices.setdefault(mac, {
                    "mac": mac, "status": "unknown", "source": [], "labels": [],
                    "dhcp": None, "wifi": None, "icmp": None, "mdns": None,
                    "interface": subnet_cfg.get("interface"),
                    "subnet": subnet_cfg["cidr"]
                })
                if ip:
                    dev["ip"] = ip

            # Update status — ICMP is ground truth for liveness
            dev["status"] = host["status"]

            # Fill vendor from nmap OUI if we don't have one
            if host.get("vendor") and not dev.get("vendor"):
                dev["vendor"] = host["vendor"]

            # ICMP timing data
            dev["icmp"] = dev.get("icmp") or {}
            dev["icmp"]["rtt_ms"] = host.get("rtt_ms")
            dev["icmp"]["last_seen"] = now_iso
            if host["status"] == "up":
                dev["icmp"]["last_up"] = now_iso

            if "probe_icmp" not in dev["source"]:
                dev["source"].append("probe_icmp")

    up = sum(1 for d in devices.values() if d.get("status") == "up")
    down = sum(1 for d in devices.values() if d.get("status") == "down")
    log.info(f"probe_icmp: complete — {up} up, {down} down")
