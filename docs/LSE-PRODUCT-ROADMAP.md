# LSE Product — Execution Roadmap

The canonical phase plan for turning the LSE into a portable, installable product.
Companion design docs: **`lse.toml.example`** (config schema) · **`LSE-PRODUCT-LAYOUT.md`**
(directory tree, file manifest, WSL bootstrap, skill layer).

## North star
One codebase runs on any box (LUCIFER, node5090, a stranger's laptop). Behaviour is
differentiated **only** by that box's `lse.toml`. Nothing hardcodes a path/IP/port/URL.
Everything lives on native fs — never `/mnt/c`. Domain capabilities ship as **deployable
skill packages**; the core is a universal framework.

## Guiding invariants (locked)
- **Native fs only.** Code/config/state/models off the Windows mount. Windows = GPU + firewall + browser.
- **Four roots:** code `$LSE_HOME` · config `$LSE_CONFIG` · state `$LSE_STATE` · models `/opt/models`.
- **System install** on the fleet: `/opt/lse` + `lsestack` group/setgid/ACLs (node5090 model); rootless `~/.local` is the portable fallback.
- **WSL invariants:** `networkingMode=mirrored` (no portproxy, ever) + `systemd=true`.
- **Config-driven:** `lse.toml` (committable) + `secrets.env` (chmod 600, referenced by name).
- **Skill packages** for domain capability (vault/pfsense/net-discovery); **runbooks** = the separate `lse-skills` ES index.
- **Faust** = git submodule. **Monorepo** on a git remote (portability + visibility off `/mnt/c`).

## Phases (in order)

| # | Phase | Status | Task | Depends on |
|---|---|---|---|---|
| 0 | Design & decisions | ✅ done | #10 | — |
| 1 | Monorepo scaffold + config loader | ⬜ next | #11 | 0 |
| 5 | Git remote (do **early** — right after 1) | ⬜ | #14 | 1 |
| 2 | Deployable skill-package layer | ⬜ | #15 | 1 |
| 3 | `bin/lse` CLI entrypoint | ⬜ | #12 | 1, 2 |
| 4 | Installer (Linux/WSL), proven on node5090 | ⬜ | #13 | 1–3 |
| 6 | macOS / launchd branch | ⏸ deferred | — | 4 |
| 7 | `cluster` skill extraction (node mgmt + Hermes + Faust) | 🔭 follow-on | — | 2 |

Note: **#5 is numbered late but executed early** — pushing to a remote right after the scaffold
is what gets us (and every box) off the `/mnt/c` mirror.

---

### Phase 0 — Design & decisions ✅
- **Done:** `lse.toml` schema, `$LSE_HOME` layout, four-roots model, WSL bootstrap templates +
  invariants, substantiated file manifest (~12 product files, ~120 to archive), skill-package layer.
- **Artifacts:** `docs/lse.toml.example`, `docs/LSE-PRODUCT-LAYOUT.md`, this roadmap.

### Phase 1 — Monorepo scaffold + config loader  (task #11)
- **Do, non-destructively (copy, don't move):**
  - `git init` a fresh `lse` monorepo; build the `$LSE_HOME` tree.
  - Copy the ~12 product files in; leave `/mnt/c` repo + `~/projects` untouched.
  - `lib/config.py`: load `lse.toml` + `secrets.env`, expand `${var}`, export `*_env` secrets to
    the process env, resolve `[[nodes]]`.
  - goethe's `Valves` + `_NODE_REGISTRY` → thin readers over the loader (fallback-safe so it still
    runs standalone in OWUI unchanged).
- **Done when:** `goethe.py` + `goethe_mcp.py` run from `$LSE_HOME` reading only `lse.toml`; no
  `/mnt/c` string anywhere; 37 tools still list.

### Phase 5 — Git remote  (task #14) — *pull forward to here*
- Push the monorepo to GitHub/Gitea; add Faust as a submodule.
- Fleet switches to **clone-from-remote**; I work from the remote, not the mount.
- **Done when:** `git clone` on a clean box yields a runnable tree.

### Phase 2 — Deployable skill-package layer  (task #15)
- Define `skill.toml` manifest + `skills/<name>/` layout.
- Extract `pfsense_graphql/query/log_summary` out of `goethe.py` → `skills/pfsense/` (tools + the
  `:9191` gateway + KB + `[pfsense]` config + `vault` dep). Package `vault` and `net-discovery` the same way.
- Gateway turns `[lse].skills` into its `--also` set.
- **Done when:** `skills=["vault","pfsense"]` exposes their tools via the gateway; core loads with
  zero skills; `lse skill add/remove/list` works.

### Phase 3 — `bin/lse` CLI  (task #12)
- One entrypoint: `lse up | down | status | doctor | install | node … | skill …`.
- Reads `lse.toml`; starts gateway + sidecars + (per role) llama-server; right transport/ports.
- **Done when:** `lse up` replaces every hand-typed `npx tsx …` / `python3 goethe_mcp.py …`.

### Phase 4 — Installer (Linux/WSL), proven on node5090  (task #13)
- `install.sh`: detect OS/privilege → pick prefix → `uv` venv + node → render systemd templates →
  write WSL bootstrap (`.wslconfig` + `/etc/wsl.conf`, assert invariants, prompt `wsl --shutdown`)
  → generate `lse.toml` from prompts → provision `secrets.env` → run `lse doctor`.
- Folds in `deploy-node5090.ps1` (Windows bootstrap) + `provision-node5090.sh` (WSL).
- **Done when:** a fresh node5090 goes from bare WSL to a running LSE in one scripted pass.

### Phase 6 — macOS / launchd  ⏸ deferred
- launchd plists, mac path/venv handling, `lse doctor` polish for the "any system" reach.

### Phase 7 — `cluster` skill  🔭 follow-on
- Peel node lifecycle (wake/query/start/stop/shutdown) + Hermes (`hermes_plan`, `_call_hermes`) +
  Faust orchestration out of core into `skills/cluster/`.

## Recommended execution order
**1 → 5 (early) → 2 → 3 → 4**, with 6 and 7 after the fleet install is proven.
