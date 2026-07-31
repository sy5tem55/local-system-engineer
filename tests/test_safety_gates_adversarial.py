"""D5 — adversarial contract tests for the safety wedge.

WHY THIS EXISTS. `sudo_delegation_block`, `_validate_command_safety` and
`_is_allowed_write` are the product's differentiator: every competing agent is
read-only or PR-only, and the pitch is "safe, auditable write access". Before
2026-07-31 that surface had no adversarial tests at all — `test_goethe_perms.py`
covers the grant *lifecycle* (ingestion, rendering, approval), never the gate
that decides whether a command runs.

The first adversarial pass found four holes. One is fixed and pinned here; three
are open and pinned as xfail so they are impossible to forget and will announce
themselves (XPASS) the moment someone fixes them.

FIXED AND PINNED
  _BLOCKED_WRITE_FILENAMES was entirely dead code. `_norm()` returns a
  trailing-slash path, so `os.path.basename("/home/u/.bashrc/")` == "" and
  nothing ever matched the blocklist. Every shell rc file, SSH private key and
  authorized_keys was writable — a textbook persistence vector inside the
  feature being sold as the safety model. The guard had never fired since it
  was written.

OPEN — pinned xfail, each a real bypass of the privilege gate
  1. Heredoc-as-executor. `_strip_heredoc_bodies` blanks heredoc bodies before
     scanning, on the correct premise that a heredoc is data. But when the
     heredoc feeds an interpreter (`bash <<EOF`, `python3 <<EOF`) the body is
     code. Payload text is never scanned, so any blocked command or privilege
     escalation placed inside executes unexamined.
  2. Whitespace evasion. `_BLOCKED_COMMANDS` is a literal substring list, so
     "rm  -rf" (two spaces) and "rm\trf" miss "rm -rf" while behaving
     identically in a shell.
  3. Shell indirection. The privilege scan looks for the literal "sudo ".
     Variable indirection, command substitution and xargs all reconstruct it
     at runtime after the scan has passed.

Fixing 1-3 means changing scan semantics, which risks false positives on
legitimate work — the failure mode where an over-eager guard blocks a KB note
that merely mentions a privileged command (already hit once, see
_strip_heredoc_bodies' own docstring). That is a design decision for the
operator, not something to sneak in behind a test. Hence xfail, not a patch.

These tests never execute a command. They call the pure predicate functions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_GOETHE = Path(__file__).resolve().parent.parent / "tools" / "goethe.py"


@pytest.fixture(scope="module")
def tools():
    spec = importlib.util.spec_from_file_location("goethe_d5", _GOETHE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Tools()


def _blocked(tools, command: str, cwd: str = "/tmp") -> bool:
    """True when the gate refuses the command."""
    return tools._validate_command_safety(command, cwd) is not None


# ───────────────────────── privilege escalation ──────────────────────────

@pytest.mark.parametrize(
    "command",
    [
        "sudo id",
        "sudo rm -rf /important",
        "ls; sudo id",
        "ls && sudo id",
        "ls | sudo tee /etc/hosts",
        "su - root",
        "doas id",
        "/usr/bin/sudo id",
        "env sudo id",
        "echo x > /tmp/f; sudo systemctl stop nginx",
    ],
)
def test_privilege_escalation_is_blocked(tools, command):
    assert _blocked(tools, command), f"privilege escalation slipped through: {command!r}"


@pytest.mark.parametrize(
    "command",
    [
        "S=sudo; $S id",
        "$(echo sudo) id",
        "echo id | xargs sudo",
    ],
)
@pytest.mark.xfail(
    reason="OPEN HOLE 3: privilege scan is literal-substring; shell indirection "
    "reconstructs 'sudo' after the scan passes",
    strict=True,
)
def test_privilege_escalation_via_shell_indirection(tools, command):
    assert _blocked(tools, command)


# ───────────────────────── hard-blocked commands ─────────────────────────

@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/x",
        "rm -fr /tmp/x",
        "rm -r -f /tmp/x",
        "RM -RF /tmp/x",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda",
        "wipefs -a /dev/sda",
        "userdel sy5",
        "shred /dev/sda",
    ],
)
def test_destructive_commands_are_blocked(tools, command):
    assert _blocked(tools, command), f"destructive command allowed: {command!r}"


@pytest.mark.parametrize("command", ["rm  -rf /tmp/x", "rm\t-rf /tmp/x"])
@pytest.mark.xfail(
    reason="OPEN HOLE 2: _BLOCKED_COMMANDS matches literal substrings, so any "
    "whitespace variant evades it while the shell behaves identically",
    strict=True,
)
def test_destructive_commands_whitespace_variants(tools, command):
    assert _blocked(tools, command)


# ─────────────────────────── heredoc handling ────────────────────────────

def test_heredoc_body_is_not_scanned_for_documentation(tools):
    """Correct behaviour: prose that merely mentions a privileged command
    must not be blocked when it is data being written to a file."""
    command = (
        "cat >> /tmp/notes.md << 'EOF'\n"
        "To install, run: sudo apt install foo\n"
        "EOF"
    )
    assert not _blocked(tools, command), "documentation heredoc must not be blocked"


def test_heredoc_redirect_to_privileged_path_is_still_blocked(tools):
    """The heredoc *header* is still scanned, so a privileged write target
    is caught even though the body is skipped."""
    command = "cat >> /etc/passwd << 'EOF'\nmalice\nEOF"
    assert _blocked(tools, command)


@pytest.mark.parametrize(
    "command",
    [
        "bash << 'EOF'\nsudo rm -rf /important\nEOF",
        "sh <<EOF\nsudo systemctl stop firewalld\nEOF",
        "python3 << 'EOF'\nimport os; os.system('sudo id')\nEOF",
    ],
)
@pytest.mark.xfail(
    reason="OPEN HOLE 1: heredoc bodies are blanked before scanning because a "
    "heredoc is assumed to be data, but when it feeds an interpreter the body "
    "is executed code and is never examined",
    strict=True,
)
def test_heredoc_feeding_an_interpreter_is_blocked(tools, command):
    assert _blocked(tools, command)


# ──────────────────────────── write-path gate ────────────────────────────

@pytest.mark.parametrize(
    "path",
    [
        "/home/sy5/.bashrc",
        "~/.bashrc",
        "/home/sy5/.zshrc",
        "/home/sy5/.profile",
        "/home/sy5/.bash_profile",
        "/home/sy5/.ssh/authorized_keys",
        "/home/sy5/.ssh/id_ed25519",
        "/home/sy5/.ssh/id_rsa",
        "/home/sy5/.ssh/config",
    ],
)
def test_shell_and_ssh_config_writes_are_blocked(tools, path):
    """REGRESSION PIN. This guard was dead code until 2026-07-31: _norm()'s
    trailing slash made basename() return "" so nothing ever matched
    _BLOCKED_WRITE_FILENAMES. Persistence vectors were freely writable."""
    assert not tools._is_allowed_write(path), f"write to protected file allowed: {path}"


@pytest.mark.parametrize(
    "path",
    [
        "/home/sy5/projects/thing.py",
        "/tmp/scratch.txt",
        "/opt/local-se/kb/note.md",
        "/home/sy5/.bashrc_notes",
        "/home/sy5/bashrc",
    ],
)
def test_legitimate_writes_still_allowed(tools, path):
    """The blocklist fix must not over-block: similarly-named files and normal
    project paths stay writable."""
    assert tools._is_allowed_write(path), f"legitimate write blocked: {path}"


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "/home/../etc/passwd",
        "/tmp/../etc/shadow",
        "/usr/bin/python3",
        "/boot/grub/grub.cfg",
    ],
)
def test_privileged_path_writes_are_blocked(tools, path):
    assert not tools._is_allowed_write(path), f"privileged path writable: {path}"


@pytest.mark.parametrize(
    "command",
    [
        "echo x > /etc/hosts",
        "echo x >> /etc/hosts",
        "tee /etc/hosts",
        "tee -a /etc/hosts",
        "cp /tmp/x /etc/hosts",
        "mv /tmp/x /usr/bin/thing",
        "sed -i s/a/b/ /etc/hosts",
        "rm /etc/hosts",
    ],
)
def test_writes_targeting_privileged_paths_are_blocked(tools, command):
    assert _blocked(tools, command), f"privileged write allowed: {command!r}"


def test_reads_from_privileged_paths_remain_allowed(tools):
    """Reads must stay permitted — the gate blocks writes, not inspection."""
    assert not _blocked(tools, "cat /etc/hosts")


@pytest.mark.parametrize("command", ["cat /etc/passwd", "grep root /etc/passwd"])
@pytest.mark.xfail(
    reason="OPEN HOLE 4 (inverted priority): _BLOCKED_COMMANDS contains 'passwd' "
    "to block the password-changing command, but literal substring matching also "
    "blocks reading /etc/passwd - a routine SRE operation. Meanwhile the far more "
    "sensitive /etc/shadow is readable, since no blocklist entry happens to appear "
    "in its name. The guard over-blocks the benign and under-blocks the dangerous.",
    strict=True,
)
def test_reading_etc_passwd_is_a_false_positive(tools, command):
    assert not _blocked(tools, command)


def test_etc_shadow_read_is_currently_unguarded(tools):
    """Documents the other half of hole 4: no gate covers /etc/shadow reads.
    Pinned as an assertion of CURRENT behaviour so that tightening the read
    path deliberately breaks this test and forces a conscious update."""
    assert not _blocked(tools, "less /etc/shadow")


# ───────────────────────── working directory gate ────────────────────────

def test_working_dir_outside_read_allowlist_is_blocked(tools):
    assert _blocked(tools, "ls", cwd="/root")
    assert _blocked(tools, "ls", cwd="/etc/../root")


def test_working_dir_inside_allowlist_is_permitted(tools):
    assert not _blocked(tools, "ls", cwd="/tmp")
    assert not _blocked(tools, "ls", cwd="/home/sy5")


# ─────────────────────────────── fail-closed ─────────────────────────────

def test_grant_lookup_failure_denies_rather_than_allows(tools, monkeypatch):
    """If the permissions module is unavailable, a privileged command must be
    refused — never allowed by default. v0.4.9 fixed a fail-closed bug on this
    path and it had no regression test."""
    monkeypatch.setattr(tools, "_perms_mod", lambda: None)
    assert _blocked(tools, "sudo systemctl restart nginx")


def test_grant_lookup_raising_denies_rather_than_allows(tools, monkeypatch):
    class Boom:
        def check_sudo(self, _cmd):
            raise RuntimeError("perms backend down")

    monkeypatch.setattr(tools, "_perms_mod", lambda: Boom())
    # The security invariant is "never silently allow". Raising is acceptable
    # (the command does not run, and goethe_mcp turns it into a tool error);
    # returning None would be a genuine hole. Measured 2026-07-31: the gate
    # currently PROPAGATES the backend error rather than returning a block
    # string - fail-closed in effect, ungraceful in form.
    try:
        verdict = tools._validate_command_safety("sudo systemctl restart nginx", "/tmp")
    except RuntimeError:
        return  # denied by exception - acceptable
    assert verdict is not None, "backend failure silently ALLOWED a privileged command"


def test_heredoc_scanner_failure_falls_back_to_scanning_raw_text(tools, monkeypatch):
    """_strip_heredoc_bodies promises to fail closed: if the regex substitution
    errors, the ORIGINAL text is scanned rather than an empty string."""
    monkeypatch.setattr(
        tools, "_HEREDOC_PATTERN", "(?P<unclosed", raising=False
    )
    assert _blocked(tools, "sudo id"), "gate stopped blocking when the scanner broke"
