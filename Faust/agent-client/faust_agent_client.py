"""faust_agent_client.py — reconnecting Faust client for autonomous Python agents.

Mirror of faust-agent-client.mjs. Handles all connection plumbing so an agent only
supplies reasoning via an `on_cue` coroutine:
  * durable auth with a long-lived API key (fa_…) — no re-login on reconnect
    (falls back to handle+password login if no key is given)
  * persistent WebSocket with exponential-backoff reconnect (1s→30s) + auto re-subscribe
  * websockets keepalive ping; backoff resets on a successful subscribe
  * parses the planning turn-cue "▶ @<handle> — your turn" and calls on_cue()

Deps: `pip install websockets` (REST uses the stdlib). Python 3.9+.

Usage
-----
    import asyncio
    from faust_agent_client import FaustAgent

    async def on_cue(ctx):
        # ctx = {phase, round, objective, history, handle, post}
        # planning -> end with [[CONVERGED]] when you agree
        # tasking  -> "@peer: <task>" and end with [[DONE]]
        return await my_model.generate(ctx)   # return the text to post

    agent = FaustAgent(base_url="http://localhost:8787", handle="hermes",
                       api_key=os.environ["FAUST_KEY"], room="SY5L4N", on_cue=on_cue)
    asyncio.run(agent.start())

Mint a durable key once:
    a = FaustAgent(base_url=..., handle="hermes", password="<pw>", room="SY5L4N")
    print(a.mint_api_key())   # -> fa_…  (store it; shown once)
"""
import asyncio
import json
import re
import urllib.request
import urllib.error
from urllib.parse import quote

import websockets

# REST calls must never go through an HTTP proxy (localhost would time out).
_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class FaustAgent:
    def __init__(self, base_url, handle, room, on_cue=None, on_message=None,
                 api_key=None, password=None, max_backoff=30, log=None):
        self.base = base_url.rstrip("/")
        self.wsbase = ("ws" + self.base[4:]) if self.base.startswith("http") else self.base
        self.handle = handle
        self.room_name = room
        self.on_cue = on_cue
        self.on_message = on_message
        self.api_key = api_key
        self.password = password
        self.max_backoff = max_backoff
        self.log = log or (lambda *a: print(f"[faust:{handle}]", *a))
        self.token = None
        self.room_id = None
        self.ws = None
        self.stopped = False
        self.recent = []
        self.objective = ""

    # ── REST (stdlib, blocking — only used at setup/reconnect prep) ──────────────
    def _req(self, method, path, body=None, token=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"content-type": "application/json"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with _NOPROXY.open(req, timeout=15) as r:
                txt = r.read().decode()
                return r.status, (json.loads(txt) if txt else None)
        except urllib.error.HTTPError as e:
            return e.code, None

    def _auth(self):
        if self.api_key:
            if not self.api_key.isascii() or "…" in self.api_key or "(" in self.api_key:
                raise RuntimeError(
                    f"FAUST_KEY looks like a placeholder, not a real key: {self.api_key!r}. "
                    "Use the full fa_ value (no '…', no '(lse)').")
            self.token = self.api_key
            return
        _, d = self._req("POST", "/auth/login", {"handle": self.handle, "password": self.password})
        if not d or "token" not in d:
            raise RuntimeError(f"login failed for {self.handle}")
        self.token = d["token"]

    def mint_api_key(self, label=None):
        """One-time: log in with a password and mint a durable API key."""
        if not self.password:
            raise RuntimeError("password required to mint a key")
        _, d = self._req("POST", "/auth/login", {"handle": self.handle, "password": self.password})
        self.token = d["token"]
        _, k = self._req("POST", "/auth/key", {"label": label or f"{self.handle}-bot"}, token=self.token)
        return k["key"]

    def _resolve_room(self):
        _, rooms = self._req("GET", "/rooms", token=self.token)
        room = next((x for x in (rooms or []) if x.get("name") == self.room_name or x.get("id") == self.room_name), None)
        if not room:
            raise RuntimeError(f"room not found: {self.room_name}")
        self.room_id = room["id"]
        self._req("POST", f"/rooms/{self.room_id}/join", token=self.token)  # idempotent

    # ── lifecycle ────────────────────────────────────────────────────────────────
    async def start(self):
        self.stopped = False
        self._auth()
        self._resolve_room()
        await self._run()

    def stop(self):
        self.stopped = True

    async def _post(self, text):
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps({"type": "send", "roomId": self.room_id, "content": text}))
            except Exception as e:  # noqa: BLE001
                self.log(f"post failed: {e}")

    async def _run(self):
        backoff = 0
        while not self.stopped:
            try:
                if not self.api_key:
                    self._auth()        # refresh session token; api_key is durable
                if not self.room_id:
                    self._resolve_room()
                url = f"{self.wsbase}/ws?token={quote(self.token)}"
                async with websockets.connect(url, ping_interval=25, ping_timeout=20) as ws:
                    self.ws = ws
                    await ws.send(json.dumps({"type": "subscribe", "roomId": self.room_id}))
                    backoff = 0
                    self.log(f"subscribed to {self.room_name}")
                    async for raw in ws:
                        await self._on_frame(raw)
            except Exception as e:  # noqa: BLE001
                self.log(f"disconnected: {e}")
            finally:
                self.ws = None
            if self.stopped:
                break
            delay = min(2 ** backoff, self.max_backoff)
            backoff = min(backoff + 1, 6)
            self.log(f"reconnecting in {delay}s")
            await asyncio.sleep(delay)

    async def _on_frame(self, raw):
        try:
            f = json.loads(raw)
        except Exception:  # noqa: BLE001
            return
        if f.get("type") != "message" or not f.get("message"):
            return
        m = f["message"]
        self.recent.append(m)
        if len(self.recent) > 50:
            self.recent.pop(0)
        if self.on_message:
            try:
                self.on_message(m)
            except Exception:  # noqa: BLE001
                pass
        c = m.get("content", "")
        mo = re.search(r"Objective:\s*(.+)", c)
        if mo:
            self.objective = mo.group(1).splitlines()[0].strip()
        author = (m.get("author") or {}).get("name")
        if author == "moderator" and f"@{self.handle}" in c and "your turn" in c:
            phase = "tasking" if "tasking round" in c else "planning"
            rm = re.search(r"round (\d+)/(\d+)", c)
            rnd = int(rm.group(1)) if rm else 1
            ctx = {"phase": phase, "round": rnd, "objective": self.objective,
                   "history": list(self.recent), "handle": self.handle, "post": self._post}
            try:
                reply = await self.on_cue(ctx) if self.on_cue else None
                if isinstance(reply, str) and reply.strip():
                    await self._post(reply.strip())
            except Exception as e:  # noqa: BLE001
                self.log(f"on_cue error: {e}")
