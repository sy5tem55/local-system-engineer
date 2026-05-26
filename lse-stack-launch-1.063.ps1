#Requires -Version 5.1
<#
.SYNOPSIS
    LSE Stack Launcher — opens Windows Terminal with all services in dedicated tabs.
.DESCRIPTION
    Writes per-service bash launch scripts to WSL (/home/sy5/.lse/launch/), then opens
    Windows Terminal with five colour-coded tabs: model server, Open WebUI,
    Playwright browser server, Open Terminal, and an LSE terminal.

    A profile menu is shown at launch. Add a new entry to $ModelProfiles to add a
    model or parameter set — no other changes needed.
.NOTES
    Requirements : Windows Terminal (wt.exe in PATH), WSL2 Ubuntu 24.04
    Run as       : sy5 — no administrator required
    First run    : scripts are written to WSL; subsequent runs reuse them
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Fixed paths (edit if your install locations change) ───────────────────────

$LaunchDir     = '/home/sy5/.lse/launch'
$LlamaBin      = '/home/sy5/llama.cpp/build/bin/llama-server'
$OwuiEnv       = '/home/sy5/owui/bin/activate'
$PlaywrightDir = '/home/sy5/owui/bin'

# ── Model profiles ─────────────────────────────────────────────────────────────
#
#   To add a new model or parameter set, copy any block and edit the values.
#   The launcher shows a numbered menu; press Enter to accept the default (first entry).
#
#   Key reference:
#     ModelFile       — filename inside /home/sy5/models/
#     CtxSize         — KV cache size in tokens
#                         32768 → fits cleanly in VRAM (~22 GB total on RTX 4090)
#                         65536 → needs ~2 GB CPU KV spillover at tail end
#     GpuLayers       — 99 = full GPU offload (all layers on VRAM)
#     FlashAttn       — $true/$false  fused attention; cuts VRAM 30–50% during attn
#     CacheTypeK      — K-tensor quant: 'f16' (default) | 'q8_0' (½ VRAM) | 'q4_0' (¼ VRAM)
#     CacheTypeV      — V-tensor quant: same options as CacheTypeK
#     Parallel        — concurrent slots; 1 = single-user (all KV budget to your session)
#     Threads         — CPU threads for prompt pre-fill (generation is GPU-bound)
#     ReasoningBudget — '3072' capped thinking (recommended; stops runaway <think> loops)
#                       '0'   suppress thinking (fastest, ~½ tokens per turn)
#                       ''    unlimited thinking (CAUTION: model never stops without -n cap)
#     MaxPredictTokens— server-side hard cap on tokens generated per request (-n flag).
#                       Applied before any OpenWebUI max_tokens setting. '8192' for thinking
#                       profiles (budget + response); '4096' for no-thinking profiles.
#     SpecType        — 'mtp' enables Multi-Token Prediction speculative decoding.
#                       Requires an MTP-GGUF (model with draft head weights included).
#                       Omit this key entirely for standard profiles.
#     SpecDraftNMax   — number of draft tokens for MTP (2–4; 3 is the recommended default).
#                       Omit if SpecType is not set.
#     TabLabel        — text shown in the Windows Terminal red tab (keep ≤ 20 chars)
#     BannerLine1     — first content line of the red-tab ASCII banner  (≤ 41 chars)
#     BannerLine2     — second content line of the red-tab ASCII banner (≤ 41 chars)

