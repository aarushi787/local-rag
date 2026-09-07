# Upgrade changelog and remaining gates

## Implemented after baseline

- Saved before-upgrade benchmark reports before source edits.
- Added rag_core evaluation/grounding components without changing the API entry point.
- Added 16-category human-review coverage validation, stable review hashes, true document retrieval metrics and a human-annotated replay evaluator.
- Fixed the five reproduced grounding/cache/system-role defects; enforced citation checks across profiles.
- Added cache option/role/corpus isolation, bounded cache expiry, owner-only cancellation and atomic optional reranker fallback.
- Made RRF_K configurable with unchanged default 60. No fusion tuning or embedding promotion.
- Kept context expansion on the cited page and removed misleading child boxes for expanded evidence.
- Corrected UI confidence/latency wording and added withheld-answer state; preserved the design and existing endpoints.
- Hardened local migration/restore targets and added read-only content/vector comparison.
- Fixed shadow builder cursor usage/model checks; shadow evaluation now rejects missing review or incomplete data.
- Added memory-safe, read-only benchmark tooling. 87 tests and frontend build pass.

## Scope versus the requested 27 phases

| Phases | Status |
|---|---|
| 1 Evaluation | Framework implemented; human dataset and full acceptance run blocked |
| 2 Retrieval | Audited; RRF configurability and provenance fixes; calibration/weight/depth promotion pending labels |
| 3 Embeddings | Active index unchanged; guarded A/B tooling improved; no model benchmark/promotion |
| 4 Reranking | Atomic fallback fixed; interface refactor, model benchmark and MMR calibration pending |
| 5–9 Chunking/context/query/multi-hop/packing | Existing features retained; no new contextual index, multi-hop planner or tokenizer budgeting |
| 10–12 Grounding/citations/refusal | Candidate checks implemented; human quality and false-refusal acceptance pending |
| 13 Numeric reasoning | Not implemented; top-k table rows must not be represented as complete aggregates |
| 14–16 Memory/routing/parameters | Audited, unchanged pending representative evaluation |
| 17 Injection | Privileged caller role removed; document prompt remains untrusted; adversarial acceptance pending |
| 18 Latency | Baseline measured; after benchmark blocked by RAM; no speedup claimed |
| 19 Migration | Tools hardened; deployment, copy, restore and cutover not performed |
| 20 Caching | Reproduced defects fixed; broader trigger/race/cache telemetry audit pending |
| 21–22 Observability/feedback | Existing metrics retained; comprehensive tracing and feedback persistence not added |
| 23–25 Tests/refactor/security | Incremental helpers and 25 new tests; residual risks documented |
| 26 Frontend | Trust/diagnostic wording improved, build verified; interactive acceptance pending |
| 27 Release gates | Blocked; not production-ready |

## Measurement and rollback policy

Every shipped candidate change has a code-level defect or explicit safety need; offline fixtures are not quality benchmarks. See the security and grounding documents for expected regressions, especially conservative paraphrase rejection and later displayed answers. No changed serving retrieval weights or embeddings are justified by the small legacy set.

Review the working-tree diff and test in an isolated environment before deployment. No commit/push or service restart was performed for this audit candidate. Revert only the reviewed candidate changes if needed; preserve unrelated user changes and databases. Migration never switched DATABASE_URL. Neon and the active embedding index remain rollback references.

## Required next inputs

Provide 150–300 source-verified questions and reviewer judgments; run live benchmarks on a machine with safe RAM headroom; install/provision local PostgreSQL tooling in an approved environment. Only then calibrate/tune retrieval, implement complete-table numeric workflows against representative fixtures, benchmark multi-hop/reranking/shadow models, and run the full production checklist. Do not fine-tune before those gates pass.
