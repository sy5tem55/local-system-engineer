# WSL Gaming Teardown v1.0
# Brings down the entire LSE stack and WSL cleanly before gaming.
# Run from an elevated PowerShell prompt on LUCIFER.
# After this script completes, VRAM and system resources are fully released.

$ErrorActionPreference = "SilentlyContinue"

function Write-Step($msg) {
    Write-Host "`n>> $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "   OK: $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "   WARN: $msg" -ForegroundColor Yellow
}

# ── Step 1: Stop Docker containers (lse-net stack) ───────────────────────────
Write-Step "1/6 Stopping Docker containers..."
$dockerRunning = wsl -e bash -c "docker ps -q 2>/dev/null" 2>$null
if ($dockerRunning) {
    wsl -e bash -c "docker stop `$(docker ps -q) 2>/dev/null; docker ps -q | wc -l"
    Write-OK "Docker containers stopped"
} else {
    Write-Warn "No running containers or Docker not reachable"
}

# ── Step 2: Kill LSE processes inside WSL ────────────────────────────────────
Write-Step "2/6 Killing LSE processes inside WSL..."
$processesToKill = @(
    "llama-server",      # Inference engine — holds all VRAM
    "uvicorn",           # OpenWebUI
    "open-webui",        # OpenWebUI alternate name
    "grafana-owui",      # Grafana → OpenWebUI adapter
    "llamacpp-slots",    # Slots exporter
    "llama-context",     # Context exporter
    "download-speed",    # Network speed exporter
    "searxng-logger",    # Logger script
    "prometheus",        # Prometheus (if not in Docker)
    "grafana-server"     # Grafana (if not in Docker)
)

foreach ($proc in $processesToKill) {
    $killed = wsl -e bash -c "pkill -f '$proc' 2>/dev/null; echo `$?" 2>$null
    if ($killed -eq "0") {
        Write-OK "Killed: $proc"
    }
}

# Give processes a moment to die cleanly
Start-Sleep -Seconds 2

# Force-kill anything still holding the llama-server port
wsl -e bash -c "fuser -k 8080/tcp 2>/dev/null; fuser -k 3000/tcp 2>/dev/null; fuser -k 3001/tcp 2>/dev/null" 2>$null
Write-OK "Freed ports 8080, 3000, 3001"

# ── Step 3: Stop Ollama (holds GPU memory for embeddings) ────────────────────
Write-Step "3/6 Stopping Ollama..."
wsl -e bash -c "systemctl --user stop ollama 2>/dev/null; pkill -f ollama 2>/dev/null" 2>$null
Write-OK "Ollama stopped"

# ── Step 4: wsl --shutdown ────────────────────────────────────────────────────
Write-Step "4/6 Shutting down WSL2..."
wsl --shutdown
Start-Sleep -Seconds 3

# Verify WSL is down
$wslStatus = wsl --list --running 2>&1
if ($wslStatus -match "no.*running" -or $wslStatus -eq "" -or $wslStatus -match "There are no") {
    Write-OK "WSL2 fully shut down"
} else {
    Write-Warn "WSL may still be running: $wslStatus"
}

# ── Step 5: Kill remaining Windows-side WSL-related processes ────────────────
Write-Step "5/6 Cleaning up Windows-side processes..."
$windowsProcs = @(
    "wslhost",
    "wsl",
    "vmmem"         # WSL2 VM memory process — confirms teardown
)

foreach ($proc in $windowsProcs) {
    $found = Get-Process -Name $proc -ErrorAction SilentlyContinue
    if ($found) {
        Stop-Process -Name $proc -Force -ErrorAction SilentlyContinue
        Write-OK "Stopped Windows process: $proc"
    }
}

# ── Step 6: VRAM verification ─────────────────────────────────────────────────
Write-Step "6/6 Verifying GPU VRAM released..."
$nvidiaSmi = & "C:\Windows\System32\nvidia-smi.exe" --query-gpu=memory.used,memory.free,memory.total --format=csv,noheader,nounits 2>$null
if ($nvidiaSmi) {
    $parts    = $nvidiaSmi.Trim() -split ",\s*"
    $used     = [int]$parts[0]
    $free     = [int]$parts[1]
    $total    = [int]$parts[2]
    $usedPct  = [math]::Round($used / $total * 100, 1)
    Write-Host "   VRAM: ${used} MB used / ${total} MB total (${usedPct}% in use)" -ForegroundColor $(if ($usedPct -lt 10) { "Green" } else { "Yellow" })
    if ($usedPct -gt 15) {
        Write-Warn "VRAM usage above 15% — a process may still be holding memory. Check Task Manager → GPU."
    } else {
        Write-OK "VRAM clear — ready for gaming"
    }
} else {
    Write-Warn "nvidia-smi not found at default path — check VRAM manually"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host " LSE stack is down. System is gaming-ready." -ForegroundColor White
Write-Host " To restart the LSE stack: run lse-stack-launch-1.073.ps1" -ForegroundColor DarkGray
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