$ModelProfiles = [ordered]@{

    # ── MTP profiles (Multi-Token Prediction — ~1.7× faster generation) ──────
    #    draft-mtp works natively with the standard GGUF — Qwen3.6 architecture
    #    has MTP heads built in. No special MTP download required.
    #    Confirmed: ~70 tok/s on no-thinking profile (vs ~38 tok/s baseline).

    'Qwen3.6 27B · MTP  [32k · default]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8
        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        SpecType         = 'draft-mtp'
        SpecDraftNMax    = 3
        TabLabel         = '  QWEN 3.6 27B · MTP'
        BannerLine1      = 'QWEN 3.6 27B  ·  MTP'
        BannerLine2      = 'MTP · think: 3072  →  :8080'
    }

    'Qwen3.6 27B · MTP  [64k ctx]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 65536
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8
        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        SpecType         = 'draft-mtp'
        SpecDraftNMax    = 3
        TabLabel         = '  QWEN 3.6 27B · MTP 64k'
        BannerLine1      = 'QWEN 3.6 27B  ·  MTP'
        BannerLine2      = 'MTP · 64k · think: 3072  →  :8080'
    }

    'Qwen3.6 27B · MTP  [no thinking]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8
        ReasoningBudget  = '0'
        MaxPredictTokens = '4096'
        SpecType         = 'draft-mtp'
        SpecDraftNMax    = 3
        TabLabel         = '  QWEN 3.6 27B · MTP fast'
        BannerLine1      = 'QWEN 3.6 27B  ·  MTP'
        BannerLine2      = 'MTP · thinking off  →  :8080'
    }

    # ── Q4_K_M + MTP profiles (lower VRAM, slightly less precision, faster) ─────
    #    Q4_K_M: ~4.8 bits/weight vs Q5_K_M ~5.7 bits/weight. Difference is small
    #    for sysadmin tasks. Good option if VRAM headroom is tight.

    'Qwen3.6 27B · Q4_K_M + MTP  [32k]' = @{
        ModelFile        = 'Qwen_Qwen3.6-27B-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8
        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        SpecType         = 'draft-mtp'
        SpecDraftNMax    = 3
        TabLabel         = '  QWEN 3.6 27B · Q4+MTP'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q4_K_M + MTP'
        BannerLine2      = 'MTP · think: 3072  →  :8080'
    }

    'Qwen3.6 27B · Q4_K_M + MTP  [no thinking]' = @{
        ModelFile        = 'Qwen_Qwen3.6-27B-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8
        ReasoningBudget  = '0'
        MaxPredictTokens = '4096'
        SpecType         = 'draft-mtp'
        SpecDraftNMax    = 3
        TabLabel         = '  QWEN 3.6 27B · Q4+MTP fast'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q4_K_M + MTP'
        BannerLine2      = 'MTP · thinking off  →  :8080'
    }

    # ── Standard profiles (no MTP — stable baseline) ──────────────────────────

    'Qwen3.6 27B · Q5_K_M  [32k · default]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8
        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  QWEN 3.6 27B'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q5_K_M'
        BannerLine2      = 'think: 3072  →  localhost:8080'
    }

    'Qwen3.6 27B · Q5_K_M  [64k ctx]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 65536
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8
        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  QWEN 3.6 27B · 64k'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q5_K_M'
        BannerLine2      = '64k · think: 3072  →  :8080'
    }

    'Qwen3.6 27B · Q5_K_M  [no thinking]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8
        ReasoningBudget  = '0'
        MaxPredictTokens = '4096'
        TabLabel         = '  QWEN 3.6 27B · fast'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q5_K_M'
        BannerLine2      = 'thinking off  →  localhost:8080'
    }

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
Write-Host "  ${c}║              Stack Launcher  v1.062                   ║${r}"
Write-Host "  ${c}╚══════════════════════════════════════════════════════╝${r}"
Write-Host ""

# ── Profile selection ─────────────────────────────────────────────────────────

$ProfileKeys = @($ModelProfiles.Keys)

