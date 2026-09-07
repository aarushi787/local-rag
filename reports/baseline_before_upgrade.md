# Baseline before upgrade

Measured September 5, 2026, before source changes, at commit `33c1349`.
Read-only Neon database: 514 documents / 5,190 chunks; corpus version 944 unchanged.

| Check | Result |
|---|---|
| Unit suite | 62 passed, 1.420 seconds |
| Frontend build | Passed, 31.29 seconds |
| Vector-only source hit@1 / @3 / @5 | 75% / 80% / 90%; MRR .7975 |
| Existing hybrid source hit@1 / @3 / @5 | 100% / 100% / 100%; MRR 1.0 |
| Vector-only retrieval p50 / p95 | 1.748 / 3.482 seconds |
| Existing hybrid retrieval p50 / p95 | 3.714 / 4.674 seconds |
| Auto answer total p50 / sample p95 | 4.692 / 18.489 seconds |
| Fast answer total p50 / sample p95 | 7.355 / 32.190 seconds |
| Quality answer total p50 / sample p95 | 8.030 / 24.807 seconds |
| Balanced | Model unavailable |
| CPU p50 / p95 | 26.45% / 92.4% |
| Available RAM minimum | 0.015 GiB on 7.326 GiB laptop |

Retrieval uses 20 answerable questions plus one refusal question for latency. Generation uses one answerable question repeated three times per available profile. All nine outputs failed the existing grounded-answer proxy; Quality refused rather than answering. These are NOT human-verified accuracy metrics. Hybrid search and context-enrichment database stages dominate retrieval time; the cross encoder was disabled.

Five offline probes reproduced: mixed-refusal bypass, truncated validation evidence, evaluator ignoring uncited claims, privileged caller system messages, and output-budget cache collisions.

## Limits and release status

Legacy questions lack human review provenance and broad company coverage. Hit rates cannot establish production accuracy. Three-sample p95 is only descriptive. The benchmark called existing Python functions, not HTTP endpoints, disabled cache and message saving, and enforced read-only database transactions. No remote data was changed. No local PostgreSQL migration, restore test, cache-hit benchmark, cross-encoder benchmark or two-user acceptance test was performed.

Severe memory pressure prevents a meaningful server-speed claim. Further live tests require safe laptop headroom. Missing metrics are null in JSON, not zero. Production readiness and embedding promotion remain blocked.
