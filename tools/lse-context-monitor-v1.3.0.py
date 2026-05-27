"""
title: LSE Context Monitor Filter
author: local-system-engineer
version: 1.3.0
description: Inlet filter for the LSE agent. Queries the llama-server Prometheus
  metrics endpoint on every turn and injects the current context fill percentage
  directly into the system message as a fact.

  This is a fundamental architectural change from v1.0–v1.2. All previous versions
  instructed the MODEL to call get_context_status (a tool action). All three versions
  failed for the same root cause: when the model receives a concrete user task, the
  task always wins over any meta-instruction to call a tool first, regardless of how
  forcefully that instruction is formatted (system message, prepend, structured
  interrupt block).

  The fix is to remove the model from the loop entirely. The filter queries
  http://localhost:8080/metrics directly on every inlet call, parses
  llama_kv_cache_usage_ratio, and injects the result as a plain fact:

    [Context: 71% full — 23,265 / 32,768 tokens used]

  The model reads this as part of its system context and acts on it naturally
  (warns the user, suggests a handover) without needing to call any tool.
  If the fill exceeds the warning threshold, the injected message is upgraded
  to a prominent warning block.

  Mechanism:
    - On every inlet call, fetch http://localhost:8080/metrics (timeout: 1s).
    - Parse llama_kv_cache_usage_ratio (float 0.0–1.0) from Prometheus text format.
    - Compute token counts from llama_kv_cache_tokens_used and
      llama_context_tokens (fallback: estimate from ratio × ctx_size valve).
    - Inject into the system message:
        Below warning_pct:  "[Context: {pct}% — {used}/{total} tokens]"
        At/above warn_pct:  "⚠ CONTEXT {pct}% FULL — consider handover soon."
        At/above critical_pct: "🔴 CONTEXT {pct}% FULL — save state NOW."
    - If the metrics endpoint is unreachable, inject nothing (fail silently).

  Changelog:
    v1.0.0: System message injection only — ignored on conversational turns.
    v1.1.0: Dual injection (system + user prepend) — still ignored; task wins.
    v1.2.0: Structured interrupt block — still ignored; same root cause.
    v1.3.0: Removed model action requirement entirely. Filter fetches context
              fill from /metrics and injects it as a fact. No tool call needed.
              Root cause diagnosis: compliance-based approaches cannot win against
              a task-focused model. Architectural fix: move the work to the filter.
"""

import re
import requests
from pydantic import BaseModel, Field


class Filter:

    class Valves(BaseModel):
        enabled: bool = Field(
            default=True,
            description="Enable or disable the context monitor filter entirely.",
        )
        metrics_url: str = Field(
            default="http://localhost:8080/metrics",
            description="Prometheus metrics endpoint exposed by llama-server --metrics.",
        )
        ctx_size: int = Field(
            default=32768,
            description=(
                "Fallback context size in tokens. Used only if llama_context_tokens "
                "is absent from the metrics response. Should match the --ctx-size "
                "value in your launcher profile."
            ),
        )
        warning_pct: int = Field(
            default=70,
            description="Context fill % at which the status line upgrades to a warning.",
        )
        critical_pct: int = Field(
            default=85,
            description="Context fill % at which the warning upgrades to a critical alert.",
        )
        fetch_timeout: float = Field(
            default=1.0,
            description="HTTP timeout in seconds for the metrics fetch. Keep low.",
        )
        debug: bool = Field(
            default=False,
            description="Append a visible debug tag to injected hints (useful during eval).",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_text(self, content) -> str:
        """Handle both plain-string and multimodal (list) message content."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return ""

    def _fetch_context_status(self) -> dict | None:
        """
        Query the llama-server Prometheus metrics endpoint and return a dict:
          { "pct": int, "used": int, "total": int }
        Returns None if the endpoint is unreachable or the expected metrics
        are not present (e.g. llama-server started without --metrics).
        """
        try:
            resp = requests.get(
                self.valves.metrics_url,
                timeout=self.valves.fetch_timeout,
            )
            if resp.status_code != 200:
                return None
            text = resp.text
        except Exception:
            return None

        # Parse llama_kv_cache_usage_ratio  (float, e.g. "0.7099...")
        ratio_match = re.search(
            r"^llama_kv_cache_usage_ratio\s+([\d.]+)",
            text,
            re.MULTILINE,
        )
        if not ratio_match:
            return None
        ratio = float(ratio_match.group(1))

        # Try to get exact token counts
        used_match = re.search(
            r"^llama_kv_cache_tokens_used\s+(\d+)",
            text,
            re.MULTILINE,
        )
        # llama.cpp exposes context size as llama_context_tokens (build-dependent name)
        total_match = re.search(
            r"^llama_context_tokens\s+(\d+)",
            text,
            re.MULTILINE,
        )

        if used_match and total_match:
            used = int(used_match.group(1))
            total = int(total_match.group(1))
        else:
            # Fall back to estimating from ratio × configured ctx_size
            total = self.valves.ctx_size
            used = int(ratio * total)

        pct = round(ratio * 100)
        return {"pct": pct, "used": used, "total": total}

    def _build_injection(self, status: dict) -> str:
        """
        Build the system-message injection string from a context status dict.
        Severity escalates at warning_pct and critical_pct.
        """
        pct = status["pct"]
        used = status["used"]
        total = status["total"]

        debug_tag = ""
        if self.valves.debug:
            debug_tag = f" [LSE-CTX-MONITOR v1.3.0 | ratio={used}/{total}]"

        if pct >= self.valves.critical_pct:
            return (
                f"\n\n🔴 CONTEXT CRITICAL — {pct}% full ({used:,} / {total:,} tokens). "
                "Save session state to /opt/local-se/session-handover.md NOW and "
                "tell the user to start a fresh conversation."
                + debug_tag
            )
        elif pct >= self.valves.warning_pct:
            return (
                f"\n\n⚠ CONTEXT WARNING — {pct}% full ({used:,} / {total:,} tokens). "
                "Mention this to the user and suggest a handover before the session fills."
                + debug_tag
            )
        else:
            return (
                f"\n\n[Context: {pct}% — {used:,} / {total:,} tokens used]"
                + debug_tag
            )

    # ── OpenWebUI Filter interface ────────────────────────────────────────────

    def inlet(self, body: dict, __user__: dict = {}) -> dict:
        """
        Pre-processing hook. Fires before the model receives each user message.

        Fetches context fill from llama-server /metrics and injects it into the
        system message on every turn. Below warning_pct this is a quiet status
        line; at/above it becomes a progressively urgent alert.

        If the metrics endpoint is unreachable (server not running, --metrics
        flag absent, wrong port), the filter does nothing and the request passes
        through unmodified.
        """
        if not self.valves.enabled:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        status = self._fetch_context_status()
        if status is None:
            return body  # fail silently — don't break the conversation

        injection = self._build_injection(status)

        # Inject into system message (append so it is the freshest instruction)
        system_found = False
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = self._extract_text(msg["content"]) + injection
                system_found = True
                break

        if not system_found:
            messages.insert(0, {"role": "system", "content": injection.strip()})

        body["messages"] = messages
        return body

    def outlet(self, body: dict, __user__: dict = {}) -> dict:
        """Post-processing hook. No modification needed on the way out."""
        return body
