<#
.SYNOPSIS
Runs Phase 1 PostgreSQL acceptance tests against a fresh, loopback-only Docker database.

.DESCRIPTION
This script never reads DATABASE_URL and never starts the application's services.
It creates a project-scoped Docker container and volume, runs test_phase1_postgres.py,
then removes only those disposable resources unless -KeepArtifacts is supplied.
#>
[CmdletBinding()]
param(
    [switch]$PreflightOnly,
    [switch]$ConfirmDisposableDatabase,
    [switch]$KeepArtifacts,
    [ValidateRange(1025, 65535)]
    [int]$Port = 55432,
    [ValidateRange(1, 16)]
    [double]$MinimumAvailableGiB = 4
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv-rag\Scripts\python.exe'
$composeFile = Join-Path $projectRoot 'local-infrastructure\docker-compose.phase1-validation.yml'
$projectName = 'local-rag-phase1-validation'

function Stop-Validation([string]$Message) {
    throw "Phase 1 PostgreSQL validation not started: $Message"
}

if (-not (Test-Path -LiteralPath $python)) {
    Stop-Validation 'the project virtual environment is missing.'
}
if (-not (Test-Path -LiteralPath $composeFile)) {
    Stop-Validation 'the disposable Compose definition is missing.'
}
try {
    $availableMiB = (Get-Counter '\Memory\Available MBytes').CounterSamples[0].CookedValue
} catch {
    Stop-Validation 'available-memory measurement is unavailable; the safety check fails closed.'
}
$availableGiB = [math]::Round($availableMiB / 1024, 2)
if ($availableGiB -lt $MinimumAvailableGiB) {
    Stop-Validation "only $availableGiB GiB is available; at least $MinimumAvailableGiB GiB is required before starting Docker."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-Validation 'Docker Desktop / Docker Engine is not available on PATH.'
}

& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-Validation 'Docker is installed but its engine is not running.'
}

$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listener) {
    Stop-Validation "loopback port $Port is already in use; choose another -Port."
}

Write-Host "Preflight passed: $availableGiB GiB available; Docker engine reachable; loopback port $Port is free."
if ($PreflightOnly) {
    return
}
if (-not $ConfirmDisposableDatabase) {
    Stop-Validation 'pass -ConfirmDisposableDatabase to create and later delete the named test container and volume.'
}

# Hex avoids URL escaping and is held only in this PowerShell process and its children.
$passwordBytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Fill($passwordBytes)
$testPassword = [Convert]::ToHexString($passwordBytes).ToLowerInvariant()
$env:PHASE1_POSTGRES_PASSWORD = $testPassword
$env:PHASE1_POSTGRES_PORT = [string]$Port
$env:LOCAL_RAG_TEST_DISPOSABLE = 'YES'
$env:LOCAL_RAG_TEST_DATABASE_URL = "postgresql://rag_phase1_owner:$testPassword@127.0.0.1:$Port/rag_phase1_test_local"
$started = $false

try {
    & docker compose --project-name $projectName --file $composeFile up --detach --wait --wait-timeout 90 postgres
    if ($LASTEXITCODE -ne 0) { Stop-Validation 'the disposable PostgreSQL container did not become healthy.' }
    $started = $true
    Push-Location $projectRoot
    try {
        & $python -m unittest -v test_phase1_postgres
        if ($LASTEXITCODE -ne 0) { throw 'One or more PostgreSQL acceptance tests failed.' }
    } finally {
        Pop-Location
    }
} finally {
    Remove-Item Env:PHASE1_POSTGRES_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:PHASE1_POSTGRES_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:LOCAL_RAG_TEST_DISPOSABLE -ErrorAction SilentlyContinue
    Remove-Item Env:LOCAL_RAG_TEST_DATABASE_URL -ErrorAction SilentlyContinue
    if ($started -and -not $KeepArtifacts) {
        # This removes only resources labelled by the fixed disposable Compose project.
        & docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Automatic cleanup failed; remove only the local-rag-phase1-validation Docker project after review.' }
    }
}
