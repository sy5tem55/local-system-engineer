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
#     ModelFile       — path relative to /home/sy5/models/ (subfolder/model.gguf)
#                         Each model lives in its own named subfolder:
#                         e.g. Qwen3.6-27B-Q5_K_M/Qwen3.6-27B-Q5_K_M.gguf
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
#     BatchSize       — prompt batch size (--batch-size). Tune with llama-optimus.
#                       Controls how many tokens are processed per forward pass during prefill.
#                       Higher = better pp throughput; must fit in VRAM alongside the model.
#                       Omit to use llama.cpp defaults.
#     UBatchSize      — micro-batch size (--ubatch-size). Tune with llama-optimus.
#                       Subdivides BatchSize for pipeline efficiency. Omit to use defaults.
#     OverrideTensor  — tensor placement override (--override-tensor). Regex=Device format.
#                       Offloads MoE expert weight tensors to CPU, freeing VRAM for more
#                       GPU layers (higher ngl). Only the ACTIVE experts run on GPU per token;
#                       inactive experts sit in CPU RAM and are never touched. Net effect:
#                       pp improves ~4%, tg is flat (CPU handles idle experts, no throughput hit).
#                       Benchmarked without MTP or KV quant — production tg will differ.
#                       Omit for standard all-GPU placement.
#     TabLabel        — text shown in the Windows Terminal red tab (keep ≤ 20 chars)
#     BannerLine1     — first content line of the red-tab ASCII banner  (≤ 41 chars)
#     BannerLine2     — second content line of the red-tab ASCII banner (≤ 41 chars)

