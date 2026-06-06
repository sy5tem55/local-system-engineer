# run-pending-challenges.ps1
# Dumps pending challenge candidates to challenge-pending-output.txt
# Run from Windows: right-click -> Run with PowerShell, or from any terminal

$outFile = "$PSScriptRoot\challenge-pending-output.txt"

Write-Host "Running challenge_generator --list-pending via WSL2..."
$result = wsl bash -c "cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer && python3 scripts/challenge_generator.py --list-pending 2>&1"

if ($LASTEXITCODE -eq 0 -or $result) {
    $result | Out-File -FilePath $outFile -Encoding utf8
    Write-Host "Output written to: $outFile"
    $result
} else {
    "ERROR: WSL2 command failed (exit $LASTEXITCODE)" | Out-File -FilePath $outFile -Encoding utf8
    Write-Host "Failed. Check $outFile"
}

Write-Host "`nDone. Claude can now read challenge-pending-output.txt."
