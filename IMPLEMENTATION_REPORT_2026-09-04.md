# Phases 1–5 Implementation Report

## Outcome

The upgraded retrieval pipeline passed all 20 factual acceptance questions at
rank 1. The separate refusal example is no longer incorrectly counted as a
retrieval miss.

| Quality metric | Before | After |
|---|---:|---:|
| Factual Recall@1 | 66.7% including the refusal case | 100% of 20 factual questions |
| Factual Recall@5 | 66.7% including the refusal case | 100% of 20 factual questions |
| Evidence coverage | 71.4% including the refusal case | 100% of 20 factual questions |
| Mean reciprocal rank | 0.667 | 1.000 |

The “after” result is measured on `rag-workflow-v1`. It is a useful regression
gate, not proof of accuracy across every company document. Expand the dataset
before claiming organization-wide quality.

## Measured latency

Machine under test: Ryzen 5 5500U laptop, about 8 GB RAM, one Ollama runtime,
remote Neon PostgreSQL. Fast profile, three uncached streaming runs, 60-token cap.

| Measurement | Before | After |
|---|---:|---:|
| Median first text | about 14.6 s | 3.43 s |
| Median total | about 17–20 s | 9.74 s |
| Median retrieval | 4.3–7.1 s | 3.16 s |
| Median hybrid SQL | not separated | 1.98 s |
| Median context enrichment | not separated | 1.17 s |
| Median generation rate | about 17.8 tok/s in an earlier short test | 10.82 tok/s in the final 60-token sample |
| Cold first text, worst of 3 | about 32 s observed previously | 25.96 s |
| Cold total, worst of 3 | about 32 s observed previously | 31.23 s |

The cold result is still dominated by model swapping: query embedding took up to
5.31 seconds and chat-model load took up to 6.73 seconds. A dedicated embedding
Ollama process on the Xeon is the next required action.

Durable and memory-cache validation:

| Cache path | Measured wall time |
|---|---:|
| First PostgreSQL cache recovery after restart | 7.75 s (remote Neon cold path) |
| Subsequent in-process memory hit | 11.51 ms |
| Second in-process memory hit | 11.37 ms |

Local PostgreSQL is expected to remove most of the remaining remote database
round-trip time, but no number is claimed until that migration is actually run.

## Implementation status

| Phase | Status | Important detail |
|---|---|---|
| 1 — latency | Implemented and measured | Batched enrichment, O(1) cache version, memory answer cache, metrics, status streaming, stable Auto model |
| 2 — retrieval | Implemented and evaluated | Intent routing, comparisons, broader aggregation, identifiers, domain query expansion, focused evidence |
| 3 — private database | Migration package ready; cutover not run | Docker/PostgreSQL is not installed on this laptop; Neon remains the active store |
| 4 — prompt | Implemented | One dynamic grounding prompt; duplicate Modelfile prompt removed |
| 5 — evaluation | Implemented and passed | Refusal denominator fixed, citation evidence checks strengthened, pooled evaluator, latency benchmark added |

## Operational cautions

- `DATABASE_URL` still points to Neon, so document text and embeddings are not yet
  fully local.
- Do not expose ports 5432, 11434, or 11435 beyond localhost.
- Do not delete Neon after migration. Keep it as rollback until local backups and
  a restore drill pass.
- The 100% result is on 20 factual cases. Add real policy, table, conflict,
  multi-document, prompt-injection, and negative questions before production sign-off.

