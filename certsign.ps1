<#
.SYNOPSIS
    Signs LSE launcher scripts with the SY5TEM5 Authenticode certificate.

.DESCRIPTION
    Retrieves the SY5TEM5 code-signing certificate from the current user's
    certificate store and signs one or more launcher .ps1 files. Use after
    creating or modifying any lse-stack-launch-*.ps1 file.

.PARAMETER Target
    The launcher filename (without path) to sign, e.g. "lse-stack-launch-1.062.ps1".
    Pass "all" to sign every lse-stack-launch-*.ps1 in the project directory.
    Defaults to "lse-stack-launch-1.062.ps1" (current production version).

.EXAMPLE
    .\certsign.ps1
    Signs the current production launcher (v1.062).

.EXAMPLE
    .\certsign.ps1 -Target lse-stack-launch-1.062.ps1
    Signs a specific version.

.EXAMPLE
    .\certsign.ps1 -Target all
    Signs every lse-stack-launch-*.ps1 found in the project directory.

.NOTES
    The signing certificate must be in Cert:\CurrentUser\My with Subject
    matching "*SY5TEM5*". Run from any PowerShell window — does not require
    elevation. After signing, commit the updated file to git.
#>

[CmdletBinding()]
param(
    [string]$Target = 'lse-stack-launch-1.062.ps1'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectDir = $PSScriptRoot

# --- Locate certificate ---
$Cert = Get-ChildItem Cert:\CurrentUser\My |
        Where-Object { $_.Subject -like '*SY5TEM5*' } |
        Select-Object -First 1

if (-not $Cert) {
    Write-Error "SY5TEM5 certificate not found in Cert:\CurrentUser\My. Ensure the code-signing cert is installed."
    exit 1
}

Write-Host "Certificate : $($Cert.Thumbprint)  ($($Cert.Subject))" -ForegroundColor Cyan

# --- Resolve target file list ---
if ($Target -eq 'all') {
    $Files = Get-ChildItem -Path $ProjectDir -Filter 'lse-stack-launch-*.ps1' |
             Where-Object { $_.Name -notmatch '\.signed\.ps1$' } |
             Sort-Object Name
    if ($Files.Count -eq 0) {
        Write-Warning "No lse-stack-launch-*.ps1 files found in $ProjectDir"
        exit 0
    }
} else {
    $FilePath = Join-Path $ProjectDir $Target
    if (-not (Test-Path $FilePath)) {
        Write-Error "File not found: $FilePath"
        exit 1
    }
    $Files = @(Get-Item $FilePath)
}

# --- Sign and verify each file ---
$Results = @()

foreach ($File in $Files) {
    Write-Host "`nSigning : $($File.Name)" -ForegroundColor Yellow

    $Sig = Set-AuthenticodeSignature -FilePath $File.FullName -Certificate $Cert

    $Verify = Get-AuthenticodeSignature -FilePath $File.FullName

    $Ok = $Verify.Status -eq 'Valid'
    $Icon = if ($Ok) { '[OK]' } else { '[FAIL]' }
    $Color = if ($Ok) { 'Green' } else { 'Red' }

    Write-Host "$Icon  $($File.Name)  —  $($Verify.StatusMessage)" -ForegroundColor $Color

    $Results += [PSCustomObject]@{
        File          = $File.Name
        Status        = $Verify.Status
        StatusMessage = $Verify.StatusMessage
        Thumbprint    = $Sig.SignerCertificate.Thumbprint
    }
}

# --- Summary ---
Write-Host "`n--- Summary ---" -ForegroundColor Cyan
$Results | Format-Table -AutoSize

$Failed = $Results | Where-Object { $_.Status -ne 'Valid' }
if ($Failed) {
    Write-Error "$($Failed.Count) file(s) failed signing. Do not commit unsigned launchers."
    exit 1
}

Write-Host "All files signed successfully. Remember to commit the updated launcher(s) to git." -ForegroundColor Green
