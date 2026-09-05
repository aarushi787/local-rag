param(
    [ValidateSet('gemma3:1b-it-qat', 'gemma3:4b-it-qat', 'gemma3:12b-it-qat')]
    [string]$Model = 'gemma3:1b-it-qat',
    [ValidateRange(1, 10)]
    [int]$Runs = 3,
    [string]$ArtifactDirectory = (Join-Path $PSScriptRoot 'artifacts'),
    [switch]$AcknowledgeProductionLoadRisk,
    [switch]$AllowNonTargetHost
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\PrivateAI.Common.ps1')

Assert-PrivateAITargetServer -AllowNonTargetHost:$AllowNonTargetHost | Out-Null
if (-not $AcknowledgeProductionLoadRisk) {
    throw 'Benchmarking deliberately saturates Ollama. Run in an approved test window with -AcknowledgeProductionLoadRisk.'
}
Assert-PrivateAILoopbackOnly -Port 11434 -ServiceName 'Ollama'
New-Item -ItemType Directory -Force $ArtifactDirectory | Out-Null

$tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
$installedModels = @($tags.models | ForEach-Object { $_.name })
if ($installedModels -notcontains $Model) {
    throw "$Model is not installed. Install it deliberately before benchmarking."
}

$results = New-Object System.Collections.Generic.List[object]
for ($run = 1; $run -le $Runs; $run++) {
    Write-Host "Benchmark run $run of $Runs for $Model" -ForegroundColor Yellow
    $body = @{
        model = $Model
        prompt = 'Explain double-entry bookkeeping in approximately 250 words. Be accurate and concise.'
        stream = $false
        options = @{ num_ctx = 4096; temperature = 0.2 }
    } | ConvertTo-Json -Depth 5

    $response = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' `
        -ContentType 'application/json' -Body $body -TimeoutSec 600
    if (-not $response.eval_duration -or -not $response.eval_count) {
        throw 'Ollama did not return evaluation timing fields.'
    }

    $results.Add([pscustomobject]@{
        Run = $run
        Model = $response.model
        GeneratedTokens = [int]$response.eval_count
        GenerationSeconds = [math]::Round($response.eval_duration / 1e9, 2)
        TokensPerSecond = [math]::Round($response.eval_count / ($response.eval_duration / 1e9), 2)
        PromptTokens = [int]$response.prompt_eval_count
        LoadSeconds = [math]::Round($response.load_duration / 1e9, 2)
    })
}

$sortedRates = @($results.TokensPerSecond | Sort-Object)
$middle = [math]::Floor($sortedRates.Count / 2)
if (($sortedRates.Count % 2) -eq 0) {
    $median = ($sortedRates[$middle - 1] + $sortedRates[$middle]) / 2
}
else {
    $median = $sortedRates[$middle]
}

$report = [pscustomobject]@{
    CapturedAt = (Get-Date).ToString('o')
    Model = $Model
    Runs = @($results)
    MedianTokensPerSecond = [math]::Round($median, 2)
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$reportPath = Join-Path $ArtifactDirectory "benchmark-$($Model.Replace(':', '-'))-$stamp.json"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8

$results | Format-Table -AutoSize
Write-Host "Median: $($report.MedianTokensPerSecond) tokens/second" -ForegroundColor Green
Write-Host "Report: $reportPath" -ForegroundColor Green
