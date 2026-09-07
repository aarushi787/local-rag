# Before / after comparison

This is a tested code candidate, not completion of the 27-phase production upgrade.

| Check | Before | After |
|---|---|---|
| Offline unit tests | 62 passing | 87 passing |
| Frontend build | Pass, 31.29 s | Pass, Vite 45.21 s; not a speedup claim |
| Mixed refusal bypass | Reproduced | Regression test rejects it |
| Evidence beyond 500-character preview | Rejected | Full-evidence regression passes |
| Uncited extra claim | Evaluator missed it | Regression test counts it unsupported |
| Caller system override | Preserved as privileged | Omitted; only server system role remains |
| Output-budget cache collision | Reproduced | Separate keys verified |
| Hybrid retrieval p50 / p95 | 3.714 / 4.674 s | Unmeasured: memory guard blocked run |
| Human generation/refusal accuracy | Unmeasured | Unmeasured |
| Embedding model | embeddinggemma | Unchanged |
| Production release | Not established | Blocked |

No before/after claim about real answer accuracy, speed, total RAM savings or production readiness is supported. The demonstrated gain is rejection of specific reproducible defects and wider offline regression coverage. Conservative citation checks may increase false refusals and delay displayed answers; human acceptance testing is required.

After benchmark attempted with 1.081 GiB available RAM and stopped before model/database work. Baseline had reached 0.015 GiB available. No production service or database was changed. Missing reviewed data, local PostgreSQL tools, representative model benchmarks, live health/authorization/concurrency acceptance and restore tests block final release.
