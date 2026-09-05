#Requires -RunAsAdministrator
param(
    [string]$ModelDirectory = 'C:\AI\Models',
    [switch]$PullOfficeModels,
    [switch]$PullAfterHoursModel,
    [switch]$AllowNonTargetHost
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\PrivateAI.Common.ps1')

Assert-PrivateAIAdministrator
$snapshot = Assert-PrivateAITargetServer -AllowNonTargetHost:$AllowNonTargetHost

New-Item -ItemType Directory -Force 'C:\AI', $ModelDirectory, 'C:\AI\Logs' | Out-Null

$settings = [ordered]@{
    OLLAMA_HOST = '127.0.0.1:11434'
    OLLAMA_MODELS = $ModelDirectory
    OLLAMA_NUM_PARALLEL = '1'
    OLLAMA_MAX_LOADED_MODELS = '1'
    OLLAMA_CONTEXT_LENGTH = '4096'
    OLLAMA_KEEP_ALIVE = '2m'
    OLLAMA_MAX_QUEUE = '4'
}

foreach ($entry in $settings.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Machine')
    Set-Item -Path "Env:$($entry.Key)" -Value $entry.Value
}

$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaCommand) {
    $defaultOllama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $defaultOllama) {
        $ollamaCommand = Get-Item -LiteralPath $defaultOllama
    }
}
if (-not $ollamaCommand) {
    throw "Ollama is not installed. Download the official Windows installer from https://ollama.com/download/windows, install it, then run this script again."
}
$ollamaPath = Get-PrivateAICommandPath -CommandInfo $ollamaCommand

Write-Host 'Applied conservative Ollama machine settings:' -ForegroundColor Green
$settings.GetEnumerator() | Format-Table Key, Value -AutoSize

$apiReady = $false
try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 | Out-Null
    $apiReady = $true
}
catch {
    Write-Warning 'Ollama is not responding yet. Restart the Ollama application or its service so it inherits the new settings.'
}

if (($PullOfficeModels -or $PullAfterHoursModel) -and -not $apiReady) {
    throw 'Model download was requested, but the Ollama API is unavailable. Restart Ollama, then rerun this script with the pull switch.'
}

if ($PullOfficeModels) {
    & $ollamaPath pull 'gemma3:1b-it-qat'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to pull gemma3:1b-it-qat.' }
    & $ollamaPath pull 'gemma3:4b-it-qat'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to pull gemma3:4b-it-qat.' }
}

if ($PullAfterHoursModel) {
    Write-Warning 'The 12B model is for after-hours validation only on this four-core server.'
    & $ollamaPath pull 'gemma3:12b-it-qat'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to pull gemma3:12b-it-qat.' }
}

if ($apiReady) {
    Assert-PrivateAILoopbackOnly -Port 11434 -ServiceName 'Ollama'
    Write-Host 'Ollama is listening on loopback only.' -ForegroundColor Green
}

Write-Host "Configured $($snapshot.ComputerName). Reboot or restart Ollama before acceptance testing." -ForegroundColor Green
