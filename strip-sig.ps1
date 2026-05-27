<#
.SYNOPSIS
    Strips the Authenticode SIG block from one or more PowerShell scripts.
.DESCRIPTION
    PowerShell Authenticode signatures are appended as a comment block at the end
    of .ps1 files. Any edit to the file after signing invalidates the signature,
    and the Edit tool used by Cowork/Claude corrupts the final line of the script
    body when a SIG block is present.

    Run strip-sig.ps1 BEFORE making any edits to a signed .ps1 file. After all
    edits are complete, re-sign with certsign.ps1.

    Workflow for a new launcher version:
        1. Copy-Item lse-stack-launch-1.066.ps1 lse-stack-launch-1.067.ps1
        2. .\strip-sig.ps1 -Target lse-stack-launch-1.067.ps1
        3. <make edits>
        4. .\certsign.ps1 -Target lse-stack-launch-1.067.ps1
        5. git add + commit

.PARAMETER Target
    Path to the .ps1 file to strip. Accepts wildcards, e.g. .\strip-sig.ps1 -Target *.ps1
.EXAMPLE
    .\strip-sig.ps1 -Target lse-stack-launch-1.067.ps1
.EXAMPLE
    .\strip-sig.ps1 -Target lse-stack-launch-1.066.ps1, lse-stack-launch-1.065.ps1
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory, ValueFromPipeline, ValueFromPipelineByPropertyName)]
    [string[]]$Target
)

process {
    foreach ($Path in $Target) {
        $Resolved = Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue
        if (-not $Resolved) {
            Write-Warning "Not found: $Path"
            continue
        }

        $Lines = Get-Content -LiteralPath $Resolved.FullName -Encoding UTF8

        # Find the SIG block start (line number is 1-based from Select-String)
        $SigMatch = $Lines | Select-String -Pattern '^# SIG # Begin signature block'
        if (-not $SigMatch) {
            Write-Host "  [SKIP] No SIG block found in $($Resolved.Name)"
            continue
        }

        # LineNumber from Select-String is 1-based; convert to 0-based index
        $SigIdx = $SigMatch.LineNumber - 1

        # Keep everything before the SIG block; trim any trailing blank lines
        $Clean = $Lines[0..($SigIdx - 1)]
        while ($Clean.Count -gt 0 -and [string]::IsNullOrWhiteSpace($Clean[-1])) {
            $Clean = $Clean[0..($Clean.Count - 2)]
        }
        # Restore exactly one trailing newline (Set-Content adds its own)
        $Clean += ''

        if ($PSCmdlet.ShouldProcess($Resolved.FullName, 'Strip SIG block')) {
            $Clean | Set-Content -LiteralPath $Resolved.FullName -Encoding UTF8
            Write-Host "  [OK]  SIG block stripped from $($Resolved.Name)  ($SigIdx lines kept)"
        }
    }
}
