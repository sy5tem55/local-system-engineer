"""
title: LSE Context Monitor Filter
author: local-system-engineer
version: 1.2.0
description: Inlet filter for the LSE agent. Counts tool calls in the conversation
  history and injects a get_context_status reminder whenever the count reaches a
  multiple of the configured threshold (default: 5).

  This enforces the v0.5 context-check protocol as a server-side backstop. The model
  prompt already instructs get_context_status after the 5th tool call; this filter
  ensures the instruction fires even if the model skips it.

  Mechanism:
    - Counts messages with role="tool" (one per tool call result) in the full history.
    - When count % threshold == 0 and count > 0, injects a REQUIRED directive into
      both the system message AND the current user message.
    - System-message injection: carries authority.
    - User-message replacement: the user's original message is preserved verbatim
      but wrapped inside a structured interrupt block that makes get_context_status
      the only permitted first action. The model sees the original question but is
      instructed to answer it only AFTER the context check completes.
    - Uses modulo so checks recur periodically (at 5, 10, 15, ...) without per-session
      state. The model's get_context_status call itself adds 1 to the count, so the
      next injection will not fire until threshold-1 more tool calls have been made.

  Changelog:
    v1.0.0: Initial version. Injected into system message only.
    v1.1.0: Dual injection — system message + user message prepend.
              Root cause: system-only injection was ignored when the threshold fired
              during a conversational (non-tool) turn.
    v1.2.0: Replaced user-message prepend with structured interrupt block.
              Root cause: v1.1.0 prepend was still ignored — Run 5 eval showed the
              model receiving the injection at count=5 (message 7, nvcc question)
              and calling execute_command directly without get_context_status. The
              model treats a direct task question as higher priority than a prepended
              meta-instruction, even with REQUIRED language.
              Fix: user message is now restructured as a two-part interrupt. Part 1
              is the mandatory context check with explicit step numbering. Part 2
              is the original question, clearly labelled as "answer this after step 1".
              The structured format (━━━ borders, numbered steps) signals a system
              interrupt rather than a soft suggestion.
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
        The count is cumulative across all turns regardless of whether they are
        tool-using turns or plain conversational turns.
        """
        return sum(1 for m in messages if m.get("role") == "tool")

    # ── OpenWebUI Filter interface ────────────────────────────────────────────

    def inlet(self, body: dict, __user__: dict = {}) -> dict:
        """
        Pre-processing hook. Fires before the model receives each user message.

        When the total tool call count hits a multiple of the threshold, injects
        the get_context_status directive in two places:

          1. System message (appended) — carries rule authority.
          2. Current user message (prepended) — carries attention. Without this,
             the model may respond conversationally to the user turn and skip the
             tool call even though the system message says REQUIRED.

        Both injections are needed. System-only injection fails silently on chat
        turns. User-message-only injection would lack the authority of a system rule.
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

        debug_tag = ""
        if self.valves.debug:
            debug_tag = (
                f"\n[LSE-CTX-MONITOR v1.2.0: count={tool_call_count} "
                f"threshold={self.valves.threshold}]"
            )

        # ── 1. Inject into system message ─────────────────────────────────────
        system_hint = (
            f"\n\n[CONTEXT MONITOR — {tool_call_count} tool calls this session]\n"
            "REQUIRED: Call get_context_status now, before responding to the user.\n"
            "Do not skip this step even if the user's message is conversational.\n"
            "Check context fill percentage, then respond."
            + debug_tag
        )

        system_found = False
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = self._extract_text(msg["content"]) + system_hint
                system_found = True
                break

        if not system_found:
            messages.insert(0, {"role": "system", "content": system_hint.strip()})

        # ── 2. Replace current user message with structured interrupt block ───
        # v1.2.0: Replaced simple prepend with a two-part structured block.
        # The original question is preserved but framed as "do this after step 1".
        # Numbered steps + visual borders signal a mandatory system interrupt
        # rather than a soft suggestion the model can deprioritise.
        for msg in reversed(messages):
            if msg.get("role") == "user":
                original = self._extract_text(msg["content"])
                msg["content"] = (
                    "━━━ CONTEXT MONITOR INTERRUPT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{tool_call_count} tool calls completed this session.\n\n"
                    "Step 1 — MANDATORY (do this first, no exceptions):\n"
                    "  Call get_context_status now.\n\n"
                    "Step 2 — answer the user's request below ONLY after step 1:\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{original}"
                )
                break

        body["messages"] = messages
        return body

    def outlet(self, body: dict, __user__: dict = {}) -> dict:
        """Post-processing hook. No modification needed on the way out."""
        return body
