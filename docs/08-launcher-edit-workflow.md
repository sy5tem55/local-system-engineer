# Launcher Edit Workflow — Avoiding Authenticode SIG Corruption

**Last updated:** 2026-05-27

---

## The Problem

The launcher files (`lse-stack-launch-*.ps1`) are Authenticode-signed. The signature is appended as a comment block at the end of the file:

```
# SIG # Begin signature block
# <base64 lines>
# SIG # End signature block
```

**The Edit tool (Cowork/Claude) corrupts signed files.** When it writes to a file that has a SIG block, the final line of the script body before the SIG block gets its closing quote stripped:

```powershell
Write-Host ""     ← becomes →     Write-Host "
```

This produces a parse error (`string is missing the terminator`) and the script will not run. The corruption is silent — the Edit tool reports success. The only way to detect it is a `powershell -Command "..."` parse check or by running the script.

**Never edit a signed PS1 file directly.** Always strip the SIG block first.

---

## The Correct Workflow

### Creating a new launcher version

```
1. Copy-Item lse-stack-launch-1.NNN.ps1 lse-stack-launch-1.NNN+1.ps1
2. .\strip-sig.ps1 -Target lse-stack-launch-1.NNN+1.ps1
3. <Claude makes edits via Edit tool>
4. .\certsign.ps1 -Target lse-stack-launch-1.NNN+1.ps1
5. git add lse-stack-launch-1.NNN+1.ps1 VERSION.md ROADMAP.md
6. git commit -m "launcher v1.NNN+1: <description>"
```

### Amending/fixing the current version in place

Only do this if the file has not been pushed to a remote, or you are comfortable with a force-push.

```
1. .\strip-sig.ps1 -Target lse-stack-launch-1.NNN.ps1
2. <Claude makes edits via Edit tool>
3. .\certsign.ps1 -Target lse-stack-launch-1.NNN.ps1
4. git add lse-stack-launch-1.NNN.ps1
5. git commit --amend --no-edit
```

---

## strip-sig.ps1 — What It Does and Why It Must Be Run First

`strip-sig.ps1` reads the file, finds the line `# SIG # Begin signature block`, keeps everything before it (trimming trailing blank lines), adds exactly one blank line, and writes the file back with UTF-8 encoding.

**Output to look for:**

```
  [OK]  SIG block stripped from lse-stack-launch-1.NNN.ps1  (NNN lines kept)
```

If you see `[SKIP] No SIG block found`, the file was already unsigned — safe to edit directly.

**Do not proceed with edits if strip-sig reports a warning or error.**

### The -SimpleMatch bug (historical — fixed in strip-sig.ps1)

An earlier version of `strip-sig.ps1` used `-SimpleMatch` on the `Select-String` call:

```powershell
# BUG — DO NOT USE
$SigMatch = $Lines | Select-String -Pattern '^# SIG # Begin signature block' -SimpleMatch
```

`-SimpleMatch` treats the pattern as a literal string, so `^` is matched as the literal character `^`, not as a regex anchor. The line is never found. `$SigMatch` is `$null`. `$null.LineNumber - 1` evaluates to `-1`. `$Lines[0..-2]` in PowerShell returns three elements (index 0, index -1 = last, index -2 = second-to-last) — the file is destroyed and written as a 3-line stub. certsign then re-signs the 3-line stub with no error.

The fix (already in place): remove `-SimpleMatch` so `^` works as a regex anchor.

---

## Post-Edit Verification

Before signing, parse-check the file to confirm no corruption:

```powershell
$errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path 'lse-stack-launch-1.NNN.ps1').Path,
    [ref]$null, [ref]$errors)
if ($errors.Count -eq 0) { "Parse OK" } else { $errors }
```

> **Note:** `$errors = $null` must appear before the ParseFile call. PowerShell refuses `[ref]` on an undeclared variable — omitting it gives `InvalidOperation: [ref] cannot be applied to a variable that does not exist` and silently skips the check.

**Only sign if you get `Parse OK`.** If there are errors, do not run certsign — fix the corruption first (see Recovery section below).

---

## certsign.ps1

Signs the file using the local Authenticode certificate. Run after all edits are complete and the parse check passes:

```powershell
.\certsign.ps1 -Target lse-stack-launch-1.NNN.ps1
```

Expected output: a `SignerCertificate` block with `Status : Valid`.

certsign does **not** validate the script before signing. It will happily sign a corrupted file. The parse check in the previous step is your guard.

---

## Recovery: File Was Signed While Corrupted

If certsign ran on a corrupted file (e.g. the `Write-Host "` truncation was not caught), the signed file is now wrong. Options:

### Option A — git restore (preferred if you have a clean prior commit)

```powershell
git checkout <clean-commit-hash> -- lse-stack-launch-1.NNN.ps1
```

Then re-apply your edits from scratch using the strip-sig workflow.

### Option B — Manual PowerShell fix before re-signing

If git restore is not available, fix the truncated line in PowerShell:

```powershell
$lines = Get-Content lse-stack-launch-1.NNN.ps1
$sigStart = ($lines | Select-String -Pattern '^# SIG # Begin signature block').LineNumber - 1
$body = $lines[0..($sigStart - 1)]
# Repair the specific corrupted line (adjust the string to match your case):
$body = $body | ForEach-Object {
    if ($_.TrimEnd("`r") -eq 'Write-Host "') { 'Write-Host ""' } else { $_ }
}
$body | Set-Content lse-stack-launch-1.NNN.ps1 -Encoding UTF8
```

Note: `.TrimEnd("`r")` is required because CRLF files leave a trailing `\r` on each line when read with `Get-Content`.

After the fix, parse-check and re-sign.

---

## Version Housekeeping After Each New Launcher Version

After committing the new PS1 file, update:

- **`VERSION.md`** — Current Versions table (Launcher row) + Launcher versions history table
- **`ROADMAP.md`** — Current production versions table (Launch script row)

Commit those together:

```powershell
git add VERSION.md ROADMAP.md
git commit -m "docs: bump launcher to v1.NNN in VERSION.md and ROADMAP.md"
```

---

## Quick Reference Card

| Step | Command | Notes |
|------|---------|-------|
| Copy | `Copy-Item lse-stack-launch-1.NNN.ps1 lse-stack-launch-1.NNN+1.ps1` | Always work on a new file |
| Strip | `.\strip-sig.ps1 -Target lse-stack-launch-1.NNN+1.ps1` | Must see `[OK]` before editing |
| Edit | Claude Edit tool | Safe on unsigned files |
| Parse check | `$errors = $null` then `ParseFile(...)` | Must see `Parse OK` before signing; `$errors = $null` must be declared first |
| Sign | `.\certsign.ps1 -Target lse-stack-launch-1.NNN+1.ps1` | Only after parse check passes |
| Commit | `git add ... && git commit -m "..."` | Include VERSION.md + ROADMAP.md |
