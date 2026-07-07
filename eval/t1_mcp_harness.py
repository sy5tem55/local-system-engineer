"""
MCP-backed propose_fn implementation for eval/t1_feedback_loop.py.

This is the piece that was explicitly deferred when t1_feedback_loop.py was
built (2026-07-07): wiring the loop's injected propose_fn(history) callback
to an actual model and actual tool execution, instead of a unit-test stand-in.

ARCHITECTURE (confirmed live 2026-07-07 against node3090):
  - Model:      Qwen3.6-35B-A3B via llama-server's OpenAI-compatible API,
                localhost:8080/v1 (from node3090's own perspective).
  - Tools:      goethe_mcp v0.4.1, localhost:9700, MCP streamable-HTTP
                transport, endpoint /mcp, bearer-token auth.
  - Task dirs:  local to node3090 (e.g. under /tmp/lse/t0t1-eval/), so
                model inference, tool execution, and pytest scoring
                (t1_feedback_loop.run_pytest) are all co-located -- this
                script is meant to run FROM node3090, not LUCIFER.

TOKEN NOTE: node3090's actual running GOETHE_MCP_TOKEN does NOT match the
"GOETHE_MCP_TOKEN" item in Vaultwarden (confirmed by testing both) -- that
vault item is stale or belongs to a different instance (likely LUCIFER's).
The real value was read directly from the running process's environment.
This module takes the token as an explicit argument for that reason; it
does not assume the vault item is trustworthy. Worth fixing in Vaultwarden
separately -- not done here, out of scope for this pass.

HISTORY CONTRACT: each propose_fn call is deliberately self-contained. It
does NOT replay t1_feedback_loop's cross-round `history` back to the model
as a full transcript -- it only reads the LATEST user-turn content (the
original task prompt on the first attempt, or the fed-back pytest failure
text on a retry) and starts a fresh tool-calling sub-conversation from
there. The model rediscovers current file state itself via its own
read_file/execute_command calls each attempt, rather than the harness
replaying every prior tool call. This keeps prompt size bounded across
retries and avoids a contract mismatch with run_t1_task's own lightweight
history bookkeeping (which only appends a done-marker + feedback text per
round, not a full transcript) -- changing that contract was avoidable, so
this module adapts to it instead.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from openai import OpenAI

from t1_feedback_loop import TurnResult

DEFAULT_SYSTEM_PROMPT = (
    "You are a coding agent working in a local directory. You have tools to "
    "read files, write files, and run shell commands. Complete the task "
    "described by the user using those tools. When you are finished, reply "
    "with a plain text message and do NOT call any more tools -- that is "
    "how the harness knows you are done. Do not modify any file whose name "
    "starts with test_."
)


def _mcp_tool_to_openai_schema(tool) -> dict:
    """Convert one MCP Tool object into an OpenAI chat-completions tool schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (tool.description or "")[:1024],
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


async def _list_tools_async(mcp_url: str, token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [_mcp_tool_to_openai_schema(t) for t in result.tools]


async def _call_tool_async(mcp_url: str, token: str, name: str, arguments: dict) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            parts = [b.text for b in result.content if hasattr(b, "text")]
            return "\n".join(parts) if parts else "(no output)"


def list_tools_schema(mcp_url: str, token: str) -> list[dict]:
    """Fetch the live tool schema from goethe_mcp, converted for chat-completions."""
    return asyncio.run(_list_tools_async(mcp_url, token))


def call_tool(mcp_url: str, token: str, name: str, arguments: dict) -> str:
    """Execute one real tool call against goethe_mcp and return its text result."""
    return asyncio.run(_call_tool_async(mcp_url, token, name, arguments))


def make_propose_fn(
    llama_base_url: str,
    mcp_url: str,
    mcp_token: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_tool_rounds: int = 20,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    request_timeout: int = 180,
):
    """
    Build a propose_fn(history) -> TurnResult, backed by a real model and
    real MCP tool execution, matching the interface run_t1_task/run_t0_task
    expect (see eval/t1_feedback_loop.py).

    Fetches the tool schema from goethe_mcp once, at build time (not per
    call) -- the schema doesn't change mid-run and re-fetching every attempt
    would be wasted round trips.
    """
    client = OpenAI(base_url=llama_base_url, api_key="local")
    tools_schema = list_tools_schema(mcp_url, mcp_token)
    resolved_model = {"name": model}  # mutable box so the closure can cache the auto-detected id

    def propose_fn(history: list[dict]) -> TurnResult:
        if resolved_model["name"] is None:
            resolved_model["name"] = client.models.list().data[0].id

        latest_prompt = next(
            m["content"] for m in reversed(history) if m.get("role") == "user"
        )
        messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
        messages.append({"role": "user", "content": latest_prompt})

        tool_call_count = 0
        for _ in range(max_tool_rounds):
            resp = client.chat.completions.create(
                model=resolved_model["name"],
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                max_tokens=max_tokens,
                timeout=request_timeout,
            )
            msg = resp.choices[0].message
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in (msg.tool_calls or [])],
                }
            )

            if not msg.tool_calls:
                return TurnResult(
                    done=True,
                    meta={"tool_calls": tool_call_count, "hit_tool_round_cap": False},
                )

            for tc in msg.tool_calls:
                tool_call_count += 1
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                try:
                    result_text = call_tool(mcp_url, mcp_token, tc.function.name, args)
                except Exception as exc:  # noqa: BLE001 -- surface any MCP/tool failure to the model
                    result_text = f"ERROR calling tool: {exc}"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text[:4000],
                    }
                )

        # Ran out of tool-call rounds within this attempt without the model
        # stopping on its own -- still return done=True so run_t1_task moves
        # on to scoring (a runaway model should show up as a test failure,
        # not hang the harness).
        return TurnResult(
            done=True,
            meta={"tool_calls": tool_call_count, "hit_tool_round_cap": True},
        )

    return propose_fn
