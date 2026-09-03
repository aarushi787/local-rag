# Local RAG API

This Windows-friendly service combines local Ollama models with Neon PostgreSQL
and pgvector. It supports background document extraction, parent-child
structural chunking, hybrid MMR retrieval with neighboring context,
CPU-conscious reranking, grounded citations, streaming, and speed metrics.

The included React interface adds saved conversations, document upload,
citations, queue status, model selection, stop-generation controls, and a
responsive layout for laptops, tablets, and phones.

The interface includes an Auto mode that routes simple prompts to Fast, normal
questions to Balanced, and complex analysis to Quality. Fast uses
`gemma3:1b-it-qat`, Balanced uses `qwen3:1.7b`, and Quality uses the configured
Gemma model. A knowledge selector can search every document or restrict retrieval
to one selected document. Repeated questions can be served from a checksum-aware
answer cache when the accessible documents have not changed.

## What is stored

`rag_documents` is the source record. It stores the filename, SHA-256 checksum,
media type, status, page/chunk counts, full extracted text, and timestamps.

`rag_chunk_parents` stores larger page and section context. `rag_chunks` stores
smaller searchable child chunks, 768-dimensional vectors, chunk hashes, source
metadata, section titles, page numbers, bounding boxes, and keyword-search data.
The HNSW vector index and GIN text index support hybrid retrieval. MMR removes
near-duplicate results, then parent and neighboring chunks restore useful context.

## Install

```powershell
.\.venv-rag\Scripts\Activate.ps1
python -m pip install -r .\requirements-rag.txt

Set-Location .\frontend
npm.cmd install
npm.cmd run build
Set-Location ..
```

Image and scanned-PDF OCR uses the existing `.venv-ocr` environment. If it is
somewhere else, set `OCR_PYTHON` to its full `python.exe` path.
Large images are resized to a 2600-pixel working copy for CPU OCR while citation
boxes are converted back to the original image coordinates. Change
`OCR_MAX_SIDE` only after testing memory use and OCR accuracy.

## Start

### Window 1: Ollama

```powershell
$env:OLLAMA_HOST = "127.0.0.1:8080"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:OLLAMA_NUM_PARALLEL = "1"
ollama serve
```

### Window 2: FastAPI

Paste the actual pooled Neon URL. Never share that value because it contains
the database password.

```powershell
Set-Location "C:\Users\Aarushi Gupta\Documents\ChatGPT\LLM Project"
.\.venv-rag\Scripts\Activate.ps1

$env:DATABASE_URL = Read-Host "Paste the actual Neon pooled connection URL"
$env:RAG_API_KEY = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
$env:RAG_API_KEY
$env:REQUIRE_API_KEY = "true"
$env:RUN_MIGRATIONS = "true"

uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Starting the server applies the new schema and safely attaches existing chunks
to document records. Keep this window open. Keep the generated API key for calls
from another PowerShell window; alternatively store settings in a local `.env`
file, which is excluded by `.gitignore`.

Open the interactive documentation at <http://127.0.0.1:8000/docs>.
Open the chat interface at <http://127.0.0.1:8000/>. On first use, paste the
same `RAG_API_KEY` into the Connection dialog. The browser keeps it in session
storage and clears it when that browser session ends.

For later starts, create `.env` from `.env.example`. Replace the complete
example `DATABASE_URL` value with the pooled connection string shown by Neon
under **Connect**. It normally contains the Neon host, username, password,
database name, and `sslmode=require`. Never paste that connection string into
chat, screenshots, source control, or frontend code.

Then use:

```powershell
.\scripts\start-local-rag.ps1
```

## Private access from your other devices

Install Tailscale on the server laptop and on each approved phone or computer,
then sign them into the same private network. With the API running, execute the
following once on the server laptop:

```powershell
.\scripts\enable-tailscale-access.ps1
```

The final command prints the private HTTPS address. Open that address on an
approved device and enter the API key. This setup keeps Ollama, Neon
credentials, and FastAPI bound to localhost; only the Tailscale HTTPS proxy is
reachable through your private network. Do not expose ports 8000 or 8080 on
your router.

For a first test on the same Wi-Fi network only, you can instead start Uvicorn
with `--host 0.0.0.0`, allow TCP port 8000 through Windows Firewall for the
Private profile, and browse to the server laptop's LAN address. Tailscale is
the recommended long-term route because it avoids router port forwarding.

## Verify health

```powershell
curl.exe "http://127.0.0.1:8000/health"
```

The response reports Ollama, Neon, stored document/chunk counts, reranking, and
API-key status. It also reports model warm-up and query-vector cache status.

## Upload a document

Supported formats: TXT, Markdown, CSV, JSON, PDF, DOCX, XLSX, PNG, JPG, and JPEG.

Set the same API key in the calling PowerShell window, then upload:

```powershell
$env:RAG_API_KEY = "PASTE_THE_KEY_FROM_THE_SERVER_WINDOW"

