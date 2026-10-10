# Shodan Dashboard — Operation Manual

Single-user Shodan search dashboard. SvelteKit frontend; **all Shodan API calls
go through the local backend MCP server**. The frontend contains no Shodan key,
no API logic, and no grouping/derivation code (audited — `audit_no_shodan_logic.txt`,
verdict `NO_SHODAN_LOGIC_PASS`).

## Architecture

```
Browser (http://localhost:5173)
 └─ SvelteKit + tRPC            (shodan-web/)
     └─ tRPC proxy fetch        (src/lib/server/trpc/router/search.ts)
         └─ http://127.0.0.1:9702/api/search   (backend, single code path)
             └─ shodan_mcp_server.py → https://api.shodan.io  (SHODAN_API_KEY)

Persistence: Prisma + SQLite (prisma/) — saved searches, bookmarks, device history.
```

## Components

| Piece | Path |
|---|---|
| Frontend | `/home/sy5/projects/local-system-engineer/shodan-web` |
| Backend (MCP server) | `.../local-system-engineer/tools/shodan_mcp_server.py` |
| Backend launcher | `.../tools/start-shodan.sh` (idempotent, health-checks) |
| Backend env file | `.../tools/shodan-mcp.env` (copy from `shodan-mcp.env.example`) |
| Backend log | `/tmp/shodan_mcp.log` |
| Studio MCP config | `/opt/local-se/mcp-servers.json` |

## Prerequisites

1. **Node v24** (nvm): `export PATH="$HOME/.nvm/versions/node/v24.16.0/bin:$PATH"`
2. **Python 3.13**: `/home/sy5/miniforge3/bin/python`
3. **Shodan API key** (free): https://account.shodan.io → API tab

## Backend — start / stop / verify

```sh
# start (idempotent — exits 0 if already running)
/home/sy5/projects/local-system-engineer/tools/start-shodan.sh

# health
curl -s http://127.0.0.1:9702/health

# raw search (works without the frontend)
curl -s 'http://127.0.0.1:9702/api/search?query=port:443&limit=5'

# stop
kill $(pgrep -f 'shodan_mcp_[s]erver.py')
```

### One-time key setup

```sh
cd /home/sy5/projects/local-system-engineer/tools
cp shodan-mcp.env.example shodan-mcp.env
# then edit shodan-mcp.env and fill in:  SHODAN_API_KEY=<your key>
```

- The key is also stored in Vaultwarden under the item name `SHODAN_API_KEY`
  (retrieve: `vault_unlock` → `get_vault_secret("SHODAN_API_KEY")`).
- **Without the key** every search returns 503:
  `SHODAN_API_KEY is not set. Export a Shodan API key (free at https://account.shodan.io)`.
- `start-shodan.sh` sources `shodan-mcp.env` with `set -a`, so the key lands in
  the server's environment. After editing the env file, restart the backend.

## Frontend — start / stop / access

```sh
cd /home/sy5/projects/local-system-engineer/shodan-web
export PATH="$HOME/.nvm/versions/node/v24.16.0/bin:$PATH"

# development server (recommended for daily use)
npm run dev -- --host 127.0.0.1        # → http://127.0.0.1:5173

# production build + preview
npm run build && npm run preview

# stop
kill $(cat /tmp/shodan_web_dev.pid)    # or: pkill -f vite
```

**Access URLs**

| From | URL |
|---|---|
| Windows host (WSL2 localhost forwarding) | `http://localhost:5173` |
| Same machine (WSL) | `http://127.0.0.1:5173` |
| LAN | bind with `--host 0.0.0.0` → `http://192.168.1.57:5173` (only if you accept LAN exposure of a single-user dashboard) |

**Features**: Shodan query bar → device table (grouped by IP: device, IP, open
ports, location/geo); save searches; bookmark devices; search history. All
persistence is local SQLite.

## Unsloth Studio — MCP integration

The Studio UI's MCP list is only as good as the engine's MCP registry. The
engine (`llama-server`, the inference backend of this very session) serves MCP
**only** when started with:

```
--ui-mcp-proxy --mcp-servers-config /opt/local-se/mcp-servers.json
```

- Without both flags: `curl http://127.0.0.1:<engine-port>/mcp-servers` → **404**,
  and any MCP card in the Studio UI is stale browser-side state — it can show
  "active" while no tools are actually routable.
- `/opt/local-se/mcp-servers.json` is Cursor-compatible JSON and currently
  registers the Shodan server (`http://127.0.0.1:9702/mcp`, streamable-HTTP).
- The engine port is **ephemeral per session** — find it with
  `ss -tlnp | grep llama-server`.
- After restarting the engine with the flags, verify:
  `curl -s http://127.0.0.1:<engine-port>/mcp-servers` must return the `shodan`
  definition (not 404). Then SHODAN appears in the Studio MCP list and its
  tools are available to the model.
- Restarting the engine interrupts the active inference session — do it
  deliberately (kill it in the terminal tab where it runs, relaunch with the
  same command line plus the two flags above).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Frontend shows 503 "Export SHODAN_API_KEY on the backend and restart it" | Key not set on backend | Fill `tools/shodan-mcp.env`, restart backend |
| Frontend page doesn't load | Dev server not running | `npm run dev -- --host 127.0.0.1` |
| Raw `/api/search` works but frontend search fails | tRPC proxy target down or stale build | Check `ss -tlnp \| grep 9702`; rebuild |
| MCP card "active" in Studio but tools fail / server missing from list | Engine lacks `--ui-mcp-proxy` + `--mcp-servers-config` (or stale client state) | Restart engine with both flags; verify `/mcp-servers` returns 200 |
| `Port 5173 already in use` | Stale dev server | `kill $(cat /tmp/shodan_web_dev.pid)` |
| Backend `/health` fails after restart | Env file typo / missing | `tail /tmp/shodan_mcp.log` |

## Audit / evidence files (read-only, kept in shodan-web/)

- `audit_no_shodan_logic.txt` — proof of no Shodan business logic in frontend
- `check_build.txt` / `check_build2.txt` — svelte-check + build results (final: 0 errors)
- `live_endpoint_probe.txt` — raw `/api/search` probe log
- `e2e_ui_check.txt` — end-to-end UI verification log
