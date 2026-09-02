# NAS KB Architecture (file layer)

Status: LIVE — soak started 2026-09-02 07:45 (node4090 + node3090 both swapped).

## Layout
- **Live source of truth (file layer):** `\\n45.home.arpa\Models\goethe\KB` (n45 NAS)
- **node4090 (LUCIFER, WSL2 Ubuntu 24.04):** `/opt/local-se/kb` → symlink →
  `/opt/local-se/nas/Models/goethe/KB` (CIFS `//n45.home.arpa/Models` mounted at
  `/opt/local-se/nas/Models`)
- **node3090 (Linux):** `/opt/local-se/kb` → symlink →
  `/opt/local-se/nas/Models/goethe/KB` (autofs master + NFSv4.1
  `n45.home.arpa:/Models`, per-share systemd mounts — no fstab work)
- **node5090 (Windows):** native path `\\n45.home.arpa\Models\goethe\KB` —
  point the gateway there when it lands. No action now.

## Versioning (git)
- `~/projects/local-system-engineer/kb` = versioned snapshot of the NAS file layer.
- `tools/kb-sync.sh` (run on node4090): rsync NAS→repo, **add/update only, no
  `--delete` during soak**, then `git commit`. Run manually after big KB sessions —
  git history tracks NAS evolution without ever removing files from the repo.
- Seed (2026-09-02): 35 files, sha256 match NAS↔repo verified, write-test OK from
  both nodes (CIFS + NFSv4.1).

## Semantic index (caveat)
- The Elasticsearch `lse-kb` index is **per-node** (346 docs as of 2026-09-02).
  `search_kb` works on each node against its own local index.
- The NAS unifies the *files*, not the *vector index*. A single shared ES would
  have to live on one node (never on CIFS/NFS) — optional phase 2.

## Soak / deletion rule
- No file deletions during soak (a few weeks of use in the new locations).
- node3090: old local KB preserved as `/opt/local-se/kb.local.bak` (contains only
  the stale Jul-14 `node3090-llama-launch.md`) — remove ONLY after soak.
- Repo `kb/` snapshot stays permanently (versioned history).

## Notes
- node3090's stale local copy carried a `--path .../ui/dist` UI-serving note for the
  decommissioned llama-ui setup. Live probe 2026-09-02: node3090's engine is the
  Unsloth Studio llama-server (ephemeral port, `--load-mode none`, no `--path`) →
  repo canonical `node3090-llama-launch.md` (2026-08-19, live-verified,
  Qwen3.8-27B-UD-Q6_K_XL) wins as-is. The stale note survives in `.local.bak` until
  soak ends.
- node4090 swap was pointer-only (43-byte symlink replaced); repo `kb/` untouched.
