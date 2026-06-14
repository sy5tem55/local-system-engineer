# Install — lse-channel skill (Hermes, node3090)

Hermes self-installs (it has file + skill_manage tools; no SSH from infra). Steps:

1. Copy `SKILL.md` to `~/.hermes/skills/lse-channel/SKILL.md` (or register via
   `skill_manage` per Hermes docs).
2. Copy `lse_channel.py` to `~/.hermes/bin/lse_channel.py`; `chmod +x`.
3. Smoke test (uses ~/.hermes/lse-outbox.json):
   ```bash
   python3 ~/.hermes/bin/lse_channel.py enqueue --body "hello LSE" --kind notify
   python3 ~/.hermes/bin/lse_channel.py flush      # prints the marker; second flush empty
   ```
4. Live test the loop end to end: from the LSE side run `check_hermes_inbox` (Cogitator
   ≥ v1.7.22). The enqueued message should surface as "HERMES → LSE (inbound)".

Round-trip already verified offline: the helper's marker parses through the LSE's exact
regex/formatter (`_extract_content_marker` → `_format_hermes_messages`) and strips clean
from the visible reply.

Companion LSE-side change required: deploy Cogitator **v1.7.22** (raises the inbox poll
`max_tokens` 8 → 1024 so a Path B marker fits on the poll). Without it, messages still ride
`call_hermes`/`hermes_plan` replies (2048 cap), but the dedicated `check_hermes_inbox` poll
would clip the marker.
