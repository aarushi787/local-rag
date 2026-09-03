param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$TunnelName,

    [string]$ConfigPath = (Join-Path $env:USERPROFILE ".cloudflared\config.yml"),

    [string]$TaskName = "Local RAG Cloudflare Tunnel"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startScript = Join-Path $projectRoot "scripts\start-cloudflare-tunnel.ps1"
. (Join-Path $PSScriptRoot "cloudflare-common.ps1")
$null = Resolve-Cloudflared
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Cloudflare Tunnel config was not found at: $ConfigPath"
}

$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScript`" -TunnelName `"$TunnelName`" -ConfigPath `"$resolvedConfig`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Starts the named Cloudflare Tunnel for Local RAG after sign-in." -Force | Out-Null
Write-Host "Installed scheduled task '$TaskName'. No tunnel token was stored in the task." -ForegroundColor Green
