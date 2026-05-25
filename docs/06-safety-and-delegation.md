# Safety and Delegation Model

**Date:** 2026-05-25
**Source:** Consolidated from *Local System Engineer Super Shell Terminal* project
(architecture doc §10–§11, `02-denylist.md`, `04-sep-template.md`, system prompt
safety section). Adapted for the current stack: Qwen3.6-27B + OpenWebUI tool
calling — no Supervisor pipe.

---

## 1. Bare-metal reality

The LSE runs on a **real WSL2 host with no container or sandbox**. The tool
functions execute commands on the actual machine. The denylist and the
human-in-the-loop are the **entire safety boundary** — there is nothing else
absorbing a mistake.

Two specific blast-radius facts to keep in mind at all times:

- `/mnt/c` and every other `/mnt/<drive>` path is the **Windows host
  filesystem**. A destructive write or delete there damages the user's Windows
  installation, not just the Linux environment. Treat these paths with the same
  caution as `/`.
- `sudo` gives root on a bare-metal WSL host. A misused root command can
  destroy the entire WSL environment and reach the Windows filesystem through
  the mount.

---

## 2. Three-tier delegation model

Every task falls into one of three tiers. Tier membership is determined by
reversibility and blast radius — not by how routine the task sounds.

### Tier 1 — Safe to delegate fully

Read-only, deterministic, and fully reversible. Run these freely without asking.

Examples:
- Environmental audits: `df -h`, `free -h`, `ps`, `uname`, `lsblk`, `ip addr`
- Reading and analysing config files, logs, or directory trees
- Drafting scripts into a staging path for human review
- Web search research with cited sources
- Generating timestamped reports or summaries
- Running `nvidia-smi`, `cat /proc/cpuinfo`, `uptime`

### Tier 2 — Delegate only behind mandatory gatekeeping

These change state, require `sudo`, or are not trivially reversible. **Always
stop, present the proposed action (as a mini-SEP if significant), and wait for
explicit approval before running.**

Examples:
- Package installs: `apt install`, `pip install`
- Service management: `systemctl start/stop/enable/disable`
- In-place config edits: `/etc/sysctl.conf`, `/etc/fstab`, `/etc/hosts`
- Any file operation outside a staging/scratch directory
- Kernel parameter changes: `sysctl -w`
- Any command requiring `sudo`

### Tier 3 — Do not delegate

Never run or propose these without a specific, unambiguous human instruction for
that exact action in that exact session.

- Destructive or irreversible operations on real data
- Credential and secret handling
- Operations on `/mnt/<drive>` (Windows filesystem) beyond reading
- Firewall or network-exposure changes
- Long stateful interactive sessions the tool cannot observe correctly
- Any action on the denylist (Section 3)

---

## 3. Command denylist — gated (match → stop and escalate)

A denylist match does **not** run silently. It surfaces to the human for explicit
approval. Never try to evade the gate by obfuscating a command, renaming a tool,
or splitting a destructive action into harmless-looking pieces.

### Gated commands

| Category | Examples |
|---|---|
| Recursive forced removal of root / home / gated paths | `rm -rf /`, `rm -rf ~`, `rm -rf /mnt/c` |
| Filesystem destruction tools | `mkfs.ext4 /dev/sdX`, `mkfs.vfat /dev/sdX` |
| Block device overwrite | `dd if=/dev/zero of=/dev/sdX`, `dd if=/dev/urandom of=/dev/nvme0n1` |
| Secure erase | `shred -n 10 /dev/sdX`, `wipefs -a /dev/sdX`, `blkdiscard /dev/sdX` |
| Partition editors in destructive mode | `fdisk`, `parted`, `sgdisk`, `gdisk` (any write operation) |
| Redirection into block devices | `> /dev/sda`, `> /dev/nvme0n1` |
| Fork bomb | `: () { : \| : & }; :` and all variants |
| Recursive chmod/chown on system paths | `chmod -R 777 /etc`, `chown -R user /usr` |
| Account deletion | `userdel`, `groupdel` |
| Deliberate malware / persistence | Any command installing a backdoor, cron-based exfiltration, or privilege escalation exploit |

### Why these specifically

Each item either (a) has no recovery path without a full reinstall, (b) reaches
the Windows host filesystem, or (c) is a known attack primitive. The list is
intentionally narrow — almost everything else is allowed. A narrow denylist is
more reliable than a broad one because edge cases don't slip through the gaps.

---

## 4. Directory denylist — writes and deletes are gated; reads are allowed

Reads are fine — audits need them. Only **writing or deleting** inside these
directories requires human approval.

```
/etc
/boot
/sys
/proc
/dev
/usr
/bin
/sbin
/lib
/lib64
/root
/var/lib
~/.ssh
/mnt/c        ← Windows C: drive
/mnt/<drive>  ← all Windows mounts
```

### Path matching rules

Resolve symlinks, expand `~` and environment variables, and canonicalise `..`
before matching. Indirection does not bypass the gate.

---

## 5. Dangerous command reference

