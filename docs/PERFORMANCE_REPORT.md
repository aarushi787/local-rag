# Performance report

## Measured before changes

See reports/baseline_before_upgrade.json for individual profile samples and method limitations.

| Measurement | Result |
|---|---|
| Existing hybrid retrieval, 21 questions | p50 3.714 s; p95 4.674 s |
| Vector-only retrieval, same questions | p50 1.748 s; p95 3.482 s |
| Auto total, one question repeated 3 times | median 4.692 s; sample p95 18.489 s |
| Fast total, same method | median 7.355 s; sample p95 32.190 s |
| Quality total, same method | median 8.030 s; sample p95 24.807 s |
| Warm-ish decode samples | Roughly 13–18 tokens/s in several runs; not a server guarantee |
| CPU, 488 samples | p50 26.45%; p95 92.4% |
| Minimum available RAM | 0.015 GiB, of 7.326 GiB physical memory |

Remote hybrid-search and context-enrichment round trips dominate retrieval. Model reloads and memory pressure contributed to slow initial profile samples. Request caching was disabled; cache-hit rate was not measured. No result predicts Xeon performance.

## After changes

87 offline tests pass. Frontend production build passes (Vite reports 45.21 s; compilation/wall-clock scheduling are additional). This is not a performance improvement over the baseline build and build times are not answer latency.

The new read-only benchmark refused to run with 1.081 GiB available RAM, below its 2 GiB pre-request safety threshold. New retrieval/generation p50/p95, CPU during generation, two-user latency and human answer-quality deltas are therefore **unmeasured**. Do not compare missing after-values with baseline values or call the system faster.

```powershell
.\.venv-rag\Scripts\python.exe scripts/benchmark-readonly.py
```

Run after freeing memory or on the target server, with ingestion stable. It sets PostgreSQL transactions read-only, disables caches and conversation saving, skips absent models and never starts migrations. It measures direct Python functions, not HTTP/authentication/network latency. It aborts on insufficient RAM. Add a separate authenticated HTTP benchmark and at least two user accounts before release.

## Local PostgreSQL

Docker, psql and pg_dump were unavailable. No local deployment or restore happened. Existing compose binds 5432 to 127.0.0.1. Hardened restore scripts accept loopback targets only, require an empty database and restore atomically. `verify-migration.py` compares canonical table-row hashes including vector and permission data using read-only snapshots; it checks the source again for changes. It does not validate sequence privileges or retrieval quality.

Cutover remains blocked until local installation, a stable source snapshot, matching row/content/vector comparisons, restore test, least-privilege tests, full evaluation and two-user/Tally responsiveness tests all pass. Keep Neon untouched as rollback. The <1 s / <2 s retrieval targets remain targets, not measurements.
