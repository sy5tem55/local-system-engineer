# Goethe GUI safe-launcher attestation + node5090 Windows variant

## Mechanism (verified 2026-09-01)
Each Goethe.App bundle ships Scripts/goethe_mcp.py — a "pinned no-replace"
entrypoint. Before exec it reads the LIVE file
~/projects/local-system-engineer/tools/goethe_mcp.py and requires an exact
SHA-256 match against UPSTREAM_SHA256 hardcoded in the bundle. Any drift
(uncommitted edits, symlinks, perm change, >1MB) => REFUSED, exit 60.
start-goethe-safe.sh additionally: never kills/replaces a running gateway
(process scan CONFLICT => exit 43; :9700 listener => exit 46); owner record
lives in /tmp/goethe-gui-runtime-<uid>/gateway.owner.

## Bundle pins (2026-09-01)
- Goethe.App-20260801-safe-03 (active GUI): 9ca2c554... = commit 4e99c94 (08-11, HEAD)
- Goethe.App-20260809-safe-04 / safe-05 / 20260810-safe-03-3.16-fix:
  1697ae63... = OLDER commit 594ccc9 (08-08) — bundle dates mislead, pins don't
- goethe-app-c7-snapshot: 5923140f... = 5dceaff (07-31)

## node5090 Windows variant (no WSL)
The live WSL file was restored to the pinned hash on 2026-09-01 after a
19-line uncommitted patch (Windows netstat/taskkill branch in _free_port)
broke GUI attestation. The Windows variant is preserved at:
  /opt/local-se/patches/goethe_mcp.py.windows-node5090   (full file, sha256 53e9c216...)
  /opt/local-se/patches/goethe_mcp-windows-node5090-freeport.patch (diff)
Deploy this to node5090 (Windows, no WSL) — do NOT apply it to the WSL live
file, or the GUI attestation breaks again.

## Recovery if GUI refuses with exit 60
1. sha256sum ~/projects/local-system-engineer/tools/goethe_mcp.py
2. compare vs bundle pin: grep UPSTREAM_SHA256 <bundle>/win-x64/Scripts/goethe_mcp.py
3. git -C ~/projects/local-system-engineer status/diff tools/goethe_mcp.py
4. intended drift -> commit + re-attest bundle pin; unintended -> git restore
