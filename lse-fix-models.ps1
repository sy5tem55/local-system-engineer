# Writes chatLanguageModels.json for VS Code Insiders.
# Run: .\lse-fix-models.ps1
#
# LUCIFER  : Qwen3.6-27B        @ localhost:8080          ctx=165K reasoning=16K
# node3090 : Gemma-4-31B        @ node3090.home.arpa:8080 ctx=160K reasoning=8K
# node3090 : Qwen3.6-35B-A3B   @ node3090.home.arpa:8080 ctx=110K
# (node3090 serves one model at a time — select whichever is currently loaded)

$target = "$env:APPDATA\Code - Insiders\User\chatLanguageModels.json"

$data = @(
    @{
        name    = "LUCIFER"
        vendor  = "customendpoint"
        apiKey  = "none"
        apiType = "chat-completions"
        models  = @(
            @{
                id             = "Qwen3.6-27B"
                name           = "Qwen3.6-27B (LUCIFER)"
                url            = "http://localhost:8080/v1/chat/completions"
                toolCalling    = $true
                vision         = $false
                thinking       = $true
                maxInputTokens = 134000   # 165K ctx - 16K reasoning - 15K output
                maxOutputTokens = 15000
            }
        )
    },
    @{
        name    = "node3090"
        vendor  = "customendpoint"
        apiKey  = "none"
        apiType = "chat-completions"
        models  = @(
            @{
                id             = "Gemma-4-31B"
                name           = "Gemma-4-31B-IT (node3090)"
                url            = "http://node3090.home.arpa:8080/v1/chat/completions"
                toolCalling    = $true
                vision         = $true
                thinking       = $true
                maxInputTokens = 143000   # 160K ctx - 8K reasoning - 8K output
                maxOutputTokens = 8192
            },
            @{
                id             = "Qwen3.6-35B-A3B"
                name           = "Qwen3.6-35B-A3B (node3090)"
                url            = "http://node3090.home.arpa:8080/v1/chat/completions"
                toolCalling    = $true
                vision         = $false
                thinking       = $true
                maxInputTokens = 94000    # 110K ctx - 16K output
                maxOutputTokens = 16000
            }
        )
    }
) | ConvertTo-Json -Depth 5

Set-Content $target $data -Encoding UTF8

Write-Host ""
Write-Host "  Written: $target" -ForegroundColor Green
Write-Host ""
(Get-Content $target | ConvertFrom-Json).models | ForEach-Object {
    # flatten across providers
}
Get-Content $target | ConvertFrom-Json | ForEach-Object {
    $p = $_
    $p.models | ForEach-Object {
        Write-Host ("  {0,-10}  {1,-30}  ctx_in={2}" -f $p.name, $_.id, $_.maxInputTokens)
    }
}