$ModelProfiles = [ordered]@{

    # ── Q5_K_M · 27B · MTP profiles ───────────────────────────────────────────
    #    Q5_K_M on RTX 4090: fits cleanly at 32k. 64k is impossible — ~23 GB
    #    weights + KV leaves no headroom under MTP load. Use Q4_K_M for 64k.
    #
    #    llama-optimus tuning (2026-05-26, build bb28c1fe2, RTX 4090):
    #      ngl 99→117, threads 8→13  ← applied
    #      batch 6637, ubatch 2875   ← NOT applied: regression confirmed v1.064/v1.066

    'Qwen3.6 27B · MTP  [32k · q8_0]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M/Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 117
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 13

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        SpecType         = 'draft-mtp'
        SpecDraftNMax    = 3
        TabLabel         = '  QWEN 3.6 27B · MTP'
        BannerLine1      = 'QWEN 3.6 27B  ·  MTP'
        BannerLine2      = 'MTP · KV:q8_0 · think:3072 → :8080'
    }

    'Qwen3.6 27B · MTP  [no-think · q8_0]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M/Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 117
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 13

        ReasoningBudget  = '0'
        MaxPredictTokens = '4096'
        SpecType         = 'draft-mtp'
        SpecDraftNMax    = 3
        TabLabel         = '  QWEN 3.6 27B · MTP fast'
        BannerLine1      = 'QWEN 3.6 27B  ·  MTP'
        BannerLine2      = 'MTP · KV:q8_0 · thinking off → :8080'
    }

    # ── Q4_K_M · 27B · MTP profiles ───────────────────────────────────────────
    #    Q4_K_M: ~4.8 bits/weight vs Q5_K_M ~5.7 bits/weight.
    #    Supports 64k context without MTP (no headroom for draft tokens at 64k).
    #
    #    llama-optimus tuning (2026-05-26, build bb28c1fe2, RTX 4090):
    #      ngl 99→129, threads 8→7  ← applied
    #      batch 6377, ubatch 4399  ← NOT applied: same regression as Q5_K_M

    'Qwen3.6 27B · Q4_K_M + MTP  [32k · q8_0]' = @{
        ModelFile        = 'Qwen3.6-27B-Q4_K_M/Qwen3.6-27B-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 129
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 7

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        SpecType         = 'draft-mtp'
        SpecDraftNMax    = 3
        TabLabel         = '  QWEN 3.6 27B · Q4+MTP'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q4_K_M + MTP'
        BannerLine2      = 'MTP · KV:q8_0 · think:3072 → :8080'
    }

    'Qwen3.6 27B · Q4_K_M + MTP  [no-think · q8_0]' = @{
        ModelFile        = 'Qwen3.6-27B-Q4_K_M/Qwen3.6-27B-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 129
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 7

        ReasoningBudget  = '0'
        MaxPredictTokens = '4096'
        SpecType         = 'draft-mtp'
        SpecDraftNMax    = 3
        TabLabel         = '  QWEN 3.6 27B · Q4+MTP fast'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q4_K_M + MTP'
        BannerLine2      = 'MTP · KV:q8_0 · thinking off → :8080'
    }

    # ── Q4_K_M · 27B · 64k profiles (no MTP — insufficient VRAM headroom at 64k) ─

    'Qwen3.6 27B · Q4_K_M  [64k · q8_0]' = @{
        ModelFile        = 'Qwen3.6-27B-Q4_K_M/Qwen3.6-27B-Q4_K_M.gguf'
        CtxSize          = 65536
        GpuLayers        = 129
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 7

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  QWEN 3.6 27B · Q4 64k'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q4_K_M'
        BannerLine2      = '64k · KV:q8_0 · think:3072 → :8080'
    }

    'Qwen3.6 27B · Q4_K_M  [64k · no-think · q8_0]' = @{
        ModelFile        = 'Qwen3.6-27B-Q4_K_M/Qwen3.6-27B-Q4_K_M.gguf'
        CtxSize          = 65536
        GpuLayers        = 129
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 7

        ReasoningBudget  = '0'
        MaxPredictTokens = '4096'
        TabLabel         = '  QWEN 3.6 27B · Q4 64k fast'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q4_K_M'
        BannerLine2      = '64k · KV:q8_0 · no-think → :8080'
    }

    # ── Q5_K_M · 27B · standard profiles (no MTP — stable baseline) ──────────

    'Qwen3.6 27B · Q5_K_M  [32k · q8_0]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M/Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 117
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 13

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  QWEN 3.6 27B'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q5_K_M'
        BannerLine2      = 'KV:q8_0 · think:3072 → localhost:8080'
    }

    'Qwen3.6 27B · Q5_K_M  [no-think · q8_0]' = @{
        ModelFile        = 'Qwen3.6-27B-Q5_K_M/Qwen3.6-27B-Q5_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 117
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 13

        ReasoningBudget  = '0'
        MaxPredictTokens = '4096'
        TabLabel         = '  QWEN 3.6 27B · fast'
        BannerLine1      = 'QWEN 3.6 27B  ·  Q5_K_M'
        BannerLine2      = 'KV:q8_0 · thinking off → localhost:8080'
    }

    # ── 35B A3B (MoE) profiles ────────────────────────────────────────────────
    #    35B total / ~3.5B active parameters (MoE architecture).
    #    Q4_K_M / Q4_K file: ~19–21 GB on RTX 4090 (24 GB).
    #    MTP DISABLED for all 35B A3B profiles — llama-server fails to measure
    #    MTP context memory for this architecture: "failed to create llama_context
    #    from model". Run without --spec-type until upstream fix lands.
    #    ngl=99: full GPU offload. If OOM, reduce to 90 and check nvidia-smi.
    #    threads=8: conservative for prompt prefill on the 9900K.

    'Qwopus 3.6 35B A3B · Q4_K_M  [32k · q8_0]' = @{
        ModelFile        = 'Qwopus3.6-35B-A3B-v1-Q4_K_M/Qwopus3.6-35B-A3B-v1-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  QWOPUS 35B'
        BannerLine1      = 'QWOPUS 3.6 35B A3B  ·  Q4_K_M'
        BannerLine2      = 'KV:q8_0 · think:3072 → :8080'
    }

    # ── Qwopus 3.6 35B A3B · 64k profile ────────────────────────────────────────
    #    64k context — needs ~2 GB CPU KV spillover at tail end.
    #    MTP DISABLED (see 35B A3B note above).

    'Qwopus 3.6 35B A3B · Q4_K_M  [96k · q8_0]' = @{
        ModelFile        = 'Qwopus3.6-35B-A3B-v1-Q4_K_M/Qwopus3.6-35B-A3B-v1-Q4_K_M.gguf'
        CtxSize          = 96000
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  QWOPUS 35B 96k'
        BannerLine1      = 'QWOPUS 3.6 35B A3B  ·  Q4_K_M'
        BannerLine2      = '64k · KV:q8_0 · think:3072 → :8080'
    }

    # ── Huihui Qwen3.6 35B A3B (MoE, abliterated) profiles ──────────────────
    #    Claude 4.7 Opus merge, abliterated. MTP disabled (see 35B A3B note above).

    'Huihui Qwen3.6 35B A3B · Q4_K  [32k · q8_0]' = @{
        ModelFile        = 'Huihui-Qwen3.6-35B-A3B-Claude-4.7-Opus-abliterated-ggml-model-Q4_K/Huihui-Qwen3.6-35B-A3B-Claude-4.7-Opus-abliterated-ggml-model-Q4_K.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  HUIHUI 35B'
        BannerLine1      = 'HUIHUI 3.6 35B A3B  ·  Q4_K'
        BannerLine2      = 'KV:q8_0 · think:3072 → :8080'
    }

    # ── HauhauCS Aggressive Qwen3.6 35B A3B (uncensored) profiles ────────────
    #    Uncensored aggressive variant. MTP disabled (see 35B A3B note above).

    'HauhauCS Aggressive 35B A3B · Q4_K_M  [32k · q8_0]' = @{
        ModelFile        = 'Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  HAUHAU 35B UNCENSORED'
        BannerLine1      = 'HAUHAU 3.6 35B A3B  ·  Q4_K_M'
        BannerLine2      = 'uncensored · KV:q8_0 · think:3072 → :8080'
    }

    # ── GLM 4.7B Flash · Q4_K_M profiles ─────────────────────────────────────
    #    Small/fast flash model (~4.7B parameters).
    #    Parameters inherited from 35B A3B baseline — same hardware.

    'GLM 4.7 Flash · Q4_K_M  [32k · q8_0]' = @{
        ModelFile        = 'GLM-4.7-Flash-Q4_K_M/GLM-4.7-Flash-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  GLM 4.7 FLASH'
        BannerLine1      = 'GLM 4.7 FLASH  ·  Q4_K_M'
        BannerLine2      = 'KV:q8_0 · think:3072 → :8080'
    }

    'GLM 4.7 Flash · Q4_K_M  [no-think · q8_0]' = @{
        ModelFile        = 'GLM-4.7-Flash-Q4_K_M/GLM-4.7-Flash-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8

        ReasoningBudget  = '0'
        MaxPredictTokens = '4096'
        TabLabel         = '  GLM 4.7 FLASH fast'
        BannerLine1      = 'GLM 4.7 FLASH  ·  Q4_K_M'
        BannerLine2      = 'KV:q8_0 · thinking off → :8080'
    }

    # ── Gemma 4 26B A4B (MoE) · Q4_K_M profiles ──────────────────────────────
    #    26B total / ~4B active parameters (MoE, A4B).
    #    Vision-capable — mmproj BF16 available in same folder (text-only here).
    #    Parameters inherited from 35B A3B baseline. MTP untested — omitted.

    'Gemma 4 26B A4B · Q4_K_M  [32k · q8_0]' = @{
        ModelFile        = 'Gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  GEMMA 4 26B A4B'
        BannerLine1      = 'GEMMA 4 26B A4B  ·  Q4_K_M'
        BannerLine2      = 'KV:q8_0 · think:3072 → :8080'
    }

    # ── Gemma 4 31B (dense) · Q4_K_M profiles ────────────────────────────────
    #    31B dense model. Vision-capable — mmproj BF16 available (text-only here).
    #    Parameters inherited from 35B A3B baseline. MTP untested — omitted.

    'Gemma 4 31B · Q4_K_M  [32k · q8_0]' = @{
        ModelFile        = 'Gemma-4-31B-it-GGUF/gemma-4-31B-it-Q4_K_M.gguf'
        CtxSize          = 32768
        GpuLayers        = 99
        FlashAttn        = $true
        CacheTypeK       = 'q8_0'
        CacheTypeV       = 'q8_0'
        Parallel         = 1
        Threads          = 8

        ReasoningBudget  = '3072'
        MaxPredictTokens = '8192'
        TabLabel         = '  GEMMA 4 31B'
        BannerLine1      = 'GEMMA 4 31B  ·  Q4_K_M'
        BannerLine2      = 'KV:q8_0 · think:3072 → :8080'
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
Write-Host "  ${c}║              Stack Launcher  v1.074                  ║${r}"
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
if ($Prof.ContainsKey('BatchSize')  -and $Prof.BatchSize)  { $CmdLines.Add("  --batch-size $($Prof.BatchSize) \") }
if ($Prof.ContainsKey('UBatchSize') -and $Prof.UBatchSize) { $CmdLines.Add("  --ubatch-size $($Prof.UBatchSize) \") }
if ($Prof.ContainsKey('OverrideTensor') -and $Prof.OverrideTensor) { $CmdLines.Add("  --override-tensor `"$($Prof.OverrideTensor)`" \") }
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
