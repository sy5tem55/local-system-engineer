"""D5 — adversarial contract tests for the safety wedge.

WHY THIS EXISTS. `sudo_delegation_block`, `_validate_command_safety` and
`_is_allowed_write` are the product's differentiator: every competing agent is
read-only or PR-only, and the pitch is "safe, auditable write access". Before
2026-07-31 that surface had no adversarial tests at all — `test_goethe_perms.py`
covers the grant *lifecycle* (ingestion, rendering, approval), never the gate
that decides whether a command runs.

The first adversarial pass (2026-07-31) found four holes. ALL FOUR ARE NOW
CLOSED, each fixed on 2026-07-31 and pinned by the tests below. The xfail
markers that held them open are gone; every test here now asserts real,
enforced behaviour. The history is kept in each test's docstring so the
reasoning survives, and the false-positive direction is covered explicitly —
over-blocking is the live risk of every one of these fixes.

FIXED AND PINNED
  _BLOCKED_WRITE_FILENAMES was entirely dead code. `_norm()` returns a
  trailing-slash path, so `os.path.basename("/home/u/.bashrc/")` == "" and
  nothing ever matched the blocklist. Every shell rc file, SSH private key and
  authorized_keys was writable — a textbook persistence vector inside the
  feature being sold as the safety model. The guard had never fired since it
  was written.

CLOSED 2026-07-31 — each was a real bypass of the privilege gate
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

Fixing 1-3 meant changing scan semantics, which risks false positives on
legitimate work — the failure mode where an over-eager guard blocks a KB note
that merely mentions a privileged command (already hit once, see
_strip_heredoc_bodies' own docstring). That is a design decision, and it was
taken deliberately by the operator on 2026-07-31 rather than slipped in behind
a test. The fixes are correspondingly narrow: heredoc bodies are still treated
as data unless the consumer is an interpreter; whitespace normalisation only
collapses runs; privilege matching moved to word boundaries; and blocked
command NAMES match in command position only, which is what let hole 4's
false positive (`cat /etc/passwd`) be fixed at the same time as its
under-block (`/etc/shadow`). Every fix has a paired test asserting the benign
case still passes.

These tests never execute a command. They call the pure predicate functions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_GOETHE = Path(__file__).resolve().parent.parent / "tools" / "goethe.py"


@pytest.fixture(scope="module")
def tools():
    """Tools instance with the grants backend DISCONNECTED.

    HERMETICITY (2026-07-31). These tests exercise the *gate*, not the
    operator's current grant list. Left connected, they read the live
    goethe_perms DB, so `sudo id` flips from blocked to allowed the moment
    anyone approves a grant for `id` — which is exactly what happened
    (grant #31), turning a green suite red with no code change. A safety
    test whose verdict depends on mutable production state is not a test.
    The two tests that specifically cover grant-lookup behaviour override
    this themselves via monkeypatch.
    """
    spec = importlib.util.spec_from_file_location("goethe_d5", _GOETHE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inst = module.Tools()
    inst._perms_mod = lambda: None
    return inst


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
def test_privilege_escalation_via_shell_indirection(tools, command):
    """CLOSED 2026-07-31. Was OPEN HOLE 3. The scan required the literal
    "sudo " with a trailing space, so every form where sudo is reconstructed
    or sits at end-of-string escaped it. Now matched on word boundaries
    (_PRIVILEGED_TOKEN_RE), which fires on "S=sudo", "$(echo sudo)" and
    "xargs sudo" alike because '=', '(' and ' ' are all word boundaries."""
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
def test_destructive_commands_whitespace_variants(tools, command):
    """CLOSED 2026-07-31. Was OPEN HOLE 2. _normalize_for_scan() collapses
    whitespace runs before the literal-substring scan, so padded variants
    can no longer diverge from the blocklist entry they are identical to."""
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
def test_heredoc_feeding_an_interpreter_is_blocked(tools, command):
    """CLOSED 2026-07-31. Was OPEN HOLE 1. _strip_heredoc_bodies() now checks
    whether the heredoc's consumer executes its body — everything left of
    `<<` is tokenised to basenames and matched against
    _INTERPRETER_HEREDOC_CMDS. Interpreter consumers keep their body for
    scanning; `cat`/`tee` and friends still get it blanked, which is what
    keeps the documentation case below passing."""
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
def test_reading_etc_passwd_is_allowed(tools, command):
    """CLOSED 2026-07-31. Was OPEN HOLE 4, first half. 'passwd' sat in
    _BLOCKED_COMMANDS as a literal substring, so it matched the PATH in
    `cat /etc/passwd` and blocked a routine read. Command names now match in
    command position only (_BLOCKED_COMMAND_NAMES + _CMD_POSITION_RE), whose
    executable-path prefixes cover real bin directories but never /etc/."""
    assert not _blocked(tools, command)


@pytest.mark.parametrize(
    "command",
    ["passwd", "passwd root", "/usr/bin/passwd root", "visudo",
     "ls; passwd root", "userdel sy5", "shred /dev/sda"],
)
def test_blocked_command_names_still_blocked_in_command_position(tools, command):
    """The other side of the same fix: narrowing to command position must not
    let the actual invocations through, including via absolute path and after
    a shell separator."""
    assert _blocked(tools, command), f"blocked command name allowed: {command!r}"


@pytest.mark.parametrize(
    "command",
    ["cat /etc/shadow", "grep sy5 /etc/shadow", "cat /etc/gshadow"],
)
def test_shadow_file_reads_are_blocked(tools, command):
    """CLOSED 2026-07-31. Was OPEN HOLE 4, second half. /etc/shadow was
    entirely unguarded — the guard over-blocked the benign (/etc/passwd) while
    under-blocking the dangerous. Now explicitly blocked via
    _BLOCKED_READ_PATHS."""
    assert _blocked(tools, command), f"shadow read allowed: {command!r}"


def test_etc_shadow_read_is_now_guarded(tools):
    """This test previously asserted the OPPOSITE — that `less /etc/shadow`
    was allowed — pinned as current behaviour precisely so that tightening the
    read path would break it and force a conscious update. That tightening
    happened on 2026-07-31 (hole 4, second half), so this is that conscious
    update: the assertion is inverted, deliberately, and the mechanism is
    _BLOCKED_READ_PATHS."""
    assert _blocked(tools, "less /etc/shadow")


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


# ─────────── 2026-08 fix: privilege-token gate false positives ───────────
#
# SPEC-privtoken-false-positive-2026-08.md. _PRIVILEGED_TOKEN_RE stays a
# wide word-boundary match (see the D5-FIX comment above) -- narrowing it
# to command position would silently reopen the three indirection bypasses
# it was built to close. Instead, a match is exempt only when the character
# immediately before OR after it is one of -/_. : the token then sits
# inside a path, branch name, or hyphenated/dotted identifier rather than
# at a position where it could execute. Every D5 bypass shape keeps a
# non-exempt neighbour (space, =, ;, |, &, `, (, newline, or string
# start/end) on both sides, so it stays blocked.


@pytest.mark.parametrize(
    "command",
    [
        # SPEC §1 -- three of the four false positives measured
        # 2026-08-01, all read-only, all blocked only because the branch
        # name `codex/fix-sudo-grants-live` puts "sudo" between hyphens
        # (and once behind a '/').
        "git log origin/codex/fix-sudo-grants-live..HEAD",
        "git status ; echo codex/fix-sudo-grants-live",
        "git rev-list --count origin/codex/fix-sudo-grants-live..HEAD",
    ],
)
def test_identifier_embedded_privilege_token_is_exempt(tools, command):
    """FIXED 2026-08. These are read-only and never execute sudo -- the
    token is part of an identifier, not a command."""
    assert not _blocked(tools, command), f"identifier false positive still blocked: {command!r}"


def test_grep_quoted_token_remains_blocked_known_limitation(tools):
    """The fourth SPEC §1 measurement -- `grep -n "sudo" tools/goethe.py`
    -- is deliberately NOT fixed by the identifier exemption. The token
    sits between two `"` characters, which are not in the exempt set
    (-/_.): widening the exempt set to cover quotes would also exempt
    `sh -c "sudo id"` / `ssh host "sudo systemctl stop x"`, a real
    execution path where a double-quoted argument is run directly by the
    shell it's handed to -- a genuine bypass, not a false positive. SPEC
    §4.1 documents the bare-grep case as a deliberate, out-of-scope known
    limitation (needs real shell tokenisation) and gives the workaround:
    `grep 's[u]do'`."""
    assert _blocked(tools, 'grep -n "sudo" tools/goethe.py')
    assert _blocked(tools, "grep sudo file.py")
    assert not _blocked(tools, "grep 's[u]do' file.py")  # documented workaround


@pytest.mark.parametrize(
    "command",
    [
        "codex/fix-sudo-grants-live",
        "/etc/sudoers",
        "goethe-perm sync-sudoers",
        "sudo_delegation_block",
        "check_sudo",
    ],
)
def test_more_identifier_shapes_are_exempt(tools, command):
    """Path separator, leading/trailing hyphen, and snake_case are all
    exempt; none of these strings are executable as a command on their own."""
    assert not _blocked(tools, command), f"identifier false positive still blocked: {command!r}"


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
        "S=sudo; $S id",
        "$(echo sudo) id",
        "echo id | xargs sudo",
    ],
)
def test_d5_bypasses_still_blocked_after_identifier_exemption(tools, command):
    """Re-asserted explicitly here, local to the 2026-08 fix, so the intent
    is visible without cross-referencing the parametrize blocks above: the
    identifier exemption must not touch any of these. None of them have an
    exempt-set character (-/_.) immediately before or after the matched
    token -- they are bounded by start-of-string, space, ;, &, |, or the
    output side of a command substitution."""
    assert _blocked(tools, command), f"D5 bypass reopened by identifier exemption: {command!r}"


# ASYMMETRIC by design. before-exempt has no "/": a "/" immediately before
# the token is how a real invocation looks ("/usr/bin/sudo id", "./sudo id",
# "bin/sudo id" all execute the real binary by path, no PATH lookup needed).
# after-exempt keeps "/": "sudo/foo" is one path token naming a "sudo"
# subdirectory, never the real /usr/bin/sudo binary. See the "2026-08 FIX"
# comment above _IDENTIFIER_ADJACENT_BEFORE/_AFTER in tools/goethe.py for
# the full rationale and the regression this asymmetry fixes.
_ADJACENT_EXEMPT_BEFORE = list("-_.")
_ADJACENT_EXEMPT_AFTER = list("-_./")
_ADJACENT_BLOCKING = [" ", "=", ";", "|", "&", "`", "("]


@pytest.mark.parametrize("token", ["sudo", "su", "doas"])
@pytest.mark.parametrize("ch", _ADJACENT_EXEMPT_BEFORE)
def test_adjacency_matrix_exempt_before(tools, token, ch):
    command = f"x{ch}{token} y"
    assert not _blocked(tools, command), f"{command!r} should be exempt (before={ch!r})"


@pytest.mark.parametrize("token", ["sudo", "su", "doas"])
@pytest.mark.parametrize("ch", _ADJACENT_EXEMPT_AFTER)
def test_adjacency_matrix_exempt_after(tools, token, ch):
    command = f"y {token}{ch}x"
    assert not _blocked(tools, command), f"{command!r} should be exempt (after={ch!r})"


@pytest.mark.parametrize("token", ["sudo", "su", "doas"])
@pytest.mark.parametrize("ch", _ADJACENT_BLOCKING + ["/"])
def test_adjacency_matrix_blocked_before(tools, token, ch):
    command = f"x{ch}{token} y"
    assert _blocked(tools, command), f"{command!r} should stay blocked (before={ch!r})"


@pytest.mark.parametrize("token", ["sudo", "su", "doas"])
@pytest.mark.parametrize("ch", _ADJACENT_BLOCKING)
def test_adjacency_matrix_blocked_after(tools, token, ch):
    command = f"y {token}{ch}x"
    assert _blocked(tools, command), f"{command!r} should stay blocked (after={ch!r})"


@pytest.mark.parametrize(
    "command",
    [
        "/usr/bin/sudo id",
        "/bin/su root",
        "/usr/bin/doas id",
        "./sudo id",
        "bin/sudo id",
        "/opt/tools/sudo id",
    ],
)
def test_absolute_or_relative_path_invocation_stays_blocked(tools, command):
    """Regression pin for the exact hazard this fix's second attempt had:
    putting "/" in the BEFORE-exempt set treated a leading path separator
    as identifier-embedding, which silently exempted the standard idiom
    for invoking a binary by path -- "/usr/bin/sudo id" is a real,
    unambiguous privilege escalation, not a false positive. Caught by the
    pre-existing pin in test_privilege_escalation_is_blocked; re-asserted
    here, explicitly, with siblings covering su/doas and relative-path
    forms too."""
    assert _blocked(tools, command), f"path-invoked privilege escalation allowed: {command!r}"


@pytest.mark.parametrize("token", ["sudo", "su", "doas"])
def test_adjacency_matrix_blocked_at_newline_boundary(tools, token):
    command = f"echo hi\n{token} id"
    assert _blocked(tools, command), f"{command!r} should stay blocked (newline before)"


@pytest.mark.parametrize("token", ["sudo", "su", "doas"])
def test_adjacency_matrix_blocked_at_start_of_string(tools, token):
    """Regression guard for the exact bug this fix's first attempt had:
    Python's `"" in "-/_."` is True, so a naive membership check treats
    start-of-string (no preceding character at all) as if it were an
    exempt character. That would silently un-block bare `sudo id`."""
    command = f"{token} id"
    assert _blocked(tools, command), f"{command!r} should stay blocked (start-of-string)"


@pytest.mark.parametrize("token", ["sudo", "su", "doas"])
def test_adjacency_matrix_blocked_at_end_of_string(tools, token):
    """Same bug, other end: end-of-string must not be treated as exempt."""
    command = f"echo id | xargs {token}"
    assert _blocked(tools, command), f"{command!r} should stay blocked (end-of-string)"


def test_etc_sudoers_write_still_blocked_by_privileged_write_gate(tools):
    """SPEC §5 item 5 -- the one place the identifier exemption and the
    privileged-write gate interact. /etc/sudoers is itself an exempt
    IDENTIFIER for the token scan ('/' immediately before "sudo" inside
    "sudoers"), but writes to it must still be caught by the separate
    _PRIVILEGED_WRITE_PATHS mechanism, which matches on the /etc/ prefix
    and has nothing to do with the word "sudo" at all."""
    assert not tools._is_allowed_write("/etc/sudoers")
    for command in [
        "echo 'evil ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers",
        "echo 'evil ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers",
        "tee /etc/sudoers",
        "tee -a /etc/sudoers",
        "cp /tmp/x /etc/sudoers",
        "sed -i s/a/b/ /etc/sudoers",
    ]:
        assert _blocked(tools, command), f"write to /etc/sudoers allowed: {command!r}"
