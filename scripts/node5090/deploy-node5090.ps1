# deploy-node5090.ps1 v1.0
# Windows-side bootstrap for node5090 (192.168.1.55, asset 1BL15, RTX 5090 32GB).
# Run from an ELEVATED PowerShell prompt on node5090.
# Idempotent — safe to re-run. Pair: provision-node5090.sh (runs inside WSL).
# Design: docs/node5090-deployment-design.md

$ErrorActionPreference = "Stop"
$DistroName = "Ubuntu-24.04"
$FwPrefix   = "LSE-node5090"

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "   OK: $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "   WARN: $msg" -ForegroundColor Yellow }

# ── Step 1/6: WSL optional features ──────────────────────────────────────────
Write-Step "1/6 Enabling WSL + VirtualMachinePlatform features..."
$features = @("Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform")
$rebootNeeded = $false
foreach ($f in $features) {
    $state = (Get-WindowsOptionalFeature -Online -FeatureName $f).State
    if ($state -ne "Enabled") {
        Enable-WindowsOptionalFeature -Online -FeatureName $f -NoRestart | Out-Null
        $rebootNeeded = $true
        Write-OK "Enabled $f"
    } else {
        Write-OK "$f already enabled"
    }
}
if ($rebootNeeded) {
    Write-Warn "REBOOT REQUIRED before continuing. Re-run this script after reboot."
    exit 0
}
wsl --update | Out-Null
Write-OK "WSL kernel up to date"

# ── Step 2/6: .wslconfig — mirrored networking + memory policy ───────────────
Write-Step "2/6 Writing .wslconfig (mirrored networking)..."
$wslConfigPath = "$env:USERPROFILE\.wslconfig"
$wslConfig = @"
# Written by deploy-node5090.ps1 — removed by teardown-node5090.ps1
[wsl2]
networkingMode=mirrored
memory=48GB
processors=16
[experimental]
autoMemoryReclaim=gradual
hostAddressLoopback=true
"@
if (Test-Path $wslConfigPath) {
    Copy-Item $wslConfigPath "$wslConfigPath.pre-lse.bak" -Force
    Write-Warn "Existing .wslconfig backed up to .wslconfig.pre-lse.bak"
}
Set-Content -Path $wslConfigPath -Value $wslConfig -Encoding UTF8
Write-OK ".wslconfig written (mirrored mode — requires Win11 22H2+)"

# ── Step 3/6: Install distro ─────────────────────────────────────────────────
Write-Step "3/6 Installing $DistroName..."
$installed = (wsl --list --quiet 2>$null) -replace "`0","" | Where-Object { $_ -eq $DistroName }
if (-not $installed) {
    wsl --install -d $DistroName --no-launch
    Write-OK "$DistroName installed — launch it once to create the 'sy5' user, then re-run this script."
    Write-Warn "ACTION: run '$DistroName' from Start menu, create user 'sy5', then re-run deploy."
    exit 0
} else {
    Write-OK "$DistroName already installed"
}

# Enable systemd inside the distro (required for service units)
wsl -d $DistroName -u root bash -c "grep -q 'systemd=true' /etc/wsl.conf 2>/dev/null || printf '[boot]\nsystemd=true\n' >> /etc/wsl.conf"
Write-OK "systemd enabled in /etc/wsl.conf"

# ── Step 4/6: Firewall rules (prefix-tagged for clean teardown) ──────────────
Write-Step "4/6 Creating firewall rules ($FwPrefix-*)..."
$rules = @(
    @{Name="$FwPrefix-ssh";          Port=22  },
    @{Name="$FwPrefix-llama-server"; Port=8080},
    @{Name="$FwPrefix-node-exporter";Port=9100},
    @{Name="$FwPrefix-nvidia-exp";   Port=9835}
)
foreach ($r in $rules) {
    if (-not (Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Protocol TCP `
            -LocalPort $r.Port -Action Allow -Profile Private | Out-Null
        Write-OK "Rule $($r.Name) (tcp/$($r.Port))"
    } else {
        Write-OK "Rule $($r.Name) exists"
    }
}

# ── Step 5/6: Restart WSL to apply config, then provision ────────────────────
Write-Step "5/6 Restarting WSL and running provision-node5090.sh..."
wsl --shutdown
Start-Sleep -Seconds 3
$provision = "\\wsl.localhost\$DistroName\tmp\provision-node5090.sh"
$srcSh = Join-Path $PSScriptRoot "provision-node5090.sh"
if (-not (Test-Path $srcSh)) { throw "provision-node5090.sh not found next to this script." }
# Copy via temp (avoids CRLF issues: dos2unix applied inside)
Copy-Item $srcSh $provision -Force
wsl -d $DistroName -u root bash -c "sed -i 's/\r$//' /tmp/provision-node5090.sh && chmod +x /tmp/provision-node5090.sh && /tmp/provision-node5090.sh 2>&1 | tee /var/log/provision-node5090.log"
if ($LASTEXITCODE -ne 0) { throw "Provision script failed — see /var/log/provision-node5090.log inside WSL." }
Write-OK "Provision complete"

# ── Step 6/6: Manual checklist ───────────────────────────────────────────────
Write-Step "6/6 Done. Manual steps remaining (external to this machine):"
Write-Host @"
   [ ] pfSense: static DHCP map this NIC's MAC -> 192.168.1.55
   [ ] pfSense DNS host overrides: node5090.home.arpa + 5090.home.arpa -> 192.168.1.55
       (Write Access Protocol: enable write, change, re-enable read-only, log in CHANGELOG)
   [ ] LUCIFER Prometheus: add node5090.home.arpa:9100, :9835, :8080/metrics scrape targets
   [ ] Verify from LUCIFER:  ssh lse-admin@node5090.home.arpa 'nvidia-smi | head -5'
   [ ] Verify model serving: curl -s http://node5090.home.arpa:8080/health
   [ ] KB entry: /opt/local-se/kb/node5090-llama-launch.md after first successful launch
"@ -ForegroundColor Yellow
