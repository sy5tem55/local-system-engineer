# run-session-start.ps1
# One-click session start: runs pending-challenge check + Samsung TV DHCP investigation
# Right-click -> Run with PowerShell   (or: powershell -File run-session-start.ps1)

$root = $PSScriptRoot

Write-Host "`n=== Step 1: Pending challenge candidates ===" -ForegroundColor Cyan
$pendingOut = "$root\challenge-pending-output.txt"
$pending = wsl bash -c "cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer && python3 scripts/challenge_generator.py --list-pending 2>&1"
$pending | Out-File -FilePath $pendingOut -Encoding utf8
$pending
Write-Host "`nSaved to: $pendingOut" -ForegroundColor Green

Write-Host "`n=== Step 2: Samsung TV DHCP hammer investigation ===" -ForegroundColor Cyan
wsl bash -c "cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer && python3 scripts/samsung_tv_dhcp_investigation.py 2>&1"

Write-Host "`n=== Done — Claude can now read both output files ===" -ForegroundColor Green
Write-Host "  challenge-pending-output.txt"
Write-Host "  samsung-tv-dhcp-report.txt"
Read-Host "`nPress Enter to close"
