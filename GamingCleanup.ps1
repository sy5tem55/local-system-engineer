<#
Minimal Gaming Cleanup Script
Optimized for:
- WSL2
- llama.cpp launched manually
- CUDA workloads
- No Docker Desktop
- No Ollama

Recommended:
Run before gaming sessions.
#>

Write-Host ""
Write-Host "==========================================" -ForegroundColor DarkGray
Write-Host " GAMING MODE CLEANUP" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor DarkGray
Write-Host ""

# -----------------------------
# Shutdown WSL
# -----------------------------

Write-Host "[1/4] Shutting down WSL..." -ForegroundColor Yellow

try {
    wsl --shutdown
    Write-Host "WSL shutdown complete." -ForegroundColor Green
}
catch {
    Write-Host "Failed to shutdown WSL." -ForegroundColor Red
}

Start-Sleep -Seconds 3

# -----------------------------
# Kill lingering llama.cpp
# -----------------------------

Write-Host ""
Write-Host "[2/4] Checking for llama.cpp processes..." -ForegroundColor Yellow

$processes = @(
    "llama-server",
    "llama-cli",
    "llama-batched",
    "main"
)

$found = $false

foreach ($proc in $processes) {

    Get-Process -Name $proc -ErrorAction SilentlyContinue | ForEach-Object {

        $found = $true

        try {
            Stop-Process -Id $_.Id -Force
            Write-Host "Stopped: $($_.ProcessName)" -ForegroundColor Green
        }
        catch {
            Write-Host "Failed to stop: $($_.ProcessName)" -ForegroundColor Red
        }
    }
}

if (-not $found) {
    Write-Host "No lingering llama.cpp processes found." -ForegroundColor Green
}

# -----------------------------
# Verify vmmemWSL
# -----------------------------

Write-Host ""
Write-Host "[3/4] Checking WSL VM status..." -ForegroundColor Yellow

$vmmem = Get-Process -Name "vmmemWSL" -ErrorAction SilentlyContinue

if ($vmmem) {
    Write-Host "WARNING: vmmemWSL is still active." -ForegroundColor Yellow
}
else {
    Write-Host "vmmemWSL fully stopped." -ForegroundColor Green
}

# -----------------------------
# GPU Status
# -----------------------------

Write-Host ""
Write-Host "[4/4] NVIDIA GPU status:" -ForegroundColor Yellow
Write-Host ""

try {
    nvidia-smi
}
catch {
    Write-Host "nvidia-smi not available." -ForegroundColor Red
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor DarkGray
Write-Host " SYSTEM READY FOR GAMING" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor DarkGray