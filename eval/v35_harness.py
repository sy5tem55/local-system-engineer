#!/usr/bin/env python3
"""
v35_harness.py -- real-model, real-tool-execution harness for the LSE's
manually-graded evaluation suites (eval/test-suite-v3.5.md and successors).

RECONSTRUCTION NOTE (2026-07-12, TRAUM Thread 4, Prompt 4.5):
The original v35_harness.py (first described in eval/eval-report-v8.md,
2026-07-06 "Run 9") was never committed to this repo -- it lived only in
the node3090 scratch dir /tmp/lse/, which has since been cleared (confirmed
gone: see eval/t1_feedback_loop.py's module docstring and CURRENT-STATE.md's
"Outstanding" note, both dated 2026-07-07). This file is a from-scratch
reconstruction, not a recovered original. It is faithful to the ONLY
surviving description of what the original did (eval-report-v8.md's
"Harness:" line) and reuses the proven MCP-client-driving-a-real-model
pattern already committed in eval/t1_mcp_harness.py (built 2026-07-07,
confirmed live against node3090) rather than reinventing that wiring.

What it does, matching the eval-report-v8.md description verbatim:
  "connects to goethe_mcp over the standard MCP streamable-HTTP transport,
  drives llama-server's chat-completions API with the real tool schema, and
  actually executes every tool call the model makes through the same safety
  gates goethe.py always enforces (blocklist, privileged-path checks,
  sudo_delegation_block). This is a genuine behavioral test, not a
  simulation."

Differences from the coding-suite harness (t1_mcp_harness.py + t1_feedback_loop.py):
  - No pytest scoring loop -- the S/A/W/P suite (eval/test-suite-v3.5.md) is
    human-graded against a 0/2/3-point rubric per scenario, not pass/fail
    against a test file. This harness's job is to produce a faithful,
    complete transcript + tool-call log per scenario for a human (or an
    LLM-assisted grading pass) to score against that rubric -- it does not
    assign scores itself.
  - Supports MULTI-TURN scenario chains. Some v3.5 scenarios are explicitly
    NOT fresh-conversation (e.g. A2: "Run this as message 7, continuing in
    the same conversation as A1" -- exercises real context accumulation,
    the whole point of the test). The suite parser below detects this
    linkage from the prose ("continuing in the same conversation as <ID>")
    and replays prior scenarios' turns into the same message history before
    sending the new one, rather than starting fresh each time.

Usage:
  # Parse the suite and show what would run, without calling the model:
  python3 v35_harness.py --suite ../eval/test-suite-v3.5.md --list

  # Run the full suite for real:
  python3 v35_harness.py --suite ../eval/test-suite-v3.5.md \\
      --llama-url http://localhost:8080/v1 \\
      --mcp-url http://localhost:9700/mcp \\
      --mcp-token "$GOETHE_MCP_TOKEN" \\
      --output eval/v35_results_condition-b.json

  # Run one scenario only (e.g. to smoke-test the harness itself):
  python3 v35_harness.py --suite ../eval/test-suite-v3.5.md --scenario S1

Output: a JSON file, one record per scenario, containing: scenario id,
category, the full message transcript (system/user/assistant/tool turns),
tool_call_count, tool_calls (name + truncated args + truncated result, in
order -- this is what a grader uses to check search_kb hits, wrong-KB-hits,
sudo_delegation_block usage, etc.), wall_clock_seconds, and
hit_tool_round_cap (a runaway-model signal, never silently swallowed).

Token note (inherited from t1_mcp_harness.py, still true 2026-07-12):
GOETHE_MCP_TOKEN in Vaultwarden may not match the token a given instance is
actually running with. This harness takes the token as an explicit CLI arg
or GOETHE_MCP_TOKEN env var -- it does not read the vault itself.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__version__ = "0.1.0"

DEFAULT_SYSTEM_PROMPT_NOTE = (
    "No system prompt is baked into this harness. Pass --system-prompt-file "
    "pointing at the exact canonical prompt file under test (e.g. "
    "prompts/node4090-v0.6.0.md) -- the whole point of an A/B eval is that "
    "Condition A and Condition B run the SAME prompt version, per the "
    "traum-ab-design.md pre-registration. A harness default here would make "
    "it too easy to drift the prompt between runs without noticing."
)

TOOL_RESULT_CAP = 4000  # matches t1_mcp_harness.py's existing convention
MAX_TOOL_ROUNDS_DEFAULT = 20


# ---------------------------------------------------------------------------
# Suite parsing: eval/test-suite-v3.5.md's markdown structure ->
# a list of scenario "turns" grouped into conversation chains.
# ---------------------------------------------------------------------------

@dataclass
class ScenarioTurn:
    scenario_id: str          # e.g. "A2"
    category: str             # e.g. "A"
    title: str
    prompt_text: str
    continues_from: Optional[str] = None   # scenario_id this replays after, or None = fresh


@dataclass
class ConversationChain:
    chain_id: str              # id of the first (fresh) scenario in the chain
    turns: list = field(default_factory=list)   # list[ScenarioTurn], in send order


_HEADING_CATEGORY_RE = re.compile(r"^##\s+Category\s+(\S+)\s")
_HEADING_SCENARIO_RE = re.compile(r"^###\s+(\S+)\s+—\s+(.+?)(\s+\*\(.*\)\*)?\s*$")
_CONTINUES_RE = re.compile(
    r"continuing in the same conversation as\s+([A-Z]\d+)", re.IGNORECASE
)
_FRESH_HINT_RE = re.compile(r"\(fresh conversation\)", re.IGNORECASE)


def parse_suite(md_path: Path) -> list[ScenarioTurn]:
    """Parse eval/test-suite-v3.5.md (or a suite in the same format) into
    an ordered list of ScenarioTurn. Deliberately conservative: raises
    ValueError on anything that doesn't match the established v3.4/v3.5
    heading + fenced-code-block conventions, rather than guessing -- a
    silently-mis-parsed eval suite is worse than a loud parse failure.
    """
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    turns: list[ScenarioTurn] = []
    current_category = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m_cat = _HEADING_CATEGORY_RE.match(line)
        if m_cat:
            current_category = m_cat.group(1)
            i += 1
            continue

        m_scn = _HEADING_SCENARIO_RE.match(line)
        if m_scn:
            scenario_id = m_scn.group(1)
            title = m_scn.group(2).strip()
            # Scan forward to the "Send this" / "Message N" fenced code
            # block, and to any "continuing in the same conversation as X"
            # linkage note, stopping at the next scenario/category heading
            # or the horizontal rule that ends a scenario ("---").
            j = i + 1
            block_lines: list[str] = []
            in_fence = False
            continues_from = None
            while j < len(lines):
                l2 = lines[j]
                if _HEADING_SCENARIO_RE.match(l2) or _HEADING_CATEGORY_RE.match(l2):
                    break
                m_cont = _CONTINUES_RE.search(l2)
                if m_cont:
                    continues_from = m_cont.group(1)
                if l2.strip() == "---" and not in_fence and block_lines:
                    break
                if l2.strip().startswith("```"):
                    if in_fence:
                        break  # end of the prompt fence -- that's the block we want
                    else:
                        in_fence = True
                        j += 1
                        continue
                if in_fence:
                    block_lines.append(l2)
                j += 1
            if not block_lines:
                raise ValueError(
                    f"{md_path}:{i + 1}: scenario {scenario_id} has no fenced "
                    f"'Send this' / 'Message N' code block -- parser assumption "
                    f"violated, fix the parser or the suite, don't guess."
                )
            prompt_text = "\n".join(block_lines).strip()
            turns.append(
                ScenarioTurn(
                    scenario_id=scenario_id,
                    category=current_category or "?",
                    title=title,
                    prompt_text=prompt_text,
                    continues_from=continues_from,
                )
            )
            i = j
            continue
        i += 1

    if not turns:
        raise ValueError(f"{md_path}: parsed zero scenarios -- check heading format")
    return turns


def group_into_chains(turns: list) -> list:
    """Group ScenarioTurns into ConversationChains using each turn's
    continues_from link. A turn with continues_from=None starts a new
    chain; a turn with continues_from=<id> is appended to the chain that
    already contains <id> (raises if that chain isn't found -- e.g. suite
    order changed and the referenced scenario hasn't been parsed yet).
    """
    chains: list = []
    by_scenario_chain: dict = {}  # scenario_id -> ConversationChain

    for t in turns:
        if t.continues_from is None:
            chain = ConversationChain(chain_id=t.scenario_id, turns=[t])
            chains.append(chain)
            by_scenario_chain[t.scenario_id] = chain
        else:
            chain = by_scenario_chain.get(t.continues_from)
            if chain is None:
                raise ValueError(
                    f"scenario {t.scenario_id} says it continues from "
                    f"{t.continues_from}, but that scenario was not found "
                    f"(or hasn't been parsed yet) -- check suite order"
                )
            chain.turns.append(t)
            by_scenario_chain[t.scenario_id] = chain

    return chains


# ---------------------------------------------------------------------------
# MCP tool wiring -- lifted from eval/t1_mcp_harness.py's proven pattern
# (per-call connect/list/call, same as the confirmed-live 2026-07-07
# architecture) rather than re-deriving it.
# ---------------------------------------------------------------------------

def _lazy_import_mcp_openai():
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        from openai import OpenAI
        return ClientSession, streamablehttp_client, OpenAI
    except ImportError as exc:
        print(
            f"FATAL: missing dependency ({exc}). This harness needs the "
            f"'mcp' and 'openai' packages -- same environment t1_mcp_harness.py "
            f"runs in (node3090, per its own docstring), not necessarily "
            f"LUCIFER's default python3.",
            file=sys.stderr,
        )
        raise


def _mcp_tool_to_openai_schema(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (tool.description or "")[:1024],
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


async def _list_tools_async(mcp_url: str, token: str) -> list:
    ClientSession, streamablehttp_client, _ = _lazy_import_mcp_openai()
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [_mcp_tool_to_openai_schema(t) for t in result.tools]


async def _call_tool_async(mcp_url: str, token: str, name: str, arguments: dict) -> str:
    ClientSession, streamablehttp_client, _ = _lazy_import_mcp_openai()
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            parts = [b.text for b in result.content if hasattr(b, "text")]
            return "\n".join(parts) if parts else "(no output)"


def list_tools_schema(mcp_url: str, token: str) -> list:
    return asyncio.run(_list_tools_async(mcp_url, token))


def call_tool(mcp_url: str, token: str, name: str, arguments: dict) -> str:
    return asyncio.run(_call_tool_async(mcp_url, token, name, arguments))


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------

def run_chain(
    chain,
    *,
    client,
    tools_schema: list,
    mcp_url: str,
    mcp_token: str,
    system_prompt: str,
    model: str,
    max_tool_rounds: int,
    request_timeout: int,
) -> list:
    """Run one ConversationChain start-to-finish, replaying each prior
    turn's real transcript (not just the prompt) into history before
    sending the next turn -- this is what makes A2's "message 7" test
    genuine rather than simulated context.

    Returns a list of per-scenario result dicts, one per turn in the chain.
    """
    messages: list = [{"role": "system", "content": system_prompt}] if system_prompt else []
    results = []

    for turn in chain.turns:
        messages.append({"role": "user", "content": turn.prompt_text})
        tool_call_count = 0
        tool_calls_log = []
        t0 = time.monotonic()
        hit_cap = False

        for _ in range(max_tool_rounds):
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                max_tokens=2048,
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
                break

            for tc in msg.tool_calls:
                tool_call_count += 1
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw_unparsed": tc.function.arguments}
                try:
                    result_text = call_tool(mcp_url, mcp_token, tc.function.name, args)
                except Exception as exc:  # noqa: BLE001 -- surface, never swallow
                    result_text = f"ERROR calling tool: {exc}"
                tool_calls_log.append(
                    {
                        "name": tc.function.name,
                        "args": args,
                        "result": result_text[:TOOL_RESULT_CAP],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text[:TOOL_RESULT_CAP],
                    }
                )
        else:
            hit_cap = True

        elapsed = time.monotonic() - t0
        final_text = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "assistant" and m.get("content")),
            "",
        )
        results.append(
            {
                "scenario_id": turn.scenario_id,
                "category": turn.category,
                "title": turn.title,
                "continues_from": turn.continues_from,
                "prompt_text": turn.prompt_text,
                "tool_call_count": tool_call_count,
                "tool_calls": tool_calls_log,
                "final_answer": final_text,
                "wall_clock_seconds": round(elapsed, 2),
                "hit_tool_round_cap": hit_cap,
            }
        )

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", required=True, type=Path, help="Path to a v3.5-format suite markdown file")
    ap.add_argument("--list", action="store_true", help="Parse and print scenario chains, do not run anything")
    ap.add_argument("--scenario", help="Run only this scenario id's chain (still replays earlier turns in its chain)")
    ap.add_argument("--output", type=Path, default=Path("v35_results.json"))
    ap.add_argument("--llama-url", default=os.environ.get("LLAMA_BASE_URL", "http://localhost:8080/v1"))
    ap.add_argument("--mcp-url", default=os.environ.get("GOETHE_MCP_URL", "http://localhost:9700/mcp"))
    ap.add_argument("--mcp-token", default=os.environ.get("GOETHE_MCP_TOKEN"))
    ap.add_argument("--model", default=os.environ.get("LLAMA_MODEL_ID"), help="If unset, auto-detects via /v1/models")
    ap.add_argument("--system-prompt-file", type=Path, help=DEFAULT_SYSTEM_PROMPT_NOTE)
    ap.add_argument("--max-tool-rounds", type=int, default=MAX_TOOL_ROUNDS_DEFAULT)
    ap.add_argument("--request-timeout", type=int, default=180)
    args = ap.parse_args()

    turns = parse_suite(args.suite)
    chains = group_into_chains(turns)

    if args.list:
        for chain in chains:
            ids = " -> ".join(t.scenario_id for t in chain.turns)
            print(f"chain[{chain.chain_id}]: {ids}")
        print(f"\n{len(turns)} scenarios in {len(chains)} conversation chain(s).")
        return 0

    if args.scenario:
        chains = [c for c in chains if any(t.scenario_id == args.scenario for t in c.turns)]
        if not chains:
            print(f"scenario {args.scenario} not found in {args.suite}", file=sys.stderr)
            return 1

    if not args.mcp_token:
        print("FATAL: --mcp-token (or GOETHE_MCP_TOKEN env var) is required to run for real.", file=sys.stderr)
        return 1

    system_prompt = ""
    if args.system_prompt_file:
        system_prompt = args.system_prompt_file.read_text(encoding="utf-8")
    else:
        print(f"WARNING: {DEFAULT_SYSTEM_PROMPT_NOTE}", file=sys.stderr)

    _, _, OpenAI = _lazy_import_mcp_openai()
    client = OpenAI(base_url=args.llama_url, api_key="local")
    model = args.model or client.models.list().data[0].id
    tools_schema = list_tools_schema(args.mcp_url, args.mcp_token)
    print(f"Model: {model} | Tools available: {len(tools_schema)} | Chains to run: {len(chains)}", file=sys.stderr)

    all_results = []
    run_started = time.strftime("%Y-%m-%dT%H:%M:%S")
    for chain in chains:
        print(f"-- running chain {chain.chain_id} ({len(chain.turns)} turn(s)) --", file=sys.stderr)
        chain_results = run_chain(
            chain,
            client=client,
            tools_schema=tools_schema,
            mcp_url=args.mcp_url,
            mcp_token=args.mcp_token,
            system_prompt=system_prompt,
            model=model,
            max_tool_rounds=args.max_tool_rounds,
            request_timeout=args.request_timeout,
        )
        for r in chain_results:
            print(
                f"   {r['scenario_id']}: {r['tool_call_count']} tool call(s), "
                f"{r['wall_clock_seconds']}s"
                + (" [HIT ROUND CAP]" if r["hit_tool_round_cap"] else ""),
                file=sys.stderr,
            )
        all_results.extend(chain_results)

    output = {
        "harness_version": __version__,
        "suite_path": str(args.suite),
        "run_started": run_started,
        "model": model,
        "n_scenarios": len(all_results),
        "results": all_results,
    }
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {len(all_results)} scenario result(s) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
