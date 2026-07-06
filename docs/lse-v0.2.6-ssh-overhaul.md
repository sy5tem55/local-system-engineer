# Goethe v0.2.6 — SSH Overhaul Design & Deployment Guide
> Drafted: 2026-06-30
> Status: READY FOR IMPLEMENTATION
> Target file: `tools/goethe.py`

---

## 1. Problem Statement

SSH operations are the backbone of the LSE's ability to manage remote nodes (node3090, RUTX50,
n45, etc.). In practice they are the most failure-prone part of the entire toolset. The failure
mode is almost always the same:

```
[exit 255]
(no output)
```

Exit 255 from SSH is a special sentinel: it means **SSH itself failed before the remote shell
ever ran the command**. It is not the remote command's exit code — it is SSH's own error code
for "I could not establish or maintain the session to deliver your command." A remote command
that exits with code 255 would also produce this, but that is rare; almost every exit 255 the
LSE sees is an SSH-layer failure.

### Why it keeps happening

There are three distinct root causes, all present in the current `execute_command` SSH path:

**Root cause 1 — Double-shell escaping.**
When `execute_command` receives a command string like:

```
ssh user@host "pkill -f foo; nohup python3 script.py > /tmp/log 2>&1 & disown"
```

It runs it via `subprocess.run(['bash', '-c', <the whole string>])`. This means:
- `bash -c` parses the outer string first
- Then SSH parses what remains
- Then the remote shell parses the inner quoted string

Each layer re-interprets special characters (`$`, `"`, `'`, `;`, `&`). A `$VAR` that should
reach the remote shell gets expanded locally. A `"` that closes the remote command string can
instead close the bash -c argument. The result is that complex one-liners arrive on the remote
host as corrupted strings — or never arrive at all, causing SSH to exit 255 with no output.

**Root cause 2 — nohup + disown in an SSH session.**
`nohup command & disown` is designed for interactive shells. In an SSH non-interactive session,
behaviour is different:

- SSH holds the connection open until all file descriptors on the remote side are closed.
- `nohup` redirects stdout/stderr to `nohup.out` (or wherever you redirect), but the SSH
  session's stdout/stderr pipe is a separate fd.
- `disown` removes the job from the shell's job table but does not close the pipe fds.
- The result is unpredictable: sometimes the SSH session closes cleanly, sometimes it hangs,
  sometimes the backgrounded process dies when SSH disconnects (SIGHUP, despite nohup).

The reliable pattern for truly backgrounding a process over SSH is:

```bash
nohup command > /tmp/log 2>&1 </dev/null &
```

The `</dev/null` closes stdin, and stdout/stderr are redirected to a file, so no fds are
inherited from the SSH session. Without it, SSH may stay open or the process may die on
session close.

**Root cause 3 — A fresh TCP connection per command.**
Every `execute_command` SSH call opens a new TCP connection: TCP handshake → SSH handshake →
key exchange → authentication → command → close. On the same LAN this is 50–200ms of overhead.
More importantly, the fingerprint check fires a *separate* SSH call before the actual command,
doubling the connection count and the failure surface. Any transient network hiccup affects both.

---

## 2. Solution Overview

Three additions to `goethe.py`, one guard added to `execute_command`.

| Addition | Purpose | Replaces |
|---|---|---|
| `ssh_run()` | Simple single remote commands, no escaping | `execute_command("ssh host 'cmd'")` |
| `ssh_script()` | Complex multi-command sequences, scripts | `execute_command("ssh host \"...\"")` one-liners |
| SSH ControlMaster | Reuse one TCP+auth connection per session | Per-call connection overhead |
| `execute_command` guard | Block complex SSH one-liners at the tool level | Silent exit 255 failures |

---

## 3. How SSH ControlMaster Works

This is the most important infrastructure change and worth understanding fully.

### The problem it solves

Each SSH call currently does:
```
TCP SYN → SYN-ACK → ACK                    (~1ms LAN)
SSH protocol version exchange               (~1ms)
Key exchange (DH/ECDH, crypto setup)        (~5-20ms)
Authentication (public key challenge/sign)  (~5-10ms)
[run command]
TCP FIN                                     (~1ms)
```

