#Requires -Version 5.1
<#
.SYNOPSIS
    LSE Stack Launcher — opens Windows Terminal with all services in dedicated tabs.
.DESCRIPTION
    Loads model profiles from lse-profiles.xml (same directory as this script),
    then opens Windows Terminal with five colour-coded tabs: model server, Open WebUI,
    Playwright browser server, Open Terminal, and an LSE terminal.

    To add or modify a profile, edit lse-profiles.xml — no changes to this script needed.
.NOTES
    Requirements : Windows Terminal (wt.exe in PATH), WSL2 Ubuntu 24.04
    Run as       : sy5 — no administrator required
    Profiles     : lse-profiles.xml  (must be in the same folder as this script)
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Fixed paths (edit if your install locations change) ───────────────────────

$LaunchDir     = '/home/sy5/.lse/launch'
$SecretsFile   = '/home/sy5/.lse/secrets'   # chmod 600 — contains: export BW_PASSWORD='...'
$LlamaBin      = '/home/sy5/llama.cpp/build/bin/llama-server'
$OwuiEnv       = '/home/sy5/owui/bin/activate'
$PlaywrightDir = '/home/sy5/owui/bin'

# ── Reasoning budget message ───────────────────────────────────────────────────
#
#   Injected as --reasoning-budget-message when a profile has ReasoningBudget > 0.
#   Tells the model to wrap up gracefully when the thinking budget is exhausted,
#   rather than hard-stopping mid-thought.

$ReasoningBudgetMsg = 'Reasoning budget reached. Wrap up your thinking and provide your best answer now.'

# ── Load profiles from XML ─────────────────────────────────────────────────────

$ProfilesXml = Join-Path $PSScriptRoot 'lse-profiles.xml'
if (-not (Test-Path $ProfilesXml)) {
    Write-Host ""
    Write-Host "  [ERROR] Profile file not found: $ProfilesXml" -ForegroundColor Red
    Write-Host "  Expected lse-profiles.xml in the same folder as this script."
    Write-Host ""
    exit 1
}

try {
    $xml          = [xml](Get-Content $ProfilesXml -Encoding UTF8)
    $ProfileNodes = @($xml.profiles.profile)
    $ProfileKeys  = @($ProfileNodes | ForEach-Object { $_.name })
} catch {
    Write-Host ""
    Write-Host "  [ERROR] Failed to parse $ProfilesXml : $_" -ForegroundColor Red
    Write-Host ""
    exit 1
}

