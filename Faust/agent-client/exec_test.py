# exec_test.py — Track B end-to-end: plan → approve → tasking → ledger →
# the real lse-sidecar executes its @lse assignment via real Goethe → posts result.
import asyncio, glob, json, os, re, subprocess, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from faust_agent_client import FaustAgent

PORT, FAKE, DB = 8799, 8089, "/tmp/exec.sqlite"
BASE = f"http://127.0.0.1:{PORT}"
GATE2 = os.path.abspath("../gate2-group-server")
# Resolve the goethe tool: stable goethe.py first, else newest legacy goethe-v*.py.
_goethe = glob.glob("../../tools/goethe.py") or sorted(glob.glob("../../tools/goethe-v*.py"), key=os.path.getmtime)
GOETHE = os.path.abspath(_goethe[-1]) if _goethe else os.path.abspath("../../tools/goethe.py")

# ── one fake model serving planning + tasking + ReAct execution ─────────────────
def decide(content):
    if "Tools available:" in content:                       # executor ReAct loop
        if "Observation:" in content:
            return "Thought: I have the output.\nFinal Answer: Host kernel reported (uname=Linux)."
        return ('Thought: check the kernel.\nAction: execute_command\n'
                'Action Input: {"command": "echo KERNEL: && uname -s", "working_dir": "/tmp/lse"}')
    if "tasking round" in content:                          # lse's tasking turn
        return "@hermes: sanity-check the kernel report [[DONE]]"
    rounds = [int(x) for x in re.findall(r"planning round (\d+)", content)]
    if rounds and max(rounds) >= 2:
        return "lse: agreed, sound plan [[CONVERGED]]"
    return "lse proposes: verify the host kernel and report it"

class FakeModel(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); raw = self.rfile.read(n).decode()
        try: body = json.loads(raw)
        except Exception: body = {}
        content = "\n".join(m.get("content", "") for m in body.get("messages", []))
        out = json.dumps({"choices": [{"message": {"role": "assistant", "content": decide(content)}}]}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(out)

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
    threading.Thread(target=lambda: [None for _ in iter(cp.stdout.readline, "")], daemon=True).start()
    return cp

async def hermes_cue(ctx):
    if ctx["phase"] == "tasking":
        return "@lse: report the host kernel [[DONE]]"
    return "agreed, looks good [[CONVERGED]]" if ctx["round"] >= 2 else "hermes proposes: check the host"

async def main():
    if os.path.exists(DB): os.remove(DB)
    ThreadingHTTPServer.allow_reuse_address = True
    fake_srv = ThreadingHTTPServer(("127.0.0.1", FAKE), FakeModel)
    threading.Thread(target=fake_srv.serve_forever, daemon=True).start()
    print("boot faust"); srv = start_faust()
    admin = auth("sy5", "pw"); auth("hermes", "pw"); auth("lse", "pw")
    _, room = req("POST", "/rooms", {"name": "SY5L4N"}, token=admin["token"])

    # hermes: scripted; lse: the REAL sidecar with execution enabled
    hermes = FaustAgent(base_url=BASE, handle="hermes", password="pw", room="SY5L4N", on_cue=hermes_cue, log=lambda *x: None)
    hermes.api_key = hermes.mint_api_key(); hermes.password = None
    htask = asyncio.create_task(hermes.start())
    side_env = {**os.environ, "FAUST_BASE": BASE, "FAUST_PASSWORD": "pw", "FAUST_HANDLE": "lse",
                "FAUST_ROOM": "SY5L4N", "LSE_MODEL_URL": f"http://127.0.0.1:{FAKE}/v1/chat/completions",
                "GOETHE_PATH": GOETHE, "GOETHE_WORKDIR": "/tmp/lse", "GOETHE_LOG": "/tmp/lse/cmd.log"}
    side = subprocess.Popen(["python3", "lse-sidecar.py"], env=side_env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    threading.Thread(target=lambda: [print("   "+l.rstrip()) for l in iter(side.stdout.readline, "")], daemon=True).start()
    await asyncio.sleep(3.5)

    print("\n=== /plan ==="); 
    await asyncio.to_thread(req, "POST", f"/rooms/{room['id']}/messages", {"content": "/plan ship the kernel audit"}, admin["token"])
    async def wait(needle, ms):
        t0 = time.time()
        while time.time()-t0 < ms/1000:
            _, msgs = await asyncio.to_thread(req, "GET", f"/rooms/{room['id']}/messages", None, admin["token"])
            if any(needle in m["content"] for m in (msgs or [])): return True
            await asyncio.sleep(0.3)
        return False
    await wait("PLAN CONVERGED", 9000)
    print("=== /approve ==="); await asyncio.to_thread(req, "POST", f"/rooms/{room['id']}/messages", {"content": "/approve"}, admin["token"])
    await wait("TASKING COMPLETE", 9000)
    ok = await wait("✅ done", 15000)

    _, dump = await asyncio.to_thread(req, "GET", f"/rooms/{room['id']}/messages", None, admin["token"])
    print("\n──────── transcript (tail) ────────")
    for m in (dump or [])[-8:]:
        print(f"   [{m['author'].get('name')}] {m['content'][:90].replace(chr(10),' ⏎ ')}")
    print("\nLSE executed its assignment via Goethe + posted result:", "✅ WORKS" if ok else "❌ FAIL")
    hermes.stop(); htask.cancel(); side.kill(); srv.kill(); fake_srv.shutdown()
    os._exit(0 if ok else 1)

asyncio.run(main())