Total: 10–30ms minimum per command on a healthy LAN. Each fingerprint check doubles this.
Under any load or transient packet loss, this becomes 200ms–3s per call.

### How ControlMaster fixes it

SSH ControlMaster maintains a **persistent multiplexer socket** after the first connection.
Subsequent SSH calls to the same host+port+user connect to the socket instead of the network:

```
First call:   Full TCP+crypto+auth setup → creates /tmp/ssh_mux_node3090
Second call:  connect(/tmp/ssh_mux_node3090) → run command immediately
Third call:   connect(/tmp/ssh_mux_node3090) → run command immediately
...
After 60s idle: socket auto-closes (ControlPersist=60s)
```

The options used:

```
-o ControlMaster=auto
```
"If a master connection exists for this host/port/user, use it. If not, become the master."
`auto` means the first caller creates the mux; all subsequent callers use it. No manual
setup required.

```
-o ControlPath=/tmp/ssh_mux_%h_%p_%r
```
The filesystem path for the mux socket. `%h` = hostname, `%p` = port, `%r` = remote user.
This makes the socket unique per host+port+user combination, so node3090 and RUTX50 don't
share a socket.

```
-o ControlPersist=60s
```
The master process stays alive for 60 seconds after the last client disconnects. This means
a burst of 10 commands in a session incurs the setup cost exactly once.

### Security note

The ControlMaster socket lives in `/tmp/` and is owned by the current user with mode 0600.
Anyone who can read `/tmp/` can see the socket filename but cannot connect to it without the
right Unix credentials. On a single-user WSL2 instance this is a non-issue.

---

## 4. How `ssh_run` Works (Inner Mechanics)

`ssh_run` is for **simple, single remote commands** — `pgrep`, `systemctl status`, `tail`,
`cat`, `ls`, anything that is one logical operation with no chaining.

### Why `subprocess.run(['ssh', ..., host, command])` works when `bash -c` doesn't

When you call:
```python
subprocess.run(['ssh', opts, 'user@host', 'the command string'])
```

Python passes `'the command string'` directly to the SSH binary as a C argument (`argv[N]`).
SSH transmits it to the remote host over the encrypted channel. The remote shell receives it
as a single pre-formed string and executes it with `sh -c 'the command string'`.

**No intermediate bash -c. No local shell expansion.** Characters like `$`, `"`, `\` are
not interpreted locally — they travel as-is to the remote shell.

Compare this to the current path:
```python
subprocess.run(['bash', '-c', 'ssh user@host "the command string"'])
```

Here `bash -c` sees the outer string and applies shell semantics to it. Every `$VAR`,
`"`, `\`, and `;` is subject to bash's interpretation *before* SSH gets involved.

### What `ssh_run` does not handle

- Multi-command chains (`cmd1; cmd2; cmd3`) — technically work but are a sign you should
  use `ssh_script` instead
- `nohup ... & disown` sequences — blocked by the function (it checks for these patterns
  and returns an actionable error)
- Commands whose output exceeds `MAX_OUTPUT_CHARS` — truncated like `execute_command`

### Return value

`ssh_run` returns a structured string:
- On success: stdout output
- On exit 255: `[SSH FAILURE]` with diagnostic hint (ping check command)
- On non-zero exit: `[exit N]` with stdout and stderr
- On timeout: `[TIMEOUT]` with elapsed time

This makes it easy for the model to triage: a `[SSH FAILURE]` means check connectivity
first; a `[exit N]` means the connection worked but the command failed.

---

## 5. How `ssh_script` Works (Inner Mechanics)

`ssh_script` is for **anything complex** — nohup/background sequences, multi-step
setup chains, environment variable exports, anything that would require nested quoting
in a one-liner.

### The principle: transfer the complexity, not the escaping

Instead of trying to escape a complex command string through multiple shell layers, we:

