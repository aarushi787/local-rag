param(
    [string]$ApiBaseUrl = '',
    [string]$ApiKey = '',
    [switch]$AllowNonTargetHost
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\PrivateAI.Common.ps1')

$snapshot = Assert-PrivateAITargetServer -AllowNonTargetHost:$AllowNonTargetHost
$checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param([string]$Name, [bool]$Passed, [string]$Detail)
    $script:checks.Add([pscustomobject]@{
        Check = $Name
        Passed = $Passed
        Detail = $Detail
    })
}

try {
    Assert-PrivateAILoopbackOnly -Port 11434 -ServiceName 'Ollama'
    Add-Check 'Ollama loopback binding' $true '127.0.0.1/::1 only'
}
catch {
    Add-Check 'Ollama loopback binding' $false $_.Exception.Message
}

try {
    Assert-PrivateAILoopbackOnly -Port 8080 -ServiceName 'Open WebUI'
    Add-Check 'Open WebUI loopback binding' $true '127.0.0.1/::1 only'
}
catch {
    Add-Check 'Open WebUI loopback binding' $false $_.Exception.Message
}

try {
    $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
    $modelNames = @($tags.models | ForEach-Object { $_.name })
    foreach ($requiredModel in @('gemma3:1b-it-qat', 'gemma3:4b-it-qat')) {
        Add-Check "Model $requiredModel" ($modelNames -contains $requiredModel) (($modelNames -join ', '))
    }
}
catch {
    Add-Check 'Ollama API' $false $_.Exception.Message
}

try {
    $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8080' -UseBasicParsing -TimeoutSec 5
    Add-Check 'Open WebUI HTTP' ($response.StatusCode -eq 200) "HTTP $($response.StatusCode)"
}
catch {
    Add-Check 'Open WebUI HTTP' $false $_.Exception.Message
}

$openWebUiService = Get-Service -Name OpenWebUI -ErrorAction SilentlyContinue
Add-Check 'OpenWebUI service' ($openWebUiService -and $openWebUiService.Status -eq 'Running') $(
    if ($openWebUiService) { "$($openWebUiService.Status), $($openWebUiService.StartType)" } else { 'Not installed' }
)

if ($ApiBaseUrl -and $ApiKey) {
    try {
        $body = @{
            model = 'gemma3:1b-it-qat'
            messages = @(@{ role = 'user'; content = 'Reply with exactly: verification passed' })
            stream = $false
        } | ConvertTo-Json -Depth 6
        $answer = Invoke-RestMethod -Method Post -Uri "$($ApiBaseUrl.TrimEnd('/'))/api/chat/completions" `
            -Headers @{ Authorization = "Bearer $ApiKey" } -ContentType 'application/json' -Body $body -TimeoutSec 120
        Add-Check 'Authenticated chat API' ([bool]$answer.choices) 'Completion returned'
    }
    catch {
        Add-Check 'Authenticated chat API' $false $_.Exception.Message
    }
}

$checks | Format-Table -AutoSize
$failed = @($checks | Where-Object { -not $_.Passed })
if ($failed.Count -gt 0) {
    throw "$($failed.Count) verification check(s) failed. Do not enable users yet."
}

Write-Host "All requested checks passed on $($snapshot.ComputerName)." -ForegroundColor Green
