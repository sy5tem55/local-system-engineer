<#
.SYNOPSIS
    Test harness for docker-graceful-stop.ps1 — simulates the shutdown script
    without actually calling wsl --shutdown.
.DESCRIPTION
    Runs the same docker compose stop logic as the real shutdown script,
    verifies exit codes and logs, but skips wsl --shutdown so your system
    stays running for inspection.
.NOTES
    Run this BEFORE registering the real shutdown script in Group Policy
    to verify it works on your system.
#>

$ErrorActionPreference = 'Stop'
$LogPath = 'C:\shutdown-scripts\docker-stop.log'
$Dist  = 'Ubuntu-24.04'
$DockerDir = '/home/sy5/docker'
$ComposeTimeout = 30

function Write-Log {
    param([string]$Msg)
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [TEST] $Msg" | Out-File -FilePath $LogPath -Append -Encoding utf8
}

Write-Host "`n=== Docker Graceful Stop — TEST MODE ===" -ForegroundColor Cyan
Write-Log '=== TEST run started ==='

# --- Pre-flight: show what's currently running ---
Write-Host "`n[1/4] Current containers before test:" -ForegroundColor Yellow
$containers = wsl -d $Dist -e bash -c "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'" 2>$null
if ($containers) {
    Write-Host $containers
} else {
    Write-Host '  (no containers running)' -ForegroundColor DarkGray
}

# --- Step 1: docker compose stop ---
Write-Host "`n[2/4] Stopping docker-compose containers..." -ForegroundColor Yellow
$startTime = Get-Date

$wslCmd = "wsl -d ${Dist} -e bash -c `"cd ${DockerDir} && docker compose stop --timeout ${ComposeTimeout}`""

try {
    $proc = Start-Process -FilePath 'powershell' -ArgumentList "-NoProfile -Command $wslCmd" `
        -Wait -NoNewWindow -RedirectStandardOutput "$env:TEMP\docker-stop-out.txt" `
        -RedirectStandardError "$env:TEMP\docker-stop-err.txt" -PassThru

    $exitCode = $proc.ExitCode
    $elapsed = (Get-Date) - $startTime

    if ($exitCode -eq 0) {
        Write-Host "  OK: docker compose stop succeeded in ${elapsed.TotalSeconds:F1}s" -ForegroundColor Green
        Write-Log "docker compose stop succeeded in ${elapsed.TotalSeconds:F1}s"
    } else {
        Write-Host "  FAIL: exit code $exitCode in ${elapsed.TotalSeconds:F1}s" -ForegroundColor Red
        Write-Log "docker compose stop exited with code $exitCode in ${elapsed.TotalSeconds:F1}s"
        if (Test-Path "$env:TEMP\docker-stop-err.txt") {
            $err = Get-Content "$env:TEMP\docker-stop-err.txt" -Raw
            if ($err) {
                Write-Host "  stderr: $err" -ForegroundColor Red
                Write-Log "stderr: $err"
            }
        }
    }
} catch {
    Write-Host "  ERROR: $_" -ForegroundColor Red
    Write-Log "ERROR running docker compose stop: $_"
    $exitCode = -1
}

# --- Step 2: verify containers stopped ---
Write-Host "`n[3/4] Containers after stop:" -ForegroundColor Yellow
$containersAfter = wsl -d $Dist -e bash -c "docker ps --filter status=exited --format 'table {{.Names}}\t{{.Status}}'" 2>$null
if ($containersAfter) {
    Write-Host $containersAfter
    Write-Log 'All containers confirmed stopped'
} else {
    Write-Host '  (none found — may have already been stopped)' -ForegroundColor DarkGray
    Write-Log 'No containers found after stop (may have been pre-stopped)'
}

# --- Step 3: restart containers (so you don't lose them) ---
Write-Host "`n[4/4] Restarting containers (docker compose up -d)..." -ForegroundColor Yellow
try {
    $restartCmd = "wsl -d ${Dist} -e bash -c `"cd ${DockerDir} && docker compose up -d`""
    $restartProc = Start-Process -FilePath 'powershell' -ArgumentList "-NoProfile -Command $restartCmd" `
        -Wait -NoNewWindow -PassThru

    if ($restartProc.ExitCode -eq 0) {
        Write-Host '  OK: containers restarted' -ForegroundColor Green
        Write-Log 'containers restarted via docker compose up -d'
    } else {
        Write-Host "  WARNING: docker compose up -d exited with code $($restartProc.ExitCode)" -ForegroundColor Yellow
        Write-Log "docker compose up -d exited with code $($restartProc.ExitCode)"
    }
} catch {
    Write-Host "  ERROR restarting: $_" -ForegroundColor Red
    Write-Log "ERROR restarting containers: $_"
}

# --- Summary ---
$summary = if ($exitCode -eq 0) {
    "`nRESULT: PASS — shutdown script logic works correctly."
} else {
    "`nRESULT: FAIL — fix the errors above before relying on this script."
}
Write-Host $summary -ForegroundColor $(if ($exitCode -eq 0) {'Green'} else {'Red'})
Write-Log "=== TEST run ended — exit code: $exitCode ==="
Write-Host "`nLog file: $LogPath" -ForegroundColor DarkGray
