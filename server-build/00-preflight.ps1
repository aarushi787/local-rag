param(
    [string]$ArtifactDirectory = (Join-Path $PSScriptRoot 'artifacts'),
    [switch]$AllowNonTargetHost
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\PrivateAI.Common.ps1')

$snapshot = Assert-PrivateAITargetServer -AllowNonTargetHost:$AllowNonTargetHost
New-Item -ItemType Directory -Path $ArtifactDirectory -Force | Out-Null

$volumes = @(Get-Volume -ErrorAction Stop |
    Where-Object { $_.DriveLetter } |
    ForEach-Object {
        [pscustomobject]@{
            DriveLetter = $_.DriveLetter
            FileSystemLabel = $_.FileSystemLabel
            SizeGB = [math]::Round($_.Size / 1GB, 1)
            FreeGB = [math]::Round($_.SizeRemaining / 1GB, 1)
        }
    })

$fallbackPaths = @{
    ollama = (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe')
    tailscale = 'C:\Program Files\Tailscale\tailscale.exe'
    uv = 'C:\AI\bin\uv.exe'
}
$commands = @('ollama', 'open-webui', 'uv', 'tailscale', 'python') | ForEach-Object {
    $command = Get-Command $_ -ErrorAction SilentlyContinue
    if (-not $command -and $fallbackPaths.ContainsKey($_) -and (Test-Path -LiteralPath $fallbackPaths[$_])) {
        $command = Get-Item -LiteralPath $fallbackPaths[$_]
    }
    [pscustomobject]@{
        Name = $_
        Installed = [bool]$command
        Path = if ($command) { Get-PrivateAICommandPath -CommandInfo $command } else { $null }
    }
}

$relatedProcesses = @(Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match 'tally|ollama|open-webui|tailscale' } |
    Select-Object ProcessName, Id, CPU,
        @{Name = 'WorkingSetMB'; Expression = {[math]::Round($_.WorkingSet64 / 1MB, 1)}},
        Path)

$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in @(443, 8080, 11434) } |
    Select-Object LocalAddress, LocalPort, OwningProcess)

$report = [pscustomobject]@{
    CapturedAt = (Get-Date).ToString('o')
    Host = $snapshot
    Volumes = $volumes
    Commands = @($commands)
    RelatedProcesses = $relatedProcesses
    RelevantListeners = $listeners
    TallyDetected = [bool]($relatedProcesses | Where-Object { $_.ProcessName -match 'tally' })
}

$reportPath = Join-Path $ArtifactDirectory 'preflight.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8

$report | Format-List
Write-Host "Preflight report: $reportPath" -ForegroundColor Green

if (-not $report.TallyDetected) {
    Write-Warning 'No Tally process is currently visible. Capture the baseline while Tally is running before enabling AI access.'
}

$systemVolume = $volumes | Where-Object { $_.DriveLetter -eq $env:SystemDrive.TrimEnd(':') }
if ($systemVolume -and $systemVolume.FreeGB -lt 60) {
    throw "The system volume has only $($systemVolume.FreeGB) GB free. Keep at least 60 GB free before installation."
}

Write-Host 'Preflight passed. No system settings were changed.' -ForegroundColor Green
