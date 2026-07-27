# LSE Filesystem Layout — post-ext4 migration (2026-07-21)

## Canonical locations (ALL on ext4 — no WSL /mnt/c boundary)
- Repo: `/home/sy5/projects/local-system-engineer` — REAL ext4 directory (was a symlink to /mnt/c until 2026-07-21).
- KB: `/opt/local-se/kb` -> symlink to `<repo>/kb` (same filesystem, harmless; keeps KB under git version control).
- Dreams/logs: `/opt/local-se/dreams`, `/opt/local-se/logs` — real ext4 dirs.

## Why the migration
The repo lived on `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer` (Windows drive via WSL 9p).
That caused: guard false-blocks (realpath escaped every allowed prefix, so the LSE could not read
or write its own KB), ~300x slower git/find, and NTFS `Zone.Identifier` litter.

## Windows access
Via `\\wsl$\Ubuntu\home\sy5\projects\local-system-engineer` (Explorer, VS Code). There is no
authoritative copy on C: any more. A pre-migration snapshot remains at the old C: path as backup.

## Rules
- Do NOT recreate the repo on /mnt/c or symlink into it.
- Goethe.App presets and goethe-dream.service reference the WSL path — unchanged by the migration.
