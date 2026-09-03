$ErrorActionPreference = "Stop"
$taskName = "Local RAG Google Drive Sync"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Drive sync task is not installed."
    return
}
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host "Removed Drive sync task: $taskName" -ForegroundColor Green
