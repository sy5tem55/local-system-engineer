#!/usr/bin/env python3
"""Convert snapshot.json to ECharts graph topology. Serves GET /topology on port 8766."""
import json, http.server, socketserver
from pathlib import Path
from urllib.parse import urlparse

SNAPSHOT = Path("/home/sy5/projects/net-discovery/snapshot.json")

DEVICE_MAP = {
    "192.168.1.50":  {"label": "pfSense (LAN)",    "type": "gateway", "tier": 1},
    "192.168.5.1":   {"label": "pfSense (IoT)",    "type": "gateway", "tier": 1},
    "192.168.10.1":  {"label": "pfSense (MGMT)",   "type": "gateway", "tier": 1},
    "192.168.1.1":   {"label": "ASUS GT-BE19000",  "type": "ap",      "tier": 2},
    "192.168.5.2":   {"label": "Netgear GS308E",   "type": "switch",  "tier": 2},
    "192.168.5.3":   {"label": "Teltonika RUTX50", "type": "ap",      "tier": 2},
}

TIER_COLORS = {
    1: {"color": "#ff4757", "glow": "#ff6b81"},
    2: {"color": "#ffa502", "glow": "#ffbe76"},
    3: {"color": "#2ed573", "glow": "#7bed9f"},
}

TYPE_SYMBOLS = {
    "gateway": "rect", "switch": "rect", "ap": "circle",
    "server": "roundRect", "wired_client": "roundRect", "unknown": "emptyCircle",
}

SUBNET_GATEWAY = {
    "192.168.1.0/24":  "192.168.1.50",
    "192.168.5.0/24":  "192.168.5.1",
    "192.168.10.0/24": "192.168.10.1",
}

def load_snapshot():
    with open(SNAPSHOT) as f:
        return json.load(f)

def build_topology(data):
    nodes, links = [], []
    categories = [
        {"name": "Gateways", "itemStyle": {"color": "#ff4757"}},
        {"name": "Network",  "itemStyle": {"color": "#ffa502"}},
        {"name": "Clients",  "itemStyle": {"color": "#2ed573"}},
    ]
    for dev in data.get("devices", []):
        ip = dev.get("ip")
        if not ip: continue
        mac, hostname, dev_type, subnet = dev.get("mac",""), dev.get("hostname",""), dev.get("type","unknown"), dev.get("subnet","")
        alive = dev.get("icmp",{}).get("alive", False)
        override = DEVICE_MAP.get(ip)
        if override:
            label, tier, dev_type = override["label"], override["tier"], override["type"]
        elif dev_type == "gateway":
            label, tier = ip, 1
        elif dev_type in ("ap","switch"):
            label, tier = hostname or ip, 2
        else:
            label, tier = hostname or ip, 3
        display = label if len(label)<=20 else label[:18]+"…"
        symbol = TYPE_SYMBOLS.get(dev_type, "emptyCircle")
        sz = 50 if tier==1 else (40 if tier==2 else 18)
        ci = tier - 1
        tc = TIER_COLORS[tier]
        nodes.append({
            "id": ip, "name": display, "symbol": symbol, "symbolSize": sz,
            "value": tier, "category": ci,
            "label": {"show":True, "fontSize":10 if tier==3 else 13, "fontWeight":"bold" if tier<=2 else "normal", "color":"#ffffff", "distance":5},
            "tooltip": {"content": f"<b>{label}</b><br>IP: {ip}<br>MAC: {mac}<br>Type: {dev_type}<br>Status: {'Online' if alive else 'Offline'}<br>Subnet: {subnet}"},
            "itemStyle": {"color": tc["color"] if alive else "#636e72", "shadowBlur": 20 if alive else 5, "shadowColor": tc["glow"] if alive else "transparent"},
        })
    node_ips = {n["id"] for n in nodes}
    for dev in data.get("devices", []):
        ip = dev.get("ip")
        if not ip or ip in DEVICE_MAP: continue
        subnet = dev.get("subnet","")
        if subnet in SUBNET_GATEWAY:
            target = SUBNET_GATEWAY[subnet]
            if target in node_ips:
                alive = dev.get("icmp",{}).get("alive",False)
                links.append({"source":ip,"target":target,"lineStyle":{"color":"#636e72","width":1,"curveness":0.2,"type":"dashed" if not alive else "solid"}})
    return {"nodes":nodes,"links":links,"categories":categories,"stats":{"total":len(nodes),"online":sum(1 for d in data.get("devices",[]) if d.get("icmp",{}).get("alive"))}}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        path = urlparse(self.path).path
        if path=="/topology":
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            self.wfile.write(json.dumps(build_topology(load_snapshot())).encode())
        elif path=="/health":
            self.send_response(200)
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.wfile.write(b"Not Found")

if __name__=="__main__":
    with socketserver.TCPServer(("",8766),Handler) as httpd:
        print("Topology API on port 8766")
        httpd.serve_forever()
