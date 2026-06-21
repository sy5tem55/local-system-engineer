#!/usr/bin/env python3
"""Provision durable Faust API keys for agents (admin-issued; no agent passwords).

Prompts (hidden) for the admin password, then issues an API key for each agent handle.
  python3 provision-keys.py            # default agents: lse hermes
  python3 provision-keys.py lse hermes qwen
Env: FAUST_BASE (http://localhost:8787), FAUST_ADMIN (sy5)
"""
import getpass, json, os, sys, urllib.request, urllib.error

BASE = os.environ.get("FAUST_BASE", "http://localhost:8787").rstrip("/")
ADMIN = os.environ.get("FAUST_ADMIN", "sy5")
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never proxy localhost


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"content-type": "application/json"}
    if token:
        h["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with _OPENER.open(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "null")
        except Exception:
            return e.code, None
    except Exception as e:
        print(f"connection error to {BASE}: {e}"); sys.exit(2)


def main():
    agents = sys.argv[1:] or ["lse", "hermes"]
    pw = getpass.getpass(f"Faust admin ({ADMIN}) password: ")
    st, d = call("POST", "/auth/login", {"handle": ADMIN, "password": pw})
    if not d or "token" not in d:
        print(f"login failed ({st}): {d}"); sys.exit(1)
    if not d.get("isAdmin"):
        print(f"NOTE: {ADMIN} is not admin yet — issuing keys for others will 403. "
              f"Post one message in a room as {ADMIN} to self-promote, then retry.")
    token = d["token"]
    print()
    for h in agents:
        st, k = call("POST", "/auth/key", {"label": f"{h}-faust", "for": h}, token=token)
        if st == 201 and k and k.get("key"):
            print(f"{h:10} FAUST_KEY={k['key']}   (owner {k.get('owner')})")
        else:
            print(f"{h:10} FAILED ({st}): {k}")


if __name__ == "__main__":
    main()
