$ErrorActionPreference = "Stop"

if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    throw "Tailscale is not installed. Download it from https://tailscale.com/download/windows, install it, sign in from the system-tray icon, reopen PowerShell, and run this script again."
}

tailscale status
tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status
