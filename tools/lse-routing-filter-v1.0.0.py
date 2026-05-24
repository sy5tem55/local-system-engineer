"""
title: LSE Routing Filter
author: local-system-engineer
version: 1.0.0
description: Inlet filter for the LSE agent. Detects "last N lines" and similar
  patterns in user messages and injects a routing override into the system prompt,
  forcing the model to use execute_command("tail -N <path>") instead of read_file.
  Does not affect any other sysadmin request patterns.
"""

import re
from pydantic import BaseModel, Field


class Filter:

    class Valves(BaseModel):
        enabled: bool = Field(
            default=True,
            description="Enable or disable the routing filter entirely.",
        )
        debug: bool = Field(
            default=False,
            description="Append a visible debug tag to injected hints (useful during eval).",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ── Patterns that indicate the user wants trailing lines of a file ────────
    #
    # Each pattern is matched case-insensitively against the last user message.
    # Keep patterns specific enough not to fire on unrelated requests.

    _TAIL_PATTERNS = [
        r"\blast\s+\d+\s+lines?\b",         # "last 20 lines", "last 5 line"
        r"\blast\s+few\s+lines?\b",          # "last few lines"
        r"\bshow\s+me\s+the\s+last\b",       # "show me the last [N lines of ...]"
        r"\bbottom\s+\d+\s+lines?\b",        # "bottom 10 lines"
        r"\btail\b",                         # any mention of "tail" (command intent)
        r"\bend\s+of\s+(the\s+)?file\b",     # "end of the file", "end of file"
    ]

    # ── Text injected at the end of the system message when a pattern fires ──

    _TAIL_HINT = (
        "\n\n[ROUTING OVERRIDE — injected by LSE inlet filter]\n"
        "The user is requesting trailing lines of a file.\n"
        "RULE: You MUST call execute_command with a tail command, e.g.:\n"
        '  execute_command("tail -20 /home/sy5/.bashrc")\n'
        "RULE: Do NOT call read_file for this request under any circumstances.\n"
        "One tool call. No plan. No preamble. Return the output directly."
    )

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

    def _matches(self, text: str) -> bool:
        lower = text.lower()
        return any(re.search(p, lower) for p in self._TAIL_PATTERNS)

    # ── OpenWebUI Filter interface ────────────────────────────────────────────

    def inlet(self, body: dict, __user__: dict = {}) -> dict:
        """
        Pre-processing hook. Fires before the model receives the request.
        If the last user message matches a tail-routing pattern, appends a
        routing override to the system message.
        """
        if not self.valves.enabled:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        # Find the last user message
        last_user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_text = self._extract_text(msg.get("content", ""))
                break

        if not last_user_text or not self._matches(last_user_text):
            return body  # Pattern did not match — pass through unchanged

        # Build the hint
        hint = self._TAIL_HINT
        if self.valves.debug:
            hint += "\n[LSE-FILTER v1.0.0: tail-routing-override active]"

        # Inject into the system message (append so it is the freshest instruction)
        system_found = False
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = self._extract_text(msg["content"]) + hint
                system_found = True
                break

        if not system_found:
            # No system message present — create one
            messages.insert(0, {"role": "system", "content": hint.strip()})

        body["messages"] = messages
        return body

    def outlet(self, body: dict, __user__: dict = {}) -> dict:
        """Post-processing hook. No modification needed on the way out."""
        return body
