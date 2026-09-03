$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv-rag\Scripts\python.exe"
$frontend = Join-Path $projectRoot "frontend"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The .venv-rag environment is missing. Follow the install section in README.md first."
}

$envFile = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Create .env from .env.example and add the Neon URL and API key first."
}

$databaseSetting = Get-Content -LiteralPath $envFile |
    Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } |
    Select-Object -Last 1
$apiKeySetting = Get-Content -LiteralPath $envFile |
    Where-Object { $_ -match '^\s*RAG_API_KEY\s*=' } |
    Select-Object -Last 1

if (-not $databaseSetting -or
    $databaseSetting -match 'HOST-pooler\.REGION|YOUR_NEON|USER:PASSWORD') {
    throw "DATABASE_URL in .env is still an example. Copy the real pooled connection string from Neon, replace the entire DATABASE_URL line, save the file, and run this script again."
}

if (-not $apiKeySetting -or $apiKeySetting -match 'REPLACE_WITH') {
    throw "RAG_API_KEY in .env is still an example. Replace it with a long random value and run this script again."
}

try {
    $live = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/live" -TimeoutSec 2
    if ($live.status -eq "alive") {
        Write-Host "Local RAG is already running at http://127.0.0.1:8000" -ForegroundColor Green
        return
    }
}
catch {
    $listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $ownerProcessId = if ($listener) { $listener.OwningProcess } else { $null }
    if (-not $ownerProcessId) {
        $netstatLine = netstat -ano -p tcp |
            Where-Object { $_ -match '^\s*TCP\s+127\.0\.0\.1:8000\s+\S+\s+LISTENING\s+(\d+)\s*$' } |
            Select-Object -First 1
        if ($netstatLine -and $netstatLine -match 'LISTENING\s+(\d+)\s*$') {
            $ownerProcessId = [int]$Matches[1]
        }
    }
    if ($ownerProcessId) {
        throw "Port 8000 is occupied by process $ownerProcessId, but it is not the current Local RAG server. Stop that process with: Stop-Process -Id $ownerProcessId -Force"
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $frontend "dist\index.html"))) {
    Push-Location $frontend
    try {
        npm.cmd install
        npm.cmd run build
    }
    finally {
        Pop-Location
    }
}

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/tags" -TimeoutSec 2 | Out-Null
}
catch {
    $env:OLLAMA_HOST = "127.0.0.1:8080"
    $env:OLLAMA_MAX_LOADED_MODELS = "2"
    $env:OLLAMA_NUM_PARALLEL = "1"
    $env:OLLAMA_KEEP_ALIVE = "30m"
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

Set-Location -LiteralPath $projectRoot
& $python -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
