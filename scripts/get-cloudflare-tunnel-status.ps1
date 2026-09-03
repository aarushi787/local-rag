param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$TunnelName,

    [string]$PublicHostname = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "cloudflare-common.ps1")
$cloudflared = Resolve-Cloudflared

Write-Host "Cloudflare connectors:" -ForegroundColor Cyan
& $cloudflared tunnel info $TunnelName
if ($LASTEXITCODE -ne 0) {
    throw "Could not read status for tunnel '$TunnelName'."
}

if ($PublicHostname) {
    $uri = "https://$($PublicHostname.Trim().TrimEnd('/'))/health/live"
    try {
        $response = Invoke-WebRequest -Uri $uri -Method Get -TimeoutSec 15 -UseBasicParsing
        Write-Host "Public endpoint: HTTP $($response.StatusCode) $uri" -ForegroundColor Green
    }
    catch {
        Write-Warning "The public health request did not succeed. If Cloudflare Access protects the hostname, an unauthenticated response or redirect is expected."
    }
}
