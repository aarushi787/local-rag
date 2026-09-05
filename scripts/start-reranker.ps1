param(
    [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot),
    [int]$Port = 8091
)

$ErrorActionPreference = 'Stop'
$python = Join-Path $ProjectPath '.venv-reranker\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Reranker environment not found. Create .venv-reranker and install requirements-reranker.txt first."
}
Set-Location -LiteralPath $ProjectPath
& $python -m uvicorn reranker_service:app --host 127.0.0.1 --port $Port
