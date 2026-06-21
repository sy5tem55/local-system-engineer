# reconnect_test.py — proves the Python FaustAgent survives a server restart
# (Python client <-> real Node server). Boots server, runs 2 agents through a planning
# round, KILLS + RESTARTS the server (same DB), confirms reconnect + converge again.
import asyncio, json, os, subprocess, time, urllib.request, urllib.error
from faust_agent_client import FaustAgent

PORT, DB = 8794, "/tmp/reconnect_py.sqlite"
BASE = f"http://127.0.0.1:{PORT}"
GATE2 = os.path.join(os.path.dirname(__file__), "..", "gate2-group-server")

def req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"content-type": "application/json"}
    if token: h["authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            t = resp.read().decode(); return resp.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, None

def auth(h, pw):
    s, d = req("POST", "/auth/register", {"handle": h, "password": pw})
    if s >= 400: _, d = req("POST", "/auth/login", {"handle": h, "password": pw})
    return d

def start_server():
    env = {**os.environ, "PORT": str(PORT), "DB_PATH": DB, "ADMIN_HANDLES": "sy5", "AGENT_HANDLES": "hermes,lse"}
    cp = subprocess.Popen(["node", "--import", "tsx", "src/index.ts"], cwd=GATE2, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(120):
        line = cp.stdout.readline()
        if "Faust running" in line: break
    import threading
    threading.Thread(target=lambda: [None for _ in iter(cp.stdout.readline, "")], daemon=True).start()
    return cp

async def on_cue(ctx):
    if ctx["phase"] == "tasking":
        peer = "lse" if ctx["handle"] == "hermes" else "hermes"
        return f"@{peer}: own your part [[DONE]]"
    return "agreed, looks good [[CONVERGED]]" if ctx["round"] >= 2 else f"{ctx['handle']} proposes: scope, MVP, measure"

async def converged_after(token, room_id, after_ts, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, msgs = await asyncio.to_thread(req, "GET", f"/rooms/{room_id}/messages", None, token)
        if any("PLAN CONVERGED" in m["content"] and m["ts"] > after_ts for m in (msgs or [])):
            return True
        await asyncio.sleep(0.2)
    return False

async def main():
    if os.path.exists(DB): os.remove(DB)
    print("boot server #1"); srv = start_server()
    admin = auth("sy5", "pw"); auth("hermes", "pw"); auth("lse", "pw")
    _, room = req("POST", "/rooms", {"name": "SY5L4N"}, token=admin["token"])
    print("room:", room["id"])

    agents = []
    for h in ("hermes", "lse"):
        a = FaustAgent(base_url=BASE, handle=h, password="pw", room="SY5L4N", on_cue=on_cue, log=(lambda hh: (lambda *x: print(f"  [{hh}]", *x)))(h))
        a.api_key = a.mint_api_key(); a.password = None      # durable-key only
        agents.append(a)
    tasks = [asyncio.create_task(a.start()) for a in agents]
    await asyncio.sleep(1.0)

    print("\n=== cycle 1 (fresh) ==="); t = int(time.time() * 1000)
    await asyncio.to_thread(req, "POST", f"/rooms/{room['id']}/messages", {"content": "/plan revamp onboarding"}, admin["token"])
    r1 = await converged_after(admin["token"], room["id"], t, 8)
    print("cycle 1 converged:", "OK" if r1 else "FAIL")
    _, dump = await asyncio.to_thread(req, "GET", f"/rooms/{room['id']}/messages", None, admin["token"])
    print("--- transcript ---")
    for mm in (dump or [])[-12:]:
        print(f"   [{mm['author'].get('name')}/{mm.get('role')}] {mm['content'][:90]}")

    print("\n=== KILL server, restart (same DB) ===")
    srv.kill(); await asyncio.sleep(1.5); srv = await asyncio.to_thread(start_server); print("server #2 up")
    print("waiting for agents to reconnect (backoff)..."); await asyncio.sleep(7)

    print("\n=== cycle 2 (after restart) ==="); t = int(time.time() * 1000)
    await asyncio.to_thread(req, "POST", f"/rooms/{room['id']}/messages", {"content": "/plan add api key scopes"}, admin["token"])
    ok2 = await converged_after(admin["token"], room["id"], t, 12)
    print("cycle 2 converged AFTER restart:", "RECONNECTION WORKS" if ok2 else "FAIL")

    for a in agents: a.stop()
    for tsk in tasks: tsk.cancel()
    srv.kill()
    os._exit(0 if ok2 else 1)

asyncio.run(main())
