#!/usr/bin/env python3
"""
pfsense-agent.py -- pfSense Administration Orchestrator (Option C)

Pipeline:
  natural language -> Qwen3.6-27B on node3090 (LM Studio)
                   -> structured LSE prompt
                   -> LSE via OpenWebUI API
                   -> streamed result

Usage:
  python3 pfsense-agent.py "block Meross IoT from the internet"
  python3 pfsense-agent.py --think "audit and harden OPT1 rules"
  python3 pfsense-agent.py --no-think "mirror ICMPv6 rule from LAN to OPT1"
  python3 pfsense-agent.py --prompt-only "show current LAN firewall rules"
  python3 pfsense-agent.py --auto "block 192.168.1.50 on LAN"
  python3 pfsense-agent.py            # interactive mode

Config: /opt/local-se/pfsense-agent.conf
  [lmstudio]
  url   = http://192.168.5.41:1234
  model = qwen/qwen3.6-27b
  [openwebui]
  url     = http://localhost:3000
  api_key = sk-...
  model   = local-system-engineer
"""

import argparse, configparser, json, os, re, sys, time
import urllib.request, urllib.error

DEFAULT_LMSTUDIO_URL   = "http://192.168.5.41:1234"
DEFAULT_LMSTUDIO_MODEL = "qwen/qwen3.6-27b"
DEFAULT_OPENWEBUI_URL  = "http://localhost:3000"
CONFIG_PATH            = "/opt/local-se/pfsense-agent.conf"

COMPLEX_KEYWORDS = {
    "audit","harden","analyze","review","plan","design","all rules",
    "security","assess","investigate","compare","explain","why",
    "how should","diagnose","report","summarize","overview","spotlight",
}

def detect_thinking(request):
    lower = request.lower()
    return any(kw in lower for kw in COMPLEX_KEYWORDS)

ORCHESTRATOR_SYSTEM = (
    "You are a pfSense Administration Orchestrator. Translate high-level network\n"
    "administration requests into precise, safe, numbered prompts for the LSE executor.\n"
    "\n"
    "TOOL ROUTING:\n"
    "  pfsense_graphql(query, api_key)                    -> ALL reads\n"
    "  pfsense_query(endpoint, method, payload, api_key)  -> writes only (POST/PATCH/PUT/DELETE)\n"
    "  pfsense_log_summary(hours, mode, api_key)          -> firewall logs only\n"
    "\n"
    "GRAPHQL SCHEMA -- use EXACTLY these resource names and fields:\n"
    "  Firewall rules:  { FirewallRule { id type interface src dst srcport dstport protocol descr enabled log } }\n"
    "  DHCP leases:     { DHCPServerLease { ip mac hostname start end } }\n"
    "  ARP table:       { ARPTable { ip mac interface hostname } }\n"
    "  Interfaces:      { NetworkInterface { name descr ipaddr subnet hwaddr } }\n"
    "  Routing table:   { Route { network gateway interface } }\n"
    "  Gateway status:  { Gateway { name interface monitor status delay } }\n"
    "  NEVER use: firewallRules, getFirewallRules, rules{}, or any other invented names.\n"
    "  NEVER use: __schema or __type -- context bomb.\n"
    "\n"
    "FIREWALL WRITE ENDPOINTS (pfsense_query only):\n"
    "  POST   /api/v2/firewall/rule          -> create rule (include placement=N, apply=true)\n"
    "  PATCH  /api/v2/firewall/rule?id=N     -> update rule by index\n"
    "  DELETE /api/v2/firewall/rule?id=N     -> delete rule by index\n"
    "  placement=N inserts before index N (0-based, per-interface)\n"
    "\n"
    "AUTHENTICATION -- Step 1 of every prompt:\n"
    "  vault_unlock() then get_vault_secret(\"pfsense-api-key\") and store as api_key\n"
    "\n"
    "PROHIBITIONS -- include verbatim at the end of every prompt:\n"
    "  DO NOT: query __schema or __type (context bomb -- crashes session)\n"
    "  DO NOT: call /api/v2/status/logs/firewall (2.7M token overflow)\n"
    "  DO NOT: write any rule without a prior read confirming current state\n"
    "  DO NOT: guess placement index -- read-first always\n"
    "\n"
    "OUTPUT FORMAT -- numbered steps only, max 6:\n"
    "  Step 1: vault_unlock() -> get_vault_secret(\"pfsense-api-key\") -> store as api_key\n"
    "  Step 2-N: pfsense_graphql reads (exact query strings, not descriptions)\n"
    "  [If write needed: CONFIRMATION GATE -> pfsense_query write -> pfsense_graphql verify]\n"
    "  [DO NOT block -- verbatim]\n"
    "\n"
    "CRITICAL: Output the numbered steps ONLY. Zero preamble, zero explanation,\n"
    "zero reasoning, zero markdown. The assistant turn begins with 'Step 1:' already written.\n"
    "Continue directly from there."
)

