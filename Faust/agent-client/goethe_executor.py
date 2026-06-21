"""goethe_executor.py — a ReAct executor that drives the LSE's model (llama-server)
through Goethe's tools, OUTSIDE OpenWebUI.

Why: OWUI's API doesn't reliably elicit tool-calls from local Qwen3.6, but the model
does ReAct fine in plain text. Goethe's `Tools` class has a light constructor and its
methods are plain Python (gates enforced internally), so we import it and run the
Thought/Action/Observation loop ourselves. Same brain + same tools, driven here.

Used by the Faust sidecar to actually EXECUTE an approved `@lse: <task>` assignment.
"""
import importlib.util
import json
import re
import urllib.request

_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Curated, safe-by-default tool surface. name -> (Goethe method, primary arg, description)
DEFAULT_TOOLS = {
    "execute_command": ("execute_command", "command",
        "Run a shell command on the host (read/write-safe; destructive ops are gated). arg: command"),
    "read_file": ("read_file", "path", "Read a text file. arg: path"),
    "search_kb": ("search_kb", "query", "Search the LSE knowledge base. arg: query"),
    "search_web": ("search_web", "query", "Web search via SearXNG. arg: query"),
}


def load_goethe(path):
    """Import goethe-v0.2.1.py (hyphenated filename) and return its Tools class."""
    spec = importlib.util.spec_from_file_location("goethe_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Tools


class GoetheExecutor:
    def __init__(self, goethe_path, model_url, model_id="default", model_key=None,
                 valves=None, tools=None, max_steps=8, max_obs=2000, log=print):
        Tools = load_goethe(goethe_path)
        self.tools = Tools()
        for k, v in (valves or {}).items():
            setattr(self.tools.valves, k, v)
        self.reg = tools or DEFAULT_TOOLS
        self.model_url = model_url
        self.model_id = model_id
        self.model_key = model_key
        self.max_steps = max_steps
        self.max_obs = max_obs
        self.log = log

    def _call_model(self, messages, max_tokens=512):
        body = json.dumps({"model": self.model_id, "messages": messages,
                           "stream": False, "max_tokens": max_tokens}).encode()
        headers = {"content-type": "application/json"}
        if self.model_key:
            headers["authorization"] = f"Bearer {self.model_key}"
        req = urllib.request.Request(self.model_url, data=body, headers=headers, method="POST")
        with _NOPROXY.open(req, timeout=120) as r:
            data = json.loads(r.read().decode())
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")

    def _system_prompt(self):
        lines = ["You are the LSE (Local System Engineer). Complete the TASK using tools.",
                 "Tools available:"]
        for name, (_m, _arg, desc) in self.reg.items():
            lines.append(f"  - {name}: {desc}")
        lines += [
            "",
            "Work ONE step at a time in EXACTLY this format:",
            "Thought: <reasoning>",
            "Action: <tool name>",
            "Action Input: <the argument value, or a JSON object of args>",
            "",
            "After each Action you receive an Observation. Never invent Observations.",
            "When the task is done, reply:",
            "Thought: <reasoning>",
            "Final Answer: <concise result for the team>",
        ]
        return "\n".join(lines)

    def _invoke(self, action, action_input):
        spec = self.reg.get(action)
        if not spec:
            return f"ERROR: unknown tool '{action}'. Available: {', '.join(self.reg)}"
        method_name, primary, _desc = spec
        # parse the input: JSON object -> kwargs; else -> {primary: value}
        kwargs = {}
        raw = (action_input or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                kwargs = parsed if isinstance(parsed, dict) else {primary: parsed}
            except Exception:
                kwargs = {primary: raw}
        try:
            out = getattr(self.tools, method_name)(**kwargs)
            return str(out)
        except Exception as e:  # noqa: BLE001
            return f"ERROR calling {action}: {e}"

    def run(self, task):
        messages = [{"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": f"TASK: {task}"}]
        trace = []
        for step in range(self.max_steps):
            reply = self._call_model(messages)
            self.log(f"[executor step {step+1}] {reply[:160]}")
            fa = re.search(r"Final Answer:\s*(.+)", reply, re.DOTALL)
            if fa:
                ans = fa.group(1).strip()
                trace.append({"final": ans})
                return {"answer": ans, "trace": trace, "steps": step + 1}
            am = re.search(r"Action:\s*([^\n]+)", reply)
            if not am:
                # no action, no final answer — treat the reply as the answer
                trace.append({"final": reply.strip()})
                return {"answer": reply.strip(), "trace": trace, "steps": step + 1}
            action = am.group(1).strip()
            im = re.search(r"Action Input:\s*(.+)", reply, re.DOTALL)
            action_input = im.group(1).strip() if im else ""
            obs = self._invoke(action, action_input)[: self.max_obs]
            trace.append({"action": action, "input": action_input, "observation": obs})
            self.log(f"[executor obs] {obs[:160]}")
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": f"Observation: {obs}"})
        return {"answer": "(reached step cap without a Final Answer)",
                "trace": trace, "steps": self.max_steps}
