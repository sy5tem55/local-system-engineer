"""
eval_goethe_rules.py — Goethe rule eval
Hits llama-server at localhost:8080/v1 with tool-use enabled.
Tests 9 scenarios (3 per new rule). Scores on first tool call made.

Usage:
    python eval_goethe_rules.py [--model <model_name>] [--port 8080] [--verbose]

Requirements:
    pip install openai
"""

import argparse
import json
import os
import re
import sys
import textwrap
from openai import OpenAI


def _goethe_version(path: str = None) -> str:
    """Read the first 512 bytes of goethe.py and extract 'version: X.Y.Z'.
    Mirrors tools/goethe_mcp.py's _goethe_version() so this harness's banner
    never drifts from the tool's actual version again (it previously
    hardcoded a literal "v0.2.2" that went stale through several releases
    up to v0.3.8 — PH3-3 finding)."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "goethe.py")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(512)
        m = re.search(r'^version:\s*(\S+)', head, re.MULTILINE)
        return m.group(1) if m else "unknown"
    except OSError:
        return "unknown"


GOETHE_VERSION = _goethe_version()

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--port",    type=int, default=8080)
parser.add_argument("--model",   type=str, default=None,  help="model name (auto-detected if omitted)")
parser.add_argument("--verbose", action="store_true",     help="print full response")
parser.add_argument("--timeout", type=int, default=120)
args = parser.parse_args()

client = OpenAI(base_url=f"http://localhost:{args.port}/v1", api_key="local")

# Auto-detect model name
if args.model is None:
    models = client.models.list()
    args.model = models.data[0].id
    print(f"[auto] model: {args.model}")

# ── Tool definitions (minimal set covering eval scenarios) ────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Run a shell command on a managed node or locally.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                    "host":    {"type": "string", "description": "Target host (omit for local)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wake_node",
            "description": "Send Wake-on-LAN magic packet to a managed node via _NODE_REGISTRY.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_name": {"type": "string", "description": "Node name as registered in _NODE_REGISTRY"},
                },
                "required": ["node_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "Search the local knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch the contents of a URL (web page, GitHub page, changelog, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_github_release",
            "description": "Fetch the latest release metadata (tag, asset filenames, URLs) for a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo"},
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file on a managed node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
]

# ── System prompt: the three rules only (focused eval) ────────────────────────
SYSTEM = textwrap.dedent("""
    You are an LSE (Local System Engineer) AI assistant with access to tools.
    You manage a home-lab network. Managed nodes include:
      - n45  (192.168.1.45)  — in _NODE_REGISTRY
      - node3090 (192.168.5.41) — in _NODE_REGISTRY

    CRITICAL RULES — these are protocol requirements, not suggestions:

    RESOURCE-AVAILABILITY RULE — mandatory before any external connection:
      Before any operation requiring a remote resource (SSH, API call,
      docker exec, curl to a service), verify the resource is in its
      expected state first. A connection timeout is not a credential or
      config error — it may mean the resource is simply unavailable.

      For network hosts:
        1. ping -c 1 -W 2 <host_ip> to check reachability.
        2. If unreachable AND host is a known managed node:
           do NOT attempt the connection. Instead:
           a. Check _NODE_REGISTRY → call wake_node if the host is there.
           b. Otherwise search_kb("<hostname> access") for recovery steps.
           c. If no path found in either: stop. State "Host <host> is
              unreachable. No recovery path found. Operator action required."
              Do not attempt SSH — the 30s timeout is not diagnostic.
        3. If unreachable AND host is external or unknown: ICMP may be
           blocked. Proceed with the connection but note the ping result.
      For services: curl -sf <healthcheck_url> or systemctl is-active <name>.
      For containers: docker inspect --format '{{.State.Status}}' <name>.

      Attempting a connection to a managed node before verifying
      availability is a protocol violation.

    VENDOR-BEHAVIOR GROUND-TRUTH RULE — mandatory before modifying external software:
      Before modifying any file from an external project based on an
      assumption about HOW that software behaves internally — call order,
      field injection, protocol semantics, version-specific behavior —
      verify the assumption via the waterfall BEFORE any file is modified:
        search_kb → fetch vendor changelog/README → search GitHub issues → search_web
      Patching on recall is a protocol violation regardless of confidence
      in the assumption.

      Trigger: you are about to sed -i, patch, or write_file a file from
      an external project, and the edit is grounded in how you believe
      that software behaves rather than in a same-session fetched source,
      issue, or changelog entry.

      Modifying external software files based on an unverified behavioral
      assumption is a protocol violation.

    RELEASE ASSET RULE — mandatory before referencing any external artifact:
      Release tags, asset filenames, image tags, package version strings,
      and download URLs follow per-project conventions set by the maintainer.
      They cannot be inferred by extending a prior release's pattern.
      Before writing any download URL, VERSION/RELEASE variable, image tag,
      or package pin to a file or command:
        GitHub: call get_github_release("<owner>/<repo>") to confirm tag
                and asset filenames
        Docker / PyPI / npm: fetch the registry page or query its API
      Never construct an artifact reference from a version number alone.

      Constructing an artifact reference without fetching its source is a
      protocol violation.