1. Write the script content to a **local tempfile** as raw bytes — no escaping at all
2. **scp** it to `/tmp/lse_script_<hash>.sh` on the remote — binary transfer, not a shell command
3. Run `ssh host 'bash /tmp/lse_script_<hash>.sh'` — a simple, unambiguous remote command
4. **Cleanup** the remote script file (optional, default on)

Step 1 and 2 together mean the script content is never interpreted by any shell until it
runs on the remote host. A `$VARIABLE` in the script is just bytes until the remote bash
sees it. A `"` is just a character. No escaping required.

### The `</dev/null` fix for backgrounded processes

For scripts that background processes (`nohup ... &`), `ssh_script` automatically appends
`</dev/null` to any `nohup` line that doesn't already have it:

```bash
# What you write:
nohup python3 goethe_mcp.py --transport http --port 9700 > /tmp/goethe.log 2>&1 &

# What ssh_script sends:
nohup python3 goethe_mcp.py --transport http --port 9700 > /tmp/goethe.log 2>&1 </dev/null &
```

`</dev/null` redirects stdin from `/dev/null`, closing the stdin pipe inherited from the
SSH session. Combined with stdout/stderr being redirected to a file, the backgrounded
process has no open file descriptors tied to the SSH session. SSH can close cleanly
without sending SIGHUP to the process.

### Script hash for idempotency

The remote filename uses an MD5 hash of the script content:
`/tmp/lse_script_<md5[:8]>.sh`

If `ssh_script` is called twice with identical content (e.g. a retry), the second call
overwrites the same filename. No leftover scripts accumulate in `/tmp/`.

### ControlMaster reuse

`scp` supports the same ControlMaster options as `ssh`. The scp transfer and the
execution call both use the same mux socket, so the entire sequence (scp + ssh exec +
ssh cleanup) costs one TCP+auth setup.

---

## 6. The `execute_command` SSH Complexity Guard

A new check fires early in `execute_command` when it detects an SSH command with patterns
that are known to fail as one-liners:

```python
_SSH_COMPLEX_MARKERS = [
    'nohup', '& disown', '&disown', 'export ', 'eval ',
    '$(', '`', "'; '", '"; "',  # nested quote sequences
]
```

If any marker is present in an SSH command, `execute_command` returns immediately with:

```
[SSH_COMPLEXITY_GUARD] This command contains patterns that fail as SSH one-liners.
Root cause: shell escaping through bash -c + SSH + remote shell corrupts the command
(produces exit 255 / no output).

→ Use ssh_script() instead:
  ssh_script(
      host="node3090.home.arpa",
      user="lse-admin",
      script="""
pkill -9 -f goethe_mcp.py 2>/dev/null || true
sleep 0.5
mkdir -p /home/lse-admin/lse /home/lse-admin/lse/bkp
GOETHE_MCP_TOKEN=... nohup python3 ~/projects/.../goethe_mcp.py \
  --transport http --port 9700 --host 0.0.0.0 \
  > /tmp/goethe-node3090.log 2>&1 &
sleep 3
pgrep -a goethe_mcp
ss -tlnp | grep 9700
tail -5 /tmp/goethe-node3090.log
"""
  )
```

The guard shows the exact `ssh_script` call structure pre-filled with the host extracted
from the original command, so the model can immediately retry correctly.

---

## 7. Code Changes — What to Add to goethe.py

### 7.1 ControlMaster helper (private, add near top of Tools class)

```python
_SSH_CTL_PATH = "/tmp/ssh_mux_{host}_{port}_{user}"
_SSH_BASE_OPTS = [
    "-o", "LogLevel=ERROR",
    "-o", "StrictHostKeyChecking=no",
    "-o", "BatchMode=yes",
    "-o", "ControlMaster=auto",
    "-o", "ControlPersist=60s",
]

def _ssh_opts(self, host: str, user: str, port: int = 22,
              connect_timeout: int = 10) -> list:
    ctl = self._SSH_CTL_PATH.format(host=host, port=port, user=user)
    return self._SSH_BASE_OPTS + [
        "-o", f"ConnectTimeout={connect_timeout}",
        "-o", f"ControlPath={ctl}",
        "-p", str(port),
    ]
