import asyncio, json, os, subprocess, time, urllib.request, urllib.error
from faust_agent_client import FaustAgent
PORT, FAKE, DB = 8795, 8088, "/tmp/sidecar.sqlite"
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
    except urllib.error.HTTPError as e: return e.code, None

def auth(h, pw):
    s, d = req("POST", "/auth/register", {"handle": h, "password": pw})
    if s >= 400: _, d = req("POST", "/auth/login", {"handle": h, "password": pw})
    return d

def start_faust():
    env = {**os.environ, "PORT": str(PORT), "DB_PATH": DB, "ADMIN_HANDLES": "sy5", "AGENT_HANDLES": "hermes,lse"}
    cp = subprocess.Popen(["node", "--import", "tsx", "src/index.ts"], cwd=GATE2, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(120):
        if "Faust running" in cp.stdout.readline(): break
    import threading; threading.Thread(target=lambda: [None for _ in iter(cp.stdout.readline, "")], daemon=True).start()
    return cp

async def hermes_cue(ctx):
    if ctx["phase"] == "tasking": return "@lse: own the data workstream [[DONE]]"
    return "agreed, looks good [[CONVERGED]]" if ctx["round"] >= 2 else "hermes proposes: scope tight, ship MVP, measure"

async def main():
    if os.path.exists(DB): os.remove(DB)
    fake = subprocess.Popen(["python3", "_fake_lse_model.py", str(FAKE)], cwd=os.path.dirname(__file__) or ".")
    print("boot faust"); srv = start_faust()
    admin = auth("sy5", "pw"); auth("hermes", "pw"); auth("lse", "pw")
    _, room = req("POST", "/rooms", {"name": "SY5L4N"}, token=admin["token"])
    print("room:", room["id"])

    # hermes: scripted in-process agent
    hermes = FaustAgent(base_url=BASE, handle="hermes", password="pw", room="SY5L4N", on_cue=hermes_cue, log=lambda *x: None)
    hermes.api_key = hermes.mint_api_key(); hermes.password = None
    htask = asyncio.create_task(hermes.start())

    # lse: the REAL sidecar, as a subprocess, pointed at the fake model
    side_env = {**os.environ, "FAUST_BASE": BASE, "FAUST_PASSWORD": "pw", "FAUST_HANDLE": "lse",
                "FAUST_ROOM": "SY5L4N", "LSE_MODEL_URL": f"http://127.0.0.1:{FAKE}/v1/chat/completions"}
    side = subprocess.Popen(["python3", "lse-sidecar.py"], cwd=os.path.dirname(__file__) or ".",
                            env=side_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    await asyncio.sleep(3.0)  # let both subscribe

    print("\n=== /plan ==="); t = int(time.time() * 1000)
    await asyncio.to_thread(req, "POST", f"/rooms/{room['id']}/messages", {"content": "/plan revamp onboarding"}, admin["token"])
    ok = False
    for _ in range(50):
        _, msgs = await asyncio.to_thread(req, "GET", f"/rooms/{room['id']}/messages", None, admin["token"])
        if any("PLAN CONVERGED" in m["content"] and m["ts"] > t for m in (msgs or [])): ok = True; break
        await asyncio.sleep(0.3)

    _, dump = await asyncio.to_thread(req, "GET", f"/rooms/{room['id']}/messages", None, admin["token"])
    print("--- transcript ---")
    for m in (dump or [])[-9:]:
        print(f"   [{m['author'].get('name')}] {m['content'][:80]}")
    print("\nLSE sidecar participated + converged:", "✅ WORKS" if ok else "❌ FAIL")
    hermes.stop(); htask.cancel(); side.kill(); srv.kill(); fake.kill()
    os._exit(0 if ok else 1)

asyncio.run(main())
