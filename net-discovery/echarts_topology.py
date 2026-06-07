#!/usr/bin/env python3
"""
echarts_topology.py
Convert snapshot.json → ECharts graph data and serve it on port 8766.

Hierarchy (confirmed from live snapshot 2026-06-07):
  Internet
    └─ pfSense LAN  192.168.1.50  (tier 1)
         ├─ ASUS GT-BE19000  192.168.1.1  (AP, tier 2) ← LAN clients
         └─ pfSense OPT1     192.168.5.1  (tier 1 sub-interface)
              ├─ Netgear GS308E  192.168.5.2  (switch, tier 2)
              │    └─ Teltonika RUTX50  192.168.5.3  (router/AP, tier 2)
              └─ pfSense OPT2  192.168.10.1  (failover)

Run from WSL:
  export SNAPSHOT=/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/net-discovery/snapshot.json
  python3 echarts_topology.py
"""

import json, http.server, socketserver, os
from pathlib import Path
from urllib.parse import urlparse

SNAPSHOT = Path(os.environ.get(
    "SNAPSHOT",
    "/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/net-discovery/snapshot.json"
))

# ip → (display_label, category_name, tier)
TIER_NODES = {
    "192.168.1.50":  ("pfSense LAN",       "gateway", 1),
    "192.168.5.1":   ("pfSense OPT1",      "gateway", 1),
    "192.168.10.1":  ("pfSense OPT2",      "gateway", 1),
    "192.168.1.1":   ("ASUS GT-BE19000",   "ap",      2),
    "192.168.5.2":   ("Netgear GS308E",    "switch",  2),
    "192.168.5.3":   ("Teltonika RUTX50",  "router",  2),
}

TIER_EDGES = [
    ("192.168.1.50", "192.168.1.1",  "LAN"),
    ("192.168.1.50", "192.168.5.1",  "OPT1"),
    ("192.168.5.1",  "192.168.5.2",  "OPT1"),
    ("192.168.5.2",  "192.168.5.3",  "uplink"),
    ("192.168.1.50", "192.168.10.1", "OPT2"),
]

SUBNET_PARENT = {
    "192.168.1.0/24":   "192.168.1.1",   # LAN → ASUS AP
    "192.168.5.0/24":   "192.168.5.2",   # OPT1 → Netgear switch
    "192.168.10.0/24":  "192.168.10.1",  # OPT2 → pfSense OPT2
}

CATEGORIES = [
    {"name": "gateway", "itemStyle": {"color": "#ff4757"}},
    {"name": "ap",      "itemStyle": {"color": "#ffd43b"}},
    {"name": "switch",  "itemStyle": {"color": "#40c057"}},
    {"name": "router",  "itemStyle": {"color": "#4dabf7"}},
    {"name": "server",  "itemStyle": {"color": "#ff922b"}},
    {"name": "nas",     "itemStyle": {"color": "#cc5de8"}},
    {"name": "client",  "itemStyle": {"color": "#74c0fc"}},
    {"name": "unknown", "itemStyle": {"color": "#868e96"}},
]
CAT_IDX = {c["name"]: i for i, c in enumerate(CATEGORIES)}

SYMBOL_SIZE = {
    "gateway": 55, "ap": 48, "switch": 48,
    "router": 44, "server": 36, "nas": 36, "client": 18, "unknown": 16,
}
SYMBOL_SHAPE = {
    "gateway": "rect", "switch": "rect", "ap": "circle",
    "router": "roundRect", "server": "roundRect",
}
TIER_COLORS = {1: "#ff4757", 2: "#ffd43b", 3: "#74c0fc"}


def _label(dev: dict) -> str:
    """hostname > vendor+MAC_suffix > IP"""
    h = (dev.get("hostname") or "").split(".")[0].strip()
    if h and h not in ("?", "-", ""):
        return h
    vendor = dev.get("vendor") or ""
    mac = (dev.get("mac") or "").replace(":", "")
    suffix = mac[-4:].upper()
    if vendor:
        short = vendor.split()[0][:12]
        return f"{short}_{suffix}" if suffix else short
    return dev.get("ip") or suffix or "?"


