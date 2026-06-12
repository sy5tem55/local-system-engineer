# pfSense REST API v2 — Local Reference

> **Source:** https://github.com/pfrest/pfSense-pkg-RESTAPI (official)
> **KB doc_id:** ed793c952f253e75 (quality 1.00, vector KB)
> **Last updated:** 2026-06-08

## Quick Reference

- **Package:** `pfSense-pkg-RESTAPI` (NOT `jaredhendrickson13/pfSense-api`)
- **Version:** 2.8.1 CE / 26.03.1 Plus
- **Endpoints:** 264 total (auth:3, diagnostics:10, firewall:33, interface:13, routing:10, services:103, status:23, system:33, vpn:28, graphql:1, user:5, users:1, interfaces:1)
- **Swagger UI:** `https://pfsense.home.arpa/api/v2/documentation`
- **Schema:** `GET /api/v2/schema/native`
- **OpenAPI:** `GET /api/v2/schema/openapi`

## Authentication (priority order)
1. `X-API-Key: <key>` header (recommended for automation)
2. `Authorization: Bearer <jwt-token>` (session-based)
3. `Authorization: Basic <base64>` (simplest, HTTPS only)

## API Key Source
Retrieve from Vaultwarden: `vault_unlock() → get_vault_secret("pfsense-api-key")`

## Log Access — MANDATORY
NEVER call `/api/v2/status/logs/firewall` directly (2.7M tokens, kills session).
Always use: `pfsense_log_summary(hours=24, mode="compact", api_key="<key>")`

## Common Control Parameters
| Param | Methods | Effect |
|-------|---------|--------|
| apply=true | POST/PATCH | Apply changes immediately |
| dry_run=true | POST/PATCH/PUT/DELETE | Validate without writing |
| async=false | All | Wait for changes (may timeout) |
| append=true | PATCH | Append to arrays |
| placement=N | POST/PATCH | Set object position |

## Write Access Protocol
1. Disable Read Only: System → REST API → Read Only: off
2. Perform write operations
3. Verify results
4. Re-enable Read Only before session end
5. Log change in CHANGELOG

## Write via pfsense_query()
```python
pfsense_query(
    endpoint="/api/v2/firewall/rule",
    method="POST",
    payload={"type":"pass","interface":"lan","protocol":"tcp",...},
    api_key="<from-vault>"
)
```