```

### 7.2 `ssh_run` tool (new public tool)

```python
def ssh_run(
    self,
    host: str,
    command: str,
    user: str = "lse-admin",
    port: int = 22,
    timeout: int = 30,
) -> str:
    """
    Run a single command on a remote host via SSH.

    Passes the command as a direct SSH argument (not via bash -c), eliminating
    all local shell escaping. ControlMaster reuses an existing authenticated
    connection if available, adding ~0ms overhead after the first call.

    Use this for: pgrep, systemctl status, tail, cat, ls, single-tool checks.
    For multi-command sequences or nohup/background operations: use ssh_script().

    KB-FIRST: search_kb("{host} SSH access") before the first ssh_run to a new host.

    Args:
        host:    remote hostname or IP (e.g. "node3090.home.arpa")
        command: single command string (no chaining, no nohup/disown)
        user:    SSH user (default: lse-admin)
        port:    SSH port (default: 22)
        timeout: total timeout in seconds (default: 30)

    Returns:
        stdout on success; structured [SSH FAILURE] / [exit N] / [TIMEOUT] on error.
    """
    import subprocess

    # Guard: complex patterns belong in ssh_script
    _COMPLEX = ["nohup", "& disown", "&disown", "export ", "$(",  "`"]
    if any(p in command for p in _COMPLEX):
        return (
            "[SSH_COMPLEXITY_GUARD] Detected nohup/disown/export/subshell in command.\n"
            "ssh_run is for simple single commands only.\n"
            f"→ Use ssh_script(host={host!r}, user={user!r}, script=<your commands as a script body>)"
        )

    opts = self._ssh_opts(host, user, port)
    cmd = ["ssh"] + opts + [f"{user}@{host}", command]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] ssh_run to {host} exceeded {timeout}s"
    except Exception as e:
        return f"[ERROR] ssh_run: {e}"

    if r.returncode == 255:
        return (
            f"[SSH FAILURE] exit 255 — SSH could not reach {host}.\n"
            f"Diagnose: ping -c2 {host} | execute_command\n"
            f"ssh stderr: {r.stderr.strip() or '(none)'}"
        )
    if r.returncode != 0:
        out = r.stdout.strip()
        err = r.stderr.strip()
        return f"[exit {r.returncode}]\n{out}\n{('[stderr] ' + err) if err else ''}".strip()

    return r.stdout.strip() or "(no output)"
