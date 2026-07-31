# NAS Access Architecture — n45 (QNAP TS-419P II)

**Status:** node3090 COMPLETE and verified 2026-07-29. LUCIFER + node5090 pending (SMB).
**Related:** docs/06-safety-and-delegation.md, docs/11-node-agent-delegation.md

---

## 1. The device

| | |
|---|---|
| Host | `n45.home.arpa` |
| IPs | **192.168.5.44** and **192.168.5.45** (dual NIC — both matter in any rule) |
| Model | QNAP TS-419P II (2011 ARM appliance, EOL firmware, BusyBox **v1.01**) |
| Segment | OPT1 / `opt4` (igc2), 192.168.5.0/24 |
| Exports | 34 shares; 3 contain spaces (`/TV Series`, `/Maid Diary`, `/Alice Diary`) |

NFSv4 enabled; NFSv3/v2/AFP disabled. `rpcinfo` registers only `nfs v4` on 2049.

### NFSv4 pseudo-root — non-obvious and important

QTS builds a **tmpfs at `/share/NFSv=4`** (yes, with an `=` in the name) and
bind-mounts each NFS-enabled share beneath it:

```
tmpfs                    on /share/NFSv=4          type tmpfs (rw,size=16M)
/share/HDA_DATA/Models   on /share/NFSv=4/Models   type none (rw,bind)
```

Clients therefore address `n45:/Models` **relative to the pseudo-root**, not the
filesystem root. It is tmpfs, so it is rebuilt on every boot or NFS service
restart — never set permissions on it; set them on the real volume paths.

Real volume paths: `ARCHIVE→HDD_DATA`, `OS→HDB_DATA`, and
`Models`/`Music`/`osImages`/`TENSORS`→`HDA_DATA`. `Public` is also exported.

---

## 2. Protocol assignment — decided by measurement

| Node | Protocol | Evidence |
|---|---|---|
| **node3090** (192.168.5.41) | **NFSv4** ✅ working | Mounted pseudo-root in **0.231s**, negotiated `vers=4.1` |
| **LUCIFER / node4090** (192.168.1.57) | **SMB** | NFS fails: `mount.nfs: mount(2): Connection timed out`, 25s, every version and path |
| **node5090** (192.168.1.55) | **SMB** | Windows — NFS identity mapping via registry AUID is not worth the friction |

**WSL2 cannot mount NFS against this NAS.** Identical command, same moment, same
server: 0.231s from native Linux, 25s timeout from WSL2. CIFS to the same box
works fine from WSL2, so the network path is good and the fault is WSL2's NFS
client. This confirms the earlier KB doc (`1b27e74e4b7aeb3e`, 2026-07-23).

Note `vers=4.1` negotiates cleanly — an earlier theory that the 2011 nfsd lacked
v4.1 session support was **wrong**.

---

## 3. Identity model

NFS `AUTH_SYS` transmits **numeric uid/gid, never usernames.**

| Node | Agent user | uid/gid | Groups added |
|---|---|---|---|
| LUCIFER | `sy5` | 1000 / 1000 | + 3000 (lse) |
| node3090 | `lse-admin` | 1001 / 1001 | + 3000 (lse), **+ 100 (users)** |

A `nologin`, homeless user+group **`lse` at uid/gid 3000** exists identically on
both Linux nodes as a numeric anchor. Nothing runs as `lse`.

### The group that actually grants access is 100, not 3000

NAS content is owned **`uid 501 gid 100 (users)` at mode 0770**, with POSIX ACLs
(`+`). Under 0770 "other" gets nothing, so `lse-admin` was **READ DENIED** on
every existing file while writes succeeded (share roots are 0777).

Fix applied: `usermod -aG users lse-admin`. AUTH_SYS then includes gid 100 in the
supplementary list and the group `rwx` bits apply. **Verified READ_OK.**

`chown -R :3000` on the NAS was attempted and did **not** land. Do not retry it:
recursive chown across ~250 GB of GGUF files on 2011 ARM hardware runs for hours
to achieve what one `usermod` achieves instantly. gid 3000 remains correct for a
future tightening step (dropping world-write), not for granting access today.

---

## 4. Access boundary

Agent shares: **ARCHIVE, Models, Music, OS, osImages, TENSORS**

NFS host access limited to `192.168.1.57`, `192.168.5.41`, `192.168.1.55`.
Squash: **ROOT_SQUASH**.

Never `NO_ROOT_SQUASH` with an open host list — with `sec=sys` that grants any
reachable host root-equivalent control of the files with no credential.

---

## 5. Mount convention — node3090 (implemented)

Mountpoints `/opt/local-se/nas/<share>`, **not** `/mnt`. `/opt/local-se/` is
already in Goethe's `_ALLOWED_READ_PREFIXES`, so `read_file()` works with **zero
code change**.

```
n45.home.arpa:/<share> /opt/local-se/nas/<share> nfs4 \
  rw,_netdev,x-systemd.automount,x-systemd.idle-timeout=600,noatime,hard,nofail 0 0
```