if ($ProfileNodes.Count -eq 0) {
    Write-Host ""
    Write-Host "  [ERROR] No profiles found in $ProfilesXml" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# ── Console banner ────────────────────────────────────────────────────────────

Clear-Host
$r = "`e[0m"; $c = "`e[96m"; $y = "`e[93m"; $g = "`e[92m"

Write-Host ""
Write-Host "  ${c}╔══════════════════════════════════════════════════════╗${r}"
Write-Host "  ${c}║                                                      ║${r}"
Write-Host "  ${c}║   ██╗     ███████╗███████╗   ███████╗████████╗       ║${r}"
Write-Host "  ${c}║   ██║     ██╔════╝██╔════╝   ██╔════╝╚══██╔══╝       ║${r}"
Write-Host "  ${c}║   ██║     ███████╗█████╗     ███████╗   ██║          ║${r}"
Write-Host "  ${c}║   ██║     ╚════██║██╔══╝     ╚════██║   ██║          ║${r}"
Write-Host "  ${c}║   ███████╗███████║███████╗   ███████║   ██║          ║${r}"
Write-Host "  ${c}║   ╚══════╝╚══════╝╚══════╝   ╚══════╝   ╚═╝          ║${r}"
Write-Host "  ${c}║                                                      ║${r}"
Write-Host "  ${c}║              Stack Launcher  v1.077                  ║${r}"
Write-Host "  ${c}╚══════════════════════════════════════════════════════╝${r}"
Write-Host ""

# ── Profile selection ─────────────────────────────────────────────────────────

if ($ProfileKeys.Count -eq 1) {
    $Prof = $ProfileNodes[0]
    Write-Host "  ${g}Profile :${r}  $($ProfileKeys[0])"
    Write-Host ""
} else {
    Write-Host "  ${y}Select a model profile:${r}"
    Write-Host ""
    for ($i = 0; $i -lt $ProfileKeys.Count; $i++) {
        $arrow = if ($i -eq 0) { "${g}►${r}" } else { " " }
        Write-Host "  $arrow ${c}[$($i + 1)]${r}  $($ProfileKeys[$i])"
    }
    Write-Host ""
    do {
        $raw = Read-Host "  Profile [1-$($ProfileKeys.Count), Enter = 1]"
        if ([string]::IsNullOrWhiteSpace($raw)) { $raw = '1' }
        $idx = 0
        $valid = [int]::TryParse($raw, [ref]$idx) -and $idx -ge 1 -and $idx -le $ProfileKeys.Count
    } while (-not $valid)
    $Prof = $ProfileNodes[$idx - 1]
    Write-Host ""
    Write-Host "  ${g}Profile :${r}  $($ProfileKeys[$idx - 1])"
    Write-Host ""
}

# ── Build llama-server command from the selected profile ──────────────────────

$ModelPath = "/home/sy5/models/$($Prof.ModelFile)"

$CmdLines = [System.Collections.Generic.List[string]]::new()
$CmdLines.Add("$LlamaBin \")
$CmdLines.Add("  --model $ModelPath \")
$CmdLines.Add("  --ctx-size $($Prof.CtxSize) \")
$CmdLines.Add("  --n-gpu-layers $($Prof.GpuLayers) \")
if ($Prof.FlashAttn -eq 'true')        { $CmdLines.Add("  --flash-attn on \") }
$CmdLines.Add("  --cache-type-k $($Prof.CacheTypeK) \")
$CmdLines.Add("  --cache-type-v $($Prof.CacheTypeV) \")
$CmdLines.Add("  --parallel $($Prof.Parallel) \")
$CmdLines.Add("  --jinja \")
$CmdLines.Add("  --threads $($Prof.Threads) \")

# threads-batch: use profile value if set, otherwise fall back to Threads
$tb = if ($Prof.ThreadsBatch) { $Prof.ThreadsBatch } else { $Prof.Threads }
$CmdLines.Add("  --threads-batch $tb \")

if ($Prof.BatchSize)                   { $CmdLines.Add("  --batch-size $($Prof.BatchSize) \") }
if ($Prof.UBatchSize)                  { $CmdLines.Add("  --ubatch-size $($Prof.UBatchSize) \") }
if ($Prof.OverrideTensor)              { $CmdLines.Add("  --override-tensor `"$($Prof.OverrideTensor)`" \") }

# reasoning-budget + message (message only injected when budget is active and > 0)
if ($Prof.ReasoningBudget -and $Prof.ReasoningBudget -ne '0') {
    $CmdLines.Add("  --reasoning-budget $($Prof.ReasoningBudget) \")
    $CmdLines.Add("  --reasoning-budget-message `"$ReasoningBudgetMsg`" \")
} elseif ($Prof.ReasoningBudget -eq '0') {
    $CmdLines.Add("  --reasoning-budget 0 \")
}

if ($Prof.MaxPredictTokens)            { $CmdLines.Add("  -n $($Prof.MaxPredictTokens) \") }
if ($Prof.SpecType)                    { $CmdLines.Add("  --spec-type $($Prof.SpecType) \") }
if ($Prof.SpecDraftNMax)               { $CmdLines.Add("  --spec-draft-n-max $($Prof.SpecDraftNMax) \") }
if ($Prof.NoMmproj -eq 'true')         { $CmdLines.Add("  --no-mmproj \") }
$CmdLines.Add("  --host 0.0.0.0 \")
$CmdLines.Add("  --port 8080 \")
$CmdLines.Add("  --metrics")
$LlamaCmd = $CmdLines -join "`n"

# Banner lines are padded to 41 chars to fill the fixed-width box (║   {41 chars}║)
$L1 = $Prof.BannerLine1.PadRight(41)
$L2 = $Prof.BannerLine2.PadRight(41)

# ── Bash launch scripts (written to WSL on every run) ─────────────────────────
#
#   Each script: prints a colour banner, runs the service, then drops to bash
#   if the service exits so the tab stays open for diagnostics.

# ── Secrets pre-flight ───────────────────────────────────────────────────────
#   BW_PASSWORD must live in ~/.lse/secrets (chmod 600), not in OpenWebUI valves.
#   First-time setup (run once in WSL):
#     mkdir -p ~/.lse && echo "export BW_PASSWORD='pw'" > ~/.lse/secrets && chmod 600 ~/.lse/secrets
$secretsOk = wsl -e bash -c "[ -f '$SecretsFile' ] && grep -q 'BW_PASSWORD' '$SecretsFile' && echo ok" 2>$null
if ($secretsOk -ne 'ok') {
    Write-Host "  ${y}⚠  SECRETS FILE MISSING: $SecretsFile${r}" -ForegroundColor Yellow
    Write-Host "  ${y}   Vaultwarden tool will not authenticate. Create the file first.${r}" -ForegroundColor Yellow
    Write-Host ""
    $cont = Read-Host "  Continue anyway? [y/N]"
    if ($cont -ne 'y' -and $cont -ne 'Y') { exit 1 }
} else {
    Write-Host "  ${g}✓${r}  Secrets file OK"
}
Write-Host ""

Write-Host "  ${y}Writing launch scripts to WSL...${r}"
Write-Host ""

$Scripts = [ordered]@{

'model.sh' = @"
#!/usr/bin/env bash
printf '\033[1;31m\n'
printf '  ╔════════════════════════════════════════════╗\n'
printf '  ║   $L1║\n'
printf '  ║   $L2║\n'
printf '  ╚════════════════════════════════════════════╝\n'
printf '\033[0m\n'
$LlamaCmd
EXIT_CODE=`$?
printf '\n\033[1;33m  Server stopped (exit %d). Type exit to close tab.\033[0m\n' "`$EXIT_CODE"
exec bash
"@

'webui.sh' = @"
#!/usr/bin/env bash
printf '\033[1;34m\n'
printf '  ╔════════════════════════════════════════════╗\n'
printf '  ║   Open WebUI  →  localhost:3000            ║\n'
printf '  ║   Backend     →  localhost:8080 (llama.cpp)║\n'
printf '  ╚════════════════════════════════════════════╝\n'
printf '\033[0m\n'
# Load secrets (BW_PASSWORD etc.) — never stored in OpenWebUI valves
[ -f ~/.lse/secrets ] && source ~/.lse/secrets || printf '\033[1;33m  WARN: ~/.lse/secrets not found — Vaultwarden auth will fail\033[0m\n'
source $OwuiEnv
OPENAI_API_BASE_URL=http://localhost:8080/v1 \
OPENAI_API_KEY=none \
open-webui serve --port 3000
EXIT_CODE=`$?
printf '\n\033[1;33m  WebUI stopped (exit %d). Type exit to close tab.\033[0m\n' "`$EXIT_CODE"
exec bash
"@

'playwright.sh' = @"
#!/usr/bin/env bash
printf '\033[1;35m\n'
printf '  ╔═══════════════════════════════════════════╗\n'
printf '  ║   Playwright browser server               ║\n'
printf '  ║   Run server  →  localhost:3001           ║\n'
printf '  ╚═══════════════════════════════════════════╝\n'
printf '\033[0m\n'
source $OwuiEnv
cd $PlaywrightDir
playwright run-server --port 3001
EXIT_CODE=`$?
printf '\n\033[1;33m  Playwright stopped (exit %d). Type exit to close tab.\033[0m\n' "`$EXIT_CODE"
exec bash
"@

'open-terminal.sh' = @"
#!/usr/bin/env bash
printf '\033[1;33m\n'
printf '  ╔═══════════════════════════════════════════╗\n'
printf '  ║   Open Terminal                           ║\n'
printf '  ╚═══════════════════════════════════════════╝\n'
printf '\033[0m\n'
/home/sy5/.local/bin/open-terminal run
EXIT_CODE=`$?
printf '\n\033[1;33m  Open Terminal stopped (exit %d). Type exit to close tab.\033[0m\n' "`$EXIT_CODE"
exec bash
"@

'terminal.sh' = @"
#!/usr/bin/env bash
printf '\033[1;32m\n'
printf '  ╔═══════════════════════════════════════════╗\n'
printf '  ║   LSE Terminal  ·  LUCIFER                ║\n'
printf '  ║   Ubuntu 24.04  ·  WSL2                   ║\n'
printf '  ╚═══════════════════════════════════════════╝\n'
printf '\033[0m\n'
bash -l
"@

}

# Write each script to WSL, make executable
foreach ($Name in $Scripts.Keys) {
    $Content = $Scripts[$Name]
    $WslPath = "$LaunchDir/$Name"
    $Content | wsl.exe -- bash -c "mkdir -p '$LaunchDir' && tr -d '\r' > '$WslPath' && chmod +x '$WslPath'"
    Write-Host "  ${g}✓${r}  $Name" -Foregrou