$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$toolsDirectory = Join-Path $projectRoot "tools"
$destination = Join-Path $toolsDirectory "cloudflared.exe"
$temporary = Join-Path $toolsDirectory "cloudflared.download.exe"
$downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

New-Item -ItemType Directory -Path $toolsDirectory -Force | Out-Null
Invoke-WebRequest -Uri $downloadUrl -OutFile $temporary -UseBasicParsing

$signature = Get-AuthenticodeSignature -FilePath $temporary
if ($signature.Status -ne "Valid") {
    Remove-Item -LiteralPath $temporary -Force
    throw "The downloaded cloudflared executable does not have a valid Windows signature. It was removed."
}

Move-Item -LiteralPath $temporary -Destination $destination -Force
Write-Host "Installed the signed cloudflared executable inside this project." -ForegroundColor Green
& $destination version

