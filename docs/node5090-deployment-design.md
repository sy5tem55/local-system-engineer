# node5090 Deployment Design
> Status: DRAFT for review · 2026-06-11 (P20 Cowork)
> Target: node5090.home.arpa · 192.168.1.55 · hostname 1BL15 · MAC a0:ad:9f:84:d5:bf
> Hardware: X870E · Ryzen 9800X3D · 64GB RAM · RTX 5090 32GB
> Host: Windows 11 Enterprise 25H2 (gaming machine, dual-use) + WSL2 Ubuntu 24.04
> Companion scripts: `scripts/node5090/{deploy-node5090.ps1, provision-node5090.sh, teardown-node5090.ps1}`

---

## 1. Role in the cluster

node5090 **is NODE3** from the roadmap. It becomes the **primary home of Qwen3.6-35B-A3B** (resolves the v1.7.0 §5.2 serving-topology decision — node3090 stays dedicated to 27B/Hermes, no more model-swap maintenance windows). Single canonical service: llama-server on :8080, same conventions as node3090.

Cluster after deployment:

| Node | IP | GPU | Serves | Port |
|---|---|---|---|---|
| LUCIFER (node4090.home.arpa) | 192.168.1.57 | RTX 4090 | Qwen3.6-27B (LSE session) + OWUI + ES + Grafana/Prom | 8080/3000/9200 |
| node3090 | 192.168.5.41 | RTX 3090 24GB | Qwen3.6-27B (Hermes backend) + LM Studio | 8080/1234 |
| **node5090** | **192.168.1.55** | **RTX 5090 32GB** | **Qwen3.6-35B-A3B (coding delegate)** | **8080** |

VRAM check: 35B-A3B Q4_K_M ≈ 19–20GB + 96k ctx KV (q8_0) fits 32GB with headroom. Launcher profile facts carry over: **`--no-mtp` is mandatory** (MTP fails on 35B A3B MoE — lse-profiles.xml note).

## 2. Decision: Dify vs n8n → neither runs on node5090

**Decision: orchestration stays centralized on LUCIFER. node5090 runs inference + exporters + sshd only.**

- **Dify** is already the adopted multi-agent UI (P18 decision: persistent Postgres chat, human-in-the-loop, on-demand at `/opt/dify`, port 4000). It orchestrates; nodes execute. Adding a second Dify fragments workflow state across hosts for zero benefit.
- **n8n** solves a different problem — event/webhook/cron integration automation, not LLM orchestration. Nothing in the current stack needs it. **Revisit only when** a concrete trigger-driven workflow appears (e.g. "on Grafana alert → run LSE diagnostic → post to Telegram"), and then deploy it **on LUCIFER or the VPS**, never per-node.
- Principle: **cluster nodes are stateless capacity.** Anything with a database, a UI, or workflow state lives on LUCIFER. This is what makes teardown-to-gaming trivial and node loss a non-event.

## 3. Directory structure — one canonical location, no duplicates by construction

node-t3-005's root pathology was *two* model locations (`/opt/models` vs `~/.lmstudio`). node5090 gets exactly one:

```
/opt/models/                      root:lsestack 2775   ← ALL GGUFs. No ~/.lmstudio, no LM Studio store.
  └─ <family>/<file>.gguf
/opt/local-se/                    root:lsestack 2775
  ├─ kb/                          node-local KB notes (synced facts)
  ├─ logs/                        llama-server.log, provision.log
  └─ scripts/                     node-local helpers
/etc/llama/llama-server-5090.env  root:root 644        ← canonical launch params (single source of truth)
```

The systemd unit reads `/etc/llama/llama-server-5090.env`. Changing model/ctx = edit env file + restart — the "canonical launch command" lives in ONE root-owned file, not in a KB doc that can drift (node-t3-003/004 class of problem).

## 4. Permission framework — the t3-005 lesson, institutionalized

Goal: **LSE never needs sudo for routine operations.** Friction is eliminated structurally, not via escalation.

1. **Group `lsestack` (gid 1900)** — members: `sy5`, `lse-admin`, any future service user.
2. **Shared dirs are setgid group-writable**: `root:lsestack`, mode `2775`; default ACL `g:lsestack:rwX` so new files inherit group access regardless of creator's umask.
3. **umask 002** via `/etc/profile.d/lsestack.sh` for group members.
4. **Scoped NOPASSWD sudoers** (`/etc/sudoers.d/lse-admin`, the only sudo LSE-adjacent accounts get):
   ```
   lse-admin ALL=(root) NOPASSWD: /usr/bin/systemctl restart llama-server-5090, \
     /usr/bin/systemctl stop llama-server-5090, /usr/bin/systemctl start llama-server-5090, \
     /usr/bin/journalctl, /usr/sbin/shutdown
   ```
   No blanket ALL. Remember: the LSE tool blocks `sudo` in `execute_command` anyway — sudoers here serves the human and `shutdown_node`-style exempted functions only.