`hard` not `soft`: these are read-write mounts and soft mounts can silently lose
data on a write timeout. The usual objection to `hard` (boot hangs) is removed by
`x-systemd.automount`, which mounts on first access rather than at boot.

**`systemctl daemon-reload` alone does NOT activate the automounts** — it
generates the `.automount` units but does not start them. Follow with
`systemctl restart remote-fs.target`. Symptom if skipped: `ls` shows `total 0`
and `mount` shows nothing, looking exactly like a failed mount.

Verified 2026-07-29: all six shares WRITE_OK, READ_OK wherever a readable file
exists, six autofs triggers active.

---

## 5b. Mount convention — LUCIFER + node5090 (SMB/CIFS)

CIFS authenticates by credential, so **none of the uid/gid mapping in section 3
applies** — group 100 and gid 3000 are irrelevant here. Ownership is fabricated
client-side by the mount options instead, which is why they are not optional.

```
//n45.home.arpa/<share> /opt/local-se/nas/<share> cifs \
  credentials=/etc/samba/n45.creds,vers=3.0,uid=1000,gid=3000,\
  file_mode=0664,dir_mode=0775,hard,x-systemd.automount,nofail,_netdev 0 0
```

**`vers=3.0` is mandatory, not cosmetic.** Modern kernels negotiate SMB 3.1.1 by
default; this is a 2011 QNAP and the two long-working CIFS mounts on LUCIFER both
pin 3.0 explicitly. Omitting it is a likely mount failure.

**`uid=`/`gid=`/`file_mode=`/`dir_mode=` are mandatory.** CIFS defaults to
`uid=0`, so without them everything under the mountpoint is owned by root and
`sy5` — therefore the Goethe gateway — cannot write and may not be able to read.
That defeats the purpose of mounting it at all.

Credentials file `/etc/samba/n45.creds`, mode 600, root:root, two lines
(`username=` / `password=`). Never in fstab, never echoed. Source: Vaultwarden
item `lse@n45.home.arpa`. `mkdir -p /etc/samba` first — the directory may not
exist if Samba was never installed.

**Before replacing the legacy mounts** (`//n45/Models` at `/tmp/n45_models`,
`//n45/OS` at `/mnt/n45_os`), check nothing holds files open:
`fuser -m /tmp/n45_models /mnt/n45_os` or `lsof +f -- <path>`. Unmounting a
share with open handles fails mid-operation rather than cleanly.

---

## 6. Failure modes — each cost real time

**Unset NFS host access produces a silent 15s hang, not an error.** QTS accepts
TCP on 2049 and never negotiates. Indistinguishable from a network or version
fault. Check host access first.

**WSL2 cannot mount NFS here.** Do not spend time on options, versions or paths.
Use SMB on LUCIFER.

**Never suppress stderr when diagnosing mounts.** A probe with `2>/dev/null`
discarded the only diagnostic available and wasted a full round trip.

**`timeout` kills `mount` silently.** A hang presents as no output at all. Time
the command: ~25s means hang, instant means clean refusal.

**BusyBox v1.01 on the NAS has no `find -exec`** and no `-maxdepth`. Use
`while read` loops.

**ROOT_SQUASH blocks `chown` over NFS** — remote root is `nobody`. Set ownership
from the NAS side.

**`usermod -aG` does not affect running processes.** The Goethe gateway and
llama-server on node3090 need restarting to pick up group 100.

**`mount | grep -c nfs` counts the CIFS mounts** — they carry `reparse=nfs` in
their options. Use `grep ' type nfs'`.

**`_ALLOWED_READ_PREFIXES` is not a security boundary.** `execute_command`
traverses `/mnt` freely while `read_file()` is blocked. Real enforcement is on
the NAS.

---

## 7. Firewall posture (pfSense, applied 2026-07-29)

Two floating quick rules, `LAN` + `OPT2` + `WLAN` → `192.168.5.0/24`:

| Rule | Ports | Purpose |
|---|---|---|
| 44 | 111 | rpcbind — NFSv4 does not use it; blocking it also makes `nlockmgr`'s dynamic ports undiscoverable |
| 45 | 30000–30002 | mountd / statd / rquotad — NFSv3-era daemons still running after v3 was disabled |

Open deliberately: 2049, 445, 22, 8080.

**Limitation:** node3090 shares a subnet with the NAS, so that traffic never
traverses pfSense and cannot be filtered by these rules.

**Side effects:** `showmount`/`rpcinfo` against the NAS no longer work from
LUCIFER. Installing `nfs-common` on node3090 also installed and enabled
`rpcbind` there — a new port 111 listener on the Studio segment, which NFSv4
does not need and which can be disabled.

---

## 8. Remaining work

1. SMB mounts on LUCIFER for the six shares, same `/opt/local-se/nas/` convention
2. SMB mount on node5090 (asleep at time of writing)
3. Restart Goethe gateway + llama-server on node3090 to pick up group 100
4. Optional: disable `rpcbind` on node3090 and LUCIFER
5. Optional tightening: remove world-write from the six shares, relying on gid 3000
