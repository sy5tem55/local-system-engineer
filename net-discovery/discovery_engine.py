"""
discovery_engine.py — LSE Network Discovery Engine
Orchestrator: loads config, runs all enabled probes in order, merges results,
normalises snapshot format, persists to SQLite, writes snapshot.json.

ws_server.py and prometheus_exporter.py watch snapshot.json via mtime — no
direct IPC needed; writing the file is the push mechanism.

Usage:
  # Single run
  python3 discovery_engine.py [--config config.json] [--output snapshot.json] [--verbose]

  # Continuous loop (recommended for live topology map)
  python3 discovery_engine.py --loop [--interval 60] [--verbose]

Probe execution order (reliability-ranked):
  L1  probe_dhcp  — pfSense DHCP leases + ARP (most reliable, zero network impact)
  L1  probe_icmp  — nmap ping sweep (confirms liveness, fills gaps)
  L2  probe_wifi  — ASUS / Teltonika WiFi client metadata (optional enrichment)
  L2  probe_mdns  — mDNS/Avahi service discovery (optional enrichment)

Internal snapshot format (during probe execution):
  snapshot["devices"] = {mac: {ip, hostname, vendor, subnet, status, source, icmp, dhcp, wifi, mdns}}

Normalised output format (written to snapshot.json, consumed by index.html / graph.py / prometheus_exporter.py):
  {
    "generated_at": "ISO8601",
    "meta": {...},
    "devices": [  ← list, not dict
      {ip, mac, hostname, vendor, subnet, type, icmp: {alive, rtt_ms, last_seen}, dhcp, wifi, sources}
    ]
  }

KNOWN_DEVICES: hardcoded IP → type/label map, kept in sync with index.html KNOWN_IPS.
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

import probe_dhcp
import probe_icmp

log = logging.getLogger(__name__)

# ── Optional probes — engine works without them ───────────────────────────────
try:
    import probe_wifi
    HAS_WIFI = True
except ImportError:
    HAS_WIFI = False

try:
    import probe_mdns
    HAS_MDNS = True
except ImportError:
    HAS_MDNS = False

# ── Optional persistence + graph — graceful if networkx/sqlite missing ────────
try:
    from schema import Database as _Database
    HAS_SCHEMA = True
except Exception:
    HAS_SCHEMA = False
    _Database = None

try:
    from graph import snapshot_to_cytoscape as _snap_to_cy, graph_summary as _graph_summary
    HAS_GRAPH = True
except Exception:
    HAS_GRAPH = False
    _snap_to_cy = None
    _graph_summary = None

# ── Static device classification — keep in sync with index.html KNOWN_IPS ────
# type: 'gateway' | 'ap' | 'server' | 'wifi_client' | 'wired_client' | 'unknown'
_KNOWN_IPS: Dict[str, Dict[str, str]] = {
    "192.168.1.1":  {"type": "ap",      "label": "ASUS GT-BE19000"},
    "192.168.5.3":  {"type": "ap",      "label": "Teltonika RUTX50"},
    "192.168.1.50": {"type": "gateway", "label": "pfSense"},
}


# ---------------------------------------------------------------------------
# Config + snapshot helpers
# ---------------------------------------------------------------------------
def load_config(path: str) -> Dict[str, Any]:
    with open(path) as f:
        cfg = json.load(f)
    for key in ("gateway", "subnets", "probe_config", "output"):
        if key not in cfg:
            raise ValueError(f"config.json missing required key: '{key}'")
    return cfg


def empty_snapshot() -> Dict[str, Any]:
    return {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_s": 0,
            "probes_run": [],
            "probes_failed": [],
            "device_count": 0,
            "up_count": 0,
            "down_count": 0,
        },
        "devices": {},   # {mac: dev_dict} during probes; converted to list at finalise
        "edges": [],
    }


# ---------------------------------------------------------------------------
# Device type classification (Python mirror of index.html classifyType())
# ---------------------------------------------------------------------------
def _classify_type(dev: Dict[str, Any]) -> str:
    ip = dev.get("ip", "")
    if ip in _KNOWN_IPS:
        return _KNOWN_IPS[ip]["type"]
    # Subnet gateway heuristic (.1 address)
    if ip and ip.endswith(".1"):
        return "gateway"
    # OPT1 static DHCP → server
    dhcp = dev.get("dhcp") or {}
    if dev.get("subnet") == "192.168.5.0/24" and dhcp.get("binding_type") == "static":
        return "server"
    # Has WiFi metadata → wifi_client
    wifi = dev.get("wifi")
    if wifi and (wifi.get("ssid") or wifi.get("rssi_dbm") is not None):
        return "wifi_client"
    status = dev.get("status", "unknown")
    if status == "unknown":
        return "unknown"
    return "wired_client"


# ---------------------------------------------------------------------------
# Snapshot normalisation
# Convert internal {mac: dev} dict to the external list format consumed by
# index.html, graph.py, and prometheus_exporter.py.
# ---------------------------------------------------------------------------
def _normalise_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a new snapshot dict suitable for JSON serialisation.
    The original snapshot is NOT mutated (probes may keep running in loop mode).
    """
    raw_devices: Dict[str, Any] = snapshot.get("devices", {})
    device_list: List[Dict[str, Any]] = []

    for mac, dev in raw_devices.items():
        # --- icmp sub-object: add 'alive' bool from 'status' ----------------
        icmp_raw = dev.get("icmp") or {}
        status = dev.get("status", "unknown")
        icmp_out = {
            "alive":     status == "up",
            "rtt_ms":    icmp_raw.get("rtt_ms"),
            "last_seen": icmp_raw.get("last_seen"),
            "last_up":   icmp_raw.get("last_up"),
        }

        # --- dhcp sub-object: normalise field names -------------------------
        dhcp_raw = dev.get("dhcp") or {}
        dhcp_out: Optional[Dict[str, Any]] = None
        if dhcp_raw:
            dhcp_out = {
                "binding_type": dhcp_raw.get("binding_type", "dynamic"),
                "expires":      dhcp_raw.get("lease_end") or dhcp_raw.get("expires"),
                "lease_start":  dhcp_raw.get("lease_start"),
            }

        # --- wifi sub-object: pass through ----------------------------------
        wifi = dev.get("wifi") or None

        # --- sources: rename 'source' → 'sources' ---------------------------
        sources = dev.get("sources") or dev.get("source") or []

        out = {
            "ip":       dev.get("ip") or "",
            "mac":      mac,
            "hostname": dev.get("hostname") or "",
            "vendor":   dev.get("vendor") or "",
            "subnet":   dev.get("subnet") or "",
            "type":     _classify_type(dev),
            "status":   status,
            "icmp":     icmp_out,
            "dhcp":     dhcp_out,
            "wifi":     wifi,
            "mdns":     dev.get("mdns"),
            "sources":  sources,
        }
        device_list.append(out)

    # Sort for stable output: subnet then IP
    device_list.sort(key=lambda d: (d.get("subnet", ""), d.get("ip") or ""))

    meta = snapshot.get("meta", {})
    normalised = {
        "generated_at": meta.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "meta":         meta,
        "devices":      device_list,
    }
    return normalised


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------
def _persist_to_db(
    normalised: Dict[str, Any],
    db: Any,
    prev_status: Dict[str, str],
) -> Dict[str, str]:
    """
    Write normalised device list to SQLite.
    prev_status: {ip: 'up'|'down'|'unknown'} from last cycle — used for event detection.
    Returns updated prev_status.
    """
    current_status: Dict[str, str] = {}

    for dev in normalised.get("devices", []):
        ip  = dev.get("ip") or ""
        mac = dev.get("mac") or ""
        if not mac or mac.startswith("ip:"):
            continue   # no MAC → skip persistence

        # Ensure host + IP assignment exist
        db.upsert_host(mac, dev.get("hostname") or None, dev.get("vendor") or None)
        if ip and dev.get("subnet"):
            binding = (dev.get("dhcp") or {}).get("binding_type", "dynamic")
            db.upsert_ip(mac, ip, dev["subnet"], binding)

        # ICMP
        icmp = dev.get("icmp") or {}
        alive = icmp.get("alive", False)
        rtt   = icmp.get("rtt_ms")
        if icmp.get("last_seen"):
            db.record_ping(ip, alive, rtt_ms=rtt, probed_at=icmp["last_seen"])

        # WiFi
        wifi = dev.get("wifi")
        if wifi:
            db.record_wifi(
                mac, dev.get("sources", [""])[0] if dev.get("sources") else "unknown",
                ssid=wifi.get("ssid"), band=wifi.get("band"),
                rssi_dbm=wifi.get("rssi_dbm"),
                tx_rate=wifi.get("tx_rate"), rx_rate=wifi.get("rx_rate"),
            )

        # State-change events
        status_str = "up" if alive else "down"
        current_status[ip] = status_str
        prev = prev_status.get(ip)
        if prev is None:
            db.record_event("new_device", ip=ip, mac=mac,
                            detail={"hostname": dev.get("hostname"), "subnet": dev.get("subnet")})
        elif prev != status_str:
            db.record_event(status_str, ip=ip, mac=mac,
                            detail={"prev": prev, "rtt_ms": rtt})

    return current_status


