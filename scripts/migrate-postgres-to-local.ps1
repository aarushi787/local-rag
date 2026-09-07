[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceUrl,
    [string]$TargetUrl = "postgresql://localrag:CHANGE_ME@127.0.0.1:5432/localrag",
    [string]$BackupDirectory = ".\backups"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'assert-local-postgres.ps1')
Assert-LocalPostgresTarget -ConnectionUrl $TargetUrl
if ($SourceUrl -eq $TargetUrl) { throw 'Source and target must differ.' }
$pgDump = (Get-Command pg_dump.exe -ErrorAction Stop).Source
$pgRestore = (Get-Command pg_restore.exe -ErrorAction Stop).Source
$psql = (Get-Command psql.exe -ErrorAction Stop).Source

$backupRoot = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $BackupDirectory))
$workspaceRoot = [System.IO.Path]::GetFullPath((Get-Location).Path)
if (-not $backupRoot.StartsWith($workspaceRoot.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupDirectory must resolve inside the current project directory."
}
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$tableCount = & $psql --dbname=$TargetUrl --tuples-only --no-align --command="SELECT COUNT(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public';"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the target PostgreSQL database." }
if ([int]$tableCount -gt 0) {
    throw "Target database is not empty. Use a new empty database; this script never overwrites existing tables."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $backupRoot "local-rag-$stamp.dump"
& $pgDump --format=custom --no-owner --no-acl --file=$backupPath --dbname=$SourceUrl
if ($LASTEXITCODE -ne 0) { throw "Source backup failed; target was not changed." }

& $pgRestore --no-owner --no-acl --single-transaction --exit-on-error --dbname=$TargetUrl $backupPath
if ($LASTEXITCODE -ne 0) {
    throw "Restore failed. The source database is unchanged. Keep $backupPath for recovery and inspect the empty target."
}

$counts = & $psql --dbname=$TargetUrl --tuples-only --no-align --command="SELECT (SELECT COUNT(*) FROM rag_documents) || ' documents, ' || (SELECT COUNT(*) FROM rag_chunks) || ' chunks';"
if ($LASTEXITCODE -ne 0) { throw "Restore completed but validation query failed." }
Write-Host "Local restore complete: $counts"
Write-Host "Backup retained at $backupPath"
Write-Host 'Not a cutover approval. First run verify-migration.py with DATABASE_URL=source and LOCAL_DATABASE_URL=target, then restore-test, evaluate and test permissions/concurrency. Keep Neon unchanged.'