curl.exe -X POST "http://127.0.0.1:8000/v1/documents/upload" -H "X-API-Key: $env:RAG_API_KEY" -F "file=@C:\Users\Aarushi Gupta\Downloads\Vector .png" -F "source=Vector RAG Diagram"
```

For an updated file with the same source, add `-F "replace=true"` to that
command.

The interface and `POST /v1/ingestion-jobs` endpoint process uploads in the
background and report extraction, chunking, embedding, and saving progress. The
pipeline preserves real PDF/image page numbers, creates chunks and vectors
locally, and stores the result in Neon. Uploading the same bytes again completes
immediately without rerunning OCR or recomputing embeddings.

## Synchronize the Google Drive archive

Google Drive remains the source of truth, while Neon stores the searchable
vectors, document records, permissions, and citations. Configure the shared
folder in `.env`:

```dotenv
GOOGLE_DRIVE_FOLDER_URL=https://drive.google.com/drive/folders/105kcn3EBPbTF8Iy5JkWudlG7FUMmeGps
```

Preview the files exposed by the sharing link:

```powershell
.\.venv-rag\Scripts\python.exe .\drive_sync.py --discover-only
```

Start or resume the full sync:

```powershell
.\scripts\run-drive-sync.ps1
```

The worker resumes Drive downloads, safely extracts supported files from ZIP
archives, removes byte-identical duplicates, and submits one ingestion job at a
time. Smaller structured JSON and spreadsheet sources are indexed first, while
CPU-intensive image OCR runs afterward. Its local manifest contains checksums
and document IDs, never the API key.
Interrupted runs can be restarted without repeating completed OCR work.

## Answer quality safeguards

The API combines semantic vectors with keyword retrieval, exact identifier
matching, reranking, MMR diversity, and neighboring chunks. Broad questions
automatically retrieve more evidence, while context packing prevents a small
local model from being overloaded. Follow-up questions use the recent user turn
to resolve phrases such as "that record" or "its status". Cached answers include
`RAG_PIPELINE_VERSION`; increase this value after materially changing retrieval
or prompting so older answers cannot hide an improvement.

To synchronize changes every six hours:

```powershell
.\scripts\install-drive-sync-task.ps1
```

Remove only the periodic sync task with
`.\scripts\remove-drive-sync-task.ps1`. Downloaded and extracted files remain in
`.drive-cache` so later runs can resume efficiently.

## List document records

```powershell
curl.exe "http://127.0.0.1:8000/v1/documents" -H "X-API-Key: $env:RAG_API_KEY"
```

## Ask a grounded question

```powershell
$headers = @{ "X-API-Key" = $env:RAG_API_KEY }
$body = @{
    model = "gemma4:e2b-it-qat"
    messages = @(
        @{
            role = "user"
            content = "How does the system use vectors to answer a question?"
        }
    )
    stream = $false
    max_tokens = 200
} | ConvertTo-Json -Depth 6

$response = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/v1/chat/completions" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body

