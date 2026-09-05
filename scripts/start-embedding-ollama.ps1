[CmdletBinding()]
param(
    [string]$ListenAddress = "127.0.0.1:11435"
)

$ErrorActionPreference = "Stop"
$ollama = (Get-Command ollama.exe -ErrorAction Stop).Source
$existing = Get-NetTCPConnection -LocalPort ([int]($ListenAddress.Split(':')[-1])) -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    throw "Port $ListenAddress is already listening. The embedding runtime may already be running."
}

$previousHost = $env:OLLAMA_HOST
try {
    $env:OLLAMA_HOST = $ListenAddress
    $process = Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden -PassThru
}
finally {
    if ($null -eq $previousHost) {
        Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue
    }
    else {
        $env:OLLAMA_HOST = $previousHost
    }
}

Start-Sleep -Seconds 2
try {
    Invoke-RestMethod -Uri "http://$ListenAddress/api/tags" -TimeoutSec 10 | Out-Null
}
catch {
    throw "Embedding Ollama process $($process.Id) started but did not become ready: $($_.Exception.Message)"
}

Write-Host "Embedding Ollama is ready at http://$ListenAddress (PID $($process.Id))."
Write-Host "Set EMBEDDING_OLLAMA_URL=http://$ListenAddress in .env and restart the RAG API."

