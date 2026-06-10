"""
LSEChallengeEnv — gymnasium.Env base class for the LSE Challenge Arena.

Wraps ChallengeDB (SQLite) in the standard Gymnasium step/reset interface.
The action is the model's raw text response; the harness parses a JSON block
from it and evaluates the three machine-checkable assertions.

Stack above this base class:
  LSEChallengeEnv
    └─ EscalationWrapper          (stagnation detection, Claude API, KB writes)
        └─ TimeLimit(max_episode_steps=3)
            └─ RecordEpisodeStatistics

Usage:
    from lse_challenge_env import LSEChallengeEnv

    env = LSEChallengeEnv(db_path="/opt/local-se/challenges.db")
    obs, info = env.reset(options={"challenge_id": "pf-t1-001", "model_id": "qwen-27b"})

    # model_response = call_model(obs)   # your model HTTP call here
    obs, reward, terminated, truncated, info = env.step(model_response)
"""

import ast
import builtins
import ipaddress
import json
import re
import sqlite3
import subprocess
from typing import Any, Optional

import gymnasium as gym

# Safe builtins for assertion exec — removes eval/exec/open/__import__ etc.
# Generator expressions need StopIteration (and other machinery) from builtins,
# so we cannot use __builtins__={} — we use an explicit allowlist instead.
_DANGEROUS_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__", "open", "input",
    "breakpoint", "exit", "quit", "help", "vars", "dir",
    "globals", "locals", "getattr", "setattr", "delattr",
    "object", "type", "super", "classmethod", "staticmethod",
    "property", "__build_class__", "memoryview", "bytearray", "bytes",
})
_SAFE_BUILTINS = {
    k: getattr(builtins, k)
    for k in dir(builtins)
    if k not in _DANGEROUS_BUILTINS and not k.startswith("__")
}


# ── Environment ───────────────────────────────────────────────────────────────