$response.choices[0].message.content
$response.sources | Format-Table filename, page_number, chunk_index, similarity, rerank_score
$response.metrics | Format-List
```

Each source includes the document ID, filename, page number, chunk number,
bounding box when available, a supporting quote, similarity, and rerank score.

## Run retrieval evaluation

The included dataset has 20 questions for the existing `Local LLMs for RAG`
document. It measures source hit rate, evidence hit rate, and reciprocal rank.

```powershell
python .\evaluate_retrieval.py
```

For a quick smoke test:

```powershell
python .\evaluate_retrieval.py --limit 2
```

Edit `evaluation_questions.jsonl` as real company documents are added. Expected
sources and evidence terms should be verified by a person, not generated from
the model's answers.

Administrators can also open **Evaluations** in the interface, start the suite
in the background, and inspect Top 1, Top 3, evidence hit rate, MRR, latency,
progress, and per-question results.

## Benchmark response modes

Run each installed profile against the same grounded question:

```powershell
python .\benchmark_profiles.py --runs 1 --max-tokens 60
```

The report compares end-to-end time, retrieval time, and generation speed. The
first request after switching models includes model-loading time; repeat with
`--runs 2` to see warm performance.

## Security and Neon permissions

The master `RAG_API_KEY` maps to the administrator account. In **Access**, an
administrator can create user keys and grant read access to individual
documents. Raw user keys are displayed only once; Neon stores only their
SHA-256 hashes. Conversations and document searches are restricted to the
authenticated user and their document permissions.

Use `sql\neon_least_privilege.sql` to create a restricted runtime role. Apply
migrations once with the Neon owner URL. Then switch `DATABASE_URL` to the
restricted role's pooled URL and set:

```powershell
$env:RUN_MIGRATIONS = "false"
```

The runtime role can read and update RAG records but cannot create extensions,
drop tables, or manage database roles.

## Start automatically with Windows

Register a per-user Scheduled Task that starts the API after sign-in:

```powershell
.\scripts\install-startup-task.ps1
```

The task uses the project's `.env`, runs with limited privileges, restarts after
failure, and hides the PowerShell window. Remove it with:

```powershell
.\scripts\remove-startup-task.ps1
```

## Endpoints

- `GET /health` — Ollama, Neon, database counts, and security status
- `GET /health/live` — process liveness
- `GET /health/ready` — dependency readiness
- `GET /v1/models` — OpenAI-compatible Ollama model list
- `GET /v1/profiles` — Auto, Fast, Balanced, and Quality mode settings
- `GET /v1/me` — current authenticated user and role
- `GET/POST /v1/users` — list or create users (administrator only)
- `DELETE /v1/users/{id}` — deactivate a user (administrator only)
- `GET /v1/queue` — current inference workload
- `POST /v1/chat/cancel/{request_id}` — stop an active or waiting generation
- `GET/POST /v1/conversations` — list or create saved conversations
- `GET/DELETE /v1/conversations/{id}` — read or remove a conversation
- `GET /v1/documents` — document inventory and ingestion status
- `POST /v1/documents` — ingest supplied plain text
- `POST /v1/documents/upload` — automatically process supported files
- `PUT /v1/documents/{id}/permissions` — grant document access
- `DELETE /v1/documents/{id}` — remove a document and its chunks
- `GET/POST /v1/ingestion-jobs` — inspect or create background ingestion jobs
- `GET/POST /v1/evaluations` — inspect or start retrieval evaluations
- `POST /v1/chat/completions` — hybrid RAG chat with optional SSE streaming

`POST /v1/chat/completions` also accepts optional `profile` and `document_id`
fields. Clients that omit them remain compatible with the original API.

Protected endpoints require `X-API-Key` when `RAG_API_KEY` is configured.

## Performance profile

The launcher keeps one generation request active at a time but permits two
Ollama models to remain in memory. This lets `embeddinggemma` and the selected
Gemma generator stay resident together on a 32 GB machine. Neon connections
are pooled, recent chat history is bounded for the 2K prompt context, and model
weights remain loaded for 30 minutes after use. The first request after a full
Ollama restart is a cold start; following requests are substantially faster.
