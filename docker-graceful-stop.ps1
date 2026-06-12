<#
.SYNOPSIS
    Graceful Docker shutdown script for Windows Group Policy shutdown events.
    Stops all docker-compose containers, then shuts down WSL2 cleanly.
.DESCRIPTION
    Registered as a Machine shutdown script via:
      Computer Configuration -> Windows Settings -> Scripts (Startup/Shutdown) -> Shutdown
    Runs as SYSTEM during shutdown. Total execution must complete within ~60 seconds
    or Windows will forcibly terminate it.
.NOTES
    Idempotent — safe to run if Docker is already stopped.
    Requires: Windows 11 Pro, WSL2 Ubuntu-24.04, Docker Desktop with WSL2 backend.
#>

$ErrorActionPreference = 'Stop'
$LogPath = 'C:\shutdown-scripts\docker-stop.log'
$Dist  = 'Ubuntu-24.04'
$DockerDir = '/home/sy5/docker'
$ComposeTimeout = 30  # seconds for docker compose stop
$Deadline = (Get-Date).AddSeconds(55)  # leave 5s margin before Windows kills us

function Write-Log {
    param([string]$Msg)
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Msg" | Out-File -FilePath $LogPath -Append -Encoding utf8
}

Write-Log '=== Shutdown script started ==='

# Step 1: Stop all docker-compose containers gracefully
Write-Log "Stopping docker-compose containers (timeout=${ComposeTimeout}s)..."
$startTime = Get-Date

$wslCmd = "wsl -d ${Dist} -e bash -c `"cd ${DockerDir} && docker compose stop --timeout ${ComposeTimeout}`""

try {
    $proc = Start-Process -FilePath 'powershell' -ArgumentList "-NoProfile -Command $wslCmd" `
        -Wait -NoNewWindow -RedirectStandardOutput "$env:TEMP\docker-stop-out.txt" `
        -RedirectStandardError "$env:TEMP\docker-stop-err.txt" -PassThru

    $exitCode = $proc.ExitCode
    $elapsed = (Get-Date) - $startTime

    if ($exitCode -eq 0) {
        Write-Log "docker compose stop succeeded in ${elapsed.TotalSeconds:F1}s"
    } else {
        Write-Log "docker compose stop exited with code $exitCode in ${elapsed.TotalSeconds:F1}s"
        if (Test-Path "$env:TEMP\docker-stop-err.txt") {
            $err = Get-Content "$env:TEMP\docker-stop-err.txt" -Raw
            if ($err) { Write-Log "stderr: $err" }
        }
    }
} catch {
    Write-Log "ERROR running docker compose stop: $_"
}

# Check deadline — if we're running out of time, skip wsl --shutdown
if ((Get-Date) -gt $Deadline) {
    Write-Log 'TIMEOUT: deadline exceeded, skipping wsl --shutdown'
    Write-Log '=== Shutdown script ended (timeout) ==='
    exit 0
}

# Step 2: Shut down WSL2 cleanly (flushes overlay2, releases disks)
Write-Log 'Running wsl --shutdown...'
try {
    $shutdownProc = Start-Process -FilePath 'wsl' -ArgumentList '--shutdown' -Wait -NoNewWindow -PassThru
    Write-Log "wsl --shutdown exited with code $($shutdownProc.ExitCode)"
} catch {
    Write-Log "ERROR running wsl --shutdown: $_"
}

Write-Log '=== Shutdown script ended ==='
