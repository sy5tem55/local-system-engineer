# Session Handover — Vaultwarden Setup

## Current State — What Is Already Done

All authentication blockers from the previous session are resolved. Do NOT repeat any of the setup steps below — they are complete.

- Vaultwarden is running at `https://localhost:3003` with a self-signed TLS cert
- LSE account: `lse@local-se.ai`
- LSE user UUID: `7dc216f7-dc47-4b60-9ef6-4d4aca446bd0`
- API key was regenerated as a valid 64-char hex string and written to the DB
- `bw` CLI v2024.2.0 is installed at `/usr/local/bin/bw` (standalone binary, NOT snap)
- `vault_unlock()` tool v1.2.0 is installed in Open WebUI with all credentials pre-configured
- `BW_PASSWORD` is set in the tool's Valves configuration

## Credential Reference

| Variable       | Value |
|----------------|-------|
| BW_HOST        | `https://localhost:3003` |
| BW_CLIENTID    | `user.7dc216f7-dc47-4b60-9ef6-4d4aca446bd0` |
| BW_CLIENTSECRET| `99cebf0ec0b88ea058fec485691c5264028e523159da3dde563c27731b394b42` |
| BW_PASSWORD    | set in Valves — do not hardcode |

## Critical Rules — Read Before Doing Anything

**1. Always use `vault_unlock()` to authenticate. Never call `bw login` manually.**
The tool handles `NODE_TLS_REJECT_UNAUTHORIZED=0`, the `user.` prefix on client_id, login, unlock, and sync in one call.

**2. `BW_CLIENTID` must always include the `user.` prefix.**
`user.7dc216f7-dc47-4b60-9ef6-4d4aca446bd0` ← correct
`7dc216f7-dc47-4b60-9ef6-4d4aca446bd0` ← wrong, will return "Malformed client_id"

**3. The bw CLI requires `NODE_TLS_REJECT_UNAUTHORIZED=0` for all calls.**
The tool sets this automatically. If you call `bw` directly via `execute_command`, you must prefix every command:
```bash
NODE_TLS_REJECT_UNAUTHORIZED=0 bw <command>
```

**4. Do not attempt to install or upgrade `bw`.**
v2024.2.0 is already at `/usr/local/bin/bw`. Do not use snap, npm, or apt to install anything.

**5. Do not modify the Vaultwarden SQLite database directly.**
The API key is correctly set. All vault operations must go through the `bw` CLI or vault tool functions.

## Task: Complete Vault Setup

### Step 1 — Verify authentication works
Call `vault_unlock()`. It must return a session token string (not starting with `ERROR:`).
If it returns an error, report it and stop — do not proceed to other steps.

### Step 2 — Create vault collections
Using the session token from Step 1, create the following collections in Vaultwarden:
- `API Keys`
- `Service Credentials`
- `Infrastructure`

Use `bw` CLI:
```bash
NODE_TLS_REJECT_UNAUTHORIZED=0 bw create org-collection \
  --organizationid <org_id> '{"name":"API Keys","externalId":null,"groups":[]}'
```
If the LSE account has no organisation, collections are not available — use folders instead:
```bash
NODE_TLS_REJECT_UNAUTHORIZED=0 bw create folder '{"name":"API Keys"}' \
  --session <session_token>
```

### Step 3 — Ingest secrets as vault items
For each secret to store, use `set_vault_secret(name, secret, session)`.
Before calling `set_vault_secret`:
1. Ask the user to confirm: "Write secret to vault item '<name>'? (yes/no)"
2. Wait for 'yes' before calling
3. After writing, call `get_vault_secret(name, session)` to verify the stored value matches

### Step 4 — Verify all items are present
Call `list_vault_items(session)` and confirm all expected items appear in the output.
Report the full list to the user.

## Fallback — If vault_unlock() Fails

If `vault_unlock()` returns an ERROR, test the raw CLI directly:
```bash
NODE_TLS_REJECT_UNAUTHORIZED=0 bw config server https://localhost:3003
NODE_TLS_REJECT_UNAUTHORIZED=0 \
  BW_CLIENTID="user.7dc216f7-dc47-4b60-9ef6-4d4aca446bd0" \
  BW_CLIENTSECRET="99cebf0ec0b88ea058fec485691c5264028e523159da3dde563c27731b394b42" \
  bw login --apikey
```

If the CLI also fails, use curl to verify the OAuth endpoint is reachable:
```bash
curl -k -s -X POST https://localhost:3003/identity/connect/token \
  -d "grant_type=client_credentials" \
  -d "client_id=user.7dc216f7-dc47-4b60-9ef6-4d4aca446bd0" \
  -d "client_secret=99cebf0ec0b88ea058fec485691c5264028e523159da3dde563c27731b394b42" \
  -d "scope=api" \
  -d "device_type=6" \
  -d "device_identifier=bw-cli" \
  -d "device_name=LSE" | python3 -m json.tool
```
Report the curl output to the user before taking any further action.

## What NOT to Do

- Do NOT call `bw login --apikey` with a bare UUID (missing `user.` prefix)
- Do NOT disable TLS globally — `NODE_TLS_REJECT_UNAUTHORIZED=0` is subprocess-only
- Do NOT try to use `NODE_EXTRA_CA_CERTS` — the bw CLI pkg binary ignores it
- Do NOT install a new version of `bw` via snap or npm
- Do NOT write secrets to the vault without user confirmation
- Do NOT report a write as successful without verifying with `get_vault_secret`
