
---

## UPDATE 2026-07-17 — P0/P1 deployed (Cowork verification session)

| Action | Status |
|--------|--------|
| `tools/redact.py` — shared module vendored from Hermes `agent/redact.py` (Hermes decommissioned; no runtime dep). LSE adaptations: URL query-param redaction ON, CLI-credential rule added, `GOETHE_REDACT_SECRETS` gate | ✅ Done |
| Write-time redaction in `goethe.py _log()` (P0) | ✅ Done — active after gateway restart |
| `goethe_mcp.py _redact_text()` — shared vendor-prefix sweep (closes bare `sk-`/`hf_` episode gap, 24 raw occurrences found) | ✅ Done |
| `dream_runner.py redact_log_text()` — chains shared module | ✅ Done |
| Redact backup #2 + 2 gateway logs (15 `api_key=`) | ✅ Done |
| Broad scrub: all episodes, logs, logs-archive, dreams artifacts | ✅ Done |
| Contract tests 84/84; harness 420/420 | ✅ Green |
| P1 residual: callers still SEND `api_key` as URL query param to pfSense — move to `X-API-Key` header | ⏳ Open |

## ROTATION CHECKLIST — redaction does not un-expose

Exposed 2026-07-04 → 2026-07-16 in 5+ file copies. Rotate in order; after each, verify the OLD credential fails against the live service.

1. 🔴 Vaultwarden master password — unlocks 56 credentials. Rotate FIRST, then rotate sensitive vault contents. Update /opt/local-se/goethe-mcp.env.
2. 🔴 OpenAI API keys (3 distinct) — revoke at platform.openai.com.
3. 🔴 Hugging Face tokens — revoke at huggingface.co/settings/tokens.
4. 🟡 SSH password — change; prefer key-only auth (PasswordAuthentication no) so sshpass disappears.
5. 🟡 Grafana passwords (7) — rotate admin/service accounts.
6. 🟡 pfSense API key — regenerate; switch caller to X-API-Key header (P1) at the same time.
7. 🟡 Goethe MCP tokens (3) — regenerate; update goethe-mcp.env.
8. 🟢 NVIDIA/Episteme/JWT/Windows/Prometheus — opportunistically.
