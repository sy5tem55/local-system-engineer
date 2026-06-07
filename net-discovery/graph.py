"""
graph.py — NetworkX graph builder and Cytoscape.js JSON exporter
Converts snapshot.json device list into a topology graph for visualization.

Standalone usage:
  python3 graph.py [snapshot.json] [--out graph.json]

As a module:
  from graph import snapshot_to_cytoscape
  cy_data = snapshot_to_cytoscape(snapshot_dict)
  # cy_data = {"nodes": [...], "edges": [...]}

Edge inference rules (no routing table — we infer from subnet + type):
  - gateway nodes       → connect to implicit "internet" root node
  - AP nodes            → connect to the gateway of their subnet
  - wifi_client nodes   → connect to the AP serving their subnet
  - all other nodes     → connect to their subnet gateway
  - if no gateway found for a subnet → connect to pfSense fallback node

Node visual encoding (matches index.html KNOWN_TYPES):
  type        shape           color
  gateway     diamond         #e8a838 (amber)
  ap          hexagon         #4a9eff (blue)
  server      roundrectangle  #3ecf8e (green)
  wifi_client ellipse         status-keyed
  wired_client ellipse        status-keyed
  unknown     ellipse         #666666

Status colors:
  up    → #3ecf8e
  down  → #e05252
  stale → #f0a500 (last_seen > 5 min)
  unknown → #888888
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import networkx as nx
except ImportError:
    print(
        "ERROR: networkx not importable.\n"
        "Check first: pip show networkx\n"
        "Install only if missing: pip install networkx --break-system-packages",
        file=sys.stderr,
    )
    sys.exit(1)

log = logging.getLogger("netobs.graph")

# ---------------------------------------------------------------------------
# Visual encoding tables — kept in sync with index.html
# ---------------------------------------------------------------------------
NODE_SHAPES: Dict[str, str] = {
    "gateway":      "diamond",
    "ap":           "hexagon",
    "server":       "roundrectangle",
    "wifi_client":  "ellipse",
    "wired_client": "ellipse",
    "unknown":      "ellipse",
}

NODE_COLORS: Dict[str, str] = {
    "gateway":      "#e8a838",
    "ap":           "#4a9eff",
    "server":       "#3ecf8e",
}

STATUS_COLORS: Dict[str, str] = {
    "up":      "#3ecf8e",
    "down":    "#e05252",
    "stale":   "#f0a500",
    "unknown": "#888888",
}

STALE_THRESHOLD = timedelta(minutes=5)

# Subnet → which AP IP serves it (derived dynamically, but fallback hardcoded)
SUBNET_AP_FALLBACK: Dict[str, str] = {
    "192.168.1.0/24":  "192.168.1.1",   # ASUS GT-BE19000
    "192.168.5.0/24":  "192.168.5.3",   # Teltonika RUTX50
}

# Internet stub node — root of the graph
INTERNET_NODE_ID = "__internet__"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _device_status(dev: Dict[str, Any]) -> str:
    """Return 'up', 'down', 'stale', or 'unknown' for a device."""
    icmp = dev.get("icmp") or {}
    alive = icmp.get("alive")
    if alive is None:
        return "unknown"
    if not alive:
        return "down"

    # Check staleness from last_seen
    last_seen_str = icmp.get("last_seen")
    if last_seen_str:
        try:
            ts = last_seen_str.replace("Z", "+00:00")
            last_seen = datetime.fromisoformat(ts)
            age = datetime.now(timezone.utc) - last_seen
            if age > STALE_THRESHOLD:
                return "stale"
        except Exception:
            pass
    return "up"


def _node_color(dev: Dict[str, Any]) -> str:
    dev_type = dev.get("type", "unknown")
    if dev_type in NODE_COLORS:
        return NODE_COLORS[dev_type]
    # For client types, use status color
    status = _device_status(dev)
    return STATUS_COLORS.get(status, STATUS_COLORS["unknown"])


def _node_label(dev: Dict[str, Any]) -> str:
    """Best human-readable label: hostname > vendor truncated > IP."""
    hostname = dev.get("hostname", "")
    if hostname and hostname not in ("-", "?", ""):
        return hostname
    vendor = dev.get("vendor", "")
    if vendor:
        # Truncate "ASUSTeK Computer Inc." → "ASUSTeK"
        return vendor.split()[0][:16]
    return dev.get("ip", "unknown")


def _node_border_color(dev: Dict[str, Any]) -> str:
    """Border color encodes subnet membership — matches index.html."""
    subnet = dev.get("subnet", "")
    if "192.168.1." in subnet:
        return "#2d5a9e"   # LAN — blue
    if "192.168.5." in subnet:
        return "#7c5fc8"   # OPT1 — purple
    if "192.168.10." in subnet:
        return "#3a9a60"   # OPT2 — green
    return "#555555"


def _build_subnet_maps(
    devices: List[Dict[str, Any]]
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Build {subnet → gateway_ip} and {subnet → ap_ip} from device list.
    Falls back to SUBNET_AP_FALLBACK for APs.
    """
    gateways: Dict[str, str] = {}
    aps: Dict[str, str] = {}

    for dev in devices:
        subnet = dev.get("subnet", "")
        ip = dev.get("ip", "")
        dev_type = dev.get("type", "")

        if dev_type == "gateway" and subnet and ip:
            gateways[subnet] = ip
        if dev_type == "ap" and subnet and ip:
            aps[subnet] = ip

    # Fill AP fallback
    for subnet, ap_ip in SUBNET_AP_FALLBACK.items():
        if subnet not in aps:
            aps[subnet] = ap_ip

    return gateways, aps


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def build_graph(snapshot: Dict[str, Any]) -> nx.DiGraph:
    """
    Build a directed NetworkX graph from a snapshot dict.
    Nodes carry all device attributes as node data.
    Edges represent physical/wireless connectivity.
    """
    G = nx.DiGraph()
    devices: List[Dict[str, Any]] = snapshot.get("devices", [])

    # Add internet stub
    G.add_node(
        INTERNET_NODE_ID,
        label="Internet",
        type="internet",
        ip="",
        mac="",
        subnet="",
        status="up",
        shape="triangle",
        color="#555555",
        border_color="#555555",
    )

    gateways, aps = _build_subnet_maps(devices)

    # Add all device nodes
    for dev in devices:
        ip = dev.get("ip", "")
        if not ip:
            continue
        G.add_node(
            ip,
            label=_node_label(dev),
            type=dev.get("type", "unknown"),
            ip=ip,
            mac=dev.get("mac", ""),
            hostname=dev.get("hostname", ""),
            vendor=dev.get("vendor", ""),
            subnet=dev.get("subnet", ""),
            status=_device_status(dev),
            shape=NODE_SHAPES.get(dev.get("type", "unknown"), "ellipse"),
            color=_node_color(dev),
            border_color=_node_border_color(dev),
            # Carry probe data for drill-down panel
            icmp=dev.get("icmp") or {},
            wifi=dev.get("wifi") or {},
            dhcp=dev.get("dhcp") or {},
            sources=dev.get("sources", []),
        )

    # Add edges — infer topology
    for dev in devices:
        ip = dev.get("ip", "")
        if not ip or ip == INTERNET_NODE_ID:
            continue

        subnet = dev.get("subnet", "")
        dev_type = dev.get("type", "unknown")

        if dev_type == "gateway":
            # Gateway → internet
            G.add_edge(ip, INTERNET_NODE_ID, type="wan", label="WAN")

        elif dev_type == "ap":
            # AP → its subnet gateway (or internet if no gateway found)
            target = gateways.get(subnet, INTERNET_NODE_ID)
            if target != ip:
                G.add_edge(ip, target, type="wired", label="uplink")

        elif dev_type in ("wifi_client",):
            # WiFi client → AP serving its subnet
            ap_ip = aps.get(subnet)
            if ap_ip and ap_ip != ip and ap_ip in G:
                G.add_edge(ip, ap_ip, type="wifi", label="wifi")
            else:
                # No known AP — connect to gateway
                target = gateways.get(subnet, INTERNET_NODE_ID)
                if target != ip:
                    G.add_edge(ip, target, type="wired", label="")

        else:
            # wired_client, server, unknown → subnet gateway
            target = gateways.get(subnet)
            if target and target != ip and target in G:
                G.add_edge(ip, target, type="wired", label="")
            else:
                # No gateway in snapshot — connect to AP as proxy
                ap_ip = aps.get(subnet)
                if ap_ip and ap_ip != ip and ap_ip in G:
                    G.add_edge(ip, ap_ip, type="wired", label="")

    return G


