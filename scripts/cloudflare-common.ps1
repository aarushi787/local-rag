function Resolve-Cloudflared {
    $command = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    $bundled = Join-Path $projectRoot "tools\cloudflared.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }

    throw "cloudflared is not installed. Run .\scripts\install-cloudflared.ps1 first."
}

