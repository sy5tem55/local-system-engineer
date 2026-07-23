"""Security contracts for exact Goethe sudo grants.

These tests use a throwaway SQLite DB and fake executables. They never read or
write /etc/sudoers.d and never execute a privileged command.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe  # noqa: E402
import goethe_perms as perms  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(perms, "DB_PATH", str(tmp_path / "perms.db"))


@pytest.fixture()
def fake_bin(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()

    def add(name):
        path = bindir / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return add


def _insert_legacy(kind, pattern, table="grants"):
    with perms._db() as conn:
        if table == "grants":
            conn.execute(
                "INSERT INTO grants(kind,pattern,note,created_at,one_time) "
                "VALUES(?,?,?,?,0)",
                (kind, pattern, "legacy fixture", perms._now()),
            )
        else:
            conn.execute(
                "INSERT INTO requests(kind,pattern,reason,requested_at,status) "
                "VALUES(?,?,?,?,'pending')",
                (kind, pattern, "legacy fixture", perms._now()),
            )
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_exact_grant_renders_underlying_binary_and_exact_args(
    fake_bin, tmp_path, monkeypatch
):
    binary = fake_bin("systemctl")
    monkeypatch.setattr(
        perms,
        "_resolve_sudo_binary",
        lambda _command: (str(binary.resolve()), ""),
    )
    gid = perms.grant(
        "sudo",
        "systemctl show goethe-dream --property=ActiveState",
        "exact fixture",
    )

    content = perms.sudoers_content()
    assert gid == 1
    assert "/usr/bin/sudo" not in content
    assert (
        f"{binary.resolve()} show goethe-dream --property\\=ActiveState"
        in content
    )
    rule = next(line for line in content.splitlines() if "ALL=(root)" in line)
    assert "|" not in rule

    visudo = shutil.which("visudo")
    if visudo:
        candidate = tmp_path / "sudoers"
        candidate.write_text(content, encoding="utf-8")
        subprocess.run([visudo, "-cf", str(candidate)], check=True)


def test_no_argument_grant_is_rendered_as_no_arguments_only(
    fake_bin, monkeypatch
):
    binary = fake_bin("true")
    monkeypatch.setattr(
        perms,
        "_resolve_sudo_binary",
        lambda _command: (str(binary.resolve()), ""),
    )
    perms.grant("sudo", "true")
    line = next(
        line for line in perms.sudoers_content().splitlines()
        if "ALL=(root)" in line
    )
    assert line.endswith(f'{binary.resolve()} ""')


@pytest.mark.parametrize(
    "pattern",
    [
        "sudo docker start valkey",
        "doas systemctl restart demo",
        "su root",
        "docker start valkey 2>&1",
        "du -ah /mnt/nvme | sort -rh",
        "id && whoami",
        "systemctl start demo *",
        "echo $(id)",
        "printf 'two words'",
        "echo #comment",
        "echo\nwhoami",
        "-H systemctl restart demo",
        "MODE=unsafe systemctl restart demo",
    ],
)
def test_unsafe_sudo_grants_are_rejected_at_ingestion(pattern):
    with pytest.raises(ValueError):
        perms.grant("sudo", pattern)
    assert perms.list_grants() == []
    assert perms.file_request("sudo", pattern, "unsafe fixture") is None
    assert perms.pending() == []


def test_unsafe_legacy_grant_is_visible_but_never_rendered(fake_bin):
    fake_bin("sudo")
    _insert_legacy("sudo", "sudo docker start valkey 2>&1")

    row = perms.list_grants()[0]
    assert row["sudoers_valid"] is False
    assert "shell control operators" in row["sudoers_error"]

    content = perms.sudoers_content()
    assert "# SKIPPED unsafe grant #1:" in content
    assert not any("ALL=(root)" in line for line in content.splitlines())


def test_user_owned_executable_is_not_rendered(fake_bin):
    binary = fake_bin("operator-script")
    perms.grant("sudo", "operator-script exact-arg")
    content = perms.sudoers_content()
    assert f"# SKIPPED grant #1: executable is not root-owned" in content
    assert str(binary) in content
    assert not any("ALL=(root)" in line for line in content.splitlines())


def test_unsafe_legacy_request_cannot_be_approved_and_stays_pending():
    rid = _insert_legacy(
        "sudo", "id && sudo -n whoami 2>&1", table="requests"
    )

    with pytest.raises(ValueError):
        perms.resolve_request(rid, approve=True)

    rows = perms.pending()
    assert [row["id"] for row in rows] == [rid]
    assert rows[0]["sudoers_valid"] is False
    assert perms.list_grants() == []


def test_clean_approval_is_atomic_and_duplicate_grants_are_deduped(fake_bin):
    fake_bin("systemctl")
    rid = perms.file_request(
        "sudo", "systemctl start goethe-dream", "clean fixture"
    )
    status, gid = perms.resolve_request(rid, approve=True)
    assert status == "approved"
    assert perms.pending() == []
    assert [row["id"] for row in perms.list_grants()] == [gid]

    rid2 = perms.file_request(
        "sudo", "systemctl start goethe-dream", "same fixture"
    )
    status2, gid2 = perms.resolve_request(rid2, approve=True)
    assert status2 == "approved"
    assert gid2 == gid
    assert len(perms.list_grants()) == 1


def test_check_sudo_matches_exact_argv_and_consumes_one_time_grant():
    gid = perms.grant("sudo", "systemctl start goethe-dream", one_time=True)
    assert perms.check_sudo("systemctl start other-service") is None
    assert perms.check_sudo("systemctl start goethe-dream") == gid
    assert perms.check_sudo("systemctl start goethe-dream") is None


def test_complex_privilege_block_never_files_an_approvable_request(
    tmp_path, monkeypatch
):
    tools = goethe.Tools()
    tools.valves.LOG_FILE = str(tmp_path / "audit.log")
    calls = []

    class FakePerms:
        @staticmethod
        def file_request(*args):
            calls.append(args)
            return 99

    monkeypatch.setattr(tools, "_perms_mod", lambda: FakePerms)
    result = tools._validate_command_safety(
        "sudo du -ah /mnt/nvme | sort -rh | head -30",
        "/home/sy5",
    )

    assert calls == []
    assert "cannot become a sudo grant" in result
    assert "split the privileged operation" in result


def test_clean_privilege_block_files_only_the_underlying_command(
    tmp_path, monkeypatch
):
    tools = goethe.Tools()
    tools.valves.LOG_FILE = str(tmp_path / "audit.log")
    calls = []

    class FakePerms:
        @staticmethod
        def check_sudo(_command):
            return None

        @staticmethod
        def file_request(*args):
            calls.append(args)
            return 42

    monkeypatch.setattr(tools, "_perms_mod", lambda: FakePerms)
    result = tools._validate_command_safety(
        "sudo systemctl start goethe-dream",
        "/home/sy5",
    )

    assert calls == [
        ("sudo", "systemctl start goethe-dream", "agent requested privileged command")
    ]
    assert "Pending grant request #42" in result