```

### 7.3 `ssh_script` tool (new public tool)

```python
def ssh_script(
    self,
    host: str,
    script: str,
    user: str = "lse-admin",
    port: int = 22,
    interpreter: str = "bash",
    timeout: int = 120,
    cleanup: bool = True,
) -> str:
    """
    Execute a multi-command script on a remote host without shell escaping.

    Writes script to a local tempfile → scp to /tmp/lse_script_<hash>.sh on remote
    → executes it → cleans up. Script content is transferred as raw bytes: no local
    shell sees it until it runs on the remote host. Eliminates all escaping issues.

    Automatically fixes nohup lines missing </dev/null (prevents process death on
    SSH session close).

    Use this for: nohup/background sequences, multi-step setup chains, env var
    exports, anything that would need nested quoting as a one-liner.

    KB-FIRST: search_kb("{host} SSH access") before first use on a new host.

    Args:
        host:        remote hostname or IP
        script:      script body as a string (no shebang needed — added automatically)
        user:        SSH user (default: lse-admin)
        port:        SSH port (default: 22)
        interpreter: script interpreter (default: bash)
        timeout:     execution timeout in seconds (default: 120)
        cleanup:     remove remote script after execution (default: True)

    Returns:
        Combined stdout/stderr from script execution; [SCP FAILED] / [TIMEOUT] on error.

    Example:
        ssh_script(
            host="node3090.home.arpa",
            script='''
pkill -9 -f goethe_mcp.py 2>/dev/null || true
sleep 0.5
mkdir -p /home/lse-admin/lse /home/lse-admin/lse/bkp
GOETHE_MCP_TOKEN=abc123 nohup python3 ~/projects/.../goethe_mcp.py \\
  --transport http --port 9700 --host 0.0.0.0 \\
  > /tmp/goethe-node3090.log 2>&1 &
sleep 3
pgrep -a goethe_mcp
ss -tlnp | grep 9700
tail -5 /tmp/goethe-node3090.log
'''
        )
    """
    import subprocess, tempfile, hashlib, os, re

    # Fix nohup lines missing </dev/null (prevents SIGHUP on SSH disconnect)
    def _fix_nohup(line: str) -> str:
        if "nohup" in line and "</dev/null" not in line and line.rstrip().endswith("&"):
            return line.rstrip()[:-1].rstrip() + " </dev/null &"
        return line

    fixed_script = "\n".join(_fix_nohup(l) for l in script.splitlines())

    # Build full script with shebang
    full_script = f"#!/usr/bin/env {interpreter}\nset -euo pipefail\n{fixed_script}\n"

    # Deterministic remote path from content hash
    script_hash = hashlib.md5(fixed_script.encode()).hexdigest()[:8]
    remote_path = f"/tmp/lse_script_{script_hash}.sh"

    opts = self._ssh_opts(host, user, port)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write(full_script)
        local_path = f.name

    try:
        # scp — also uses ControlMaster so after first ssh call it's free
        scp_cmd = (
            ["scp"]
            + [o for o in opts if o not in ["-p", str(port)]]  # scp uses -P not -p
            + ["-P", str(port), local_path, f"{user}@{host}:{remote_path}"]
        )
        scp = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
        if scp.returncode != 0:
            return (
                f"[SCP FAILED] Could not transfer script to {host}:{remote_path}\n"
                f"stderr: {scp.stderr.strip()}"
            )

        # Execute
        run_cmd = ["ssh"] + opts + [f"{user}@{host}", f"{interpreter} {remote_path}"]
        r = subprocess.run(run_cmd, capture_output=True, text=True, timeout=timeout)

        out = r.stdout.strip()
        err = r.stderr.strip()
        result = out
        if err:
            result += f"\n[stderr] {err}"
        if r.returncode not in (0,):
            result = f"[exit {r.returncode}]\n{result}"

        return result.strip() or "(no output)"

    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] ssh_script on {host} exceeded {timeout}s"
    except Exception as e:
        return f"[ERROR] ssh_script: {e}"
    finally:
        os.unlink(local_path)
        if cleanup:
            subprocess.run(
                ["ssh"] + opts + [f"{user}@{host}", f"rm -f {remote_path}"],
                capture_output=True, timeout=10,
            )
```

### 7.4 Guard addition in `execute_command`

Add after the SSH fingerprint block, before the actual `subprocess.run`:

```python
# SSH complexity guard — catch patterns that reliably fail as one-liners
if _is_ssh_cmd:
    _COMPLEX_MARKERS = ["nohup", "& disown", "&disown", "export ", "eval ", "$(", "`"]
    if any(m in command for m in _COMPLEX_MARKERS):
        # Extract host from command for the hint
        import re as _re
        _host_match = _re.search(r'ssh\s+(?:\S+\s+)*(\S+@)?(\S+\.home\.arpa|\d+\.\d+\.\d+\.\d+)', command)
        _host_hint = _host_match.group(0).split()[-1] if _host_match else "<host>"
        return (
            "[SSH_COMPLEXITY_GUARD] This command contains patterns that cause exit 255 "
            "when passed through bash -c + SSH:\n"
            f"  Detected: {[m for m in _COMPLEX_MARKERS if m in command]}\n\n"
            "Root cause: three shell layers (Python → bash -c → SSH → remote sh) "
            "corrupt escaping. The command never reaches the remote host intact.\n\n"
            "→ Use ssh_script() — transfers the script as a file, zero escaping:\n\n"
            f"  ssh_script(\n"
            f"      host={_host_hint!r},\n"
            f"      script='''\n"
            f"  <paste your commands here, one per line, no escaping needed>\n"
            f"  '''\n"
            f"  )"
        )
