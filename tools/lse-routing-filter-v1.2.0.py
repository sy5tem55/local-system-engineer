"""
title: LSE Routing Filter
author: local-system-engineer
version: 1.2.0
description: Inlet filter for the LSE agent. Detects user requests for trailing
  file content and injects a routing override into the system prompt, ensuring the
  model calls execute_command("tail -N <path>") instead of read_file.

  Changelog:
    v1.0.0: Initial version.
    v1.1.0: Removed r"\\btail\\b" pattern — it was too broad and matched "tail"
            appearing as part of a shell command in the user's message (e.g.
            "add an alias for tail -f ..."), causing the routing override to fire
            during file-edit operations and pushing the model to use partial reads
            before overwrites, which caused data loss (M2 eval regression).
            Patterns now only match when the user is explicitly requesting to READ
            trailing lines, not when "tail" appears incidentally.
    v1.2.0: Added TARGET_MODEL_PATTERN valve. OpenWebUI filters are global —
            there is no per-model or per-preset enable toggle. Without this guard,
            the Qwen3-specific routing hint fires for Claude presets too, which is
            wrong. inlet() now checks body["model"] against TARGET_MODEL_PATTERN
            (default: "qwen") and returns the body unmodified if there is no match.
            Claude presets (claude-opus-4-6, claude-sonnet-4-6) pass through cleanly.
"""

import re
from pydantic import BaseModel, Field


class Filter:

    class Valves(BaseModel):
        enabled: bool = Field(
            default=True,
            description="Enable or disable the routing filter entirely.",
        )
        target_model_pattern: str = Field(
            default="qwen",
            description=(
                "Case-insensitive substring matched against the request model ID. "
                "Routing hints are only injected when the active model contains this "
                "string. Set to empty string '' to apply to all models. "
                "Default 'qwen' ensures Claude and other non-Qwen models are unaffected."
            ),
        )
        debug: bool = Field(
            default=False,
            description="Append a visible debug tag to injected hints (useful during eval).",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ── Patterns that indicate the user wants to READ trailing lines ──────────
    #
    # IMPORTANT: Only match when the user is asking to READ trailing content.
    # Do NOT use patterns that match "tail" as a bare word — it fires on
    # shell commands containing "tail" (e.g. alias definitions, pipelines).
    #
    # Each pattern is matched case-insensitively against the last user message.

    _TAIL_PATTERNS = [
        r"\blast\s+\d+\s+lines?\b",         # "last 20 lines", "last 5 line"
        r"\blast\s+few\s+lines?\b",          # "last few lines"
        r"\bshow\s+me\s+the\s+last\b",       # "show me the last [N lines of ...]"
        r"\bbottom\s+\d+\s+lines?\b",        # "bottom 10 lines"
        r"\bend\s+of\s+(the\s+)?file\b",     # "end of the file", "end of file"
        # NOTE: r"\btail\b" intentionally omitted — see v1.1.0 changelog above.
        # If you need to re-add tail matching, use a more specific pattern such as:
        #   r"\btail\s+(?:-\d+\s+)?[/~][\w/.]+\b"  ← only matches "tail <filepath>"
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

    def _model_is_targeted(self, body: dict) -> bool:
        """Return True if the active model should receive routing hints.

        An empty TARGET_MODEL_PATTERN means 'all models'. Otherwise the
        pattern must appear (case-insensitively) in the model ID string.
        """
        pattern = self.valves.target_model_pattern.strip().lower()
        if not pattern:
            return True  # empty pattern → apply to all models
        model_id = body.get("model", "").lower()
        return pattern in model_id

    # ── OpenWebUI Filter interface ────────────────────────────────────────────

    def inlet(self, body: dict, __user__: dict = {}) -> dict:
        """
        Pre-processing hook. Fires before the model receives the request.

        Guard order:
          1. enabled valve — master off switch
          2. target_model_pattern — skip non-Qwen models entirely (v1.2.0)
          3. tail pattern match — inject routing hint only when relevant
        """
        if not self.valves.enabled:
            return body

        # v1.2.0: skip models that don't match the target pattern
        if not self._model_is_targeted(body):
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
            hint += "\n[LSE-FILTER v1.2.0: tail-routing-override active]"

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
