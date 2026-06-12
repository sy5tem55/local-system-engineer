# teardown-node5090.ps1 v1.0
# FULL RESTORE: returns node5090 to its original Windows 11 state, pre-WSL.
# Run from an ELEVATED PowerShell prompt on node5090.
#
# Tier 1 (game mode, daily):  .\teardown-node5090.ps1 -GameMode
#     Stops services + wsl --shutdown. All VRAM/RAM released. Fully reversible.
# Tier 2 (full restore):      .\teardown-node5090.ps1
#     Unregisters the distro, removes .wslconfig + firewall rules, disables WSL
#     features. Machine is back to pre-WSL Windows 11 (NVIDIA gaming driver kept).
#
# Design: docs/node5090-deployment-design.md §7

param(
    [switch]$GameMode,
    [switch]$SkipBackup
)

$ErrorActionPreference = "SilentlyContinue"
$DistroName = "Ubuntu-24.04"
$FwPrefix   = "LSE-node5090"

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "   OK: $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "   WARN: $msg" -ForegroundColor Yellow }

# ── Tier 1: stop services + shutdown WSL (always runs) ───────────────────────
Write-Step "Stopping LSE services inside WSL..."
wsl -d $DistroName -u root bash -c "systemctl stop llama-server-5090 node-exporter 2>/dev/null; pkill -f llama-server 2>/dev/null; exit 0" 2>$null
Write-OK "Services stopped"

Write-Step "Shutting down WSL (releases all VRAM/RAM)..."
wsl --shutdown
Start-Sleep -Seconds 2
Write-OK "WSL down"

if ($GameMode) {
    nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>$null | ForEach-Object { Write-OK "GPU memory now: $_" }
    Write-Host "`nGame mode: WSL is down, all resources released. 'wsl' to bring it back." -ForegroundColor Green
    exit 0
}

# ── Tier 2: full restore ─────────────────────────────────────────────────────
Write-Warn "FULL RESTORE selected — this removes the Linux distro and all its data."
$confirm = Read-Host "Type 'RESTORE' to continue"
if ($confirm -ne "RESTORE") { Write-Warn "Aborted."; exit 1 }

# 1. Optional backup
if (-not $SkipBackup) {
    Write-Step "1/5 Exporting distro backup (skip with -SkipBackup)..."
    $bak = "$env:USERPROFILE\node5090-wsl-backup-$(Get-Date -Format yyyyMMdd-HHmmss).tar"
    wsl --export $DistroName $bak
    if (Test-Path $bak) { Write-OK "Backup: $bak ($([math]::Round((Get-Item $bak).Length/1GB,1)) GB)" }
    else { Write-Warn "Export failed or distro absent — continuing" }
} else {
    Write-Step "1/5 Backup skipped (-SkipBackup)"
}

# 2. Unregister distro (removes vhdx + all Linux state)
Write-Step "2/5 Unregistering $DistroName..."
wsl --unregister $DistroName
Write-OK "Distro removed"

# 3. Remove .wslconfig (restore pre-LSE backup if one was made)
Write-Step "3/5 Removing .wslconfig..."
$wslConfigPath = "$env:USERPROFILE\.wslconfig"
if (Test-Path "$wslConfigPath.pre-lse.bak") {
    Move-Item "$wslConfigPath.pre-lse.bak" $wslConfigPath -Force
    Write-OK "Pre-LSE .wslconfig restored"
} elseif (Test-Path $wslConfigPath) {
    Remove-Item $wslConfigPath -Force
    Write-OK ".wslconfig deleted"
} else { Write-OK "No .wslconfig present" }

# 4. Remove firewall rules by prefix
Write-Step "4/5 Removing $FwPrefix-* firewall rules..."
$removed = 0
Get-NetFirewallRule -DisplayName "$FwPrefix-*" | ForEach-Object {
    Remove-NetFirewallRule -DisplayName $_.DisplayName
    $removed++
}
Write-OK "$removed rule(s) removed"

# 5. Disable WSL optional features
Write-Step "5/5 Disabling WSL Windows features..."
foreach ($f in @("Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform")) {
    $state = (Get-WindowsOptionalFeature -Online -FeatureName $f).State
    if ($state -eq "Enabled") {
        Disable-WindowsOptionalFeature -Online -FeatureName $f -NoRestart | Out-Null
        Write-OK "Disabled $f"
    } else { Write-OK "$f already disabled" }
}
# Remove the WSL store app if present (newer installs)
Get-AppxPackage MicrosoftCorporationII.WindowsSubsystemForLinux 2>$null | Remove-AppxPackage 2>$null

# ── Residue checklist (external state this script cannot touch) ──────────────
Write-Host @"

══════════════════════════════════════════════════════════════
 RESTORE COMPLETE — reboot to finalize feature removal.
 Machine is back to pre-WSL Windows 11.

 Kept intentionally:
   - NVIDIA driver (it is the gaming driver)
   - Distro backup .tar in your user profile (if exported)

 External cleanup (manual, on other hosts):
   [ ] pfSense: remove static DHCP map + DNS overrides
       node5090.home.arpa / 5090.home.arpa (Write Access Protocol)
   [ ] LUCIFER Prometheus: remove node5090 scrape targets
   [ ] LUCIFER known_hosts: ssh-keygen -R node5090.home.arpa
   [ ] CHANGELOG entry: node5090 decommissioned <date>
══════════════════════════════════════════════════════════════
"@ -ForegroundColor Yellow

$reboot = Read-Host "Reboot now? [y/N]"
if ($reboot -eq "y") { Restart-Computer }