class LSEChallengeEnv(gym.Env):
    """
    Single-episode LSE challenge harness.

    observation_space: Dict[Text, Text, Text]
        challenge       — full challenge prompt (description + assertions + output format)
        attempt_history — prior attempts, truncated for context efficiency
        kb_context      — KB hit injected by EscalationWrapper (empty string if no hit)

    action_space: Text
        The model's raw text response. Must contain a ```json ... ``` block whose
        keys match the variables referenced in the challenge assertions.

    Reward per step:
        all 3 assertions pass  → solve_bonus (10/7/4 for attempt 1/2/3) + 3
        partial                → number of assertions that passed (0–2)
        Discipline multiplier is applied by LeaderboardService, not here.
    """

    metadata = {"render_modes": ["ansi"]}

    # Solve bonus by attempt number
    SOLVE_BONUS = {1: 10, 2: 7, 3: 4}
    SOLVE_BONUS_DEFAULT = 2  # escalation path

    def __init__(
        self,
        db_path: str = "/opt/local-se/challenges.db",
        model_endpoint: str = "http://localhost:8080/v1/chat/completions",
        render_mode: Optional[str] = None,
    ):
        super().__init__()
        self.db_path = db_path
        self.model_endpoint = model_endpoint
        self.render_mode = render_mode

        self.observation_space = gym.spaces.Dict({
            "challenge":       gym.spaces.Text(max_length=8192),
            "attempt_history": gym.spaces.Text(max_length=16384),
            "kb_context":      gym.spaces.Text(max_length=4096),
        })
        self.action_space = gym.spaces.Text(min_length=1, max_length=16384)

        # Episode state (reset on each reset() call)
        self._current_challenge: dict = {}
        self._attempt_texts: list[str] = []
        self._attempt_assertion_results: list[list[dict]] = []
        self._kb_context: str = ""
        self._model_id: str = "unknown"

    # ── Gymnasium API ─────────────────────────────────────────────────────────

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> tuple[dict, dict]:
        """
        Start a new episode.

        options keys:
            challenge_id  (str)  — specific challenge; if None, picks first T1
            model_id      (str)  — identifier logged in episode statistics
            kb_context    (str)  — pre-fetched KB hit from EscalationWrapper
        """
        super().reset(seed=seed)
        options = options or {}

        self._model_id = options.get("model_id", "unknown")
        self._kb_context = options.get("kb_context", "")
        self._current_challenge = self._load_challenge(options.get("challenge_id"))
        self._attempt_texts = []
        self._attempt_assertion_results = []

        return self._get_obs(), self._get_info()

    def step(self, action: str) -> tuple[dict, float, bool, bool, dict]:
        """
        Process one model response.

        action: raw text from the model, expected to contain a ```json ... ``` block.

        Returns: (observation, reward, terminated, truncated, info)
            terminated = True  → all 3 assertions passed (challenge solved)
            truncated  = True  → max_attempts reached without solving
            reward             → points earned this step
        """
        self._attempt_texts.append(action)
        attempt_n = len(self._attempt_texts)
        max_attempts = self._current_challenge.get("max_attempts", 3)

        results = self._evaluate_assertions(action)
        self._attempt_assertion_results.append(results)

        n_passed = sum(1 for r in results if r["passed"])
        n_total = len(results)
        all_passed = n_passed == n_total

        if all_passed:
            solve_bonus = self.SOLVE_BONUS.get(attempt_n, self.SOLVE_BONUS_DEFAULT)
            reward = float(solve_bonus + n_passed)
        else:
            reward = float(n_passed)

        terminated = all_passed
        truncated = (not all_passed) and (attempt_n >= max_attempts)

        return self._get_obs(), reward, terminated, truncated, self._get_info()

    def render(self) -> Optional[str]:
        if self.render_mode != "ansi":
            return None
        c = self._current_challenge
        lines = [
            f"\n{'─'*60}",
            f"  {c.get('id')} — {c.get('title')}",
            f"  Discipline: {c.get('discipline')} ({c.get('discipline_multiplier')}×)",
            f"  Attempt: {len(self._attempt_texts)} / {c.get('max_attempts', 3)}",
        ]
        if self._attempt_assertion_results:
            last = self._attempt_assertion_results[-1]
            for r in last:
                icon = "✅" if r["passed"] else "❌"
                err = f" — {r['error']}" if r.get("error") else ""
                lines.append(f"  {icon} [{r['id']}] {r.get('description', '')}{err}")
        lines.append(f"{'─'*60}")
        return "\n".join(lines)

    def close(self) -> None:
        pass

    # ── Observation and Info ──────────────────────────────────────────────────

    def _get_obs(self) -> dict:
        return {
            "challenge":       self._build_challenge_prompt(),
            "attempt_history": self._build_attempt_history(),
            "kb_context":      self._kb_context,
        }

    def _get_info(self) -> dict:
        c = self._current_challenge
        last_results = self._attempt_assertion_results[-1] if self._attempt_assertion_results else []
        return {
            "challenge_id":          c.get("id", ""),
            "model_id":              self._model_id,
            "attempt_n":             len(self._attempt_texts),
            "max_attempts":          c.get("max_attempts", 3),
            "discipline":            c.get("discipline", ""),
            "discipline_multiplier": c.get("discipline_multiplier", 1.0),
            "kb_assisted":           bool(self._kb_context),
            "assertion_results":     last_results,
            "assertions_passed":     sum(1 for r in last_results if r["passed"]),
            "assertions_total":      len(last_results),
        }

    def _build_challenge_prompt(self) -> str:
        c = self._current_challenge
        criteria = json.loads(c.get("success_criteria", "{}"))
        assertions = criteria.get("assertions", [])
        state = json.loads(c.get("starting_state", "{}"))
        required_vars = _extract_required_vars(assertions)

        lines = [
            f"CHALLENGE: {c.get('id')} — {c.get('title')}",
            f"Domain: {c.get('domain')} | Discipline: {c.get('discipline')} | Tier: {c.get('tier')}",
            f"Mode: {c.get('mode')}",
            "",
            "TASK:",
            c.get("description", ""),
        ]

        if state:
            lines += ["", "ENVIRONMENT:", json.dumps(state, indent=2)]

        lines += ["", "ASSERTIONS — your output must satisfy all three:"]
        for a in assertions:
            lines.append(f"  [{a['id']}] {a['description']}")
            lines.append(f"         {a['code']}")

        if required_vars:
            schema = {v: "..." for v in sorted(required_vars)}
            lines += [
                "",
                "OUTPUT FORMAT — include a ```json code block with these keys:",
                "```json",
                json.dumps(schema, indent=2),
                "```",
                "Use the exact key names above. Values must match what the assertions check.",
            ]

        if self._kb_context:
            lines += [
                "",
                "KB CONTEXT — retrieved from prior sessions, use this:",
                self._kb_context,
            ]

        return "\n".join(lines)

    def _build_attempt_history(self) -> str:
        if not self._attempt_texts:
            return ""
        parts = []
        for i, (text, results) in enumerate(
            zip(self._attempt_texts, self._attempt_assertion_results), 1
        ):
            n_passed = sum(1 for r in results if r["passed"])
            n_total = len(results)
            failed = [r for r in results if not r["passed"]]
            summary = f"{n_passed}/{n_total} assertions passed"
            if failed:
                summary += " | failed: " + ", ".join(
                    f"{r['id']} ({r.get('error', 'assertion error')})" for r in failed
                )
            # Truncate long attempts to save context
            truncated = text[:800] + "...[truncated]" if len(text) > 800 else text
            parts.append(f"--- Attempt {i} [{summary}] ---\n{truncated}")
        return "\n\n".join(parts)

    # ── Assertion Evaluation ──────────────────────────────────────────────────

    def _evaluate_assertions(self, model_response: str) -> list[dict]:
        """
        Parse the model's JSON block and evaluate each assertion in a
        restricted namespace. Returns a list of result dicts.
        """
        criteria = json.loads(self._current_challenge.get("success_criteria", "{}"))
        assertions = criteria.get("assertions", [])
        namespace = _build_assertion_namespace(model_response)
        results = []

        for a in assertions:
            # ── Ground-truth SSH verification ────────────────────────────────
            # If the assertion defines verify_ssh, SSH to the target and
            # inject the real values into the namespace, overriding anything
            # the model self-reported. This prevents hallucination passes.
            if "verify_ssh" in a:
                v = a["verify_ssh"]
                ssh_vars = _run_ssh_verification(
                    host=v["host"],
                    user=v.get("user", "lse-admin"),
                    cmd=v["cmd"],
                    parse=v["parse"],
                )
                if "_ssh_error" in ssh_vars:
                    results.append({
                        "id":          a["id"],
                        "passed":      False,
                        "description": a.get("description", ""),
                        "error":       f"SSH verification failed: {ssh_vars['_ssh_error']}",
                    })
                    continue
                # Override model self-report with ground-truth SSH values
                namespace.update(ssh_vars)

            try:
                exec(a["code"], {"__builtins__": _SAFE_BUILTINS, **namespace})  # noqa: S102
                results.append({
                    "id":          a["id"],
                    "passed":      True,
                    "description": a.get("description", ""),
                    "error":       None,
                })
            except AssertionError:
                results.append({
                    "id":          a["id"],
                    "passed":      False,
                    "description": a.get("description", ""),
                    "error":       "assertion not satisfied",
                })
            except NameError as e:
                results.append({
                    "id":          a["id"],
                    "passed":      False,
                    "description": a.get("description", ""),
                    "error":       f"NameError: {e} — model JSON missing this key",
                })
            except (KeyError, TypeError, IndexError) as e:
                results.append({
                    "id":          a["id"],
                    "passed":      False,
                    "description": a.get("description", ""),
                    "error":       f"{type(e).__name__}: {e}",
                })

        return results

    # ── DB Access ─────────────────────────────────────────────────────────────

    def _load_challenge(self, challenge_id: Optional[str]) -> dict:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            if challenge_id:
                row = con.execute(
                    "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
                ).fetchone()
            else:
                row = con.execute(
                    "SELECT * FROM challenges WHERE tier = 1 ORDER BY id LIMIT 1"
                ).fetchone()
            if not row:
                raise ValueError(f"Challenge not found: {challenge_id!r}")
            return dict(row)
        finally:
            con.close()

    def list_challenges(self, tier: Optional[int] = None) -> list[dict]:
        """Return challenge summary rows from DB."""
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            if tier is not None:
                rows = con.execute(
                    "SELECT id, title, domain, discipline, tier, discipline_multiplier "
                    "FROM challenges WHERE tier = ? ORDER BY id", (tier,)
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT id, title, domain, discipline, tier, discipline_multiplier "
                    "FROM challenges ORDER BY tier, id"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()


# ── Module-level helpers ──────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """
    Extract a JSON object from model response text. Handles:
      1. Well-formed ```json ... ``` fenced block  (normal case)
      2. Unclosed fence — response truncated before closing ```
         (happens when JSON list is large and hits MaxPredictTokens)
      3. Bare JSON object in text
      4. Partial JSON repair — truncated mid-object, attempt to close
    Returns empty dict if nothing parseable.
    """
    # 1. Well-formed fenced block
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Unclosed fence — model hit token limit before closing ```
    unclosed = re.search(r"```json\s*(.*?)$", text, re.DOTALL | re.IGNORECASE)
    if unclosed:
        raw = unclosed.group(1).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        repaired = _repair_truncated_json(raw)
        if repaired:
            return repaired

    # 3. Bare JSON object
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 4. Find first { ... } block in text
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def _repair_truncated_json(raw: str) -> dict:
    """
    Close a truncated JSON object using a stack to track open
    bracket/brace nesting order, then append closers in reverse.
    This correctly handles mid-entry truncation inside nested arrays.
    Only attempts repair when the raw string starts with '{'.
    """
    if not raw.startswith("{"):
        return {}

    stack = []
    in_string = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and in_string:
            i += 2          # skip escaped character
            continue
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch in ("{", "["):
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()
        i += 1

    if not stack:
        return {}           # already balanced — normal parse failed elsewhere

    trimmed = raw.rstrip()
    trimmed = re.sub(r",\s*$", "", trimmed)
    close  = {"{": "}", "[": "]"}
    suffix = "".join(close[ch] for ch in reversed(stack))
    try:
        return json.loads(trimmed + suffix)
    except json.JSONDecodeError:
        return {}

def _is_rfc1918(ip: str) -> bool:
    """Return True if the string is a valid RFC1918 private IP address."""
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def _run_ssh_verification(host: str, user: str, cmd: str, parse: str) -> dict:
    """
    SSH ground-truth verifier — runs cmd on host, then exec()s parse code
    against {stdout, stderr, exit_code} to extract verified variable values.

    On success: returns dict of variables extracted by parse code (merged
    into the assertion namespace, OVERRIDING model self-report).
    On failure: returns {"_ssh_error": "<reason>"}.

    Security: parse code runs in a restricted namespace (no builtins).
    """
    try:
        result = subprocess.run(  # noqa: S603
            [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=8",
                "-o", "BatchMode=yes",      # never prompt for password
                "-o", "LogLevel=ERROR",
                f"{user}@{host}",
                cmd,
            ],
            capture_output=True, text=True, timeout=20,
        )
        stdout   = result.stdout.strip()
        stderr   = result.stderr.strip()
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        return {"_ssh_error": f"SSH timeout (>20s) to {user}@{host}"}
    except Exception as exc:  # noqa: BLE001
        return {"_ssh_error": f"SSH failed: {exc}"}

    # Provide re (regex) in parse namespace — safe and commonly needed for
    # extracting version strings from command output. import is blocked.
    local_vars: dict = {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}
    parse_ns = {"__builtins__": {}, "re": re, "True": True, "False": False, "None": None,
                "int": int, "float": float, "str": str, "bool": bool, "len": len,
                "any": any, "all": all}
    try:
        exec(parse, parse_ns, local_vars)  # noqa: S102
    except Exception as exc:  # noqa: BLE001
        return {"_ssh_error": f"parse() failed: {exc}", "stdout": stdout}

    # Return only the new variables set by parse (not the input helpers)
    return {
        k: v for k, v in local_vars.items()
        if k not in ("stdout", "stderr", "exit_code") and not k.startswith("_")
    }


def _build_assertion_namespace(model_response: str) -> dict:
    """
    Build the namespace for assertion exec():
      - Parse model JSON response
      - Inject safe built-ins and domain helpers
    """
    data = _extract_json(model_response)

    # Coerce string booleans — models occasionally emit "True"/"False" as JSON
    # strings rather than JSON true/false. Silently convert so `is True` checks
    # don't NameError on legitimate responses, but still fail on bad JSON schema.
    for k, v in list(data.items()):
        if isinstance(v, str):
            if v.lower() == "true":
                data[k] = True
            elif v.lower() == "false":
                data[k] = False

    namespace: dict[str, Any] = {
        # Domain helpers
        "is_rfc1918": _is_rfc1918,
        # Safe built-ins (explicit allowlist — __builtins__ is suppressed in exec)
        "True": True, "False": False, "None": None,
        "len": len, "any": any, "all": all, "sum": sum,
        "isinstance": isinstance, "list": list, "dict": dict,
        "str": str, "int": int, "float": float, "bool": bool,
        "sorted": sorted, "enumerate": enumerate, "zip": zip,
        "min": min, "max": max,
    }
    # Merge parsed model output — keys become variable names in assertions
    namespace.update(data)
    return namespace


def _extract_required_vars(assertions: list[dict]) -> set[str]:
    """
    Heuristically extract variable names referenced in assertion code,
    excluding built-ins and known helpers.
    """
    SKIP = {
        "len", "any", "all", "sum", "min", "max", "sorted", "enumerate", "zip",
        "True", "False", "None", "isinstance", "list", "dict", "str", "int",
        "float", "bool", "is_rfc1918",
    }
    names: set[str] = set()
    for a in assertions:
        try:
            tree = ast.parse(a["code"])
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id not in SKIP and len(node.id) > 1:
                    names.add(node.id)
                elif isinstance(node, ast.Subscript):
                    if isinstance(node.value, ast.Name) and node.value.id not in SKIP and len(node.value.id) > 1:
                        names.add(node.value.id)
        except SyntaxError:
            pass
    return names
