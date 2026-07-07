# LSE product layout — Phase 1 target (review draft)

Design goal: identical code on LUCIFER, node5090, or any box. Nothing in the code knows
where it lives — paths/IPs/ports/URLs resolve from `lse.toml` (+ `secrets.env`). The
Windows boundary is crossed only for GPU, firewall, and browser. No project file ever on
`/mnt/c`.

## Four roots (separate code / config / state / secrets — XDG-clean on every OS)

| Root | env | rootless default | system default | holds |
|---|---|---|---|---|
| **code** | `LSE_HOME` | `~/.local/share/lse` | `/opt/lse` | the monorepo (versioned) |
| **config** | `LSE_CONFIG` | `~/.config/lse` | `/etc/lse` | `lse.toml`, `secrets.env` |
| **state** | `LSE_STATE` | `~/.local/state/lse` | `/var/lib/lse` | sqlite, logs, caches |
| **models** | `LSE_MODELS` | `~/.local/share/lse/models` | `/opt/models` | GGUFs |

The installer picks rootless vs system from privilege/flags. On the Linux fleet it uses the
system roots + your node5090 `lsestack` group/setgid/ACL model so the agent never needs sudo.

## Code tree ($LSE_HOME)

```
$LSE_HOME/
  goethe/
    goethe.py                       # the tool brain (reads lse.toml via the loader)
    vaultwarden_tools_v1.3.0.py     # vault tools (BW_* from secrets.env)
  mcp/
    goethe_mcp.py                   # the gateway (--also already supports multi-module)
  faust/                            # git submodule -> the Faust repo (own remote)
    gate2-group-server/
    agent-client/
  lib/
    config.py                       # loads lse.toml + secrets.env, ${var} expansion, env injection
  bin/
    lse                             # ONE entrypoint: up | down | status | doctor | install | node
  services/
    goethe-mcp.service.tmpl         # rendered by the installer ({{LSE_HOME}}, {{PORT}}, ...)
    faust.service.tmpl
    llama-server.service.tmpl
  installer/
    install.sh                      # detect OS/privilege -> prefix -> deps -> services -> config -> doctor
    lib/{linux.sh, wsl.sh, common.sh}
    templates/{lse.toml.tmpl, secrets.env.tmpl}
  docs/
  CHANGELOG.md  README.md  VERSION.md
```

## Config + secrets (never in the code tree)

```
$LSE_CONFIG/
  lse.toml          # non-secret host config (the schema in lse.toml.example)
  secrets.env       # chmod 600 — the actual secrets, referenced by *_env names in lse.toml:
                    #   GOETHE_MCP_TOKEN, BW_CLIENTSECRET, BW_PASSWORD, PFSENSE_API_KEY,
                    #   HERMES_API_KEY, LSE_FAUST_KEY, HERMES_FAUST_KEY
$LSE_STATE/
  data/   kb.sqlite  tasks.db
  logs/   agent_commands.log  llama-server.log
  cache/  fetch/  device-fingerprint/  search-budget.json
```

## Carve mapping — current repo → target (what moves where)

| Current (`/mnt/c/...local-system-engineer`) | Target |
|---|---|
| `tools/goethe.py` | `$LSE_HOME/goethe/goethe.py` |
| `tools/vaultwarden_tools_v1.3.0.py` | `$LSE_HOME/goethe/vaultwarden_tools_v1.3.0.py` |
| `tools/goethe_mcp.py` | `$LSE_HOME/mcp/goethe_mcp.py` |
| `tools/goethe-mcp.service` / `.env.example` | `$LSE_HOME/services/goethe-mcp.service.tmpl` + `installer/templates/secrets.env.tmpl` |
| `tools/download-monitor.py`, other tool scripts | `$LSE_HOME/goethe/` or `$LSE_HOME/bin/` helpers |
| `Faust/` (and `~/projects/Faust`, the canonical) | `$LSE_HOME/faust/` as a **submodule** of the Faust remote |
| `coding-gauntlet/`, old `lse-stack-launch-*.ps1`, `*.bak`, dup copies | `archive/` (out of the product path) |
| `/opt/local-se/{tasks.db, agent_commands.log, *.search_budget}` | `$LSE_STATE/{data,logs,cache}` |
| `/opt/local-se/goethe-mcp.env`, `~/.lse/secrets`, scattered keys | `$LSE_CONFIG/secrets.env` (one file) |
| hardcoded `_NODE_REGISTRY`, `/mnt/c` paths, ports, model URLs | `lse.toml` (`[[nodes]]`, `[mcp]`, `[model]`, …) |

## The one code change that unlocks it all

`lib/config.py` loads `lse.toml`, expands `${var}`, reads `secrets.env`, and hands goethe a
resolved settings object (and exports the `*_env` secrets into the process env so
`vault_unlock`/Hermes/pfSense pick them up exactly like OWUI does today). goethe's `Valves`
and `_NODE_REGISTRY` become thin wrappers that read from it — so the same `goethe.py` runs on
any box, differentiated only by that box's `lse.toml`.

## Decisions (locked)
- Faust = **git submodule** (own remote + history).
- **System install** default on the fleet: `/opt/lse` + `lsestack` group/setgid/ACLs (node5090 model);
  rootless `~/.local` is the portable fallback the installer offers.