def load_config():
    cfg = {
        "lmstudio_url":    os.environ.get("LMSTUDIO_URL",       DEFAULT_LMSTUDIO_URL),
        "lmstudio_model":  os.environ.get("LMSTUDIO_MODEL",     DEFAULT_LMSTUDIO_MODEL),
        "openwebui_url":   os.environ.get("OPENWEBUI_URL",      DEFAULT_OPENWEBUI_URL),
        "openwebui_key":   os.environ.get("OPENWEBUI_API_KEY",  ""),
        "openwebui_model": os.environ.get("OPENWEBUI_LSE_MODEL",""),
    }
    if os.path.exists(CONFIG_PATH):
        ini = configparser.ConfigParser()
        ini.read(CONFIG_PATH)
        if "lmstudio" in ini:
            s = ini["lmstudio"]
            if s.get("url"):   cfg["lmstudio_url"]   = s["url"]
            if s.get("model"): cfg["lmstudio_model"] = s["model"]
        if "openwebui" in ini:
            s = ini["openwebui"]
            if s.get("url"):     cfg["openwebui_url"]   = s["url"]
            if s.get("api_key"): cfg["openwebui_key"]   = s["api_key"]
            if s.get("model"):   cfg["openwebui_model"] = s["model"]
    return cfg

def _stream_post(url, payload, headers=None, timeout=60):
    body = json.dumps(payload).encode()
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data.strip() == "[DONE]":
                return
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content") or delta.get("reasoning_content", "")
                if content:
                    yield content
            except Exception:
                continue

def _extract_prompt(raw, prefilled=False):
    # Strip tagged think blocks
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Prefill: stream starts after "Step 1: " seed
    if prefilled and not raw.lstrip().startswith("Step 1:"):
        raw = "Step 1: " + raw.lstrip()

    # Anchor on the LAST DO NOT block, then work backwards to the nearest Step N:.
    # This correctly handles thinking traces where Step 1 appears mid-trace.
    # IMPORTANT: use ^[ \t]* not ^\s* -- multiline ^ + \s* swallows preceding newline,
    # causing match.start() to land on \n instead of the first space of the step line.
    FIRST_DO_NOT = "DO NOT: query __schema or __type (context bomb -- crashes session)"
    LAST_DO_NOT  = "DO NOT: guess placement index -- read-first always"

    last_do_not_start = raw.rfind(FIRST_DO_NOT)
    last_do_not_end   = raw.rfind(LAST_DO_NOT)

    if last_do_not_start != -1 and last_do_not_end != -1:
        do_not_block = raw[last_do_not_start : last_do_not_end + len(LAST_DO_NOT)].strip()
        before = raw[:last_do_not_start]
        step_matches = list(re.finditer(r"(?m)^[ \t]*Step (\d+):", before))
        if step_matches:
            # Walk backwards to find the start of the last contiguous ascending run
            group_start_idx = len(step_matches) - 1
            prev_num = int(step_matches[group_start_idx].group(1))
            for i in range(len(step_matches) - 2, -1, -1):
                num = int(step_matches[i].group(1))
                if num == prev_num - 1:
                    prev_num = num
                    group_start_idx = i
                else:
                    break
            raw = before[step_matches[group_start_idx].start():].rstrip() + "\n" + do_not_block
        else:
            raw = do_not_block
    else:
        # No DO NOT block found -- fall back to last Step N: search
        matches = list(re.finditer(r"(?m)^[ \t]*Step \d+:", raw))
        if matches:
            raw = raw[matches[-1].start():]

    # Dedent: strip common leading whitespace from all lines
    lines = raw.splitlines()
    if lines:
        indent = len(lines[0]) - len(lines[0].lstrip())
        dedented = []
        for line in lines:
            if line[:indent] == " " * indent:
                dedented.append(line[indent:])
            else:
                dedented.append(line.lstrip())
        raw = "\n".join(dedented).strip()

    # If model started at Step 2 (told "Step 1 is pre-written"), restore Step 1
    if raw.startswith("Step 2:") or raw.startswith("2:"):
        raw = ("Step 1: vault_unlock() -> get_vault_secret(\"pfsense-api-key\") -> store as api_key\n"
               + raw)

    return raw

