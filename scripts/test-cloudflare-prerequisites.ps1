param(
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "cloudflare-common.ps1")
$cloudflared = Resolve-Cloudflared

$envFile = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "The project .env file is missing. Copy .env.example to .env and configure it first."
}

if ($ConfigPath -and -not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Cloudflare Tunnel config was not found at: $ConfigPath"
}

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/ready" -TimeoutSec 10
}
catch {
    throw "Local RAG is not ready at http://127.0.0.1:8000. Start it before starting the tunnel."
}

$version = (& $cloudflared version 2>&1 | Select-Object -First 1)
[pscustomobject]@{
    Cloudflared = $version
    LocalRag = $health.status
    Config = if ($ConfigPath) { (Resolve-Path -LiteralPath $ConfigPath).Path } else { "not checked" }
}
