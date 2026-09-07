[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl,
    [string]$BackupDirectory = ".\backups"
)

$ErrorActionPreference = "Stop"
$pgDump = (Get-Command pg_dump.exe -ErrorAction Stop).Source
$backupRoot = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $BackupDirectory))
$workspaceRoot = [System.IO.Path]::GetFullPath((Get-Location).Path)
if (-not $backupRoot.StartsWith($workspaceRoot.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupDirectory must resolve inside the current project directory."
}
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$backupPath = Join-Path $backupRoot ("local-rag-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".dump")
& $pgDump --format=custom --no-owner --no-acl --file=$backupPath --dbname=$DatabaseUrl
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL backup failed." }
Write-Host "Backup created: $backupPath"
