param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$TunnelName,

    [string]$ConfigPath = (Join-Path $env:USERPROFILE ".cloudflared\config.yml")
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "cloudflare-common.ps1")
$cloudflared = Resolve-Cloudflared
$preflight = Join-Path $PSScriptRoot "test-cloudflare-prerequisites.ps1"
& $preflight -ConfigPath $ConfigPath | Format-List
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path

Write-Host "Starting named Cloudflare Tunnel '$TunnelName'. Press Ctrl+C to stop it." -ForegroundColor Cyan
& $cloudflared tunnel --config $resolvedConfig --grace-period 60s --loglevel info run $TunnelName
if ($LASTEXITCODE -ne 0) {
    throw "cloudflared exited with code $LASTEXITCODE"
}
