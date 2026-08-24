#!/usr/bin/env python3
"""
goethe_netsec.py — SSH transport + nmap surface, extracted from goethe.py
============================================================================
D7 (2026-07-31): first mixin extraction of the 2026-07-31 refactor, pilot for
the coupling-ordered plan in docs/D7-MIXIN-EXTRACTION-PLAN.md. Extracted
because this group has the lowest external coupling (only `self._log`),
making it the cheapest place to prove the extraction pattern before moving
larger, more interconnected groups.

`Tools` in goethe.py inherits `NetSecMixin` alongside `KBMixin`; goethe_mcp
discovers tools via dir(instance), so the exposed MCP tool list is unchanged.
Follows the exact shape of goethe_kb.KBMixin (see /tmp/d7_pattern.md,
2026-07-31): a plain class with no __init__ and no Valves declaration, using
self.valves / self._log from the host Tools class. This module must never
import goethe.py — import direction is one-way, goethe.py imports this file.

Methods moved verbatim (2026-07-31, from tools/goethe.py @ 23f73f9,
lines 515-532, 1826-1956, 1958-2097, 4299-4455):
  _SSH_CTL_PATH, _SSH_BASE_OPTS, _ssh_opts, ssh_run, ssh_script, nmap_summary
No logic, docstring, or formatting changes were made during the move — this
is a pure relocation. Behavior is pinned by the full test suite (currently
548 passed, 10 xfailed) plus the runtime proof recorded in
docs/D7-MIXIN-EXTRACTION-PLAN.md Step 6.
"""


import os

