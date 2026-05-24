"""
title: LSE Context Monitor Filter
author: local-system-engineer
version: 1.0.0
description: Inlet filter for the LSE agent. Counts tool calls in the conversation
  history and injects a get_context_status reminder into the system prompt whenever
  the count reaches a multiple of the configured threshold (default: 5).

  This enforces the v0.5 context-check protocol as a server-side backstop. The model
  prompt already instructs get_context_status after the 5th tool call; this filter
  ensures the instruction fires even if the model skips it.

  Mechanism:
    - Counts messages with role="tool" (one per tool call result) in the full history.
    - When count % threshold == 0 and count > 0, appends a REQUIRED directive to the
      system message before the model sees the request.
    - Uses modulo so checks recur periodically (at 5, 10, 15, ...) without per-session
      state. The model's get_context_status call itself adds 1 to the count, so the
      next injection will not fire until 4 more tool calls have been made.

  Changelog:
    v1.0.0: Initial version.
"""

from pydantic import BaseModel, Field


class Filter:

    class Valves(BaseModel):
        enabled: bool = Field(
            default=True,
            description="Enable or disable the context monitor filter entirely.",
        )
        threshold: int = Field(
            default=5,
            description=(
                "Inject the get_context_status reminder every N tool calls. "
                "Default 5 matches the v0.5 prompt rule."
            ),
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

    def _count_tool_calls(self, messages: list) -> int:
        """
        Count tool result messages in the conversation history.
        Each tool call produces exactly one role='tool' message, so this gives
        the total number of tool calls made so far in the session.
        """
        return sum(1 for m in messages if m.get("role") == "tool")

    # ── OpenWebUI Filter interface ────────────────────────────────────────────

    def inlet(self, body: dict, __user__: dict = {}) -> dict:
        """
        Pre-processing hook. Fires before the model receives the request.
        If the total tool call count is a non-zero multiple of the threshold,
        appends a get_context_status directive to the system message.
        """
        if not self.valves.enabled:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        tool_call_count = self._count_tool_calls(messages)

        # Only fire at multiples of threshold (5, 10, 15 ...), never at 0
        if tool_call_count == 0 or tool_call_count % self.valves.threshold != 0:
            return body

        hint = (
            f"\n\n[CONTEXT MONITOR — {tool_call_count} tool calls this session]\n"
            "REQUIRED: Call get_context_status now, before responding to the user.\n"
            "Do not skip this step. Check context fill percentage, then respond."
        )
        if self.valves.debug:
            hint += (
                f"\n[LSE-CTX-MONITOR v1.0.0: count={tool_call_count} "
                f"threshold={self.valves.threshold}]"
            )

        # Inject into the system message (append so it is the freshest instruction)
        system_found = False
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = self._extract_text(msg["content"]) + hint
                system_found = True
                break

        if not system_found:
            messages.insert(0, {"role": "system", "content": hint.strip()})

        body["messages"] = messages
        return body

    def outlet(self, body: dict, __user__: dict = {}) -> dict:
        """Post-processing hook. No modification needed on the way out."""
        return body