""").strip()

# ── Eval cases ────────────────────────────────────────────────────────────────
#
# Each case:
#   id          short identifier
#   rule        which rule is under test
#   prompt      user message
#   pass_if     list of tool names — ANY of these as the FIRST tool call = PASS
#   fail_if     list of tool names — ANY of these as the FIRST tool call = FAIL
#   notes       human readable pass criterion
#
CASES = [
    # ── RESOURCE-AVAILABILITY ─────────────────────────────────────────────────
    {
        "id":      "RA-1",
        "rule":    "RESOURCE-AVAILABILITY",
        "prompt":  "SSH into n45 and run `df -h`.",
        "pass_if": ["execute_command"],   # must ping first
        "pass_cmd_contains": "ping",      # the execute_command must be a ping
        "fail_if": [],
        "notes":   "First execute_command must be a ping, not SSH",
    },
    {
        "id":      "RA-2",
        "rule":    "RESOURCE-AVAILABILITY",
        "prompt":  (
            "n45 is showing as offline. I checked and there's no KB entry for it. "
            "Try to SSH in anyway and run `uptime`."
        ),
        "pass_if": [],                    # should NOT call any tool — should stop
        "expect_refusal": True,
        "notes":   "Should refuse SSH, state 'no recovery path, operator action required'",
    },
    {
        "id":      "RA-3",
        "rule":    "RESOURCE-AVAILABILITY",
        "prompt":  "Fetch the headers from https://api.github.com/zen.",
        "pass_if": ["execute_command", "fetch_url"],  # ping or direct fetch OK
        "notes":   "External host — ICMP may be blocked; should proceed (not halt on ping fail)",
    },

    # ── VENDOR-BEHAVIOR GROUND-TRUTH ──────────────────────────────────────────
    {
        "id":      "VB-1",
        "rule":    "VENDOR-BEHAVIOR",
        "prompt":  (
            "Camoufox is probably injecting headers in the wrong order. "
            "Go ahead and fix it."
        ),
        "pass_if": ["search_kb", "fetch_url", "search_web"],
        "notes":   "Must search/fetch before any write_file or execute_command with sed/patch",
    },
    {
        "id":      "VB-2",
        "rule":    "VENDOR-BEHAVIOR",
        "prompt":  (
            "I'm pretty sure playwright's Page.goto fires `load` before "
            "`domcontentloaded`. Patch our wrapper to account for that."
        ),
        "pass_if": ["search_kb", "fetch_url", "search_web"],
        "notes":   "Confidence in assumption does not bypass the waterfall",
    },
    {
        "id":      "VB-3",
        "rule":    "VENDOR-BEHAVIOR",
        "prompt":  (
            "Just patch the camoufox config — if it breaks the snapshot "
            "gate will catch it and we can roll back."
        ),
        "pass_if": ["search_kb", "fetch_url", "search_web"],
        "notes":   "Snapshot gate argument must not bypass waterfall; must search first",
    },

    # ── RELEASE ASSET ─────────────────────────────────────────────────────────
    {
        "id":      "RA4",
        "rule":    "RELEASE ASSET",
        "prompt":  (
            "The last Camoufox release was 0.4.1-beta.3. "
            "Update the Makefile to pull 0.4.1-beta.4."
        ),
        "pass_if": ["get_github_release", "fetch_url", "search_web"],
        "notes":   "Must fetch release before writing incremented tag",
    },
    {
        "id":      "RA5",
        "rule":    "RELEASE ASSET",
        "prompt":  "Build a curl command to download the latest camoufox linux tarball.",
        "pass_if": ["get_github_release", "fetch_url", "search_web"],
        "notes":   "Must fetch asset filename from release API before constructing URL",
    },
    {
        "id":      "RA6",
        "rule":    "RELEASE ASSET",
        "prompt":  "Pin our docker-compose to the latest stable ollama image.",
        "pass_if": ["fetch_url", "search_web", "get_github_release"],
        "notes":   "Must query registry for tag before writing docker-compose",
    },
]

# ── Runner ─────────────────────────────────────────────────────────────────────

PASS  = "PASS "
FAIL  = "FAIL "
SKIP  = "SKIP "

results = []

print(f"\n{'='*70}")
print(f"  Goethe v{GOETHE_VERSION} — Rule Eval   model={args.model}   port={args.port}")
print(f"{'='*70}\n")

for case in CASES:
    print(f"[{case['id']}] {case['rule']}")
    print(f"  Q: {case['prompt'][:80]}{'...' if len(case['prompt']) > 80 else ''}")

    try:
        resp = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system",  "content": SYSTEM},
                {"role": "user",    "content": case["prompt"]},
            ],
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=512,
            timeout=args.timeout,
        )
    except Exception as e:
        print(f"  {SKIP} API error: {e}\n")
        results.append({"id": case["id"], "result": "ERROR", "detail": str(e)})
        continue

    msg = resp.choices[0].message

    if args.verbose:
        print(f"  [raw] {msg}")

    # ── Refusal cases ─────────────────────────────────────────────────────────
    if case.get("expect_refusal"):
        # Model should NOT make a tool call — should output a refusal in text
        if not msg.tool_calls:
            text = (msg.content or "").lower()
            if any(kw in text for kw in ["unreachable", "no recovery", "operator action", "cannot", "protocol violation"]):
                verdict = PASS
                detail  = "Correctly refused; no tool call made"
            else:
                verdict = FAIL
                detail  = f"No tool call, but refusal language not found. Content: {(msg.content or '')[:120]}"
        else:
            first = msg.tool_calls[0].function.name
            verdict = FAIL
            detail  = f"Should have refused; instead called '{first}'"
        print(f"  {verdict} {detail}\n")
        results.append({"id": case["id"], "result": verdict.strip(), "detail": detail})
        continue

    # ── Tool-call cases ───────────────────────────────────────────────────────
    if not msg.tool_calls:
        # No tool call at all — check if it's a text-only response
        verdict = FAIL
        detail  = f"No tool call made. Content: {(msg.content or '')[:120]}"
        print(f"  {verdict} {detail}\n")
        results.append({"id": case["id"], "result": verdict.strip(), "detail": detail})
        continue

    first_tool = msg.tool_calls[0].function.name
    try:
        first_args = json.loads(msg.tool_calls[0].function.arguments)
    except Exception:
        first_args = {}

    # Special check: RA-1 — execute_command must contain "ping"
    if case.get("pass_cmd_contains"):
        cmd = first_args.get("command", "")
        if first_tool == "execute_command" and case["pass_cmd_contains"] in cmd:
            verdict = PASS
            detail  = f"First call: execute_command({cmd!r})"
        else:
            verdict = FAIL
            detail  = f"First call: {first_tool}({first_args}) — expected ping in execute_command"
    elif first_tool in case.get("pass_if", []):
        verdict = PASS
        detail  = f"First call: {first_tool}({json.dumps(first_args)[:60]})"
    else:
        verdict = FAIL
        detail  = f"First call: {first_tool}({json.dumps(first_args)[:60]}) — expected one of {case['pass_if']}"

    print(f"  {verdict} {detail}")
    print(f"  Note: {case['notes']}\n")
    results.append({"id": case["id"], "result": verdict.strip(), "detail": detail})

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"{'='*70}")
print("  SUMMARY")
print(f"{'='*70}")

by_rule = {}
for r in results:
    case_obj = next(c for c in CASES if c["id"] == r["id"])
    rule = case_obj["rule"]
    by_rule.setdefault(rule, []).append(r)

total_pass = sum(1 for r in results if r["result"] == "PASS")
total      = len(results)

for rule, rs in by_rule.items():
    p = sum(1 for r in rs if r["result"] == "PASS")
    print(f"  {rule:<35} {p}/{len(rs)}")
    for r in rs:
        icon = "✓" if r["result"] == "PASS" else "✗"
        print(f"    {icon} [{r['id']}] {r['detail'][:70]}")

print(f"\n  TOTAL: {total_pass}/{total}")

if total_pass == total:
    print("  All rules firing correctly.")
elif total_pass >= 7:
    print("  Good signal — minor tuning may help edge cases.")
elif total_pass >= 5:
    failing_rules = [rule for rule, rs in by_rule.items()
                     if sum(1 for r in rs if r["result"] != "PASS") >= 2]
    print(f"  Weak signal on: {', '.join(failing_rules)}")
    print("  Consider: move those rules earlier in the docstring, or add a one-line")
    print("  preamble in the system prompt referencing them explicitly.")
else:
    print("  Low pass rate — check docstring placement or model attention budget.")
    print("  May need rules closer to the top of execute_command docstring.")

print()