def build_topology(data: dict) -> dict:
    nodes, links = [], []
    all_ips = set()

    snap_by_ip = {d["ip"]: d for d in data.get("devices", []) if d.get("ip")}

    for ip, (label, cat, tier) in TIER_NODES.items():
        dev = snap_by_ip.get(ip, {})
        alive = dev.get("icmp", {}).get("alive", False) if dev else (tier <= 2)
        mac = dev.get("mac", "")
        color = TIER_COLORS[tier] if alive else "#495057"
        nodes.append({
            "id": ip, "name": label,
            "symbol": SYMBOL_SHAPE.get(cat, "circle"),
            "symbolSize": SYMBOL_SIZE.get(cat, 40),
            "value": tier, "category": CAT_IDX.get(cat, 7),
            "label": {"show": True, "fontSize": 12, "fontWeight": "bold",
                      "color": "#ffffff", "distance": 6},
            "itemStyle": {"color": color, "shadowBlur": 15 if alive else 0,
                          "shadowColor": color},
            "tooltip": {"content": f"<b>{label}</b><br>IP: {ip}<br>MAC: {mac}<br>"
                                   f"Tier: {tier}<br>Status: {'Online' if alive else 'Offline'}"},
        })
        all_ips.add(ip)

    for src, dst, elabel in TIER_EDGES:
        if src in all_ips and dst in all_ips:
            links.append({
                "source": src, "target": dst,
                "lineStyle": {"color": "#666", "width": 2},
                "label": {"show": True, "formatter": elabel,
                          "fontSize": 9, "color": "#aaa"},
            })

    tier_ips = set(TIER_NODES.keys())
    for dev in data.get("devices", []):
        ip = dev.get("ip")
        if not ip or ip in tier_ips:
            continue
        mac = dev.get("mac", "")
        dev_type = (dev.get("type") or "client").lower()
        subnet = dev.get("subnet") or ""
        alive = dev.get("icmp", {}).get("alive", False)
        parent = SUBNET_PARENT.get(subnet, "192.168.1.50")
        label = _label(dev)
        show_label = bool(dev.get("hostname") and dev["hostname"] not in ("?", "-"))

        nodes.append({
            "id": ip, "name": label,
            "symbol": SYMBOL_SHAPE.get(dev_type, "circle"),
            "symbolSize": SYMBOL_SIZE.get(dev_type, SYMBOL_SIZE["client"]),
            "value": 3, "category": CAT_IDX.get(dev_type, CAT_IDX["unknown"]),
            "label": {"show": show_label, "fontSize": 10, "color": "#e9ecef",
                      "distance": 4},
            "itemStyle": {"color": "#74c0fc" if alive else "#495057",
                          "shadowBlur": 8 if alive else 0, "shadowColor": "#74c0fc"},
            "tooltip": {"content": f"<b>{label}</b><br>IP: {ip}<br>MAC: {mac}<br>"
                                   f"Vendor: {dev.get('vendor') or '?'}<br>"
                                   f"Type: {dev_type}<br>"
                                   f"Status: {'Online' if alive else 'Offline'}<br>"
                                   f"Subnet: {subnet}"},
        })
        if parent in all_ips:
            links.append({
                "source": parent, "target": ip,
                "lineStyle": {"color": "#444", "width": 1,
                              "type": "solid" if alive else "dashed",
                              "curveness": 0.1},
            })
        all_ips.add(ip)

    devices = data.get("devices", [])
    online = sum(1 for d in devices if d.get("icmp", {}).get("alive"))
    return {
        "categories": CATEGORIES, "nodes": nodes, "links": links,
        "stats": {"total": len(devices), "online": online,
                  "tier_nodes": len(TIER_NODES),
                  "clients": len(nodes) - len(TIER_NODES)},
    }


def load_snapshot() -> dict:
    with open(SNAPSHOT) as f:
        return json.load(f)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/topology":
            try:
                body = json.dumps(build_topology(load_snapshot())).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


if __name__ == "__main__":
    port = int(os.environ.get("TOPOLOGY_PORT", "8766"))
    print(f"Topology API on :{port}  snapshot={SNAPSHOT}")
    with socketserver.TCPServer(("", port), Handler) as httpd:
        httpd.socket.setsockopt(1, 2, 1)
        httpd.serve_forever()
