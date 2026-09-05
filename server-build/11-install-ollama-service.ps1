#Requires -RunAsAdministrator
param(
    [string]$OllamaExecutable = 'C:\AI\Ollama\ollama.exe',
    [string]$NssmExecutable = 'C:\AI\bin\nssm.exe',
    [string]$ModelDirectory = 'C:\AI\Models',
    [switch]$ConfirmCutover,
    [switch]$AllowNonTargetHost
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\PrivateAI.Common.ps1')

Assert-PrivateAIAdministrator
Assert-PrivateAITargetServer -AllowNonTargetHost:$AllowNonTargetHost | Out-Null

if (-not $ConfirmCutover) {
    throw 'This cutover stops the tray-based Ollama process. Rerun in a maintenance window with -ConfirmCutover.'
}
if (-not (Test-Path -LiteralPath $OllamaExecutable)) {
    throw "Standalone Ollama was not found at '$OllamaExecutable'. Extract the official ollama-windows-amd64.zip there first."
}
if (-not (Test-Path -LiteralPath $NssmExecutable)) {
    throw "NSSM was not found at '$NssmExecutable'."
}
if (Get-Service -Name Ollama -ErrorAction SilentlyContinue) {
    throw 'An Ollama Windows service already exists. This script will not overwrite it.'
}

New-Item -ItemType Directory -Force $ModelDirectory, 'C:\AI\Logs' | Out-Null
icacls $ModelDirectory /grant '*S-1-5-19:(OI)(CI)M' /T | Out-Null
icacls 'C:\AI\Logs' /grant '*S-1-5-19:(OI)(CI)M' /T | Out-Null

$runningOllama = @(Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match '^ollama' })
if ($runningOllama.Count -gt 0) {
    Write-Warning 'Stopping the existing Ollama application. Active AI requests will be interrupted; Tally is not touched.'
    $runningOllama | Stop-Process -Force
    Start-Sleep -Seconds 2
}

$remainingListener = Get-PrivateAIListener -Port 11434
if ($remainingListener.Count -gt 0) {
    throw 'TCP port 11434 is still occupied. Resolve the listener before installing the service.'
}

& $NssmExecutable install Ollama $OllamaExecutable 'serve'
if ($LASTEXITCODE -ne 0) { throw 'NSSM could not install the Ollama service.' }

& $NssmExecutable set Ollama ObjectName 'NT AUTHORITY\LocalService'
& $NssmExecutable set Ollama AppDirectory (Split-Path -Parent $OllamaExecutable)
& $NssmExecutable set Ollama AppEnvironmentExtra `
    'OLLAMA_HOST=127.0.0.1:11434' `
    "OLLAMA_MODELS=$ModelDirectory" `
    'OLLAMA_NUM_PARALLEL=1' `
    'OLLAMA_MAX_LOADED_MODELS=1' `
    'OLLAMA_CONTEXT_LENGTH=4096' `
    'OLLAMA_KEEP_ALIVE=2m' `
    'OLLAMA_MAX_QUEUE=4'
& $NssmExecutable set Ollama AppStdout 'C:\AI\Logs\ollama.log'
& $NssmExecutable set Ollama AppStderr 'C:\AI\Logs\ollama-error.log'
& $NssmExecutable set Ollama AppRestartDelay 5000
& $NssmExecutable set Ollama AppPriority BELOW_NORMAL_PRIORITY_CLASS
& $NssmExecutable set Ollama AppNoConsole 1
& $NssmExecutable set Ollama Start SERVICE_DELAYED_AUTO_START

Start-Service Ollama
$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Seconds 1
    $listeners = Get-PrivateAIListener -Port 11434
} while ($listeners.Count -eq 0 -and (Get-Date) -lt $deadline)

try {
    Assert-PrivateAILoopbackOnly -Port 11434 -ServiceName 'Ollama'
    Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 | Out-Null
}
catch {
    Stop-Service Ollama -ErrorAction SilentlyContinue
    throw "Ollama service validation failed and the service was stopped. $($_.Exception.Message)"
}

Write-Host 'Ollama now runs as a delayed-auto-start, below-normal-priority service on loopback only.' -ForegroundColor Green
