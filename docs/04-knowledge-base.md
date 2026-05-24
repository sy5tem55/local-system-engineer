# 04 — Knowledge Base Design

## 1. Purpose

The knowledge base (KB) is a curated, versioned reference document that the agent can access without issuing tool calls. Its goal is to reduce tool calls (and therefore context tokens) for facts that are stable, well-known, and specific to the target environment.

Without a KB, the agent issues a `read_file` or `execute_command` call every time it needs to recall something like "where does Ubuntu 24.04 put nginx's error log?" — wasting tool budget and context. With a KB, it answers from memory.

---

## 2. KB Content Scope

### 2.1 Ubuntu 24.04 LTS Reference

**Package management (apt)**
- Default sources: `/etc/apt/sources.list` and `/etc/apt/sources.list.d/`
- Lock files: `/var/lib/dpkg/lock-frontend`, `/var/lib/apt/lists/lock`
- Cache: `/var/cache/apt/archives/`
- Common operations: `apt update`, `apt upgrade -y`, `apt install`, `apt remove --purge`, `apt autoremove`, `apt list --installed`, `dpkg -l`, `dpkg -S <file>`
- Hold a package: `apt-mark hold <pkg>` / `apt-mark unhold <pkg>`

**Standard log locations**
```
/var/log/syslog           — general system log
/var/log/auth.log         — authentication events
/var/log/apt/history.log  — package installation history
/var/log/dpkg.log         — dpkg operation log
/var/log/kern.log         — kernel messages
/var/log/nginx/           — nginx access and error logs
/var/log/apache2/         — apache2 logs
/var/log/mysql/           — mysql logs
/var/log/journal/         — systemd journal (use: journalctl -u <service>)
```

**Standard config locations**
```
/etc/hostname             — machine hostname
/etc/hosts                — static host entries
/etc/resolv.conf          — DNS resolver config (managed by systemd-resolved on 24.04)
/etc/fstab                — filesystem mount table
/etc/environment          — system-wide environment variables
/etc/profile.d/           — shell profile scripts (loaded for all users)
/etc/sudoers.d/           — sudoers drop-in directory
/etc/cron.d/              — system cron jobs
/etc/systemd/system/      — user-defined service units
/etc/ssh/sshd_config      — SSH daemon config
/etc/netplan/             — network configuration (Ubuntu 24.04 default)
```

**User-space config locations**
```
~/.bashrc                 — bash interactive shell config
~/.bash_profile           — bash login shell config
~/.profile                — POSIX shell login config
~/.config/                — XDG config directory
~/.local/share/           — XDG data directory
~/.ssh/                   — SSH keys and config
```

### 2.2 systemd Reference

**Key commands**
```bash
systemctl status <unit>          # show unit status
systemctl list-units --type=service --state=running
systemctl list-unit-files        # all units and their enable state
systemctl enable --now <unit>    # enable and start
systemctl disable --now <unit>   # disable and stop
systemctl daemon-reload          # reload after unit file changes
journalctl -u <unit> -n 50 --no-pager   # last 50 lines of unit log
journalctl -u <unit> --since "1 hour ago"
```

**Unit file locations** (priority order, highest first):
1. `/etc/systemd/system/` — admin overrides
2. `/run/systemd/system/` — runtime units
3. `/usr/lib/systemd/system/` — package-installed units

**Requires sudo**: all `systemctl start/stop/restart/enable/disable/daemon-reload` commands.

### 2.3 WSL2 Ubuntu 24.04 Specifics

- `/mnt/c/`, `/mnt/d/` etc. — Windows drives mounted via DrvFs
- `/proc/version` contains `Microsoft` for WSL detection
- `wsl.conf` at `/etc/wsl.conf` controls automount, interop, hostname
- Networking: WSL2 uses a NAT'd virtual switch; the Windows host is at the gateway IP (typically `172.16.x.1` or `192.168.x.1`)
- `systemd` is available on WSL2 Ubuntu 24.04 when `[boot] systemd=true` is set in `/etc/wsl.conf`
- Common WSL path translation: `C:\Users\<user>` → `/mnt/c/Users/<user>`
- Windows executables callable from WSL: append `.exe` (e.g., `notepad.exe`, `explorer.exe`)
- X11/Wayland: WSLg provides GUI support; `DISPLAY` is set automatically

