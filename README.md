# Local System Engineer (LSE)

A locally-hosted AI system administrator running on a private inference stack. Operates within a strict permission boundary on WSL2/Ubuntu 24.04: executes shell commands, reads/writes files in allowed paths, delegates sudo to the user, searches the web only on demand, and never escalates privileges silently.

---

## Current Stack

| Layer | Component |
|---|---|
| Host | Windows 11 → WSL2 → Ubuntu 24.04 (hostname: LUCIFER) |
| Inference | llama.cpp `llama-server` |
| Model | Qwen3.6-27B-Q5_K_M (32k ctx · MTP · thinking budget 3072) |
| Frontend | OpenWebUI (localhost:3000) |
| Web search | SearxNG (self-hosted, localhost:8088) |
| Monitoring | Prometheus + Grafana + custom context alert pipeline |
| Launcher | Windows Terminal PowerShell profiles (lse-stack-launch-*.ps1) |

---

## Current Component Versions

| Component | Version | File |
|---|---|---|
| Tool | v1.5.7 | `tools/openwebui-tool-v1.5.7.py` |
| Prompt | v0.5.4 | `prompts/v0.5.4.md` |
| Routing filter | v1.1.0 | `tools/lse-routing-filter-v1.1.0.py` |
| Launcher | v1.070 | `lse-stack-launch-1.070.ps1` |
| Test suite | v3.5 | `eval/test-suite-v3.5.md` |

Context monitoring is handled externally — see [Context Alert Pipeline](#context-alert-pipeline).

---

## Agent Capabilities

- Read files within `/home/` `/etc/` `/var/log/` `/tmp/lse/` `/opt/local-se/`
- Write files within `/home/` `/tmp/lse/` `/opt/local-se/`
- Execute shell commands with output filtering (never >80 lines raw)
- Delegate any `sudo` operation to the user via `sudo_delegation_block` — never runs sudo itself
- Search the web via SearxNG only when knowledge is insufficient, announced before calling
- Look up GitHub release versions via `get_github_release()`
- Report context fill on explicit user request via `get_context_status()`

**Permanently blocked (no exceptions, no delegation):** `mkfs fdisk parted iptables -F passwd visudo wipefs dd if=`

---

## Repository Layout

```
local-system-engineer/
├── README.md
├── ROADMAP.md                             ← project status and pending work
├── VERSION.md                             ← component version registry + co-test matrix
│
├── docs/
│   ├── 01-model-evaluation.md             ← model selection rationale (Qwen3.6-27B)
│   ├── 02-terminal-interaction.md         ← OpenWebUI tool design and safety model
│   ├── 03-context-management.md           ← context observability and remediation
│   ├── 04-knowledge-base.md               ← KB design and injection strategy
│   ├── 05-skills-planning.md              ← skills roadmap
│   ├── 06-safety-and-delegation.md        ← three-tier model, denylist, SEP template
│   ├── 07-operations-runbook.md           ← stack start, recovery, hot-swap, shutdown
│   └── 08-launcher-edit-workflow.md       ← strip-sig / edit / certsign workflow for PS1 files
│
├── prompts/
│   ├── CHANGELOG.md                       ← version history and rationale for every bump
│   ├── v0.5.4.md                          ← current production prompt
│   └── v0.1-baseline.md … v0.5.3.md      ← full history (never overwrite)
│
├── tools/
│   ├── openwebui-tool-v1.5.7.py           ← current production tool (upload to OpenWebUI Admin → Tools)
│   └── lse-routing-filter-v1.1.0.py       ← active routing filter (OpenWebUI Admin → Functions)
│
├── eval/
│   ├── test-suite-v3.5.md                 ← 21-question scored eval suite
│   ├── eval-report-v1.md … v4.md          ← scored run reports
│   └── eval-runner/                       ← lse:eval-runner skill
│
└── skills/
    ├── lse-eval-runner/                   ← structured eval session guide
    ├── lse-docstring-optimizer/           ← docstring review against LSE failure history
    ├── lse-stack-health-check/            ← pre-session service verification
    ├── lse-session-debrief/               ← end-of-session KB update guide
    └── lse-version-manager/               ← changelog + co-test matrix management
```

---

## Context Alert Pipeline

Context monitoring is decoupled from the model. A Grafana alert fires when the KV cache exceeds 80% and posts to the `lse-alerts` OpenWebUI channel.

```
llama-server /slots + /metrics
    ↓
llama-context-exporter  (systemd, port 9836)
    → llama_kv_cache_usage_ratio  (dynamic: works for 32k and 64k profiles)
    → llama_context_size
    ↓
Prometheus scrapes every 15s
    ↓
Grafana alert: llama_kv_cache_usage_ratio > 0.8, for=1m
    ↓
grafana-owui-adapter  (systemd, port 9837)
    → converts Grafana JSON → {"content": "⚠ ..."}
    ↓
OpenWebUI channel webhook → lse-alerts channel
```

Service files: `/etc/systemd/system/llama-context-exporter.service` and `grafana-owui-adapter.service`
Scripts: `/opt/local-se/llama-context-exporter.py` and `/opt/local-se/grafana-owui-adapter.py`

---

## Eval Score History

| Run | Tool | Prompt | Mode | Score |
|---|---|---|---|---|
| Run 1 | v1.4.0 | v0.1-baseline | thinking | unscored baseline |
| Run 2 | v1.5.1 | v0.4.1 | thinking | 45/57 |
| Run 3 | v1.5.4 | v0.5.1 | thinking (budget 3072) | **57/57** |
| Run 4 | v1.5.5 | v0.5.2 | no-think (budget 0) | 49/57 |
| Run 5 (partial) | v1.5.6 | v0.5.2 | thinking (budget 3072) | 15/21 subset |

---

## Key Design Decisions

**No autonomous sudo.** Every privileged operation emits a `sudo_delegation_block` the user runs manually. No silent escalation, ever.

**Confirmation before destruction.** Any `rm`, truncate, or file overwrite requires the model to state exactly what will be deleted and wait for an explicit yes/no.

**Read before write.** Any sudo operation touching a config file must read the current state first.

**Eval-driven development.** Every version bump gets a scored eval run before being considered production-ready.

**Context monitoring outside the model.** All previous in-model context monitoring approaches (v1.0–v1.3 filter) failed — the model always prioritises task completion over meta-monitoring. Monitoring is now handled externally by the Grafana pipeline.

---

## Launcher Edit Workflow

The launcher (`.ps1`) is Authenticode-signed. Any edit requires stripping the signature first:

```powershell
.\strip-sig.ps1 -Path .\lse-stack-launch-1.070.ps1
# edit the file
$errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path .\lse-stack-launch-1.070.ps1).Path, [ref]$null, [ref]$errors)
$errors   # must be empty before signing
.\certsign.ps1 -Path .\lse-stack-launch-1.070.ps1
```

See `docs/08-launcher-edit-workflow.md` for full details.
