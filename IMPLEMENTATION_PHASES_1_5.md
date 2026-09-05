# Local RAG Improvement Implementation

## Architecture

```text
Phone / laptop browser
        |
        | HTTPS through LAN, Tailscale, or the existing tunnel
        v
FastAPI RAG API :8000
        |-- account/API-key and document permissions
        |-- intent router and query rewrite
        |-- answer cache keyed by corpus version
        |-- hybrid retrieval + rerank + MMR
        |-- batched parent/neighbor evidence lookup
        |-- grounding prompt and streaming status
        |
        +---- PostgreSQL 16 + pgvector :5432 (localhost only)
        |
        +---- Ollama chat :11434 (localhost only)
        |
        `---- Ollama embeddings :11435 (optional dedicated process, localhost only)
```

Only port 8000 belongs behind the authenticated access layer. Ports 5432, 11434,
and 11435 must remain bound to `127.0.0.1`.

## Phase 1: latency and stability

Implemented:

- Context enrichment uses one SQL request for all selected chunks instead of one request per chunk.
- Answer-cache invalidation reads one corpus version instead of scanning every document checksum.
- Auto mode remains on `CHAT_MODEL` unless `AUTO_MODEL_ROUTING=true` is explicitly selected.
- `EMBEDDING_OLLAMA_URL` allows embeddings to stay in a separate Ollama process.
- Response metrics now separate cache, query embedding, hybrid SQL, rerank/MMR,
  context enrichment, context packing, model load, first-token, and total time.
- Streaming emits `rag.status` events for search and generation.

Start the optional embedding process:

```powershell
.\scripts\start-embedding-ollama.ps1
```

Then set this in `.env` and restart the API:

```dotenv
EMBEDDING_OLLAMA_URL=http://127.0.0.1:11435
```

On an 8 GB laptop, first test this with the Fast 1B model and watch committed
memory. On the 32 GB Xeon server it is the recommended arrangement.

## Phase 2: retrieval and answer quality

Implemented deterministic routes for conversation, summary, exact identifiers,
comparison, aggregation, and normal factual questions. Comparisons search each
side independently. Aggregation requests retrieve a broader evidence set and the
prompt prohibits claiming completeness unless the evidence proves it.

Long parent/neighbor context is reduced by query relevance while retaining
section titles and exact-record excerpts. The current CPU-light reranker remains
the safe default. A cross-encoder should be introduced only after a measured A/B
evaluation on the Xeon because it adds RAM and latency.

## Phase 3: local private database

The current `.env` still points to Neon. The following migration is intentionally
not automatic: changing a production document store requires an acceptance test
and a rollback path.

1. Copy the local database configuration and set a unique password.

```powershell
Copy-Item .\local-infrastructure\.env.example .\local-infrastructure\.env
notepad .\local-infrastructure\.env
```

2. If Docker/WSL2 is supported on the host, start local PostgreSQL/pgvector.

```powershell
docker compose --env-file .\local-infrastructure\.env `
  -f .\local-infrastructure\docker-compose.yml up -d
```

3. Stop document ingestion for the migration window. Create a backup and restore
   into a new, empty local database. This operation never deletes or edits Neon.

```powershell
.\scripts\migrate-postgres-to-local.ps1 `
  -SourceUrl $env:NEON_DATABASE_URL `
  -TargetUrl $env:LOCAL_DATABASE_URL
```

4. Change `DATABASE_URL` only after document and chunk counts match. Restart,
   check `/health`, run retrieval evaluation, and run the latency benchmark.

5. Rollback is simply restoring the previous `DATABASE_URL` and restarting the
   API. Keep Neon unchanged until the local system has passed acceptance testing
   and at least one local backup has been restored successfully.

## Phase 4: grounding prompt

The application is now the single owner of RAG instructions. The custom Ollama
Modelfile no longer includes a second RAG system prompt. The dynamic prompt:

- treats document text as untrusted evidence;
- requires a citation after every factual claim;
- requires direct claim-to-source support;
- handles conflicts and partial answers explicitly;
- refuses unsupported questions with a fixed phrase;
- forbids unsupported completeness claims for totals and lists.

Recreate the custom model after changing its Modelfile, if that model is used:

```powershell
ollama create gemma-rag -f .\models\Modelfile.gemma-rag
```

## Phase 5: evaluation and release gates

The answer scorer now recognizes both supported refusal phrases and checks lexical
and numeric support between cited claims and their cited evidence excerpt. Refusal
examples are no longer included in the standalone retrieval denominator.

Run tests and measurements:

```powershell
.\.venv-rag\Scripts\python.exe -m unittest test_rag.py
.\.venv-rag\Scripts\python.exe evaluate_retrieval.py
.\.venv-rag\Scripts\python.exe .\scripts\benchmark-latency.py --profile fast --runs 3
```

Release targets:

| Metric | Initial gate |
|---|---:|
| Factual evidence Recall@5 | 90% or higher |
| Citation support precision | 95% or higher |
| Unsupported answer rate | 2% or lower |
| Correct refusal rate | 95% or higher |
| Fast first token, p95 | under 5 seconds on laptop; under 3 seconds on Xeon target |
| Fast short answer, p95 | under 10 seconds |
| Timeout rate | 0% |

Do not promote a new embedding model, reranker, chunking policy, or prompt unless
it passes the same fixed evaluation set and does not regress latency outside the
agreed budget.

