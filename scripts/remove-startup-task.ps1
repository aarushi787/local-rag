$ErrorActionPreference = "Stop"
$taskName = "Local RAG Server"

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Startup task is not installed."
    return
}

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host "Removed startup task: $taskName" -ForegroundColor Green
