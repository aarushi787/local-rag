#Requires -RunAsAdministrator
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupTarget,
    [switch]$AcknowledgeAiDowntime,
    [switch]$AllowNonTargetHost
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\PrivateAI.Common.ps1')

Assert-PrivateAIAdministrator
Assert-PrivateAITargetServer -AllowNonTargetHost:$AllowNonTargetHost | Out-Null

if (-not $AcknowledgeAiDowntime) {
    throw 'A consistent SQLite/Chroma backup briefly stops Open WebUI. Rerun with -AcknowledgeAiDowntime.'
}
if (-not (Test-Path -LiteralPath $BackupTarget -PathType Container)) {
    throw "Backup target does not exist: $BackupTarget"
}

$dataDirectory = 'C:\AI\OpenWebUI\data'
if (-not (Test-Path -LiteralPath $dataDirectory -PathType Container)) {
    throw "Open WebUI data directory does not exist: $dataDirectory"
}

$resolvedTarget = (Resolve-Path -LiteralPath $BackupTarget).Path.TrimEnd('\')
$resolvedData = (Resolve-Path -LiteralPath $dataDirectory).Path.TrimEnd('\')
if ($resolvedTarget.StartsWith($resolvedData, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The backup target cannot be inside the live Open WebUI data directory.'
}

$service = Get-Service -Name OpenWebUI -ErrorAction Stop
$wasRunning = $service.Status -eq 'Running'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$archive = Join-Path $resolvedTarget "OpenWebUI-$stamp.zip"

try {
    if ($wasRunning) {
        Stop-Service OpenWebUI
        (Get-Service OpenWebUI).WaitForStatus('Stopped', (New-TimeSpan -Seconds 30))
    }
    Compress-Archive -Path (Join-Path $dataDirectory '*') -DestinationPath $archive -CompressionLevel Optimal
}
finally {
    if ($wasRunning) {
        Start-Service OpenWebUI
    }
}

$backupFile = Get-Item -LiteralPath $archive
if ($backupFile.Length -le 0) {
    throw 'The backup archive is empty.'
}

$hash = Get-FileHash -LiteralPath $archive -Algorithm SHA256
[pscustomobject]@{
    Archive = $backupFile.FullName
    SizeMB = [math]::Round($backupFile.Length / 1MB, 1)
    SHA256 = $hash.Hash
    OpenWebUIRestarted = $wasRunning
} | Format-List
