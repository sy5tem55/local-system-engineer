#!/usr/bin/env python3
"""echarts_topology.py — Convert snapshot.json → ECharts graph data, serve on port 8766."""

import json, http.server, socketserver
from pathlib import Path
from urllib.parse import urlparse

SNAPSHOT_PATH = Path("/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/net-discovery/snapshot.json")

TIER_NODES = {
    "192.168.1.50": ("pfSense LAN",      "gateway", 1),
    "192.168.5.1":  ("pfSense OPT1",     "gateway", 1),
    "192.168.10.1": ("pfSense OPT2",     "gateway", 1),
    "192.168.1.1":  ("ASUS GT-BE19000",  "ap",      2),
    "192.168.5.2":  ("Netgear GS308E",   "switch",  2),
    "192.168.5.3":  ("Teltonika RUTX50", "router",  2),
}
TIER_EDGES = [
    ("192.168.1.50", "192.168.1.1",  "LAN"),
    ("192.168.1.50", "192.168.5.1",  "OPT1"),
    ("192.168.5.1",  "192.168.5.2",  "OPT1"),
    ("192.168.5.2",  "192.168.5.3",  "uplink"),
    ("192.168.5.1",  "192.168.10.1", "OPT2"),
]
SUBNET_PARENTS = {
    "192.168.1.0/24":  "192.168.1.1",
    "192.168.5.0/24":  "192.168.5.2",
    "192.168.10.0/24": "192.168.10.1",
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
SYMBOL_SIZE  = {"gateway":55,"ap":48,"switch":48,"router":44,"server":36,"nas":36,"client":18,"unknown":16}
SYMBOL_SHAPE = {"gateway":"rect","switch":"rect","ap":"circle","router":"roundRect","server":"roundRect"}
TIER_COLORS  = {1:"#ff4757", 2:"#ffd43b", 3:"#74c0fc"}

def _label(dev):
    h = (dev.get("hostname") or "").split(".")[0].strip()
    if h and h not in ("?","-",""):
        return h
    vendor = dev.get("vendor") or ""
    mac    = (dev.get("mac") or "").replace(":","")
    suffix = mac[-4:].upper()
    if vendor:
        short = vendor.split()[0][:12]
        return f"{short}_{suffix}" if suffix else short
    return dev.get("ip") or suffix or "?"

def build_topology(data):
    nodes, links, all_ips = [], [], set()
    snap_by_ip = {d["ip"]: d for d in data.get("devices",[]) if d.get("ip")}
    for ip,(label,cat,tier) in TIER_NODES.items():
        dev   = snap_by_ip.get(ip,{})
        alive = dev.get("icmp",{}).get("alive",False) if dev else (tier<=2)
        mac   = dev.get("mac","")
        color = TIER_COLORS[tier] if alive else "#495057"
        nodes.append({"id":ip,"name":label,"symbol":SYMBOL_SHAPE.get(cat,"circle"),
            "symbolSize":SYMBOL_SIZE.get(cat,40),"value":tier,"category":CAT_IDX.get(cat,7),
            "label":{"show":True,"fontSize":12,"fontWeight":"bold","color":"#ffffff","distance":6},
            "itemStyle":{"color":color,"shadowBlur":15 if alive else 0,"shadowColor":color},
            "tooltip":{"content":f"<b>{label}</b><br>IP: {ip}<br>MAC: {mac}<br>Tier: {tier}<br>Status: {'Online' if alive else 'Offline'}"}})
        all_ips.add(ip)
    for src,dst,elabel in TIER_EDGES:
        if src in all_ips and dst in all_ips:
            links.append({"source":src,"target":dst,
                "lineStyle":{"color":"#666","width":2},
                "label":{"show":True,"formatter":elabel,"fontSize":9,"color":"#aaa"}})
    tier_ips = set(TIER_NODES.keys())
    for dev in data.get("devices",[]):
        ip = dev.get("ip")
        if not ip or ip in all_ips: continue
        mac      = dev.get("mac","")
        dev_type = (dev.get("type") or "client").lower()
        subnet   = dev.get("subnet") or ""
        alive    = dev.get("icmp",{}).get("alive",False)
        parent   = SUBNET_PARENTS.get(subnet,"192.168.1.50")
        label    = _label(dev)
        show_label = bool(dev.get("hostname") and dev["hostname"] not in ("?","-"))
        nodes.append({"id":ip,"name":label,"symbol":SYMBOL_SHAPE.get(dev_type,"circle"),
            "symbolSize":SYMBOL_SIZE.get(dev_type,SYMBOL_SIZE["client"]),
            "value":3,"category":CAT_IDX.get(dev_type,CAT_IDX["unknown"]),
            "label":{"show":show_label,"fontSize":10,"color":"#e9ecef","distance":4},
            "itemStyle":{"color":"#74c0fc" if alive else "#495057","shadowBlur":8 if alive else 0,"shadowColor":"#74c0fc"},
            "tooltip":{"content":f"<b>{label}</b><br>IP: {ip}<br>MAC: {mac}<br>Vendor: {dev.get('vendor') or '?'}<br>Type: {dev_type}<br>Status: {'Online' if alive else 'Offline'}<br>Subnet: {subnet}"}})
        if parent in all_ips:
            links.append({"source":parent,"target":ip,
                "lineStyle":{"color":"#444","width":1,"type":"solid" if alive else "dashed","curveness":0.1}})
        all_ips.add(ip)
    devices = data.get("devices",[])
    online  = sum(1 for d in devices if d.get("icmp",{}).get("alive"))
    return {"categories":CATEGORIES,"nodes":nodes,"links":links,
            "stats":{"total":len(devices),"online":online,"tier_nodes":len(TIER_NODES),"clients":len(nodes)-len(TIER_NODES)}}

def load_snapshot():
    with open(SNAPSHOT_PATH) as f:
        return json.load(f)

class TopologyHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._serve_html()
        elif path in ("/topology", "/data.json"):
            self._serve_json()
        else:
            self.send_error(404)

    def _serve_json(self):
        topo = build_topology(load_snapshot())
        body = json.dumps(topo).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self):
        topo = build_topology(load_snapshot())
        html = HTML.replace("{DATA_JSON}", json.dumps(topo)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, fmt, *args): pass

HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Network Topology</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>body{margin:0;background:#1a1a1a;color:#eee;font-family:sans-serif}
#chart{width:100vw;height:100vh}
#stats{position:absolute;top:10px;left:10px;background:rgba(0,0,0,0.7);padding:10px;border-radius:6px;pointer-events:none;z-index:10}</style>
</head><body>
<div id="stats"></div><div id="chart"></div>
<script>
const DATA={DATA_JSON};
const chart=echarts.init(document.getElementById('chart'));
const s=DATA.stats;
document.getElementById('stats').innerHTML='<b>Topology</b><br>Total: '+s.total+' | Online: '+s.online+'<br>Tier: '+s.tier_nodes+' | Clients: '+s.clients;
chart.setOption({backgroundColor:'#1a1a1a',
  tooltip:{trigger:'item',formatter:p=>p.data?.tooltip?.content||p.name},
  legend:{data:DATA.categories.map(c=>c.name),textStyle:{color:'#eee'},top:10,right:10},
  series:[{type:'graph',layout:'force',categories:DATA.categories,data:DATA.nodes,links:DATA.links,
    roam:true,draggable:true,
    label:{show:true,position:'right',formatter:'{b}',color:'#eee'},
    force:{repulsion:800,edgeLength:120,gravity:0.1},
    lineStyle:{color:'source',curveness:0.3,width:2},
    emphasis:{focus:'adjacency',scale:1.1}}]});
window.addEventListener('resize',()=>chart.resize());
</script></body></html>"""

if __name__ == "__main__":
    PORT = 8766
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), TopologyHandler) as httpd:
        print(f"Serving topology on :{PORT}")
        httpd.serve_forever()
