# Skill #1 — Permission-blocked cleanup (sudo-blocker discovery)

> S0.3 artifact (`docs/self-learning-trajectory.md`). Seeded to `lse-skills` via
> `rag/07-seed-skills.py`. skill_id: `linux-sysadmin/permission-blocked-file-operations-without-sudo`

## Task
Perform file operations (delete/write) in a privileged path when `execute_command`
blocks `sudo` and the path is owned by another user.

## Preconditions
- `execute_command` blocks `sudo` by SUBSTRING match — any command containing it is rejected
- Target path owned by a different user/group (e.g. `/opt/models` owned by sy5)

## Procedure
1. Confirm the block is structural, not transient: `id`, `ls -ld <dir>`, `stat -c '%U %G %a' <dir>`
2. Do NOT attempt sudo variants or escalation — the blocklist is intentional; workarounds are protocol violations
3. Fix structurally via the human operator: group membership (`usermod -aG <group> <user>`) or setgid directory — group changes need a fresh login/session to apply
4. Verify write access with a probe: `touch <dir>/.probe && rm <dir>/.probe`
5. For deletions, verify before unlink: `readlink -f` + `stat -c %i` BOTH paths (symlink ≠ duplicate — one inode means deletion removes the only copy), sha256 the survivor, then delete and confirm `df` delta

## Verification
Probe touch/rm exits 0 as the unprivileged user; the original operation's ground-truth
check passes (file absent / df delta / content hash unchanged on survivor).

## Failure modes
- sudo substring triggers even inside strings/echo
- Glob expands before sudo in a non-root shell → literal "No such file" (`sudo bash -c '...'` form — human-run only)
- Group membership not effective in existing sessions
- "Duplicate" behind a symlink is ONE inode — deleting it destroys the only copy (node-t3-005 retraction)

## Provenance
episodes #32–34 (node-t3-005) · ROADMAP P20 entry · docs/incident-2026-06-11-model-deletion.md
