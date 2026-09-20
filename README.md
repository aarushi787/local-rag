# Local RAG API

> **Phase 1 safety changes:** See [baseline, verification and deployment handoff](docs/PHASE1_HANDOFF.md).
> Anonymous administration is disabled, migrations default to off, and replacement
> keeps the document ID/permissions in one activation transaction. These changes
> have not been deployed or verified against the live database.

> **New user?** See [Setup and access from any device](USER_SETUP_GUIDE.md) for browser access, personal keys, private remote/LAN access, Windows installation and troubleshooting. The guide distinguishes the current custom app from the separate Open WebUI build kit.

> **Xeon server deployment:** The guarded Windows Server 2025 build kit for
> Ollama + Open WebUI is in [`server-build/`](server-build/README.md). It is
> intentionally isolated from this laptop application because the two stacks
> use different ports and service layouts.

This Windows-friendly service combines local Ollama models with Neon PostgreSQL
and pgvector. It supports background document extraction, parent-child
structural chunking, hybrid MMR retrieval with neighboring context,
CPU-conscious reranking, grounded citations, streaming, and speed metrics.

The included React interface adds saved conversations, document upload,
citations, queue status, model selection, stop-generation controls, and a
responsive layout for laptops, tablets, and phones.

When `AUTO_MODEL_ROUTING=true`, Auto mode routes simple prompts to Fast, normal
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
$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:OLLAMA_NUM_PARALLEL = "1"
ollama serve
```

### Window 2: FastAPI

For a new installation only, create a private `.env` from `.env.example` without
overwriting an existing file. Configure the intended runtime database URL and a
secure random ASCII `RAG_API_KEY` of at least 32 characters. Do not rotate an
existing key as part of routine startup. `REQUIRE_API_KEY=false` no longer permits
anonymous access. Never share the connection URL or key.

**Schema changes are a separate, explicit maintenance operation.** A new empty
database must be initialized first using an owner connection in a separate
PowerShell session. For an existing database, obtain approval and a tested backup
before running `app.initialize_database()`; its existing migration runner uses
autocommit, so an interrupted migration is not automatically rolled back. Follow
the [Phase 1 bootstrap and grants instructions](docs/PHASE1_HANDOFF.md).

Start normally with the runtime connection from `.env`, not the migration-owner
connection. The following does not rotate keys or apply migrations:

```powershell
Set-Location "C:\Users\Aarushi Gupta\Documents\ChatGPT\LLM Project"
.\.venv-rag\Scripts\Activate.ps1

$env:RUN_MIGRATIONS = "false"

uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Keep this window open. The private `.env` is excluded by `.gitignore`.
Starting with missing/weak administrator credentials fails closed.

Open the interactive documentation at <http://127.0.0.1:8000/docs>.
Open the chat interface at <http://127.0.0.1:8000/>. On first use, paste the
same `RAG_API_KEY` into the Connection dialog. The dialog also accepts a
different HTTPS server address, which lets one deployed frontend connect to a
secondary laptop. The browser keeps the API key in session storage and clears
it when that browser session ends. The server address is stored locally on that
device.

The frontend renders Markdown and expandable citations with
filename, page, and relevance. It supports stop, regenerate, edit-and-resend,
copy, conversation search/rename/delete/export, drag-and-drop uploads, ingestion
progress, document search/filter/delete, response profiles, component status,
latency metrics, keyboard shortcuts, per-user access, and light/dark responsive
layouts. Retrieval internals and the evaluation dashboard remain administrator-only.
With strict grounded-answer validation enabled, answer text is buffered until
validation finishes. Streaming status events are not a promise of immediate text.

## Build or deploy the frontend

For the simplest private deployment, let FastAPI serve `frontend/dist` and use
the Tailscale HTTPS address described below. This keeps the webpage and API on
the same origin and requires no separate frontend host.

To rebuild after frontend changes:

```powershell
Set-Location .\frontend
npm.cmd install
npm.cmd run build
Set-Location ..
```

For separate static hosting, optionally set `VITE_API_URL` before building, or
enter the server address at runtime in the Connection dialog. Add the exact
frontend HTTPS origin to `ALLOWED_ORIGINS` in the server `.env`. Never place
`DATABASE_URL` or `RAG_API_KEY` in `VITE_*` variables because those values are
visible in the browser bundle.

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

## Run retrieval and answer-quality evaluation

The versioned dataset contains expected documents, pages or sections, required
facts, and refusal expectations. It measures Recall@1/3/5, MRR, evidence hits,
citations, grounded answers, unsupported claims, refusals, latency, generation
speed, and cache hits.

```powershell
python .\evaluate_retrieval.py --pipeline upgraded
python .\evaluate_retrieval.py --pipeline baseline
```

For a quick smoke test:

```powershell
python .\evaluate_retrieval.py --limit 2
```

Edit `evaluation_questions.jsonl` as real company documents are added. Expected
sources and evidence terms should be verified by a person, not generated from
the model's answers.

Administrators can open **Evaluations** in the interface and run the retained
semantic-only baseline or the complete upgraded pipeline against exactly the
same questions. The full upgraded run generates answers and is deliberately
slow on CPU.

## Customize Gemma safely

The recommended prompt-only profile is in `models\Modelfile.gemma-rag`:

```powershell
$env:OLLAMA_HOST = "127.0.0.1:11434"
ollama create local-rag-gemma -f .\models\Modelfile.gemma-rag
```

This profile uses the installed Gemma model, a 2048-token context, low
temperature, citation rules, and explicit insufficient-evidence refusal. It does
not modify model weights.