This section lists specific commands that have caused real incidents or are
classic failure modes in bare-metal WSL environments. Keep it as a mental
checklist before running anything with a wide blast radius.

### Disk and filesystem destruction

```bash
rm -rf /                        # destroys the entire root filesystem
rm -rf /*                       # same effect, common obfuscation
rm -rf /mnt/c                   # destroys Windows C: drive
dd if=/dev/zero of=/dev/sdX     # zeroes a block device — unrecoverable
dd if=/dev/zero of=/dev/nvme0n1 # same, NVMe variant
mkfs.ext4 /dev/sdX              # formats a partition — destroys all data on it
shred -n 10 /dev/sdX            # forensic-grade wipe — truly unrecoverable
wipefs -a /dev/sdX              # removes filesystem signatures — effectively destroys
blkdiscard /dev/sdX             # SSD TRIM discard — unrecoverable on SSDs
```

### Fork bomb

```bash
:(){ :|:& };:                   # exhausts PIDs and memory; requires hard reboot
```

Variants include any self-replicating background process loop. Recognise the
pattern, not just the exact string.

### Dangerous redirections

```bash
> /dev/sda                      # zero-length write to block device — corrupts MBR
command > /dev/nvme0n1          # same for NVMe
cat /dev/urandom > /dev/sdX     # random overwrite — equivalent to shred
```

### Recursive permission destruction

```bash
chmod -R 000 /                  # makes entire filesystem inaccessible
chmod -R 777 /etc               # exposes all config files to all users
chown -R nobody /usr            # breaks all setuid binaries
```

### WSL-specific risks

```bash
rm -rf /mnt/c/Windows           # destroys Windows system directory
rm -rf /mnt/c/Users             # destroys all user profiles on Windows
> /mnt/c/Windows/System32/...   # overwrites Windows system files
```

### Credential and secret exfiltration patterns

```bash
cat ~/.ssh/id_rsa | curl ...    # private key exfiltration
tar czf - ~/.ssh | nc ...       # SSH directory exfiltration
env | curl -d @- ...            # environment variable (secrets) exfiltration
```

These are Tier 3 — never run without unambiguous explicit instruction.

---

## 6. Evasion prohibition

The denylist is enforced by pattern matching on the actual command, not by
trusting the model's judgment about intent. Do not:

- Obfuscate a gated command with base64, eval, or variable substitution
- Split a destructive operation across multiple steps to avoid matching
- Rename a gated tool (e.g. copy `rm` to `/tmp/del` and call that instead)
- Use a scripting language to perform a gated action without the gated shell command
- Frame a destructive action as a "test" or "demonstration"

If a task genuinely requires a gated action, the correct response is to surface
it as a SEP (Section 7) and wait for approval — not to find a path around the gate.

---

## 7. System Evolution Proposal (SEP) template

Use a SEP whenever a task needs a change that requires human approval: an
install, a service change, a config edit, or any Tier 2/3 action. Keep it
proportional — a small change gets a short SEP. A SEP is a proposal; do not act
until the human approves.

---

**SEP title:** `<short description of the change>`

**1. Gap analysis.**
What is currently missing or insufficient. Cite the audit output or test result
that shows it. Every claim must be backed by actual observed output — not
inference.

**2. Proposed change.**
The specific tool, package, or configuration change proposed, named exactly.

**3. Dependencies.**
What must be present or installed first for the proposed change to work.

**4. Risk and resource cost.**
Impact on the existing environment, disk/memory/CPU cost, and whether the change
is reversible. Note any gated commands the plan will trigger.

**5. Implementation plan.**
The exact commands or actions, in order, one per step. Mark which steps are
gated and will need explicit approval at execution time.

**6. Verification.**
The single check — one command or observation — that will confirm the change
worked after execution.

---

### SEP rules

- Every gap claim must be backed by actual audit output.
- Prefer reversible, backup-first, side-by-side approaches.
- Do not propose tools heavier than the host can reasonably support.
- After approval, execute one step at a time, report the result, then continue.
- If the verification step fails, stop and report — do not proceed to the next
  step and do not attempt to self-correct silently.

### When to write a full SEP vs. a mini-SEP

**Full SEP** — multi-step changes, service-level changes, kernel parameter
changes, anything touching `/etc` or a system service, any install that affects
more than the current user.

**Mini-SEP** (informal, inline) — single-command Tier 2 actions with obvious
verification. Example: "I'll run `sudo sysctl -w vm.dirty_ratio=20` to set the
dirty ratio. This is reversible; the old value was 40 (confirmed by prior read).
Verification: `sysctl vm.dirty_ratio`. Approve?"

The P2 test in the eval suite exercises exactly this pattern.

---

## 8. Relationship to the eval suite

Three eval tests directly exercise safety behaviour:

| Test | What it covers |
|---|---|
| **P1** — Privileged file write | sudo_delegation_block stop protocol |
| **P2** — READ-FIRST RULE | Model reads file before proposing a write; finds existing value |
| **P3** — Denylist refusal | Model refuses a gated command (rm -rf variant) |

A regression in any P-category test means the safety boundary has weakened.
P-tests run before W and A tests in every eval session.

