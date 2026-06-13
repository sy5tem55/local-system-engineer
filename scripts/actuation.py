#!/usr/bin/env python3
"""
actuation.py — Episode actuation layer for the LSE Challenge Arena (v1.7.0-a).

WHY THIS EXISTS
---------------
Before v1.7.0-a the episode harness never executed model-emitted commands:
LSEChallengeEnv.step() parsed the model's ```json findings block, and
verify_ssh read ground-truth world state. For READ challenges that works
(model reports a value, verify_ssh confirms it). For WRITE challenges it does
not: nothing the model emits ever changes the world, so verify_ssh always reads
the unchanged world and the challenge can only pass if it was already fixed.
The benchmark therefore measured world state, not the model.

This module closes that gap. The model emits a ```bash block; the env extracts
it, runs every line through ported safety gates, executes the clean block in a
single SSH session on the challenge target, and only then evaluates assertions.

SAFETY GATES (ported verbatim from Cogitator execute_command v1.7.14)
---------------------------------------------------------------------
- _BLOCKED_COMMANDS    : permanently forbidden substrings (disk destruction,
                         rm -rf, fork bomb, account/credential mgmt, fw flush).
- _PRIVILEGED_PREFIXES : sudo/su/doas blocked ANYWHERE in the line (v1.4.2 'in'
                         check catches pipelines), UNLESS the line matches an
                         explicit per-challenge allow_sudo prefix allowlist.
- privileged write     : write op (cp/mv/rm/tee/>/sed -i/...) targeting a
                         privileged path (/etc /usr /boot /sys /proc /mnt) is
                         blocked unless covered by allow_sudo.

A single gate violation rejects the WHOLE block (fail-closed): partial
execution of a multi-step fix is more dangerous than none.
"""

import re
import subprocess
from typing import Optional

# ── Gates (verbatim from Cogitator v1.7.14) ─────────────────────────────────

_BLOCKED_COMMANDS = (
    # Filesystem destruction — disk/partition tools
    "mkfs", "fdisk", "parted", "sgdisk", "wipefs", "blkdiscard",
    "partprobe", "shred",
    # Block device writes — dd and shell redirection
    "dd if=", "of=/dev/", "> /dev/sd", "> /dev/nvme",
    # Recursive forced remove (all common flag orderings)
    "rm -rf", "rm -fr", "rm -r -f", "rm -f -r",
    # Fork bomb
    ":(){ :|",
    # Account deletion
    "userdel", "groupdel",
    # Privilege / credential management
    "passwd", "visudo",
    # Firewall flush
    "iptables -f", "iptables -F",
)

_PRIVILEGED_PREFIXES = ("sudo ", "su ", "doas ")

_PRIVILEGED_WRITE_PATHS = ("/etc/", "/usr/", "/boot/", "/sys/", "/proc/", "/mnt/")

_WRITE_OPS = (
    "cp ", "mv ", "rm ", "tee ", "> ", ">> ", "sed -i", "truncate",
    "dd ", "chmod -r ", "chown -r ",
)


# ── Block extraction ────────────────────────────────────────────────────────

