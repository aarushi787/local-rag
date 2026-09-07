[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [Parameter(Mandatory = $true)]
    [string]$DisposableDatabaseUrl,
    [Parameter(Mandatory = $true)]
    [switch]$ConfirmTargetIsDisposable
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'assert-local-postgres.ps1')
Assert-LocalPostgresTarget -ConnectionUrl $DisposableDatabaseUrl
if (-not $ConfirmTargetIsDisposable) { throw 'Explicit disposable-target confirmation is required.' }
$backup = (Resolve-Path -LiteralPath $BackupFile).Path
if ([System.IO.Path]::GetExtension($backup) -ne '.dump') {
    throw 'BackupFile must be a custom-format .dump created by backup-local-postgres.ps1.'
}
if ($DisposableDatabaseUrl -notmatch '/([^/?]+)(?:\?|$)') {
    throw 'Could not determine the target database name.'
}
$databaseName = $Matches[1]
if ($databaseName -notmatch '(?i)(restore|test|disposable)') {
    throw "Safety check failed: target database name must contain restore, test, or disposable."
}

$pgRestore = (Get-Command pg_restore.exe -ErrorAction Stop).Source
$psql = (Get-Command psql.exe -ErrorAction Stop).Source
& $pgRestore --list $backup | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The backup archive cannot be read.' }

$existing = & $psql $DisposableDatabaseUrl --tuples-only --no-align --command "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public';"
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the disposable target.' }
if ([int]$existing -ne 0) {
    throw 'Disposable target is not empty. Create a new empty restore-test database.'
}

& $pgRestore --single-transaction --exit-on-error --no-owner --no-acl --dbname=$DisposableDatabaseUrl $backup
if ($LASTEXITCODE -ne 0) { throw 'Restore verification failed during pg_restore.' }

$counts = & $psql $DisposableDatabaseUrl --no-align --field-separator=',' --command "SELECT (SELECT COUNT(*) FROM rag_documents) AS documents, (SELECT COUNT(*) FROM rag_chunks) AS chunks, (SELECT COUNT(*) FROM rag_users) AS users;"
if ($LASTEXITCODE -ne 0) { throw 'Restore completed but integrity queries failed.' }
Write-Host 'Restore smoke check passed. Counts alone do not verify content or embeddings; run verify-migration.py before cutover.'
Write-Host $counts
