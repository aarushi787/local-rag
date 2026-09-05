#Requires -RunAsAdministrator
param(
    [string]$UvExecutable = '',
    [string]$NssmExecutable = 'C:\AI\bin\nssm.exe',
    [string]$InstallRoot = 'C:\AI\OpenWebUI',
    [switch]$AllowNonTargetHost
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\PrivateAI.Common.ps1')

Assert-PrivateAIAdministrator
Assert-PrivateAITargetServer -AllowNonTargetHost:$AllowNonTargetHost | Out-Null

if (-not (Test-Path -LiteralPath $NssmExecutable)) {
    throw "NSSM was not found at '$NssmExecutable'. Place the 64-bit nssm.exe there before running this script."
}

if (-not $UvExecutable) {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) {
        $UvExecutable = $uvCommand.Source
    }
    elseif (Test-Path -LiteralPath 'C:\AI\bin\uv.exe') {
        $UvExecutable = 'C:\AI\bin\uv.exe'
    }
}

if (-not $UvExecutable -or -not (Test-Path -LiteralPath $UvExecutable)) {
    throw "uv was not found. Install the official Windows uv binary, place uv.exe at C:\AI\bin\uv.exe, and run this script again."
}

$toolDirectory = Join-Path $InstallRoot 'uv-tools'
$binDirectory = Join-Path $InstallRoot 'bin'
$dataDirectory = Join-Path $InstallRoot 'data'
$logDirectory = 'C:\AI\Logs'

New-Item -ItemType Directory -Force $InstallRoot, $toolDirectory, $binDirectory, $dataDirectory, $logDirectory | Out-Null

$env:UV_TOOL_DIR = $toolDirectory
$env:UV_TOOL_BIN_DIR = $binDirectory
[Environment]::SetEnvironmentVariable('UV_TOOL_DIR', $toolDirectory, 'Machine')
[Environment]::SetEnvironmentVariable('UV_TOOL_BIN_DIR', $binDirectory, 'Machine')

& $UvExecutable python install 3.11
if ($LASTEXITCODE -ne 0) { throw 'uv could not install Python 3.11.' }

$webUiExecutable = Join-Path $binDirectory 'open-webui.exe'
if (-not (Test-Path -LiteralPath $webUiExecutable)) {
    & $UvExecutable tool install --python 3.11 'open-webui@latest'
    if ($LASTEXITCODE -ne 0) { throw 'uv could not install Open WebUI.' }
}
else {
    Write-Host "Open WebUI is already installed at $webUiExecutable" -ForegroundColor Yellow
}

icacls $InstallRoot /grant '*S-1-5-19:(OI)(CI)M' /T | Out-Null
icacls $logDirectory /grant '*S-1-5-19:(OI)(CI)M' /T | Out-Null

$existingService = Get-Service -Name OpenWebUI -ErrorAction SilentlyContinue
if ($existingService) {
    throw 'The OpenWebUI service already exists. This installer will not overwrite it. Inspect or remove the existing service deliberately first.'
}

& $NssmExecutable install OpenWebUI $webUiExecutable 'serve --host 127.0.0.1 --port 8080'
if ($LASTEXITCODE -ne 0) { throw 'NSSM could not install the OpenWebUI service.' }

& $NssmExecutable set OpenWebUI ObjectName 'NT AUTHORITY\LocalService'
& $NssmExecutable set OpenWebUI AppDirectory $InstallRoot
& $NssmExecutable set OpenWebUI AppEnvironmentExtra `
    "DATA_DIR=$dataDirectory" `
    'OLLAMA_BASE_URL=http://127.0.0.1:11434' `
    'UVICORN_WORKERS=1' `
    'DEFAULT_USER_ROLE=pending' `
    'ENABLE_SIGNUP=true' `
    'ENABLE_API_KEYS=true' `
    'USER_PERMISSIONS_FEATURES_API_KEYS=false'
& $NssmExecutable set OpenWebUI AppStdout (Join-Path $logDirectory 'open-webui.log')
& $NssmExecutable set OpenWebUI AppStderr (Join-Path $logDirectory 'open-webui-error.log')
& $NssmExecutable set OpenWebUI AppRestartDelay 5000
& $NssmExecutable set OpenWebUI AppPriority BELOW_NORMAL_PRIORITY_CLASS
& $NssmExecutable set OpenWebUI Start SERVICE_DELAYED_AUTO_START

Start-Service OpenWebUI

$deadline = (Get-Date).AddSeconds(60)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8080' -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            $ready = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    throw "Open WebUI did not become ready within 60 seconds. Inspect C:\AI\Logs\open-webui-error.log."
}

Assert-PrivateAILoopbackOnly -Port 8080 -ServiceName 'Open WebUI'
Write-Host 'Open WebUI is running at http://127.0.0.1:8080 and is not exposed to the LAN.' -ForegroundColor Green
Write-Host 'Create the first administrator account locally, then run 30-enable-tailscale.ps1.' -ForegroundColor Green