if ($ProfileKeys.Count -eq 1) {
    $Prof = $ModelProfiles[$ProfileKeys[0]]
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
    $Prof = $ModelProfiles[$ProfileKeys[$idx - 1]]
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
if ($Prof.FlashAttn)                  { $CmdLines.Add("  --flash-attn on \") }
$CmdLines.Add("  --cache-type-k $($Prof.CacheTypeK) \")
$CmdLines.Add("  --cache-type-v $($Prof.CacheTypeV) \")
$CmdLines.Add("  --parallel $($Prof.Parallel) \")
$CmdLines.Add("  --jinja \")
$CmdLines.Add("  --threads $($Prof.Threads) \")
if ($Prof.ReasoningBudget -ne '')     { $CmdLines.Add("  --reasoning-budget $($Prof.ReasoningBudget) \") }
if ($Prof.MaxPredictTokens -ne '')    { $CmdLines.Add("  -n $($Prof.MaxPredictTokens) \") }
if ($Prof.ContainsKey('SpecType') -and $Prof.SpecType)      { $CmdLines.Add("  --spec-type $($Prof.SpecType) \") }
if ($Prof.ContainsKey('SpecDraftNMax') -and $Prof.SpecDraftNMax) { $CmdLines.Add("  --spec-draft-n-max $($Prof.SpecDraftNMax) \") }
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
    Write-Host "  ${g}✓${r}  $Name" -ForegroundColor Green
}

Write-Host ""
Write-Host "  ${y}Opening Windows Terminal...${r}"
Write-Host ""

# ── Windows Terminal: five colour-coded tabs ───────────────────────────────
#
#   Tab colours (tab stripe only — terminal theme stays as your default):
#     Red    #CC2222  — model server (GPU-heavy, stands out)
#     Blue   #2255CC  — Open WebUI
#     Purple #8822CC  — Playwright
#     Orange #CC7722  — Open Terminal
#     Green  #229966  — LSE terminal

$WtArgs = (
    "new-tab --title `"$($Prof.TabLabel)`"   --tabColor `"#CC2222`" -- wsl.exe bash $LaunchDir/model.sh",
    "; new-tab --title `"  Open WebUI`"    --tabColor `"#2255CC`" -- wsl.exe bash $LaunchDir/webui.sh",
    "; new-tab --title `"  Playwright`"    --tabColor `"#8822CC`" -- wsl.exe bash $LaunchDir/playwright.sh",
    "; new-tab --title `"  Open Terminal`" --tabColor `"#CC7722`" -- wsl.exe bash $LaunchDir/open-terminal.sh",
    "; new-tab --title `"  LSE Terminal`"  --tabColor `"#229966`" -- wsl.exe bash $LaunchDir/terminal.sh"
) -join " "

Start-Process wt -ArgumentList $WtArgs

Write-Host "  ${g}All tabs launched.${r}"
Write-Host "  Model server takes ~30 s to load — watch the red tab."
Write-Host ""

# SIG # Begin signature block
# MIIFngYJKoZIhvcNAQcCoIIFjzCCBYsCAQExDzANBglghkgBZQMEAgEFADB5Bgor
# BgEEAYI3AgEEoGswaTA0BgorBgEEAYI3AgEeMCYCAwEAAAQQH8w7YFlLCE63JNLG
# KX7zUQIBAAIBAAIBAAIBAAIBADAxMA0GCWCGSAFlAwQCAQUABCDEa3C++I4JJqAZ
# 0R/+7c5XyqqC83cQQ5/dzXBXcohrAqCCAxgwggMUMIIB/KADAgECAhAnjvKeW2tW
# hkFhZBM0k1neMA0GCSqGSIb3DQEBCwUAMBYxFDASBgNVBAMMC1NZNVRFTTVDZXJ0
# MB4XDTI1MDkwNzEzMzcxNVoXDTI2MDkwNzEzNTcxNVowFjEUMBIGA1UEAwwLU1k1
# VEVNNUNlcnQwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDsHkeVknvs
# WeMMMCfE8Nn7Y2CcbQUFA3XCMQth4BgbQzp5UndUrwyBWS/QIXcejWWsU3JNY7EG
# S52t7rhdPLfNlK7rrTCpY2N0tDhhXf3Ghn4MyK3RcGx+NfkyOklc0VZS58iwcqda
# V1Ei0ITVSHD04i9OunyaJh9fPtMRDckUtfW/oYcDeQUd8V7QnpgZG1hKTKhkkBYU
# QjTcQQzx8h/E4J7FJq7xbx/cPMofsnZZJveh406M8gaYiFDvdWjSx/GjE0nPxFSL
# tYi+mg+I5kc+nc+uVJh4iuox4xG6F5OzNC5THvww3DS23BLNcgtauYG6yX/OJbXz
# EB4AOqU4uPY9AgMBAAGjXjBcMA4GA1UdDwEB/wQEAwIHgDATBgNVHSUEDDAKBggr
# BgEFBQcDAzAWBgNVHREEDzANggtTWTVURU01Q2VydDAdBgNVHQ4EFgQUdZz/MNsL
# SXt/c3LsJRy6mW9ocyQwDQYJKoZIhvcNAQELBQADggEBADY1Pv1GpfeZE48k29yB
# dibzGXLBM5CpH4ySpftbJ+PMTGfVejTGDJ1EI22/E5S1NXtbB8wyaiBvpt/O7Fw+
# DFpNJJ+DiCedeiRUa1OkoUOmBf1Yg3Btv7Z56t4yJqMlOAVZFvcvgH+Dfdabvo+m
# 3gFBzIQKKb5v88NjQ2VsjH/5LlA+MSQ9j7PbYCGOsdFgDOacPcE5sxzB2HJZ66aE
# nr1tN8Jb6EOT1bYrsPW8773GqR5IzgCUmuvwSYbki4KbqLYG6ZafNNYgoAAkAV3y
# dgj2eOPYlUZl+vrVZzyFNBtXyUj8eSi7Z1rosKXaYP1uzi6TH9liOGtrArGTL8rt
# EjUxggHcMIIB2AIBATAqMBYxFDASBgNVBAMMC1NZNVRFTTVDZXJ0AhAnjvKeW2tW
# hkFhZBM0k1neMA0GCWCGSAFlAwQCAQUAoIGEMBgGCisGAQQBgjcCAQwxCjAIoAKA
# AKECgAAwGQYJKoZIhvcNAQkDMQwGCisGAQQBgjcCAQQwHAYKKwYBBAGCNwIBCzEO
# MAwGCisGAQQBgjcCARUwLwYJKoZIhvcNAQkEMSIEIIiiZXAcYpNY/0PPt8jScinK
# spPcykcRYk4E7cwyltQvMA0GCSqGSIb3DQEBAQUABIIBAJU9NnkQMXkCCy1nLXVw
# ni9sLCLOwLeQOaZOOVh8xv06TWckcL5iVyhoDRWQi8If9CaHB5hUL8JdjgEiYR+Z
# LxxFWB26eBHBZ85EqX/SQPpxoOY1ba+tQHE/TfVOrFGdPydyhVJ9y0OjOzEkGMFy
# cc1JT6tDWatqcMle5AO4204wVc48DbLEICr84OYkqW8Vw8GC7TT0TFawsEe5NEo0
# kbTr40GyGHdmqfbUFSmIEefM61bpJmVm2ZCvINCQAFFX7mtBHl3/hswhI0PDuYKV
# ZH7rO3+t0zuNEmNDfhT+SZRQfKvfig43iKP42D/qRymHFakwiHG5XcSupDbarU+C
# qy0=
# SIG # End signature block