Optional LoRA preparation is documented in `training\README.md`. Only
administrator-approved conversations can be exported. The export pipeline
redacts common credentials and personal identifiers and creates deterministic
train, validation, and held-out test JSONL files for mandatory human review.
Training is never started automatically and must use the original
`google/gemma-3-1b-it` checkpoint, not an Ollama Q4/QAT model.

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

## Publish safely with a named Cloudflare Tunnel

Use a named tunnel for production. Keep FastAPI bound to `127.0.0.1:8000`;
Cloudflare Tunnel makes the outbound connection, so do not open port 8000 on
the router or Windows Firewall. Quick Tunnels are suitable only for temporary
testing and are not part of this deployment.

Before the account-specific setup, install the official signed `cloudflared`
binary inside the project, start Local RAG, and run the local preflight check:

```powershell
.\scripts\install-cloudflared.ps1
.\scripts\test-cloudflare-prerequisites.ps1
```

Then complete the account-owned steps manually. These commands open a browser
and create Cloudflare credentials, so they must not be automated or committed:

```powershell
.\tools\cloudflared.exe tunnel login
.\tools\cloudflared.exe tunnel create local-rag
.\tools\cloudflared.exe tunnel route dns local-rag rag.example.com
```

Copy `cloudflare\config.example.yml` to
`$env:USERPROFILE\.cloudflared\config.yml`, replace the tunnel UUID,
credentials path, and hostname, then validate and start it:

```powershell
.\scripts\test-cloudflare-prerequisites.ps1 `
    -ConfigPath "$env:USERPROFILE\.cloudflared\config.yml"

.\scripts\start-cloudflare-tunnel.ps1 `
    -TunnelName "local-rag" `
    -ConfigPath "$env:USERPROFILE\.cloudflared\config.yml"
```

For automatic startup after Windows sign-in:

```powershell
.\scripts\install-cloudflare-tunnel-task.ps1 `
    -TunnelName "local-rag" `
    -ConfigPath "$env:USERPROFILE\.cloudflared\config.yml"

.\scripts\get-cloudflare-tunnel-status.ps1 `
    -TunnelName "local-rag" `
    -PublicHostname "rag.example.com"
```

Remove only the scheduled task with
`.\scripts\remove-cloudflare-tunnel-task.ps1`. The removal script deliberately
keeps the tunnel configuration and credentials so recovery is straightforward.

In Cloudflare Zero Trust, create a self-hosted Access application for the exact
hostname. Add an Allow policy containing only approved email addresses or your
company email domain, and choose a short session duration such as eight hours.
Keep `X-API-Key` enabled in Local RAG as a second application-level check.

Production `.env` example:

```dotenv
REQUIRE_API_KEY=true
ALLOWED_ORIGINS=https://rag.example.com
ALLOWED_HOSTS=127.0.0.1,localhost,rag.example.com
PUBLIC_BASE_URL=https://rag.example.com
REQUEST_TIMEOUT_SECONDS=360
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

Use only exact HTTPS origins. The server rejects wildcard CORS configuration,
adds browser security headers, enforces request-size and request-time limits,
and rate-limits `/v1` traffic without storing or logging raw API keys. Avoid
`debug` tunnel logging because request headers may contain authentication data.

## Endpoints

- `GET /health` — Ollama, Neon, database counts, and security status
- `GET /health/live` — process liveness
- `GET /health/ready` — dependency readiness
- `GET /v1/models` — OpenAI-compatible Ollama model list
- `GET /v1/profiles` — Auto, Fast, Balanced, and Quality mode settings
- `GET /v1/me` — current authenticated user and role
- `GET/POST /v1/users` — list or create users (administrator only)
- `POST /v1/users/{id}/rotate-key` — invalidate and replace a user's API key (administrator only)
- `PATCH /v1/users/{id}/limits` — set per-account RPM, concurrency, model allowlist, expiry and active state
- `DELETE /v1/users/{id}` — deactivate a user (administrator only)
- `GET /v1/queue` — current inference workload
- `POST /v1/chat/cancel/{request_id}` — stop an active or waiting generation
- `GET/POST /v1/conversations` — list or create saved conversations
- `GET/PATCH/DELETE /v1/conversations/{id}` — read, rename, or remove a conversation
- `PUT /v1/conversations/{id}/training-approval` — approve export (administrator only)
- `GET /v1/documents` — document inventory and ingestion status
- `POST /v1/documents` — ingest supplied plain text
- `POST /v1/documents/upload` — automatically process supported files
- `PUT /v1/documents/{id}/permissions` — grant document access
- `PATCH /v1/documents/{id}/lifecycle` — activate, archive, or supersede a document version
- `DELETE /v1/documents/{id}` — remove a document and its chunks
- `GET/POST /v1/ingestion-jobs` — inspect or create background ingestion jobs
- `GET/POST /v1/evaluations` — inspect or start baseline/upgraded evaluations
- `GET /v1/metrics/summary` — administrator-only p50/p95 latency and throughput summary
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
Neon startup uses bounded retries and pool reconnection, ingestion is restricted
to a bounded single-worker lane by default, and logs are structured JSON without
request bodies or document content.

The full safety architecture, shadow-index procedure, cross-encoder staging,
evaluation gate, and restore drill are documented in
`HARDENING_RELEASE_2026-09-04.md`.



$adminKey = ((Get-Content .env | Where-Object { $_ -match '^RAG_API_KEY=' }) -replace '^RAG_API_KEY=', '').Trim()

$body = @{
    name = "Alice"
    role = "user"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/v1/users" `
    -Headers @{ "X-API-Key" = $adminKey } `
    -ContentType "application/json" `
    -Body $body
