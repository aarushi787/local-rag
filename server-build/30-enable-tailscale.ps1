#Requires -RunAsAdministrator
param(
    [switch]$AllowNonTargetHost
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\PrivateAI.Common.ps1')

Assert-PrivateAIAdministrator
Assert-PrivateAITargetServer -AllowNonTargetHost:$AllowNonTargetHost | Out-Null
Assert-PrivateAILoopbackOnly -Port 11434 -ServiceName 'Ollama'
Assert-PrivateAILoopbackOnly -Port 8080 -ServiceName 'Open WebUI'

$tailscaleCommand = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $tailscaleCommand -and (Test-Path -LiteralPath 'C:\Program Files\Tailscale\tailscale.exe')) {
    $tailscaleCommand = Get-Item -LiteralPath 'C:\Program Files\Tailscale\tailscale.exe'
}
if (-not $tailscaleCommand) {
    throw 'Tailscale is not installed. Install it from https://tailscale.com/download/windows and sign in before running this script.'
}
$tailscalePath = Get-PrivateAICommandPath -CommandInfo $tailscaleCommand

& $tailscalePath status
if ($LASTEXITCODE -ne 0) {
    throw 'Tailscale is installed but not connected. Run tailscale up and complete authentication first.'
}

& $tailscalePath serve --bg --https=443 'http://127.0.0.1:8080'
if ($LASTEXITCODE -ne 0) { throw 'Tailscale Serve configuration failed.' }

& $tailscalePath serve status
if ($LASTEXITCODE -ne 0) { throw 'Could not verify Tailscale Serve status.' }

Write-Host 'Private HTTPS access is enabled through Tailscale. No router or Windows Firewall port was opened.' -ForegroundColor Green
