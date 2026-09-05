#Requires -RunAsAdministrator
param(
    [ValidateSet('Baseline', 'Gemma1B', 'Gemma4B')]
    [string]$Mode = 'Baseline',
    [ValidateRange(60, 1800)]
    [int]$DurationSeconds = 300,
    [string]$ArtifactDirectory = (Join-Path $PSScriptRoot 'artifacts'),
    [switch]$AcknowledgeProductionLoadRisk,
    [switch]$AllowNonTargetHost
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\PrivateAI.Common.ps1')

Assert-PrivateAIAdministrator
Assert-PrivateAITargetServer -AllowNonTargetHost:$AllowNonTargetHost | Out-Null

if ($Mode -ne 'Baseline' -and -not $AcknowledgeProductionLoadRisk) {
    throw 'This test deliberately loads the CPU. Rerun in an approved test window with -AcknowledgeProductionLoadRisk.'
}

New-Item -ItemType Directory -Path $ArtifactDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outputPath = Join-Path $ArtifactDirectory "tally-$($Mode.ToLowerInvariant())-$stamp.blg"
$sampleCount = [math]::Floor($DurationSeconds / 2)
$loadJob = $null

if ($Mode -ne 'Baseline') {
    Assert-PrivateAILoopbackOnly -Port 11434 -ServiceName 'Ollama'
    $model = if ($Mode -eq 'Gemma1B') { 'gemma3:1b-it-qat' } else { 'gemma3:4b-it-qat' }
    Write-Warning "Starting a controlled, single-request $model load for $DurationSeconds seconds. Keep Tally open and time the agreed workflow now."
    $loadJob = Start-Job -ArgumentList $model, $DurationSeconds -ScriptBlock {
        param($ModelName, $RunSeconds)
        $endTime = (Get-Date).AddSeconds($RunSeconds)
        while ((Get-Date) -lt $endTime) {
            $body = @{
                model = $ModelName
                prompt = 'Explain one practical accounting control in approximately 300 words.'
                stream = $false
                options = @{ num_ctx = 4096 }
            } | ConvertTo-Json -Depth 5
            try {
                Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' `
                    -ContentType 'application/json' -Body $body -TimeoutSec 180 | Out-Null
            }
            catch {
                Write-Error $_
                break
            }
        }
    }
}
else {
    Write-Host "Capturing a $DurationSeconds-second Tally baseline. Perform the agreed Tally workflow now." -ForegroundColor Yellow
}

$counters = @(
    '\Processor(_Total)\% Processor Time',
    '\Memory\Available MBytes',
    '\PhysicalDisk(_Total)\Avg. Disk sec/Transfer',
    '\System\Processor Queue Length'
)

try {
    Get-Counter -Counter $counters -SampleInterval 2 -MaxSamples $sampleCount |
        Export-Counter -Path $outputPath -FileFormat BLG -Force
}
finally {
    if ($loadJob) {
        Stop-Job -Job $loadJob -ErrorAction SilentlyContinue
        Receive-Job -Job $loadJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $loadJob -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Performance capture saved to $outputPath" -ForegroundColor Green
Write-Host 'Record the median and worst Tally operation times. Do not approve a model if median latency rises over 10% or worst latency over 20%.' -ForegroundColor Yellow
