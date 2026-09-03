$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv-rag\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The .venv-rag environment is missing."
}

try {
    $ready = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/ready" -TimeoutSec 3
}
catch {
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSScriptRoot\start-local-rag.ps1`"" `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden
    $ready = $null
    foreach ($attempt in 1..30) {
        Start-Sleep -Seconds 2
        try {
            $ready = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/ready" -TimeoutSec 3
            break
        }
        catch {
            $ready = $null
        }
    }
}

if (-not $ready -or $ready.status -notin @("ready", "healthy")) {
    throw "Local RAG did not become ready before the Drive sync timeout."
}

Set-Location -LiteralPath $projectRoot
& $python .\drive_sync.py
exit $LASTEXITCODE
