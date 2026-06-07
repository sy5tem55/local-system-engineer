#!/usr/bin/env python3
"""
backup_grafana_dashboards.py
Export all Grafana dashboards to JSON files.

Usage (from WSL):
  python3 backup_grafana_dashboards.py
  python3 backup_grafana_dashboards.py --url http://localhost:3002 --pass LSEgrafana2026

Output: grafana-dashboards/<uid>__<slug>.json
"""
import json, sys, argparse, urllib.request, urllib.error, base64
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--url",  default="http://localhost:3002")
ap.add_argument("--user", default="admin")
ap.add_argument("--pass", dest="password", default="LSEgrafana2026")
ap.add_argument("--out",  default="grafana-dashboards", help="Output directory")
args = ap.parse_args()

BASE = args.url.rstrip("/")
OUT  = Path(args.out)
OUT.mkdir(exist_ok=True)

def auth_header():
    token = base64.b64encode(f"{args.user}:{args.password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

def api_get(path):
    req = urllib.request.Request(BASE + path, headers=auth_header())
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()[:200]}")
        return None

# Verify auth
org = api_get("/api/org")
if org is None:
    print("❌  Auth failed")
    sys.exit(1)
print(f"✓  Connected to Grafana — org: {org.get('name')}")

# List all dashboards (folders too, but filter to dash-db)
search = api_get("/api/search?type=dash-db&limit=500")
if not search:
    print("❌  Could not list dashboards")
    sys.exit(1)

print(f"   Found {len(search)} dashboard(s)")

saved = []
for item in search:
    uid   = item.get("uid")
    title = item.get("title", "untitled")
    slug  = title.lower().replace(" ", "_").replace("/", "-")[:50]

    detail = api_get(f"/api/dashboards/uid/{uid}")
    if not detail:
        print(f"  ⚠  Skipped: {title} ({uid})")
        continue

    fname = OUT / f"{uid}__{slug}.json"
    fname.write_text(json.dumps(detail, indent=2))
    print(f"  ✓  {fname.name}")
    saved.append(str(fname))

print(f"\n✓  Saved {len(saved)} dashboard(s) to ./{args.out}/")
