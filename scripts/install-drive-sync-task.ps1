$ErrorActionPreference = "Stop"
$taskName = "Local RAG Google Drive Sync"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$syncScript = Join-Path $projectRoot "scripts\run-drive-sync.ps1"
$envFile = Join-Path $projectRoot ".env"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $syncScript)) {
    throw "Drive sync script not found: $syncScript"
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Create .env before installing the Drive sync task."
}
$folderSetting = Get-Content -LiteralPath $envFile |
    Where-Object { $_ -match '^\s*GOOGLE_DRIVE_FOLDER_URL\s*=' } |
    Select-Object -Last 1
if (-not $folderSetting) {
    throw "Add GOOGLE_DRIVE_FOLDER_URL to .env before installing this task."
}

$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$syncScript`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours 6)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $taskName `
    -Description "Synchronizes the shared Google Drive knowledge archive into Local RAG every six hours." `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User $currentUser `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Installed Drive sync task: $taskName" -ForegroundColor Green
Write-Host "The first sync starts in about two minutes, then repeats every six hours."