```

---

## 8. Changelog Entry (for goethe.py module docstring)

```
Goethe v0.2.6: SSH OVERHAUL — ssh_run + ssh_script + ControlMaster + complexity guard.
  Three root causes of exit-255 SSH failures addressed:
  (1) Double-shell escaping: new ssh_run() passes commands as argv[], not via bash -c.
      No local shell sees the command — it arrives on the remote host exactly as written.
  (2) nohup/disown in SSH sessions: new ssh_script() transfers script content as a file
      via scp, executes it as bash /tmp/lse_script_<hash>.sh. Auto-injects </dev/null
      on nohup lines to prevent SIGHUP on SSH session close.
  (3) Per-call TCP+auth overhead: SSH ControlMaster (-o ControlMaster=auto, ControlPersist=60s)
      maintains a persistent mux socket. After the first call, all subsequent ssh/scp calls
      to the same host+port+user reuse the socket — zero TCP+crypto overhead.
  execute_command SSH complexity guard: if a command contains nohup/disown/export/eval/subshell
  markers, execution is blocked and an actionable ssh_script() call is returned instead of
  silently producing exit 255.
```

---

## 9. Deployment Guide (Step by Step)

### Phase 1 — Understand what you're deploying (read before touching anything)

You are adding three things to the running LSE tool file (`goethe.py`):

1. A private helper `_ssh_opts()` — builds the SSH option list (ControlMaster etc.)
   in one place so both `ssh_run` and `ssh_script` stay consistent.
2. A new tool `ssh_run()` — simple remote commands, no escaping, ControlMaster.
3. A new tool `ssh_script()` — complex scripts, scp-based, auto-fixes nohup.
4. A guard in `execute_command` — blocks complex SSH one-liners before they can fail.

Nothing is removed. `execute_command` still works for simple `ssh host 'cmd'` patterns
that don't match the complexity guard. The guard only fires on the patterns that have
been proven to fail.

### Phase 2 — Locate the insertion points in goethe.py

Before touching the file, identify where each addition goes. Open
`tools/goethe.py` and search for:

1. **`_ssh_opts` insertion point:** Find `_device_cache` in `__init__`. The helper
   and constants go directly below it, still inside the `Tools` class but before
   any existing tool methods.

2. **`ssh_run` insertion point:** Find `def execute_command`. Place `ssh_run`
   immediately *before* `execute_command` — they are conceptually related and
   the docstring cross-reference makes sense in this order.

3. **`ssh_script` insertion point:** Place immediately after `ssh_run`.

4. **Complexity guard insertion point:** Inside `execute_command`, find the block
   that checks `_is_ssh_cmd` and runs the fingerprint. The guard goes immediately
   after the fingerprint block, before `subprocess.run` is called for the actual command.

### Phase 3 — Apply the changes

**Option A (recommended): edit goethe.py in OWUI / llama-ui**

Because `goethe.py` is loaded by `goethe_mcp.py` at startup, any edit to the file
on disk takes effect only after goethe_mcp is restarted. The sequence is:

```
1. Open tools/goethe.py in your editor
2. Apply the four changes from Section 7 above
3. Verify: python3 -c "import ast; ast.parse(open('tools/goethe.py').read()); print('ast OK')"
4. Restart goethe_mcp on LUCIFER:
   bash ~/projects/local-system-engineer/tools/start-goethe.sh
5. Verify goethe_mcp loaded the new tool surface:
   curl -s -H "Authorization: Bearer 6e003f5c..." http://localhost:9700/mcp
   → look for "ssh_run" and "ssh_script" in the tools list