# ---------------------------------------------------------------------------
# Snapshot save + history management
# ---------------------------------------------------------------------------
def save_snapshot(
    normalised: Dict[str, Any],
    output_path: str,
    history_dir: str,
    history_keep_days: int,
) -> None:
    """Atomically write snapshot.json and archive a timestamped copy."""
    tmp = output_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(normalised, f, indent=2, default=str)
    # Atomic rename — ws_server sees consistent file
    os.replace(tmp, output_path)
    log.info("Snapshot written → %s  (%d devices)",
             output_path, len(normalised.get("devices", [])))

    # Archive
    Path(history_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(output_path, os.path.join(history_dir, f"snapshot_{ts}.json"))

    # Prune old archives
    cutoff = time.time() - (history_keep_days * 86400)
    for f in Path(history_dir).glob("snapshot_*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            log.debug("Pruned old snapshot: %s", f.name)


# ---------------------------------------------------------------------------
# Single discovery run
# ---------------------------------------------------------------------------
def run(
    config_path: str = "config.json",
    output_path: Optional[str] = None,
    db: Optional[Any] = None,
    prev_status: Optional[Dict[str, str]] = None,
) -> tuple[Dict[str, Any], Dict[str, str]]:
    """
    Execute one full discovery cycle.

    Returns (normalised_snapshot, current_status_dict).
    current_status_dict can be passed back as prev_status on the next call
    to enable state-change event detection.
    """
    config = load_config(config_path)
    out_cfg = config["output"]
    output_path = output_path or out_cfg.get("snapshot_file", "snapshot.json")
    history_dir = out_cfg.get("history_dir", "history/")
    history_keep_days = out_cfg.get("history_keep_days", 7)
    if prev_status is None:
        prev_status = {}

    snapshot = empty_snapshot()
    start = time.time()

    # ── L1: DHCP + ARP ───────────────────────────────────────────────────────
    log.info("=== probe_dhcp: START ===")
    try:
        probe_dhcp.run(config, snapshot)
        snapshot["meta"]["probes_run"].append("probe_dhcp")
    except Exception as e:
        log.error("probe_dhcp: FATAL: %s", e, exc_info=True)
        snapshot["meta"]["probes_failed"].append("probe_dhcp")

    # ── L1: ICMP ping sweep ──────────────────────────────────────────────────
    log.info("=== probe_icmp: START ===")
    try:
        probe_icmp.run(config, snapshot)
        snapshot["meta"]["probes_run"].append("probe_icmp")
    except Exception as e:
        log.error("probe_icmp: FATAL: %s", e, exc_info=True)
        snapshot["meta"]["probes_failed"].append("probe_icmp")

    # ── L2: WiFi metadata ────────────────────────────────────────────────────
    if HAS_WIFI:
        enabled_routers = [r for r in config.get("wifi_routers", []) if r.get("enabled")]
        if enabled_routers:
            log.info("=== probe_wifi: START ===")
            try:
                probe_wifi.run(config, snapshot)
                snapshot["meta"]["probes_run"].append("probe_wifi")
            except Exception as e:
                log.error("probe_wifi: FATAL: %s", e, exc_info=True)
                snapshot["meta"]["probes_failed"].append("probe_wifi")

    # ── L2: mDNS ────────────────────────────────────────────────────────────
    if HAS_MDNS:
        log.info("=== probe_mdns: START ===")
        try:
            probe_mdns.run(config, snapshot)
            snapshot["meta"]["probes_run"].append("probe_mdns")
        except Exception as e:
            log.error("probe_mdns: FATAL: %s", e, exc_info=True)
            snapshot["meta"]["probes_failed"].append("probe_mdns")

    # ── Finalise metadata ────────────────────────────────────────────────────
    devices = snapshot["devices"]

    # Filter test/loopback artifacts
    _EXCLUDE_MACS = {"de:ad:be:ef:55:5a"}
    _EXCLUDE_IPS  = {"127.0.0.2"}
    snapshot["devices"] = {
        mac: dev for mac, dev in snapshot["devices"].items()
        if mac not in _EXCLUDE_MACS and dev.get("ip") not in _EXCLUDE_IPS
    }
    devices = snapshot["devices"]
    up_count   = sum(1 for d in devices.values() if d.get("status") == "up")
    down_count = sum(1 for d in devices.values() if d.get("status") == "down")
    snapshot["meta"].update({
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "duration_s":   round(time.time() - start, 2),
        "device_count": len(devices),
        "up_count":     up_count,
        "down_count":   down_count,
    })

    # ── Normalise to external list format ────────────────────────────────────
    normalised = _normalise_snapshot(snapshot)

    # ── Persist to SQLite ────────────────────────────────────────────────────
    current_status: Dict[str, str] = {}
    if HAS_SCHEMA and db is not None:
        try:
            current_status = _persist_to_db(normalised, db, prev_status)
            db.prune_ping_history(keep_days=history_keep_days)
        except Exception as e:
            log.error("schema persistence failed: %s", e, exc_info=True)

    # ── Graph summary (logged only — graph JSON is generated by ws_server) ────
    if HAS_GRAPH:
        try:
            from graph import build_graph, graph_summary
            G = build_graph(normalised)
            summary = graph_summary(G)
            log.info("Graph: %d nodes, %d edges — by_type: %s",
                     summary["nodes"], summary["edges"], summary["by_type"])
        except Exception as e:
            log.debug("graph summary failed (non-fatal): %s", e)

    # ── Write snapshot.json (triggers ws_server broadcast) ───────────────────
    save_snapshot(normalised, output_path, history_dir, history_keep_days)

    log.info(
        "Discovery complete in %.1fs — %d devices (%d up, %d down) | probes: %s%s",
        normalised["meta"]["duration_s"],
        normalised["meta"]["device_count"],
        normalised["meta"]["up_count"],
        normalised["meta"]["down_count"],
        ", ".join(normalised["meta"]["probes_run"]) or "none",
        f" | FAILED: {normalised['meta']['probes_failed']}" if normalised["meta"]["probes_failed"] else "",
    )
    return normalised, current_status


# ---------------------------------------------------------------------------
# Continuous loop mode
# ---------------------------------------------------------------------------
def run_loop(
    config_path: str,
    output_path: Optional[str],
    interval: int,
) -> None:
    """
    Run discovery in a continuous loop.
    Opens DB once; passes prev_status between cycles for event detection.
    """
    db = None
    if HAS_SCHEMA:
        try:
            config = load_config(config_path)
            db_path = Path(config_path).parent / "db" / "netobs.db"
            db = _Database(db_path)
            log.info("SQLite persistence: %s", db_path)
        except Exception as e:
            log.warning("Could not open SQLite DB: %s — persistence disabled", e)

    if not HAS_SCHEMA:
        log.warning(
            "schema.py not importable — persistence disabled. "
            "Check: pip show sqlite3 (it's stdlib — check schema.py imports)"
        )

    prev_status: Dict[str, str] = {}
    cycle = 0

    log.info("Loop mode: interval=%ds — Ctrl+C to stop", interval)
    while True:
        cycle += 1
        log.info("─── Cycle %d ───", cycle)
        try:
            _, prev_status = run(
                config_path=config_path,
                output_path=output_path,
                db=db,
                prev_status=prev_status,
            )
        except Exception as e:
            log.error("Cycle %d crashed: %s", cycle, e, exc_info=True)

        log.info("Sleeping %ds until next cycle...", interval)
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Loop stopped by user.")
            break


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LSE Network Discovery Engine")
    parser.add_argument("--config",   default="config.json", help="Path to config.json")
    parser.add_argument("--output",   default=None,          help="Override snapshot output path")
    parser.add_argument("--verbose",  action="store_true",   help="Enable debug logging")
    parser.add_argument("--loop",     action="store_true",   help="Run continuously")
    parser.add_argument("--interval", type=int, default=60,  help="Loop interval in seconds (default: 60)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    if args.loop:
        run_loop(args.config, args.output, args.interval)
        sys.exit(0)

    # Single run — open DB here for single-shot mode
    db = None
    if HAS_SCHEMA:
        try:
            config = load_config(args.config)
            db_path = Path(args.config).parent / "db" / "netobs.db"
            db = _Database(db_path)
        except Exception as e:
            log.warning("Could not open SQLite DB: %s — persistence disabled", e)

    try:
        result, _ = run(
            config_path=args.config,
            output_path=args.output,
            db=db,
        )
        sys.exit(0 if not result["meta"]["probes_failed"] else 1)
    except Exception as e:
        log.critical("Discovery engine crashed: %s", e, exc_info=True)
        sys.exit(2)
