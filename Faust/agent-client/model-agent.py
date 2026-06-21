#!/usr/bin/env python3
"""model-agent.py — generic reconnecting Faust PLANNING agent backed by any
OpenAI-compatible model endpoint. Use it to put a model (e.g. Claude via the OWUI
Opus preset) into a Faust planning room. Reasoning-only (planning + tasking turns);
for tool EXECUTION see lse-sidecar.py + goethe_executor.py.

Env:
  FAUST_BASE (http://localhost:8787)   FAUST_KEY (fa_…, required)   FAUST_HANDLE (required)
  FAUST_ROOM (SY5L4N)
  MODEL_URL  (required)   e.g. http://localhost:3000/api/chat/completions   (OWUI)
  MODEL_ID   (default)    model/preset id, e.g. claude-opus-4-6
  MODEL_KEY              bearer for the model endpoint (OWUI API key / provider key)
  AGENT_PERSONA         optional system-prompt override
  MODEL_MAX_TOKENS (700)
Run (Claude via OWUI):
  FAUST_KEY=fa_… FAUST_HANDLE=claude \
    MODEL_URL=http://localhost:3000/api/chat/completions MODEL_ID=claude-opus-4-6 MODEL_KEY=<owui key> \
    python3 model-agent.py
"""
import asyncio
import json
import os
import urllib.request

from faust_agent_client import FaustAgent

_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

FAUST_BASE = os.environ.get("FAUST_BASE", "http://localhost:8787")
FAUST_KEY = os.environ.get("FAUST_KEY")
HANDLE = os.environ.get("FAUST_HANDLE")
ROOM = os.environ.get("FAUST_ROOM", "SY5L4N")
MODEL_URL = os.environ.get("MODEL_URL")
MODEL_ID = os.environ.get("MODEL_ID", "default")
MODEL_KEY = os.environ.get("MODEL_KEY")
MAX_TOKENS = int(os.environ.get("MODEL_MAX_TOKENS", "700"))

PERSONA = os.environ.get("AGENT_PERSONA") or (
    f"You are '{HANDLE}', a participant in a Faust multi-agent planning room with other agents "
    f"and a human admin ('sy5'). Speak only on your turn; be concise and specific; build on prior "
    f"points, don't repeat. In PLANNING: propose or refine the plan in <=120 words; end with the "
    f"exact token [[CONVERGED]] once you genuinely agree with the current plan. In TASKING: assign "
    f"concrete work to peers as '@handle: <task>' and end with [[DONE]] once your assignments are placed."
)


def _call_model(messages):
    body = json.dumps({"model": MODEL_ID, "messages": messages, "stream": False,
                       "max_tokens": MAX_TOKENS}).encode()
    h = {"content-type": "application/json"}
    if MODEL_KEY:
        h["authorization"] = f"Bearer {MODEL_KEY}"
    req = urllib.request.Request(MODEL_URL, data=body, headers=h, method="POST")
    with _NOPROXY.open(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")


async def on_cue(ctx):
    transcript = "\n".join(
        f"{(m.get('author') or {}).get('name')}: {m.get('content')}"
        for m in ctx["history"] if m.get("content")
    )
    if ctx["phase"] == "planning":
        user = (f"OBJECTIVE: {ctx['objective']}\n\nROOM SO FAR:\n{transcript}\n\n"
                f"It is your turn (planning round {ctx['round']}). Respond per the protocol.")
    else:
        user = (f"ROOM SO FAR:\n{transcript}\n\nIt is your turn (tasking round {ctx['round']}). "
                f"Respond per the protocol.")
    messages = [{"role": "system", "content": PERSONA}, {"role": "user", "content": user}]
    try:
        return await asyncio.to_thread(_call_model, messages)
    except Exception as e:  # noqa: BLE001
        print(f"[{HANDLE}] model call failed: {e}")
        return None


async def main():
    if not (FAUST_KEY and HANDLE and MODEL_URL):
        raise SystemExit("set FAUST_KEY, FAUST_HANDLE, MODEL_URL")
    agent = FaustAgent(base_url=FAUST_BASE, handle=HANDLE, room=ROOM, on_cue=on_cue, api_key=FAUST_KEY)
    print(f"[{HANDLE}] faust={FAUST_BASE} room={ROOM} model={MODEL_URL} id={MODEL_ID}")
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
