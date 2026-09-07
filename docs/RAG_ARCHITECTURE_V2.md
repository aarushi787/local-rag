# Local RAG architecture — audited upgrade candidate

Status: incremental candidate, NOT production-approved. Baseline September 5; offline validation September 7, 2026. No service restart, migration, remote database writes or embedding promotion performed.

## Current flow

```text
Browser / API client
  -> FastAPI app.py :8000 (key authentication, limits, document permissions)
  -> permission/corpus-scoped answer cache
  -> bounded inference queue and configured resource checks
  -> query rewriting / intent routing
  -> embeddinggemma through loopback Ollama
  -> PostgreSQL vector + lexical RRF / exact IDs / table rows
  -> built-in reranking, optional cross encoder, MMR
  -> parent / same-page neighbor context -> context packing
  -> local Gemma generation -> claim/citation gate -> answer + sources
```

The database is currently remote Neon, not local PostgreSQL. Model execution is local; stored documents, vectors, permissions and chat data are not all on the laptop. The inspected test machine has about 7.326 GiB RAM, not the planned Xeon/32 GB server. Fast/Auto/Quality currently use Gemma 3 1B. Balanced references an unavailable model.

## Strengths

- Existing retrieval already uses RRF, GIN lexical search, HNSW vectors, permission predicates and active-document filtering.
- Structural/parent-child chunking, OCR ingestion, table records and source metadata exist.
- Queueing, user limits, hashed personal keys, ingestion jobs and conversation persistence are implemented.
- Parent/neighbor lookups are batched. Query embeddings and answers are cached.
- React build and 62 original tests passed before changes.

## Weaknesses, bottlenecks and debt

- Evaluation: 21 narrow, unreviewed questions cannot validate production correctness. Legacy source-hit scores were labelled too broadly.
- Generation: all nine samples on one repeated question failed the legacy grounding proxy. This does not measure general accuracy.
- Remote database stages dominate retrieval: hybrid p50 3.714 s / p95 4.674 s before changes.
- Laptop free RAM fell to 0.015 GiB during baseline. Installed models and profiles do not match the eventual server design.
- Aggregation retrieves selected rows; it does not compute complete-table sums deterministically. Comparisons are multiple searches, not evidence-driven multi-hop reasoning.
- Confidence is an uncalibrated heuristic; context packing is character-based, not a full model-token budget.
- app.py remains large. New evaluation/grounding helpers live in rag_core to avoid a conflicting app/ package and preserve `uvicorn app:app`.
- Ingestion/OCR resource control, logging redaction, migration/restore acceptance, broader permission tests and schema least-privilege grants need additional work.

## Top 10 improvements, ranked

| Rank | Improvement | Evidence / release condition |
|---|---|---|
| 1 | Reviewed evaluation and explicit metric denominators | Existing set cannot support acceptance; framework implemented, 150 reviewed items still needed |
| 2 | Database locality and measured round trips | Baseline database stages dominate; migration tooling hardened, deployment blocked |
| 3 | Cache authorization/version/options isolation | Reproduced output-budget collision; fixed and tested |
| 4 | Claim/citation/refusal contract | Five reproducible defects; addressed with regression tests |
| 5 | Score calibration on held-out examples | Current scores are not probabilities; no threshold promotion without labels |
| 6 | Context budget and evidence provenance | Cross-page enrichment and short previews; same-page boundary/full evidence fixed, tokenizer budget pending |
| 7 | Deterministic table calculations | Retrieved top-k rows cannot prove complete totals; needs reviewed tables and integration tests |
| 8 | Structured query plans and bounded multi-hop | Current routing is heuristic; needs multi-document evaluations |
| 9 | Cross encoder / embedding A/B evaluation | Optional model availability and reviewed-data gates block promotion |
| 10 | Trustworthy diagnostics and feedback | UI scores overstated certainty; labels corrected, feedback persistence not added |

## Boundaries

Expose only the authenticated frontend/API through approved LAN/VPN/TLS configuration. Keep Ollama 11434/11435 and PostgreSQL 5432 on loopback. No firewall or listener changes were made. Tally protection must remain enabled on the production server; the laptop's OFFICE_HOURS_POLICY=false is not a production configuration.
