#!/usr/bin/env python3
"""
push_topology_dashboard.py
Pushes the corrected ECharts network topology dashboard to Grafana.

Usage (from WSL):
  python3 push_topology_dashboard.py
  python3 push_topology_dashboard.py --url http://localhost:3002 --user admin --pass admin
"""
import json, sys, argparse, urllib.request, urllib.error

# ── Args ─────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--url",  default="http://localhost:3002")
ap.add_argument("--user", default="admin")
ap.add_argument("--pass", dest="password", default="admin")
args = ap.parse_args()

BASE = args.url.rstrip("/")
AUTH = (args.user, args.password)

# ── getOption script ─────────────────────────────────────────────────────────
# Runs in the browser — fetches topology directly from topology server.
# topology_api must be running: python3 echarts_topology.py (port 8766)
GET_OPTION = r"""
// ── Network Topology ─ fetches directly from topology API ───────────────────
let topo;
try {
  const r = await fetch('http://localhost:8766/topology');
  if (!r.ok) throw new Error('HTTP ' + r.status);
  topo = await r.json();
} catch(e) {
  return {
    backgroundColor: 'transparent',
    title: {
      text: '⚠ Topology API offline',
      subtext: 'From WSL: cd net-discovery && python3 echarts_topology.py',
      left: 'center', top: '40%',
      textStyle: { color: '#ff4757', fontSize: 16 },
      subtextStyle: { color: '#aaa', fontSize: 12 },
    },
  };
}

const total  = topo.stats?.total   ?? topo.nodes?.length ?? 0;
const online = topo.stats?.online  ?? 0;

return {
  backgroundColor: 'transparent',
  title: {
    text: 'Network Topology',
    subtext: `${total} devices · ${online} online`,
    left: 'center',
    textStyle:    { color: '#ffffff', fontSize: 18, fontWeight: 'bold' },
    subtextStyle: { color: '#aaaaaa', fontSize: 12 },
  },
  tooltip: {
    trigger: 'item',
    formatter: (p) => p.data?.tooltip?.content || `<b>${p.name}</b>`,
    backgroundColor: 'rgba(20,20,20,0.95)',
    borderColor: '#333',
    textStyle: { color: '#fff', fontSize: 12 },
  },
  legend: {
    orient: 'vertical',
    right: 10,
    top: 'center',
    textStyle: { color: '#cccccc', fontSize: 11 },
    data: (topo.categories ?? []).map(c => c.name),
  },
  series: [{
    type: 'graph',
    layout: 'force',
    force: {
      repulsion: 900,
      gravity: 0.05,
      edgeLength: [80, 200],
      layoutAnimation: true,
    },
    categories: topo.categories ?? [],
    data: topo.nodes ?? [],
    links: topo.links ?? [],
    roam: true,
    draggable: true,
    lineStyle: { color: '#555555', width: 1, curveness: 0.15 },
    emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
    selectedMode: 'single',
  }],
};
"""

# ── Dashboard JSON ────────────────────────────────────────────────────────────
DASHBOARD = {
    "uid":   "net-topology",
    "title": "Network Topology",
    "tags":  ["netobs", "topology"],
    "schemaVersion": 39,
    "refresh": "30s",
    "time": {"from": "now-1h", "to": "now"},
    "panels": [
        {
            "id": 1,
            "type": "volkovlabs-echarts-panel",
            "title": "Network Topology Map",
            "gridPos": {"x": 0, "y": 0, "w": 24, "h": 20},
            "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "targets": [],   # no datasource needed — getOption fetches directly
            "options": {
                "renderer": "canvas",
                "map": "none",
                "editorMode": "code",
                "getOption": GET_OPTION.strip(),
                "cacheTimeoutSeconds": 30,
            },
            "fieldConfig": {"defaults": {}, "overrides": []},
        }
    ],
}

# ── API helpers ───────────────────────────────────────────────────────────────
import base64

def _auth_header():
    token = base64.b64encode(f"{AUTH[0]}:{AUTH[1]}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

def api(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_auth_header(), method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode()
        print(f"  HTTP {e.code}: {msg[:200]}")
        return None

# ── Push ──────────────────────────────────────────────────────────────────────
print(f"Connecting to Grafana at {BASE} ...")

# Get org ID / check auth
org = api("GET", "/api/org")
if org is None:
    print("❌  Auth failed — check --user / --pass (default: admin/admin)")
    sys.exit(1)
print(f"✓  Authenticated — org: {org.get('name')}")

# Find existing dashboard to get its numeric id (needed for update)
existing = api("GET", "/api/dashboards/uid/net-topology")
dash_id = existing["dashboard"]["id"] if existing else None
folder_id = existing.get("meta", {}).get("folderId", 0) if existing else 0

payload = {
    "dashboard": {**DASHBOARD, "id": dash_id, "version": 0},
    "folderId": folder_id,
    "overwrite": True,
    "message": "fix: direct-fetch getOption — no Infinity needed",
}

result = api("POST", "/api/dashboards/db", payload)
if result and result.get("status") == "success":
    print(f"✓  Dashboard updated: {BASE}/d/net-topology/network-topology")
else:
    print(f"❌  Push failed: {result}")
    sys.exit(1)