5. **llama-server runs as `llama` service user** (member of lsestack, no shell, no sudo). Process ownership never blocks `pkill`-style management because lifecycle goes through systemctl (covered by the sudoers scope) — but for symmetric parity with node3090 conventions, the unit also allows lse-admin restart without sudo via `systemctl --user`? No — keep it simple: scoped sudoers above is the single mechanism.

## 5. Networking

- **WSL2 mirrored networking** (`.wslconfig: networkingMode=mirrored`) — WSL services bind directly on 192.168.1.55; no netsh portproxy table to maintain or tear down. ✅ Supported: host is Win11 Enterprise 25H2.
- Windows Defender Firewall inbound allows: 22 (sshd), 8080 (llama-server), 9100 (node_exporter), 9835 (nvidia exporter) — created by deploy script with `LSE-` name prefix so teardown can remove them by prefix.
- **pfSense:** ✅ DONE (2026-06-11) — static DHCP `a0:ad:9f:84:d5:bf` → 192.168.1.55 (hostname 1BL15); host override `node5090.home.arpa` → 192.168.1.55. Alias convention confirmed as `nodeXXXX` (LUCIFER alias is `node4090.home.arpa`, supersedes the old `4090`/`5090` roadmap naming).
- **LUCIFER Prometheus:** add scrape targets `node5090.home.arpa:9100`, `:9835`, llama-server `/metrics` on :8080.

## 6. Deployment flow

```
deploy-node5090.ps1 (elevated, Windows)         provision-node5090.sh (inside WSL, once)
  1. Enable WSL + VirtualMachinePlatform          1. apt base + build deps + CUDA toolkit (WSL)
  2. Write .wslconfig (mirrored, RAM cap,         2. Create lsestack group, lse-admin + llama users,
     autoMemoryReclaim=gradual)                      sudoers scope, umask profile
  3. Install Ubuntu-24.04, enable systemd         3. Create /opt tree (2775 + default ACLs)
  4. Firewall rules (LSE-* prefix)                4. Build llama.cpp (CUDA) → /usr/local/bin/llama-server
  5. Invoke provision script in WSL               5. Install authorized_keys (LUCIFER pubkeys), sshd
  6. Print pfSense/Prometheus manual checklist    6. systemd units: llama-server-5090 + exporters
                                                  7. Model fetch (scp from n45/node3090 or HF) → /opt/models
                                                  8. Health verify: /health + nvidia-smi + group-write probe
```

Idempotent: both scripts are safe to re-run; every step checks before acting.

## 7. Teardown — two tiers

**Tier 1 — game mode (minutes, reversible):** `wsl --shutdown` after stopping services. Releases ALL VRAM/RAM to Windows. This is the daily path (existing `wsl-gaming-teardown.ps1` pattern; node5090 variant included in deploy kit as it only needs to stop llama-server + exporters).

**Tier 2 — full restore to pre-WSL Windows 11** (`teardown-node5090.ps1`):
1. Optional `wsl --export` backup of the distro to a `.tar` (prompted).
2. `wsl --unregister Ubuntu-24.04` — removes distro + vhdx (all Linux state).
3. Delete `%USERPROFILE%\.wslconfig`.
4. Remove all `LSE-*` firewall rules.
5. Disable optional features: `Microsoft-Windows-Subsystem-Linux`, `VirtualMachinePlatform` (+ remove WSL store app if present).
6. Print residue checklist (NVIDIA driver stays — it's the gaming driver; pfSense entries are external and listed for manual removal).
7. Reboot prompt — machine is back to pre-WSL Windows 11.

Everything the deploy script creates is enumerable (LSE-prefixed rules, one .wslconfig, one distro) — that is what makes Tier 2 honest. Nothing is installed Windows-side except the WSL features themselves.

## 8. Open items / human steps
- [x] ~~Confirm mirrored networking support~~ — Win11 Enterprise 25H2 ✅
- [x] ~~pfSense static DHCP + DNS overrides~~ — DONE 2026-06-11 (1BL15 / a0:ad:9f:84:d5:bf → .55; node5090.home.arpa live)
- [ ] Prometheus scrape config on LUCIFER + Grafana panels.
- [ ] **Model transfer — decision:** stage via **n45 NAS** for the initial deploy (boring, fast, LAN);
  the **LSE+Hermes-orchestrated node-to-node transfer** becomes its own arena challenge
  (`node5090-t2-xxx`: LSE scp node3090→node5090 with Hermes pre/post notification, checksum
  verify, df check on both ends) — perfect first exercise of the §2 hermes_notify protocol
  and a natural skills-distillation source.
- [ ] Arena challenges: `node5090-t1-001` (discovery), `t2` (health), `t3` (35B delegation smoke test) — feeds the v1.7.0 delegation workstream.
- [ ] KB entry `/opt/local-se/kb/node5090-llama-launch.md` after first successful launch.
