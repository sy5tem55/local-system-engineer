# LSE Stack Launcher — Release Procedure

**File pattern:** `lse-stack-launch-<version>.ps1`
**Location:** `C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\`
**Signing cert:** CN=SY5TEM5Cert · Thumbprint `2ACAC827D2AF5D24469E07B33A1E62A7464826FB`

---

## Adding or Editing a Profile

Edit the `$ModelProfiles` ordered hashtable in the current launcher. Key reference is in the file header comments. Rules:

- **No MTP for 35B A3B MoE models** — `--spec-type draft-mtp` causes "failed to measure MTP context memory: failed to create llama_context from model". Omit `SpecType` and `SpecDraftNMax` entirely.
- **No MTP at 64k context** — insufficient VRAM headroom on RTX 4090.
- **BannerLine1/2** must be ≤ 41 chars (fills fixed-width box).
- **TabLabel** must be ≤ 20 chars (Windows Terminal tab stripe).

---

## Release Checklist

### 1. Create the new file

Copy the current launcher to the new version number. **Do this in PowerShell, not bash** — bash `cp` produces LF line endings which break Authenticode.

```powershell
Copy-Item lse-stack-launch-1.071.ps1 lse-stack-launch-1.072.ps1
```

### 2. Strip the stale signature block

The copied file inherits the previous version's signature. It must be stripped before any edits and before re-signing:

```powershell
.\strip-sig.ps1 lse-stack-launch-1.072.ps1
```

Expected output: `[OK] SIG block stripped from lse-stack-launch-1.072.ps1 (N lines kept)`

### 3. Edit the file

Make profile changes and bump the banner version string:

```powershell
# Find and update the version line in the banner:
# Write-Host "  ${c}║              Stack Launcher  v1.071 ...
# Change to the new version number.
```

### 4. Re-encode to UTF-8 with BOM

PowerShell 7 writes UTF-8 without BOM by default. Windows Authenticode requires BOM. Always run this before signing, even if you edited in a text editor:

```powershell
$c = Get-Content ".\lse-stack-launch-1.072.ps1"
Set-Content ".\lse-stack-launch-1.072.ps1" -Value $c -Encoding utf8BOM
```

### 5. Sign

```powershell
.\certsign.ps1 -Target lse-stack-launch-1.072.ps1
```

Expected output: `[OK] lse-stack-launch-1.072.ps1 — Signature verified.`

### 6. Update VERSION.md

Update the Current Versions table and append a row to the Launcher version history table.

### 7. Commit

```powershell
git add lse-stack-launch-1.072.ps1 VERSION.md
git commit -m "launcher: v1.072 — <short description>"
```

If `git commit` fails with `cannot lock ref 'HEAD'`:

```powershell
Remove-Item ".git\HEAD.lock" -Force
git commit -m "launcher: v1.072 — <short description>"
```

---

## Known Failure Modes

| Symptom | Cause | Fix |
|---|---|---|
| `certsign.ps1: The property 'Thumbprint' cannot be found` | File has stale/invalid sig block, or wrong encoding | Strip sig first (`strip-sig.ps1`), then re-encode to utf8BOM |
| `An attempt was made to load a program with an incorrect format` | File is UTF-8 without BOM | Re-encode: `$c = Get-Content <f>; Set-Content <f> -Value $c -Encoding utf8BOM` |
| `The process cannot access the file ... used by another process` | `Get-Content` and `Set-Content` piped to same file | Read into variable first, then write separately |
| `fatal: cannot lock ref 'HEAD'` | Stale `.git/HEAD.lock` from a previous interrupted process | `Remove-Item .git\HEAD.lock -Force` |
| MTP context memory error on 35B A3B model | Architecture incompatibility with current llama.cpp build | Remove `SpecType`/`SpecDraftNMax` from the profile |