class NetSecMixin:
    """SSH transport (ControlMaster-based) and nmap scanning tool methods
    mixed into goethe.Tools. Uses self.valves, self._log from the host class.
    """

    # ── SSH ControlMaster constants (v0.2.6) ─────────────────────────────────
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
        """Return SSH option list with ControlMaster socket path."""
        ctl = self._SSH_CTL_PATH.format(host=host, port=port, user=user)
        return self._SSH_BASE_OPTS + [
            "-o", f"ConnectTimeout={connect_timeout}",
            "-o", f"ControlPath={ctl}",
            "-p", str(port),
        ]

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

        Passes the command as a direct SSH argv argument (NOT via bash -c), eliminating
        all local shell escaping. ControlMaster reuses an existing authenticated connection
        if one exists, adding ~0ms overhead after the first call to a host.

        Use this for: pgrep, systemctl status, tail, cat, ls, single-tool checks.
        For multi-command sequences, nohup/background operations, or env var exports:
        use ssh_script() instead.

        PKILL RULE (v0.3.7 — enforced in code, 2026-07-04 post-mortem):
          'pkill -f <pattern>' sent through ssh_run matches the remote shell's
          OWN command line (it contains the pattern) and kills the SSH session:
          exit 255, target possibly dead but unconfirmed. The guard blocks
          unbracketed patterns.
          GOOD: ssh_run(host, "pkill -f 'llama[-]server'")
                ← bracketed char: regex matches the process, not this cmdline
          GOOD: kill by PID via ssh_script (script files never self-match)
          BAD:  ssh_run(host, "pkill -f llama-server")  ← self-kill, blocked

        MUX AUTO-RECOVERY (v0.3.7): a stale ControlMaster socket is the #1
        cause of exit 255 on a REACHABLE host. On exit 255 with a mux socket
        present, ssh_run now terminates the stale master, removes the socket,
        and retries ONCE automatically — do not hand-rm /tmp/ssh_mux_* first.

        KB-FIRST: search_kb("{host} SSH access") before the first ssh_run to a new host.

        Args:
            host:    remote hostname or IP (e.g. "node3090.home.arpa")
            command: single command string — no chaining (;/&&/||), no nohup/disown
            user:    SSH user (default: lse-admin)
            port:    SSH port (default: 22)
            timeout: total timeout in seconds (default: 30)

        Returns:
            stdout on success; [SSH FAILURE] / [exit N] / [TIMEOUT] on error.
        """
        import subprocess as _sp

        _COMPLEX = ["nohup", "& disown", "&disown", "export ", "$(", "`", "eval "]
        if any(p in command for p in _COMPLEX):
            return (
                "[SSH_COMPLEXITY_GUARD] ssh_run is for simple single commands only.\n"
                f"Detected pattern: {[p for p in _COMPLEX if p in command]}\n"
                f"→ Use ssh_script(host={host!r}, user={user!r}, script=<commands as script body>)"
            )

        # v0.3.7 PKILL SELF-MATCH GUARD (2026-07-04 post-mortem): the remote
        # shell's cmdline contains the pattern → pkill -f kills the session.
        toks = command.split()
        if "pkill" in toks and "-f" in toks:
            try:
                pat = toks[toks.index("-f") + 1].strip("'\"")
            except IndexError:
                pat = ""
            if pat and "[" not in pat:
                return (
                    "[PKILL_SELF_MATCH_GUARD] 'pkill -f "
                    f"{pat}' over ssh_run matches the remote shell's own command "
                    "line and kills the SSH session (exit 255; target possibly "
                    "dead but UNCONFIRMED).\n"
                    f"→ Bracket one character: pkill -f '{pat[:1]}[{pat[1:2] or pat[:1]}]"
                    f"{pat[2:]}'  — or kill by PID via ssh_script (script files "
                    "do not self-match)."
                )

        opts = self._ssh_opts(host, user, port)
        cmd = ["ssh"] + opts + [f"{user}@{host}", command]

        try:
            r = _sp.run(cmd, capture_output=True, text=True, timeout=timeout)
        except _sp.TimeoutExpired:
            return f"[TIMEOUT] ssh_run to {host} exceeded {timeout}s"
        except OSError as e:
            return f"[ERROR] ssh_run: {e}"

        note = ""
        if r.returncode == 255:
            # v0.3.7 MUX AUTO-RECOVERY: stale ControlMaster socket → kill the
            # dead master, remove the socket, retry ONCE.
            ctl = self._SSH_CTL_PATH.format(host=host, port=port, user=user)
            if os.path.exists(ctl):
                try:
                    _sp.run(
                        ["ssh", "-O", "exit", "-o", f"ControlPath={ctl}",
                         f"{user}@{host}"],
                        capture_output=True, text=True, timeout=10,
                    )
                except Exception:  # noqa: BLE001 (mux cleanup)
                    pass
                try:
                    os.unlink(ctl)
                except OSError:
                    pass
                try:
                    r2 = _sp.run(cmd, capture_output=True, text=True, timeout=timeout)
                    if r2.returncode != 255:
                        r = r2
                        note = ("[stale ControlMaster mux detected — socket "
                                "removed, retried OK]\n")
                        self._log(f"SSH-RUN: mux auto-recovery on {host}")
                except _sp.TimeoutExpired:
                    return f"[TIMEOUT] ssh_run mux-retry to {host} exceeded {timeout}s"

        if r.returncode == 255:
            return (
                f"[SSH FAILURE] exit 255 — SSH could not reach {host} "
                "(mux already auto-cleared and retried).\n"
                f"Diagnose in order: (1) ping -c2 {host}; (2) sshd on the host; "
                "(3) if your command embeds a process pattern (pkill/pgrep), "
                "suspect self-match.\n"
                f"ssh stderr: {r.stderr.strip() or '(none)'}"
            )
        if r.returncode != 0:
            out = r.stdout.strip()
            err = r.stderr.strip()
            return (
                f"{note}[exit {r.returncode}]\n{out}\n"
                f"{('[stderr] ' + err) if err else ''}"
            ).strip()

        return (note + (r.stdout.strip() or "(no output)")).strip()

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

        Writes script to a local tempfile → scp to /tmp/lse_script_<hash>.sh on
        the remote → executes it → cleans up. Script content is never interpreted
        by any local shell: characters like $, ", \\, ; are transmitted as raw bytes
        and only evaluated by the remote bash. Eliminates all nested quoting issues.

        Auto-injects </dev/null on nohup lines that lack it, preventing SIGHUP from
        killing backgrounded processes when the SSH session closes.

        Use this for: nohup/background sequences, multi-step setup chains, env var
        exports, kill+restart sequences — anything that would need nested quoting as
        a one-liner in execute_command.

        PKILL IN SCRIPTS (v0.3.7, 2026-07-04 post-mortem):
          Script files do NOT self-match pkill -f patterns (the remote cmdline is
          'bash /tmp/lse_script_<hash>.sh'), so kill-by-pattern is SAFE here —
          this is the correct home for process management, not ssh_run.
          BUT: pkill exits 1 when NOTHING matched. If the kill is the script's
          LAST line, that exit 1 becomes the script exit code. Append '|| true' to every pkill/kill
          line whose target may already be dead:
          GOOD: pkill -9 -f 'llama[-]server' 2>/dev/null || true
          BAD:  pkill -9 -f 'llama-server'   ← exit 1 when already dead is a
                false failure; you will misread it as "the kill failed".

        KB-FIRST: search_kb("{host} SSH access") before first use on a new host.

        Args:
            host:        remote hostname or IP
            script:      script body as a string (shebang added automatically)
            user:        SSH user (default: lse-admin)
            port:        SSH port (default: 22)
            interpreter: script interpreter (default: bash)
            timeout:     execution timeout in seconds (default: 120)
            cleanup:     remove remote script file after execution (default: True)

        Returns:
            Combined stdout/stderr on success; [SCP FAILED] / [TIMEOUT] / [exit N] on error.

        Example:
            ssh_script(
                host="node3090.home.arpa",
                script='''
pkill -9 -f goethe_mcp.py 2>/dev/null || true
sleep 0.5
mkdir -p /home/lse-admin/lse
GOETHE_MCP_TOKEN=abc123 nohup python3 ~/goethe_mcp.py \\
  --transport http --port 9700 --host 0.0.0.0 \\
  > /tmp/goethe-node3090.log 2>&1 &
sleep 3
pgrep -a goethe_mcp
ss -tlnp | grep 9700
tail -5 /tmp/goethe-node3090.log
'''
            )
        """
        import subprocess as _sp
        import tempfile as _tf
        import hashlib as _hl
        import os as _os

        # Auto-inject </dev/null on nohup lines missing it (prevents SIGHUP)
        def _fix_nohup(line: str) -> str:
            stripped = line.rstrip()
            if "nohup" in stripped and "</dev/null" not in stripped and stripped.endswith("&"):
                return stripped[:-1].rstrip() + " </dev/null &"
            return line

        fixed_script = "\n".join(_fix_nohup(l) for l in script.splitlines())
        # 2026-08-23 (node3090 power-up post-mortem): dropped -e and -u.
        # With set -e, one failing line (e.g. curl exit 7 on a not-yet-up
        # service) silently aborted the REST of the script — output looked
        # like a successful partial run. Keep pipefail so the final exit
        # code still carries real pipeline failures.
        full_script = f"#!/usr/bin/env {interpreter}\nset -o pipefail\n{fixed_script}\n"

        script_hash = _hl.md5(fixed_script.encode()).hexdigest()[:8]
        remote_path = f"/tmp/lse_script_{script_hash}.sh"

        opts = self._ssh_opts(host, user, port)

        with _tf.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(full_script)
            local_path = f.name

        try:
            # scp shares ControlMaster socket — free after first ssh call to host
            # scp uses -P (uppercase) for port, unlike ssh which uses -p
            # Simpler: rebuild opts without -p/port, add -P for scp
            scp_base_opts = []
            skip_next = False
            for idx, o in enumerate(opts):
                if skip_next:
                    skip_next = False
                    continue
                if o == "-p":
                    skip_next = True
                    continue
                scp_base_opts.append(o)

            scp_cmd = (
                ["scp"] + scp_base_opts + ["-P", str(port),
                local_path, f"{user}@{host}:{remote_path}"]
            )
            scp = _sp.run(scp_cmd, capture_output=True, text=True, timeout=30)
            if scp.returncode != 0:
                return (
                    f"[SCP FAILED] Could not transfer script to {host}:{remote_path}\n"
                    f"stderr: {scp.stderr.strip()}"
                )

            run_cmd = ["ssh"] + opts + [f"{user}@{host}", f"{interpreter} {remote_path}"]
            r = _sp.run(run_cmd, capture_output=True, text=True, timeout=timeout)

            out = r.stdout.strip()
            err = r.stderr.strip()
            result = out
            if err:
                result += f"\n[stderr] {err}"
            if r.returncode not in (0,):
                result = f"[exit {r.returncode}]\n{result}"
            return result.strip() or "(no output)"

        except _sp.TimeoutExpired:
            return f"[TIMEOUT] ssh_script on {host} exceeded {timeout}s"
        except OSError as e:
            return f"[ERROR] ssh_script: {e}"
        finally:
            _os.unlink(local_path)
            if cleanup:
                _sp.run(
                    ["ssh"] + opts + [f"{user}@{host}", f"rm -f {remote_path}"],
                    capture_output=True, timeout=10,
                )

    def nmap_summary(
        self,
        targets: str,
        top_ports: int = 1000,
        known_services: str = "",
    ) -> str:
        """
        Run nmap and return a COMPACT STRUCTURED SUMMARY. NEVER use
        execute_command('nmap ...') for network audits — raw nmap output is
        thousands of lines and fills context. This function parses nmap XML
        output and returns only the structured data the assertions need.

        PREREQUISITES: nmap must be installed on LUCIFER WSL2.
          Check: execute_command('which nmap') — install if missing:
          sudo_delegation_block('apt-get install -y nmap')

        WHAT THIS FUNCTION DOES:
          1. Runs: nmap -sV --top-ports <N> -oX - <targets>  (XML output to stdout)
          2. Parses XML — no raw text in the return value.
          3. Cross-references results against known_services baseline.
          4. Returns compact JSON with per-host port/service map + unexpected findings.

        RETURNED JSON keys:
          scan_results     — dict[ip, {ports: [int], services: {port: service_string}}]
          unexpected_ports — list[{ip, port, service}]: ports not in known_services
          host_count       — int: hosts that responded (up)
          scan_time_s      — float: elapsed scan time reported by nmap
          command          — str: exact nmap command that was run (for audit trail)

        Args:
            targets:        Space-separated IPs or CIDR ranges.
                            e.g. "192.168.1.0/24 192.168.5.0/24"
            top_ports:      Number of top ports to scan (default 1000).
            known_services: JSON string — dict[ip, list[int]] of expected ports.
                            Ports present in scan but absent here are flagged as
                            unexpected. Pass "" to skip unexpected-port analysis.
                            e.g. '{"192.168.1.50": [22, 80, 443, 514]}'
        """
        import subprocess
        import xml.etree.ElementTree as ET
        import json as _json
        import shutil
        import time

        if not shutil.which("nmap"):
            return (
                "ERROR: nmap not found. Install with:\n"
                "  sudo_delegation_block('apt-get install -y nmap')"
            )

        target_list = targets.strip().split()
        if not target_list:
            return "ERROR: nmap_summary — targets must be a non-empty string."

        cmd = [
            "nmap",
            "-sV",
            f"--top-ports={top_ports}",
            "-oX",
            "-",
            "--open",
        ] + target_list
        cmd_str = " ".join(cmd)
        self._log(f"NMAP: {cmd_str}")

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: nmap timed out after 300s. Reduce target scope or top_ports."
        except subprocess.SubprocessError as e:
            return f"ERROR running nmap: {e}"
        elapsed = round(time.monotonic() - t0, 1)

        if proc.returncode != 0 and not proc.stdout.strip():
            return f"ERROR: nmap failed (exit {proc.returncode}): {proc.stderr[:500]}"

        # ── Parse XML ─────────────────────────────────────────────────────────
        scan_results = {}
        nmap_elapsed = elapsed
        try:
            root = ET.fromstring(proc.stdout)
            run_stats = root.find("runstats/finished")
            if run_stats is not None:
                nmap_elapsed = float(run_stats.get("elapsed", elapsed))

            for host in root.findall("host"):
                status = host.find("status")
                if status is None or status.get("state") != "up":
                    continue
                addr_el = host.find("address[@addrtype='ipv4']")
                if addr_el is None:
                    continue
                ip = addr_el.get("addr", "unknown")

                ports_open = []
                services = {}
                for port_el in host.findall("ports/port"):
                    state_el = port_el.find("state")
                    if state_el is None or state_el.get("state") != "open":
                        continue
                    portnum = int(port_el.get("portid", 0))
                    ports_open.append(portnum)
                    svc_el = port_el.find("service")
                    if svc_el is not None:
                        svc_name = svc_el.get("name", "")
                        svc_product = svc_el.get("product", "")
                        svc_ver = svc_el.get("version", "")
                        services[str(portnum)] = " ".join(
                            p for p in [svc_name, svc_product, svc_ver] if p
                        ).strip()

                scan_results[ip] = {"ports": sorted(ports_open), "services": services}

        except ET.ParseError as e:
            return f"ERROR: nmap XML parse failed: {e}\nRaw output (first 500): {proc.stdout[:500]}"

        # ── Cross-reference against known baseline ────────────────────────────
        unexpected = []
        if known_services:
            try:
                baseline = _json.loads(known_services)
                for ip, info in scan_results.items():
                    expected = set(baseline.get(ip, []))
                    for port in info["ports"]:
                        if expected and port not in expected:
                            unexpected.append(
                                {
                                    "ip": ip,
                                    "port": port,
                                    "service": info["services"].get(
                                        str(port), "unknown"
                                    ),
                                }
                            )
            except _json.JSONDecodeError:
                unexpected = [
                    {"error": "known_services JSON invalid — skipped baseline check"}
                ]

        result = {
            "scan_results": scan_results,
            "unexpected_ports": unexpected,
            "host_count": len(scan_results),
            "scan_time_s": nmap_elapsed,
            "command": cmd_str,
        }
        self._log(
            f"NMAP-SUMMARY: {len(scan_results)} hosts up, "
            f"{len(unexpected)} unexpected ports, {nmap_elapsed}s"
        )
        return _json.dumps(result, indent=2)