- Models: **`/opt/models`** canonical on every node (`[lse].models_dir`).
- `download-monitor.py` is **product**.

## Product file manifest (substantiated) → target
| File(s) | Target | Note |
|---|---|---|
| `goethe.py`, `vaultwarden_tools_v1.3.0.py` | `$LSE_HOME/goethe/` | core tool brains |
| `goethe_mcp.py` | `$LSE_HOME/mcp/` | the gateway |
| `download-monitor.py` | `$LSE_HOME/goethe/` | + `download-speed-exporter.py` (its metric source) |
| `pfsense_graphql/query/log_summary` (methods **extracted from** `goethe.py`) + `pfsense_log_gateway.py` | `$LSE_HOME/skills/pfsense/` | **deployable skill** (see below) |
| `net-discovery/*` | `$LSE_HOME/skills/net-discovery/` | **deployable skill** |
| `vaultwarden_tools_v1.3.0.py` | `$LSE_HOME/skills/vault/` | **deployable skill** (the prototype) |
| `llamacpp-slots-exporter.py`, `nvidia-gpu-exporter.py`, `download-speed-exporter.py` | `$LSE_HOME/exporters/` | per-node Prometheus exporters |
| `lse-context-monitor-v1.3.0.py`, `lse-routing-filter-v1.2.0.py` | `$LSE_HOME/owui/` | OWUI-only filters (optional) |
| `rag/{02-es-setup,03-kb-seed,05…,06…,07…}.py` | `$LSE_HOME/installer/setup/` | run-once ES/KB/runbook bootstrap |
| ~120 version/eval/one-off files | `archive/` (outside the product path; in git history) | not shipped |

## Deployable skills layer
A **skill** = a self-contained capability package the gateway loads on demand. Core stays
universal; domain capabilities (firewall admin, topology discovery, secret access) deploy
per-box. `vaultwarden` already works this way (loaded via `goethe_mcp --also`) — we formalize it.

> Distinct from **runbooks** (the `lse-skills` ES index + `skill_search`/`skill_record`): those
> are runtime procedures the model retrieves. A *skill package* is an installable bundle.

```
$LSE_HOME/skills/<name>/
  skill.toml        # manifest: name, version, tools module, services, kb/, config keys, deps
  tools.py          # the OWUI Tools class (model-callable methods) — gateway loads via --also
  services/         # background services + *.service.tmpl   (pfsense: the :9191 log gateway)
  kb/               # KB/runbook seed docs, indexed on deploy (pfsense: API + GraphQL schema)
  config.schema     # the lse.toml fragment this skill needs ([pfsense], [vault], …)
  README.md
```

`skill.toml` example (pfsense):
```toml
name = "pfsense"
version = "1.0.0"
tools = "tools.py"                    # → gateway --also
services = ["services/pfsense-log-gateway.service.tmpl"]
config = ["pfsense"]                  # lse.toml sections it owns
deps = ["vault"]                      # needs vault_unlock for the api_key
kb = "kb/"                            # seeded into ES on `lse skill add pfsense`
```

**Selection in `lse.toml`** — one line decides what a box runs:
```toml
[lse]
skills = ["vault", "pfsense"]         # node5090 might be ["vault"]; a topology box adds "net-discovery"
```
The gateway turns `skills` into its `--also` set automatically; `lse skill add/remove/list`
manage them (register tools, start/stop services, seed/prune KB, prompt for config/secrets).

**Skill boundaries (now and later):** `vault`, `pfsense`, `net-discovery` first. The same
extraction later peels `cluster` (wake/query/start/stop/shutdown node + Hermes `hermes_plan` +
Faust) out of core too — but that's a follow-on, not Phase 1.

## WSL host bootstrap (the foundation — managed templates, enforced invariants)
Two files, two layers, two owners — both rendered by the installer, never hand-maintained:

```
installer/templates/
  wslconfig.tmpl     ->  C:\Users\<user>\.wslconfig   (Windows host; VM-level: RAM/CPU/swap/network)
  wsl.conf.tmpl      ->  /etc/wsl.conf                (inside WSL; systemd/DNS)
```

**`.wslconfig` (Windows, VM resources)** — per-machine values come from the host config:
```ini
[wsl2]
memory={{ wsl_memory }}          # LUCIFER: 48GB
processors={{ wsl_processors }}  # LUCIFER: 20
swap={{ wsl_swap }}              # LUCIFER: 8GB
networkingMode=mirrored          # INVARIANT — no netsh portproxy (the self-loop disaster)
```
**`/etc/wsl.conf` (inside WSL)**:
```ini
[boot]
systemd=true                     # INVARIANT — required for the systemd services we ship
[network]
generateResolvConf=false         # your DNS choice on node4090; carried per-host
```

**Product invariants for any WSL host** (the installer asserts these, refuses otherwise):
1. `networkingMode=mirrored` — bind LAN directly, **no portproxy table** (and never forward to the
   host IP — that's the infinite loop we hit).
2. `systemd=true` — so `goethe-mcp`, `faust`, `llama-server` run as units, not hand-launched.
3. After writing these, a **`wsl --shutdown`** is required for them to take effect (installer prompts).

These VM/WSL values are **host-bootstrap config**, separate from `lse.toml` (which lives *inside*
WSL and is set later) — they're captured in the installer's per-host params, since `.wslconfig`
must exist before WSL is even usable.
