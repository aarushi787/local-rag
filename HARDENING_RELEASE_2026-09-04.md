# Local RAG hardening release — 2026-09-04

## Outcome

The serving pipeline is upgraded in place without switching the active embedding model or deleting existing data. The service remains localhost-only on port 8000, Ollama remains localhost-only on port 11434, and PostgreSQL holds 401 documents / 4,841 chunks at release verification time.

## Runtime architecture

```text
Phone / browser / API client
          |
          | HTTPS through Tailscale or Cloudflare; per-account API key
          v
FastAPI Local RAG (127.0.0.1:8000)
  |-- authentication, per-user RPM/model/concurrency policy
  |-- answer + corpus-version caches
  |-- query rewrite and intent routing
  |-- hybrid vector + lexical + exact-ID retrieval
  |-- structured table-row retrieval for aggregation
  |-- parent/neighbor context packing
  |-- confidence gate and citation validator
  |-- global inference queue + Tally resource circuit breaker
  |
  +--> PostgreSQL + pgvector
  |      |-- documents, versions, permissions, lifecycle
  |      |-- active embedding index: embeddinggemma (768 dimensions)
  |      |-- shadow index: BGE-M3 (1024 dimensions; never auto-promoted)
  |      `-- structured records, evaluations, latency metrics
  |
  +--> Ollama chat (127.0.0.1:11434)
  `--> optional BGE cross encoder (127.0.0.1:8091/rerank)
```

## Implemented controls

| Improvement | Status | Safe behavior |
|---|---|---|
| Query-result and answer cache | Active | Corpus-version trigger invalidates stale answers |
| Intent routing | Active | Separate conversation, factual, exact ID, summary, comparison and aggregation paths |
| Query expansion | Active | Adds domain terms without changing the user-visible question |
| Parent/neighbor retrieval | Active | One batched database query; capped context |
| Confidence gate | Active | Low-evidence factual questions are instructed to refuse |
| Citation validation | Active | Quality profile buffers and blocks unsupported generated answers |
| Table-aware ingestion | Active for new CSV/XLSX/DOCX uploads | Stores named fields and searchable table rows |
| OCR confidence | Active for new OCR uploads | Captured per block and summarized per document |
| Document versions/lifecycle | Active | Superseded/archived documents are excluded unless explicitly selected |
| Per-account API controls | Active | RPM, allowed models, expiry and concurrent generation caps |
| Tally protection | Active | Rejects new generation temporarily when RAM/CPU safety limits are crossed |
| Detailed latency metrics | Active | Retrieval stages, queue, first token, total latency and tokens/sec |
| BGE-M3 shadow index | Schema and build/eval tools ready | Cannot affect active results until explicitly promoted |
| BGE cross encoder | Optional service ready | Built-in reranker remains fallback if service is absent or times out |
| Evaluation release gate | Active mechanism | Requires 150 human-reviewed questions before a production model/index promotion |
| Backup verification | Ready | Restore target must be empty and named restore/test/disposable |

## Measured results

Measurements below are from the current development host and remote PostgreSQL,
not the intended 32 GB Xeon server. They therefore establish the present
bottleneck; re-run them after server cutover.

| Measurement | Result |
|---|---:|
| Retrieval eval | 20/20 answerable questions found supporting evidence |
| Overall Recall@1 | 95.24% (20 answerable + 1 intentional refusal case) |
| Evidence coverage | 100% |
| Fast first token, warm p50 / p95 | 11.94 s / 20.36 s |
| Fast total, warm p50 / p95 | 15.66 s / 23.22 s |
| Fast generation throughput p50 | 16.09 tokens/s |
| Retrieval p50 / p95 | 11.82 s / 12.63 s |
| Hybrid database search p50 / p95 | 4.35 s / 6.14 s |
| Context enrichment p50 / p95 | 5.67 s / 5.88 s |

The remote PostgreSQL round trips dominate latency. Docker/PostgreSQL is not
installed on this host, so the prepared local-pgvector migration cannot be
cut over here. On the Xeon server, deploy `local-infrastructure/compose.yaml`,
migrate with `scripts/migrate-postgres-to-local.ps1`, verify counts, and only
then change `DATABASE_URL`. Keep the remote database intact as rollback until
the restore drill passes.

The office-hours circuit breaker was also exercised: it refused generation
when available RAM fell below 8 GB. The protection now applies only during the
configured office window, allowing after-hours maintenance and benchmarking.

Metadata backfill completed for 401 existing document records and a second run
updated zero records, confirming idempotency.

## Safe activation commands

### Backfill metadata for older documents

```powershell
& .\.venv-rag\Scripts\python.exe scripts\backfill-document-metadata.py
```

This only fills missing lifecycle metadata and preserves existing document IDs,
permissions, chunks, and embeddings.

### Build and evaluate BGE-M3 shadow embeddings

Run after hours. This can consume CPU for a long time but cannot change serving results.

```powershell
ollama pull bge-m3
& .\.venv-rag\Scripts\python.exe scripts\build-shadow-index.py --batch-size 16
& .\.venv-rag\Scripts\python.exe scripts\evaluate-shadow-index.py
```

Do not change `EMBEDDING_MODEL` unless shadow Recall@1/3/5, evidence coverage, ingest time, and query latency meet the approved production thresholds.

### Start the optional cross encoder

Run after hours and measure RAM/CPU before enabling it in the API.

```powershell
py -3.11 -m venv .venv-reranker
& .\.venv-reranker\Scripts\python.exe -m pip install -r requirements-reranker.txt
& .\scripts\start-reranker.ps1
```

Only after `/health` on port 8091 succeeds, set:

```text
CROSS_ENCODER_URL=http://127.0.0.1:8091/rerank
```

Then restart Local RAG and compare accuracy and p95 latency. Clear the setting immediately if Tally responsiveness changes.

### Validate evaluation coverage

```powershell
& .\.venv-rag\Scripts\python.exe scripts\validate-evaluation-coverage.py
```

The current small engineering dataset is useful for smoke tests but intentionally fails the 150-question release gate until real, reviewed company questions are added.

### Backup and restore drill

```powershell
& .\scripts\backup-local-postgres.ps1 -DatabaseUrl '<local-production-url>'
& .\scripts\verify-postgres-restore.ps1 `
  -BackupFile '.\backups\local-rag-YYYYMMDD-HHMMSS.dump' `
  -DisposableDatabaseUrl '<empty-restore-test-url>' `
  -ConfirmTargetIsDisposable
```

Never point restore verification at the production database.

## Release gates

1. `python -m unittest test_rag.py` must pass.
2. Frontend production build must pass.
3. `/health` must report Ollama and database connected.
4. Current retrieval evaluation must not regress.
5. p95 first-token and total latency must be measured warm and under concurrency.
6. Tally must remain responsive during a two-user Fast-profile test.
7. Any embedding or reranker promotion requires the 150-question human-reviewed evaluation set.