### 2.4 Common Service Patterns

```bash
# Check if a service is running
systemctl is-active <service>

# One-liner: install + enable + start
sudo apt install -y <pkg> && sudo systemctl enable --now <service>

# Reload without restart (for nginx, apache, etc.)
sudo nginx -t && sudo systemctl reload nginx

# Watch a service log live
journalctl -fu <service>

# Find which package owns a config file
dpkg -S /etc/nginx/nginx.conf
```

### 2.5 Agent Operational Constraints Reference

Store the environment-specific constraints here so they are always available without a tool call:

```
ALLOWED_READ_PATHS:  /home/, /etc/, /var/log/, /tmp/lse/, /opt/local-se/
ALLOWED_WRITE_PATHS: /home/, /tmp/lse/, /opt/local-se/
SUDO_REQUIRED_FOR:   /etc/ writes, systemctl start/stop/restart/enable/disable, apt install/remove, passwd, any command using 'sudo'
BLOCKED_ALWAYS:      mkfs, fdisk, parted, iptables -F, visudo direct edits, /boot/ writes
SESSION_STATE_FILE:  /opt/local-se/session-state.md
SEARXNG_URL:         http://localhost:8888
LLAMA_SERVER_URL:    http://localhost:8080
```

---

## 3. KB Injection Strategy

Two approaches, chosen based on KB size:

### 3.1 Inline Injection (for KBs < 2 000 tokens)

Paste the KB directly into the system prompt (see `prompts/v0.3-context-aware.md`). This is the simplest approach and ensures the model always has the KB in context without a tool call. Keep it tightly scoped — every token in the system prompt counts against the context budget for every turn.

### 3.2 OpenWebUI Knowledge Documents (for larger KBs)

OpenWebUI supports **Knowledge** (RAG): upload documents, then enable them per-model. The model can query them on demand via retrieval, without injecting the full KB into every turn.

Recommended split:
- **Inline** (always present): Operational constraints, allowed paths, sudo rules, WSL path translation rules, common command one-liners (~800 tokens)
- **Knowledge doc** (retrieved on demand): Full package/service reference, log locations, config file locations, systemd reference

To create the Knowledge doc:
1. In OpenWebUI: **Workspace → Knowledge → New Knowledge**
2. Upload the KB content as a `.md` file
3. Enable the Knowledge collection for the Local System Engineer model
4. In the system prompt, instruct the model: "Query the knowledge base before making a tool call for system-specific facts."

### 3.3 `/opt/local-se/` as a Live Knowledge Store

Use the agent's write-accessible directory `/opt/local-se/` as a live knowledge store it can update during sessions:

```
/opt/local-se/
├── session-state.md          ← current session context (see doc 03)
├── environment-notes.md      ← machine-specific facts discovered during past sessions
├── installed-packages.md     ← last known package list (updated by agent after apt ops)
└── service-registry.md       ← known services, their unit names, and their config paths
```

The agent updates these files as it discovers facts, reducing the need to re-discover them in future sessions. Example entry in `environment-notes.md`:
```markdown
## 2026-05-15 — nginx config location
Confirmed: main config at /etc/nginx/nginx.conf
Site configs at /etc/nginx/sites-available/, enabled via symlinks to sites-enabled/
Log rotation at /etc/logrotate.d/nginx
```

---

## 4. KB Maintenance

**Update triggers**:
- After a package install or removal — update `installed-packages.md`
- After discovering an environment-specific quirk — update `environment-notes.md`
- After each session — update `session-state.md`
- Monthly — review the inline KB for accuracy against current Ubuntu 24.04 LTS state

**Version control**: Commit `/opt/local-se/` to a git repository. This gives you a history of what the agent learned and when. Initialize with:
```bash
cd /opt/local-se && git init && git add . && git commit -m "Initial KB state"
```

**Keeping the inline KB small**: The inline KB is a fixed cost on every turn. Every 100 tokens of KB adds ~3 % to context fill per turn. Audit it quarterly; move anything that isn't consulted every session to the Knowledge doc.