def call_orchestrator(request, cfg, thinking=None):
    use_thinking = thinking if thinking is not None else detect_thinking(request)
    print(
        "\033[2m[Orchestrator] model={} thinking={}\033[0m".format(
            cfg["lmstudio_model"], "ON" if use_thinking else "OFF"),
        file=sys.stderr
    )

    messages = [
        {"role": "system", "content": ORCHESTRATOR_SYSTEM},
        {"role": "user",   "content": request},
    ]
    if not use_thinking:
        # Assistant prefill forces output to start at Step 1 with no preamble
        messages.append({"role": "assistant", "content": "Step 1: "})

    payload = {
        "model":       cfg["lmstudio_model"],
        "messages":    messages,
        "temperature": 0.4 if use_thinking else 0.2,
        "max_tokens":  4096 if use_thinking else 2048,
        "stream":      True,
    }

    url = cfg["lmstudio_url"].rstrip("/") + "/v1/chat/completions"
    t0 = time.time()
    think_chars = output_chars = 0
    in_think = think_done = False
    full = []

    try:
        for chunk in _stream_post(url, payload, timeout=60):
            full.append(chunk)
            elapsed  = time.time() - t0
            combined = "".join(full)
            if not think_done:
                if "<think>" in combined:    in_think = True
                if "</think>" in combined and in_think:
                    in_think = False; think_done = True
            if in_think:
                think_chars += len(chunk)
                print("\r\033[2m[Thinking] {:,} chars  {:.0f}s\033[0m  ".format(
                    think_chars, elapsed), end="", flush=True, file=sys.stderr)
            else:
                if think_done and output_chars == 0:
                    print(file=sys.stderr)
                output_chars += len(chunk)
                print("\r\033[2m[Output]   {:,} chars  {:.0f}s\033[0m  ".format(
                    output_chars, elapsed), end="", flush=True, file=sys.stderr)
    except TimeoutError:
        print("\n\033[31m[Orchestrator] First-token timeout\033[0m", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print("\n\033[31m[Orchestrator] {}: {}\033[0m".format(url, e), file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - t0
    print("\n\033[2m[Done] {:.1f}s | think={:,} output={:,} chars\033[0m".format(
        elapsed, think_chars, output_chars), file=sys.stderr)

    return _extract_prompt("".join(full), prefilled=(not use_thinking))

def submit_to_lse(prompt, cfg):
    if not cfg["openwebui_key"]:
        print("\033[33m[LSE] api_key not set in pfsense-agent.conf\033[0m", file=sys.stderr)
        return
    if not cfg["openwebui_model"]:
        print("\033[33m[LSE] model not set in pfsense-agent.conf\033[0m", file=sys.stderr)
        return
    url = cfg["openwebui_url"].rstrip("/") + "/api/chat/completions"
    payload = {
        "model":    cfg["openwebui_model"],
        "messages": [{"role": "user", "content": prompt}],
        "stream":   True,
        "tool_ids": ["lse_system_admin_terminal", "lse_vaultwarden_tools"],
    }
    headers = {"Authorization": "Bearer " + cfg["openwebui_key"]}
    print("\033[2m[LSE] -> {}\033[0m".format(cfg["openwebui_model"]), file=sys.stderr)
    print("\n" + "-" * 60)
    try:
        for chunk in _stream_post(url, payload, headers=headers, timeout=60):
            print(chunk, end="", flush=True)
    except urllib.error.URLError as e:
        print("\n\033[31m[LSE] {}\033[0m".format(e), file=sys.stderr)
        sys.exit(1)
    print("\n" + "-" * 60)

def main():
    p = argparse.ArgumentParser(description="pfSense Admin Orchestrator -- Qwen3.6 -> LSE")
    p.add_argument("request",      nargs="?")
    p.add_argument("--think",      action="store_true")
    p.add_argument("--no-think",   action="store_true")
    p.add_argument("--prompt-only",action="store_true")
    p.add_argument("--auto",       action="store_true")
    p.add_argument("--lmstudio",   metavar="URL")
    p.add_argument("--model",      metavar="ID")
    args = p.parse_args()

    cfg = load_config()
    if args.lmstudio: cfg["lmstudio_url"]   = args.lmstudio
    if args.model:    cfg["lmstudio_model"] = args.model

    request = args.request
    if not request:
        print("pfSense Admin > ", end="", flush=True)
        request = input().strip()
    if not request:
        p.print_help(); sys.exit(1)

    if args.think and args.no_think:
        p.error("--think and --no-think are mutually exclusive")
    thinking = True if args.think else (False if args.no_think else None)

    print("\033[2m[Orchestrator] Generating LSE prompt...\033[0m", file=sys.stderr)
    lse_prompt = call_orchestrator(request, cfg, thinking)

    print("\n===== Generated LSE Prompt " + "=" * 35)
    print(lse_prompt)
    print("=" * 62 + "\n")

    if args.prompt_only:
        return

    if not args.auto:
        try:
            answer = input("Submit to LSE? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted."); return
        if answer not in ("y", "yes"):
            print("Aborted."); return

    submit_to_lse(lse_prompt, cfg)

if __name__ == "__main__":
    main()
