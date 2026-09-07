# Retrieval pipeline and experiment gates

## Serving behavior

`retrieve` embeds an expanded query, executes vector and PostgreSQL full-text rankings, fuses with reciprocal rank fusion, adds literal identifier candidates, reranks and uses MMR. PostgreSQL `ts_rank_cd` is not BM25. The existing RRF formula was already present; `RRF_K` is now configurable and defaults to the unchanged value 60. No weight, embedding or similarity threshold has been promoted.

Permissions are applied in SQL. General retrieval selects active documents; explicitly selected documents retain the existing historical-document behavior. After selection, context lookup uses one batch. Parent and neighbor expansion now stays on the same page; additional pages must be separately retrieved and cited. Expanded evidence does not advertise the original child's bounding box.

The cross encoder now validates all scores before changing rows; malformed, non-finite or unavailable responses preserve built-in results. Optional cross-encoder quality, MMR score calibration and candidate counts 10/20/30 still require an actual model benchmark.

## Not yet implemented or promoted

- Learned confidence thresholds and query-dependent fusion weights. Gather relevant/irrelevant/refusal distributions with human labels and a held-out split first.
- General structured QueryPlan, entity resolution, explicit metadata-filter confidence, source-diverse comparison coverage and bounded evidence-driven multi-hop.
- Whole-table deterministic calculations. Never treat retrieved top-k rows as a complete dataset.
- Contextualized embedding representations and alternative chunking shadow experiments.
- Full tokenizer-aware input/output/history accounting. Existing character packing is still approximate.

## Embedding A/B safety

The serving index remains embeddinggemma/768 dimensions. Shadow generation is restricted to an explicitly configured loopback LOCAL_DATABASE_URL and requires at least 3 GiB available RAM before each batch. It no longer calls a nonexistent connection-level executemany method. Existing shadow rows from a different model cause a refusal rather than mixing models.

`scripts/evaluate-shadow-index.py` requires 150 reviewed questions across all 16 categories. It compares vector-only active and shadow searches and filters shadow rows by model. It is not a benchmark of the complete serving hybrid pipeline and never approves promotion. No shadow embeddings were created in this upgrade.

Before any promotion, freeze a dataset/corpus version, verify content checksums, benchmark candidate recall and serving generation, measure p50/p95 and resources, review paired per-question changes, and retain the prior index for rollback. Repeatable snapshots and contextual-index lineage remain acceptance work.