# ---------------------------------------------------------------------------
# Cytoscape.js serialiser
# ---------------------------------------------------------------------------
def graph_to_cytoscape(G: nx.DiGraph) -> Dict[str, List[Dict[str, Any]]]:
    """
    Convert NetworkX DiGraph to Cytoscape.js elements format:
    {"nodes": [{"data": {...}}, ...], "edges": [{"data": {...}}, ...]}
    """
    nodes = []
    for node_id, attrs in G.nodes(data=True):
        nodes.append({
            "data": {
                "id": node_id,
                **attrs,
            }
        })

    edges = []
    for i, (src, tgt, attrs) in enumerate(G.edges(data=True)):
        edges.append({
            "data": {
                "id": f"e{i}-{src}-{tgt}",
                "source": src,
                "target": tgt,
                **attrs,
            }
        })

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def snapshot_to_cytoscape(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    High-level entry point.
    snapshot → NetworkX graph → Cytoscape.js JSON dict.
    """
    G = build_graph(snapshot)
    cy = graph_to_cytoscape(G)
    log.debug(
        "Graph: %d nodes, %d edges",
        G.number_of_nodes(),
        G.number_of_edges(),
    )
    return cy


def snapshot_file_to_cytoscape(snapshot_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Read snapshot.json from disk and return Cytoscape.js JSON dict."""
    with open(snapshot_path) as f:
        snapshot = json.load(f)
    return snapshot_to_cytoscape(snapshot)


# ---------------------------------------------------------------------------
# Stats helper — useful for discovery_engine logging
# ---------------------------------------------------------------------------
def graph_summary(G: nx.DiGraph) -> Dict[str, Any]:
    type_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    for _, attrs in G.nodes(data=True):
        t = attrs.get("type", "unknown")
        s = attrs.get("status", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "by_type": type_counts,
        "by_status": status_counts,
    }


# ---------------------------------------------------------------------------
# CLI — standalone test/inspection
# ---------------------------------------------------------------------------
def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Convert snapshot.json to Cytoscape.js graph JSON"
    )
    parser.add_argument(
        "snapshot",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "snapshot.json",
        help="Path to snapshot.json (default: snapshot.json alongside this script)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write output JSON to file (default: stdout)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print graph summary instead of full JSON",
    )
    args = parser.parse_args()

    if not args.snapshot.exists():
        print(f"ERROR: {args.snapshot} not found", file=sys.stderr)
        sys.exit(1)

    with open(args.snapshot) as f:
        snapshot = json.load(f)

    G = build_graph(snapshot)

    if args.summary:
        print(json.dumps(graph_summary(G), indent=2))
        return

    cy = graph_to_cytoscape(G)

    if args.out:
        args.out.write_text(json.dumps(cy, indent=2))
        print(f"Written to {args.out}")
    else:
        print(json.dumps(cy, indent=2))


if __name__ == "__main__":
    main()
