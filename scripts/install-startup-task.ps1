$ErrorActionPreference = "Stop"
$taskName = "Local RAG Server"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startScript = Join-Path $projectRoot "scripts\start-local-rag.ps1"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $startScript)) {
    throw "Start script not found: $startScript"
}

$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $taskName `
    -Description "Starts the private Local RAG API and Ollama after sign-in." `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User $currentUser `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Installed startup task: $taskName" -ForegroundColor Green
Write-Host "It will start Local RAG automatically when $currentUser signs in."