```

**Option B: edit and rsync to node3090 simultaneously**

If you want both LUCIFER and node3090 to get the update in one step:

```
1. Edit tools/goethe.py on LUCIFER (apply all four changes)
2. python3 -c "import ast; ast.parse(open('tools/goethe.py').read()); print('ast OK')"
3. bash ~/projects/local-system-engineer/tools/start-goethe.sh       # restart LUCIFER
4. bash ~/projects/local-system-engineer/tools/start-goethe-node3090.sh  # rsync + restart node3090
```

`start-goethe-node3090.sh` already handles the rsync of `goethe.py` to the remote node
and kills/restarts goethe_mcp there. No additional steps needed for node3090.

### Phase 4 — Verify ControlMaster is working

After restarting, the first `ssh_run` to node3090 will create the mux socket.
Verify it with:

```bash
ls -la /tmp/ssh_mux_node3090*
```

You should see something like:
```
srw------- 1 sy5 sy5 0 Jun 30 11:23 /tmp/ssh_mux_node3090.home.arpa_22_lse-admin
```

The `s` at the start means it's a Unix socket. If it exists, ControlMaster is working.
All subsequent `ssh_run` and `ssh_script` calls to node3090 in this session will reuse it.

To confirm a call is reusing the socket (rather than opening a new connection):
```bash
time ssh -o ControlPath=/tmp/ssh_mux_node3090.home.arpa_22_lse-admin \
         node3090.home.arpa 'echo ok'
```
Should return in < 50ms. Without the socket it takes 200ms–2s.

### Phase 5 — Test the new tools via LSE

With the new version loaded, test in sequence:

**Test 1 — ssh_run basic:**
```
ask LSE: "run ssh_run on node3090 to check uptime"
expected: "up X days, X:XX, X users, load average: ..."
```

**Test 2 — complexity guard:**
```
ask LSE: "via execute_command: ssh lse-admin@node3090 \"nohup echo test & disown\""
expected: [SSH_COMPLEXITY_GUARD] message with ssh_script hint, NOT an exit 255
```

**Test 3 — ssh_script with background process:**
```
ask LSE: "use ssh_script to kill and restart goethe_mcp on node3090"
expected: LSE constructs the script body and calls ssh_script() — no escaping issues,
          process stays alive after SSH session closes
```

**Test 4 — ControlMaster persistence:**
```
ask LSE: "run ssh_run on node3090: pgrep -a goethe_mcp, then ss -tlnp | grep 9700"
expected: both commands return quickly (mux reuse), no second auth handshake
```

### Phase 6 — Update VERSION.md and CURRENT-STATE.md

After confirming the tools work:

```
VERSION.md     → add Goethe v0.2.6 row to Goethe checksums table + line count tally
CURRENT-STATE.md → update Tool row to v0.2.6
CHANGELOG.md   → append session entry
```

Line count will increase by approximately +120–150 lines (the three functions + guard + constants).

---

## 10. Known Limitations and Future Work

**`set -euo pipefail` in ssh_script:** The auto-prepended `set -euo pipefail` causes the
script to exit immediately on any error. For scripts where partial failure is acceptable
(e.g. `pkill` returning non-zero because the process wasn't running), prefix that line
with `|| true`:
```bash
pkill -9 -f goethe_mcp.py 2>/dev/null || true
```
This is explicitly shown in the `ssh_script` docstring example.

**ControlMaster socket cleanup:** Sockets in `/tmp/` persist until the `ControlPersist`
timer expires (60s) or the system reboots. On a long-running LUCIFER session you may
accumulate multiple sockets. They are harmless but can be cleaned with:
```bash
rm -f /tmp/ssh_mux_*
```

**Async / parallel SSH:** Both `ssh_run` and `ssh_script` are synchronous (blocking).
If LSE needs to run operations on multiple nodes simultaneously in a future version,
`asyncio.create_subprocess_exec` is the path.

**Key selection:** Both tools inherit SSH key selection from the user's `~/.ssh/config`
and agent. The existing KB-FIRST rule (search_kb for SSH access before connecting) ensures
the model knows which key to pass if `~/.ssh/config` doesn't have a `Host` entry for the
target.