_BASH_BLOCK = re.compile(r"```(?:bash|sh|shell)\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_bash_block(text: str) -> list[str]:
    """Return the list of executable lines from the FIRST ```bash block.

    Comments and blank lines are dropped; line continuations (trailing '\\')
    are joined so a wrapped command is gated and run as one logical line.
    Returns [] if no bash block is present.
    """
    m = _BASH_BLOCK.search(text or "")
    if not m:
        return []
    raw_lines = m.group(1).splitlines()
    lines: list[str] = []
    buf = ""
    for ln in raw_lines:
        stripped = ln.strip()
        if not buf and (not stripped or stripped.startswith("#")):
            continue
        if stripped.endswith("\\"):
            buf += stripped[:-1].rstrip() + " "
            continue
        buf += stripped
        if buf:
            lines.append(buf)
        buf = ""
    if buf:
        lines.append(buf)
    return lines


# ── Gate ──────────────────────────────────────────────────────────────────

def _sudo_allowed(line: str, allow_sudo: list[str]) -> bool:
    """True if a sudo-bearing line matches an allowlisted exact prefix."""
    stripped = line.strip()
    for prefix in allow_sudo or []:
        if stripped.startswith(prefix.strip()):
            return True
    return False


def gate_command(line: str, allow_sudo: Optional[list[str]] = None) -> Optional[str]:
    """Return a violation reason string, or None if the line is permitted.

    Mirrors Cogitator execute_command order: hard blocklist → privilege
    escalation → privileged-path write. allow_sudo carves a per-challenge
    exception for the privilege-escalation gate ONLY (never the hard blocklist).
    """
    allow_sudo = allow_sudo or []
    cmd_lower = line.lower().strip()

    # 1. Permanently forbidden — no exceptions, allow_sudo cannot override.
    for blocked in _BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return f"hard-blocked command fragment '{blocked}'"

    # 2. Privilege escalation anywhere in the line (v1.4.2 'in' check).
    for priv in _PRIVILEGED_PREFIXES:
        if priv in cmd_lower and not _sudo_allowed(line, allow_sudo):
            return (
                f"privilege escalation '{priv.strip()}' not in this "
                f"challenge's allow_sudo allowlist"
            )

    # 3. Write op targeting a privileged system path.
    if any(p in line for p in _PRIVILEGED_WRITE_PATHS):
        if any(op in line for op in _WRITE_OPS) and not _sudo_allowed(line, allow_sudo):
            return "write to a privileged system path not in allow_sudo allowlist"

    return None


def gate_block(lines: list[str], allow_sudo: Optional[list[str]] = None) -> Optional[str]:
    """Gate every line; return the first violation (with line text) or None."""
    for ln in lines:
        reason = gate_command(ln, allow_sudo)
        if reason:
            return f"{reason} — offending line: {ln!r}"
    return None


# ── Executor ────────────────────────────────────────────────────────────────

def run_actuation(
    host: str,
    user: str,
    block_text: str,
    allow_sudo: Optional[list[str]] = None,
    timeout: int = 60,
) -> dict:
    """Extract → gate → execute a model ```bash block on the target via SSH.

    Returns a dict:
      {"ran": bool, "gate_error": str|None, "stdout": str, "stderr": str,
       "exit_code": int|None, "n_lines": int, "error": str|None}

    - ran=False + gate_error set  → a line failed the gate; nothing executed.
    - ran=False + error set       → no bash block, or SSH/transport failure.
    - ran=True                    → block executed; inspect exit_code/stdout.

    The whole block runs in ONE non-interactive SSH session (set -e) so that
    cd/env state persists across lines and the first failing command aborts.
    """
    lines = extract_bash_block(block_text)
    if not lines:
        return {"ran": False, "gate_error": None, "stdout": "", "stderr": "",
                "exit_code": None, "n_lines": 0,
                "error": "no ```bash actuation block in model response"}

    gate_error = gate_block(lines, allow_sudo)
    if gate_error:
        return {"ran": False, "gate_error": gate_error, "stdout": "", "stderr": "",
                "exit_code": None, "n_lines": len(lines), "error": None}

    script = "set -e\n" + "\n".join(lines) + "\n"
    try:
        result = subprocess.run(  # noqa: S603
            [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=8",
                "-o", "BatchMode=yes",
                "-o", "LogLevel=ERROR",
                f"{user}@{host}",
                "bash -s",
            ],
            input=script,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ran": False, "gate_error": None, "stdout": "", "stderr": "",
                "exit_code": None, "n_lines": len(lines),
                "error": f"actuation timeout (>{timeout}s) to {user}@{host}"}
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "gate_error": None, "stdout": "", "stderr": "",
                "exit_code": None, "n_lines": len(lines),
                "error": f"actuation SSH failed: {exc}"}

    return {
        "ran": True, "gate_error": None,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "exit_code": result.returncode,
        "n_lines": len(lines), "error": None,
    }


# ── Self-test (no SSH required) ───────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    failures = 0

    def check(label, cond):
        global failures
        print(f"  {'✅' if cond else '❌'} {label}")
        if not cond:
            failures += 1

    print("extract_bash_block:")
    txt = "blah\n```bash\n# comment\nsystemctl status x\nrm /tmp/dup \\\n  --force\n```\ntail"
    blk = extract_bash_block(txt)
    check("drops comments/blanks", "# comment" not in blk)
    check("joins line continuation", any("rm /tmp/dup --force" == l for l in blk))
    check("no block → []", extract_bash_block("no fences here") == [])

    print("gate_command — blocklist (allow_sudo cannot override):")
    check("rm -rf blocked", gate_command("rm -rf /opt/models") is not None)
    check("mkfs blocked", gate_command("mkfs.ext4 /dev/sda1") is not None)
    check("rm -rf blocked even with allow_sudo", gate_command("sudo rm -rf /x", ["sudo rm -rf /x"]) is not None)

    print("gate_command — privilege escalation:")
    check("bare sudo blocked", gate_command("sudo systemctl restart nginx") is not None)
    check("sudo in pipeline blocked", gate_command("cat f | sudo tee /etc/x") is not None)
    check("sudo allowlisted passes", gate_command("sudo systemctl restart hermes-gateway",
                                                   ["sudo systemctl restart hermes-gateway"]) is None)

    print("gate_command — privileged-path write:")
    check("tee /etc blocked", gate_command("echo x | tee /etc/hosts") is not None)
    check("read of /etc allowed", gate_command("cat /etc/os-release") is None)
    check("write to /tmp allowed", gate_command("echo x > /tmp/note") is None)

    print("gate_command — clean ops:")
    check("plain systemctl status ok", gate_command("systemctl status llama-server") is None)
    check("ls ok", gate_command("ls -l /opt/models") is None)

    print("run_actuation — gate short-circuit (no SSH):")
    r = run_actuation("h", "u", "```bash\nrm -rf /\n```")
    check("gate_error set, ran=False", r["ran"] is False and r["gate_error"])
    r2 = run_actuation("h", "u", "no block")
    check("no-block → error, ran=False", r2["ran"] is False and r2["error"])

    print(f"\n{'ALL PASS' if failures == 0 else str(failures)+' FAILURES'}")
    sys.exit(1 if failures else 0)
