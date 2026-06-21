"""lse-sidecar.py — keeps the LSE present in a Faust room, answers planning turn cues
by calling its model (llama-server), and — when GOETHE_PATH is set — EXECUTES the
`@lse:` assignments from the tasking ledger using Goethe's tools via a ReAct loop.

The LSE is an OpenWebUI tool (Goethe) and can't hold a socket, so this standalone
sidecar holds the Faust WebSocket. Planning turns -> model reasoning. After the human
approves the plan and tasking converges, the moderator posts a "TASKING COMPLETE"
ledger; this sidecar runs each `@lse: <task>` through GoetheExecutor (gates enforced)
and posts the result back to the room. Plan-approval-only: no extra gate on execution.

Env:
  FAUST_BASE (http://localhost:8787)   FAUST_KEY (fa_…, preferred)   FAUST_PASSWORD (fallback)
  FAUST_ROOM (SY5L4N)                  FAUST_HANDLE (lse)
  LSE_MODEL_URL (http://localhost:8080/v1/chat/completions)   LSE_MODEL_ID (default)   LSE_MODEL_KEY
  GOETHE_PATH    path to goethe-v0.2.1.py — set to ENABLE execution (unset = reason-only)
  GOETHE_WORKDIR, GOETHE_LOG, GOETHE_MAX_STEPS   optional valve/loop overrides
Run:  pip install websockets ; FAUST_KEY=fa_… GOETHE_PATH=…/goethe-v0.2.1.py python3 lse-sidecar.py
"""
import asyncio
import json
import os
import re
import urllib.request

from faust_agent_client import FaustAgent

_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

FAUST_BASE = os.environ.get("FAUST_BASE", "http://localhost:8787")
FAUST_KEY = os.environ.get("FAUST_KEY")
FAUST_PASSWORD = os.environ.get("FAUST_PASSWORD")
ROOM = os.environ.get("FAUST_ROOM", "SY5L4N")
HANDLE = os.environ.get("FAUST_HANDLE", "lse")
MODEL_URL = os.environ.get("LSE_MODEL_URL", "http://localhost:8080/v1/chat/completions")
MODEL_ID = os.environ.get("LSE_MODEL_ID", "default")
MODEL_KEY = os.environ.get("LSE_MODEL_KEY")
MAX_TOKENS = int(os.environ.get("LSE_MAX_TOKENS", "512"))
GOETHE_PATH = os.environ.get("GOETHE_PATH")  # set => execution enabled

PERSONA = (
    "You are 'lse' (the Local System Engineer), a participant in a Faust planning room "
    "with another agent ('hermes') and a human admin ('sy5'). Speak only when it is your "
    "turn. Be concise and specific; build on what others said, don't repeat. "
    "In PLANNING: propose or refine the plan in <=120 words; end with the exact token "
    "[[CONVERGED]] once you genuinely agree with the current plan. "
    "In TASKING: assign concrete work to peers as '@handle: <task>' and end with [[DONE]] "
    "once your assignments are placed."
)


def _call_model(messages):
    body = json.dumps({"model": MODEL_ID, "messages": messages, "stream": False,
                       "max_tokens": MAX_TOKENS}).encode()
    headers = {"content-type": "application/json"}
    if MODEL_KEY:
        headers["authorization"] = f"Bearer {MODEL_KEY}"
    req = urllib.request.Request(MODEL_URL, data=body, headers=headers, method="POST")
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
        print(f"[lse-sidecar] model call failed: {e}")
        return None


# ── Execution: run @lse assignments from the tasking ledger via Goethe ───────────
_executor = None
_done_ledgers = set()   # message ids already executed (dedupe re-broadcasts)
_LEDGER_RE = re.compile(rf"→\s*@{re.escape(HANDLE)}:\s*(.+)")


def _make_executor():
    if not GOETHE_PATH:
        return None
    from goethe_executor import GoetheExecutor
    valves = {}
    if os.environ.get("GOETHE_LOG"):
        valves["LOG_FILE"] = os.environ["GOETHE_LOG"]
    if os.environ.get("GOETHE_WORKDIR"):
        valves["DEFAULT_WORKING_DIR"] = os.environ["GOETHE_WORKDIR"]
    return GoetheExecutor(
        goethe_path=GOETHE_PATH, model_url=MODEL_URL, model_id=MODEL_ID, model_key=MODEL_KEY,
        valves=valves, max_steps=int(os.environ.get("GOETHE_MAX_STEPS", "8")),
        log=lambda *a: print("[lse-sidecar]", *a),
    )


def make_on_message(agent):
    """Watch for the TASKING COMPLETE ledger; execute @lse assignments via Goethe."""
    def on_message(m):
        if _executor is None:
            return
        author = (m.get("author") or {}).get("name")
        content = m.get("content", "")
        if author != "moderator" or "TASKING COMPLETE" not in content:
            return
        mid = m.get("id")
        if mid in _done_ledgers:
            return
        _done_ledgers.add(mid)
        tasks = [t.strip() for t in _LEDGER_RE.findall(content)]
        if not tasks:
            return
        print(f"[lse-sidecar] ledger: {len(tasks)} task(s) assigned to {HANDLE}; executing")
        asyncio.get_event_loop().create_task(_execute_all(agent, tasks))
    return on_message


async def _execute_all(agent, tasks):
    for task in tasks:
        await agent._post(f"▶ executing: {task}")
        try:
            result = await asyncio.to_thread(_executor.run, task)
            ans = result.get("answer", "(no answer)")
            steps = result.get("steps")
            await agent._post(f"✅ done ({steps} step(s)): {task}\n{ans}")
        except Exception as e:  # noqa: BLE001
            await agent._post(f"❌ execution failed: {task}\n{e}")


async def main():
    global _executor
    try:
        _executor = _make_executor()
    except Exception as e:  # noqa: BLE001
        # NEVER let execution setup block joining the room — degrade to reason-only.
        print(f"[lse-sidecar] executor init FAILED ({e}); continuing WITHOUT execution. "
              f"Planning still works. Fix GOETHE_PATH / deps to enable execution.")
        _executor = None
    agent = FaustAgent(base_url=FAUST_BASE, handle=HANDLE, room=ROOM, on_cue=on_cue,
                       api_key=FAUST_KEY, password=FAUST_PASSWORD)
    agent.on_message = make_on_message(agent)
    if not FAUST_KEY and FAUST_PASSWORD:
        try:
            agent.api_key = agent.mint_api_key()
            print(f"[lse-sidecar] minted API key (store as FAUST_KEY): {agent.api_key}")
        except Exception as e:  # noqa: BLE001
            print(f"[lse-sidecar] key mint failed, will login per-connect: {e}")
    print(f"[lse-sidecar] faust={FAUST_BASE} room={ROOM} handle={HANDLE} model={MODEL_URL}")
    print(f"[lse-sidecar] execution: {'ENABLED via ' + GOETHE_PATH if _executor else 'disabled (set GOETHE_PATH)'}")
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
