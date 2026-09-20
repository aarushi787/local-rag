# Phase 0 baseline and Phase 1 handoff

Date: 19 September 2026. Base commit: `9bb53ab`.

**Status: Phase 0 complete; Phase 1 local code candidate implemented and tested offline. Not deployed or production-approved. Real PostgreSQL acceptance remains blocked. Phase 2 has not started.**

## Scope and unchanged state

The custom app is React -> authenticated FastAPI -> permission-filtered PostgreSQL retrieval -> local Ollama -> answer validation -> response and conversation storage. Ingestion extracts/OCRs files, chunks and embeds them, then activates documents in PostgreSQL. The `server-build/` Open WebUI kit is a separate stack, not this application's frontend.

The working machine reports Windows 11, an AMD processor, 7.33 GiB total RAM and 0.28 GiB available at the baseline check. Windows CIM access was denied; the fallback used `platform` and `psutil`. This is not the intended Xeon/32 GB/Windows Server Tally host. No inference, OCR batches, model downloads or load benchmarks were run.

The inspected private configuration still selects `gemma3:1b-it-qat` and `embeddinggemma`, requires authentication, enables strict citation validation, disables migrations, disables the office-hours resource policy and has no configured cross encoder. Its database host is remote. These are file settings, not proof of running-process configuration. No secrets are included in this handoff.

No live service, `.env`, database, model, firewall, key, scheduled task, Tally process or Git history was changed. Existing training changes, assessment files and report output were preserved. Nothing was committed or pushed.

## Phase 0 findings and acceptance map

Status describes the rechecked baseline; the final column distinguishes the code fix from deployment evidence.

| Finding | Baseline status and evidence | Impact / priority | Fix or next action | Acceptance / current result |
| --- | --- | --- | --- | --- |
| Offline tests | Confirmed: `test_rag.py`, `test_upgrade.py`, training review tests; 91 pass | Regression baseline / P0 | Retain suite and add targeted tests | Expanded suite passes; see verification below |
| Frontend typing | Confirmed: TypeScript no-emit check passes | Client contract safety / P0 | Recheck after backend changes | Pass; no UI implementation changes |
| Evaluation coverage | Confirmed: 21 cases, 0 human-reviewed, gate not ready | No credible accuracy percentage / P1 | Human review and held-out MSME cases | Not relabelled, fabricated or expanded with synthetic approvals |
| Configured models | Confirmed in private file; `app.py` defaults differ | Deployment drift / P1 | Keep config; document actual versus default | Installed/running model identity unverified |
| Remote database | Confirmed configured remote host | Not wholly local storage / P0 | Explicit privacy/storage decision | No migration or cutover performed |
| Authentication and strict gate enabled | Confirmed configuration | Useful protections / P0 | Preserve both | Configuration untouched |
| Anonymous-admin fallback | Confirmed: `require_api_key` | Exposure on misconfiguration / P0 | Always fail closed; explicit bootstrap | Offline auth and isolated HTTP tests pass |
| Resource policy disabled | Confirmed configuration; incomplete call coverage | Tally contention risk / P0 | Extend admission checks without silently enabling policy | Blocked readings, low RAM and entry-point tests pass; host-load acceptance pending |
| Cross encoder absent | Confirmed no configured endpoint | Optional quality/performance trade-off / P1 | Defer measured evaluation | No installation or promotion |
| Unsafe replacement | Confirmed old deletion before embedding | Lost usable version / P0 | Prepare first; atomic stable-ID activation | Offline fault-injection passes; PostgreSQL rollback test prepared but not run |
| Runtime grants incomplete | Confirmed old four-table SQL | Startup/auth/ingestion failure or owner-role workaround / P0 | Explicit full runtime allowlist; separate migration role | Static contract passes; real role test pending |
| Cache timing reused | Confirmed streaming and non-streaming paths | False performance claims / P0 | Fresh request timings and explicit timing scope | Both response paths tested |
| Missing CORS PATCH | Confirmed middleware options | Split-frontend updates fail / P0 | Add PATCH and Authorization to explicit-origin policy | Approved-origin preflight passes; unknown origin rejected |
| Selected-row aggregation | Confirmed `retrieve_for_question` | Business totals not authoritative / P1 | Deterministic analytics in later approved phase | Unchanged; no accounting correctness claim |
| English-oriented keyword search | Confirmed `lexical_tsquery` | Hindi/Marathi retrieval gaps / P1 | Unicode/language-aware evaluation in Phase 2 | Unchanged |
| Lexical grounding | Confirmed `rag_core/grounding.py` | False refusals and unsupported interpretations / P1 | Human-reviewed improvement, not removal of gate | Validator retained; unsafe diagnostic text output removed |
| Retrieval-first routing | Confirmed `is_conversational_message` and routing | General-assistant limitations / P1 | Explicit three-mode design in Phase 3 | Not implemented prematurely |
| Training preparation only | Confirmed source/config and existing training report | No demonstrated fine-tuned model / P2 | Separate approved training/evaluation workflow | No training or dataset export run |

Legacy `ask_rag.py` and `ingest_text.py` still use old runtime/schema assumptions. Do not use them as the supported authenticated ingestion path. The large app/UI, private Drive permissions, semantic grounding, multilingual retrieval and multi-company isolation remain later work.

## Phase 1 changes

### Authentication and permissions

- Protected endpoints never create an anonymous administrator when the master key is missing. Startup requires a random ASCII master key of at least 32 characters. The legacy `REQUIRE_API_KEY=false` value cannot opt out.
- Both `X-API-Key` and `Authorization: Bearer ...` work. Different simultaneous credentials return 400; malformed/invalid credentials return 401; missing bootstrap configuration returns 503 before database access. This improves authentication compatibility, not every aspect of the OpenAI API contract.
- CORS permits PATCH and Authorization only for explicitly configured origins. Same-origin hosting still needs no CORS entries.
- Memory and database cache hits recheck every source document's current active/ready status and read permission. Legacy cache entries without usable document IDs are misses. Existing account/corpus-specific cache identities remain intact.
- Uploading identical bytes no longer automatically grants access to another user's existing document. A conflict requires administrator attention. Non-admin text replacement now returns 403 instead of silently becoming an ordinary import.
- Historical conversations retain their existing owner-based access semantics. Revoking document access is not a retroactive erasure of information already disclosed or saved in that user's conversations.

### Atomic document activation

Extraction and all embeddings finish before activation opens its write transaction. Source/checksum advisory locks serialize cooperating writers. Replacement updates the existing document ID, preserving ownership, permissions, lifecycle and external references. Old chunks, parent context and structured rows are replaced in the same transaction as the new content and ready status.

Extraction/embedding failures never modify the old document. Persistence/activation failures roll back within the database transaction. A separate ingestion-job failure record is attempted without including raw exception contents. Ambiguous source names and conflicting checksums return 409 rather than delete multiple documents. An old interrupted import can require an explicit administrator replacement; it is not silently deleted to clear its checksum.

Database rollback semantics have offline fault-injection coverage, not live PostgreSQL proof yet. A lost connection during commit can leave the outcome unknown; verify document state before retrying. Post-commit progress-report failure is logged without turning a successful activation into a failed replacement. If failure logging itself cannot reach the database, only a sanitized warning is available. Background ingestion may record both its existing failed job and a separate failed store attempt.

Lifecycle updates now raise a missing-target error inside the transaction, so they cannot commit a superseded predecessor when the new target does not exist.

### Resource control and cancellation

- Admission checks cover direct model calls, embeddings, warmup, reranker dispatch, API ingestion and extraction. PDF extraction checks each page; OCR checks before launching its subprocess. Model requests recheck after queue wait.
- When the enabled office-hours policy cannot obtain finite resource readings, it fails closed with 503 and Retry-After. Invalid policy times/budgets are rejected during validation.
- All app ingestion routes share a bounded single-worker ingestion queue. Nested extraction/store calls reuse the lease. Synchronous file processing runs off the asynchronous request loop. Queue-full and wait-timeout responses are explicit.
- Queue cancellation produces a cancelled outcome, clears the request registry and releases slots. Cancelled buffered output is neither saved nor cached.
- A new test reproduced withheld generated claims leaking through `grounding_validation` metadata. Response diagnostics now expose status, counts and citation indices, not generated claim text.

**Limitations:** The existing policy is still disabled in the actual `.env`. Enabling it remains an approved deployment decision. It is an admission check during configured office hours, not a hard CPU/RAM cap or continuous process monitor. An admitted OCR/model operation can continue until it completes or its existing timeout fires; cancellation is observed between returned model chunks, not guaranteed to interrupt a stalled network read instantly. Explicit standalone maintenance scripts and the independent reranker service are not protected by the API's in-process queue. Keep them private and run only under a separately approved resource budget. Use one API worker and `INGESTION_WORKERS=1`; multi-process limits are not shared.

### Timing and diagnostics

New results distinguish queue wait, retrieval, generation, validation, model-first-token and server-first-visible-text timing. Strict validation still buffers grounded answer text. Non-streamed calls cannot observe the model's first token, so that value is null. Cache hits report zero generation work and null generation throughput instead of stale inference speed; non-timing grounding/profile metadata is retained in sanitized form.

`timing_scope=server_before_persistence_and_transport` explicitly excludes final persistence and network/browser rendering. These are server-side measurements, not end-user latency guarantees. The metrics summary excludes old messages without this scope marker rather than mix misleading historical cache timings into new statistics. Empty aggregates return null, not a fabricated zero-millisecond measurement. Existing historical records are not rewritten.

## Verification

Executed locally with no app startup, live model calls or database connections:

```powershell
.\.venv-rag\Scripts\python.exe -m unittest test_rag test_upgrade test_phase1 training.test_prepare_drive_review test_phase1_postgres
```

Result: **130 tests passed; one PostgreSQL integration class skipped before any connection attempt.** The 39 new offline tests cover auth, HTTP/CORS contracts, transactional fault injection, permissions/cache revocation, extraction/resource admission, cancellation, fresh timing and schema/grant coverage. Synthetic fixtures are not human-reviewed business ground truth.

Frontend verification:

```powershell
node .\frontend\node_modules\typescript\bin\tsc --project .\frontend\tsconfig.app.json --noEmit --incremental false
```

Python compilation and `git diff --check` also pass. The existing Starlette test client warns that httpx support is deprecated; tests currently pass using installed httpx 0.28.1. Its BSD-3-Clause license was checked from installed distribution metadata. `requirements-dev.txt` records this development-only dependency; no dependencies were installed or upgraded.

### Prepared but not executed PostgreSQL acceptance

`test_phase1_postgres.py` includes four real-database tests: runtime grants/DDL denial, expired/deactivated/rotated authentication, transactional replacement failure/success, and permission-trigger/cache invalidation.

It refuses to connect unless both conditions are explicitly set by the operator:

- `LOCAL_RAG_TEST_DISPOSABLE=YES`.
- `LOCAL_RAG_TEST_DATABASE_URL` identifies an empty loopback database named `rag_phase1_test_<name>`, without URL query overrides.

It never falls back to `DATABASE_URL`. The database must have pgvector available and an isolated owner able to create the schema and a temporary role. Fixtures, grants, schema and temporary role creation run inside a rollback-only outer transaction. Do not point it at a shared or production database. It refuses a non-empty public schema. An empty database is not permission to run against the production PostgreSQL cluster; provision an isolated test instance first.

PostgreSQL tools were not available on PATH or in the standard checked installation directory; no test database was provided. Memory headroom was also unsafe for provisioning new workloads. These tests are therefore **pending, not passing**. Their schema extraction and Python syntax were checked offline.

### Disposable validation runner

`local-infrastructure/docker-compose.phase1-validation.yml` and `scripts/run-phase1-postgres-validation.ps1` now provide the only supported local acceptance path. They use a new loopback-only Docker container named through the fixed Compose project `local-rag-phase1-validation`, a database named `rag_phase1_test_local`, a generated in-memory password, and a project-scoped volume. They do not read `DATABASE_URL`, start the app, start Ollama, or reuse the ordinary local PostgreSQL Compose service.

The runner fails closed unless Docker Engine is reachable, TCP port 55432 is unused, the project virtual environment exists, and at least 4 GiB of system RAM is available. It requires a deliberate `-ConfirmDisposableDatabase` switch before creating resources. After the test it removes that exact project's container and volume by default. `-KeepArtifacts` is only for diagnosing a failed test, and leaves the disposable data behind until the operator removes that named project.

Run a no-write readiness check first:

```powershell
.\scripts\run-phase1-postgres-validation.ps1 -PreflightOnly
```

Only on a machine with adequate headroom and Docker Engine running, run the disposable test suite:

```powershell
.\scripts\run-phase1-postgres-validation.ps1 -ConfirmDisposableDatabase
```

Readiness checks on the current development laptop found only 0.43–1.01 GiB free RAM and no Docker command, so neither command is approved to start Docker there. This is still pending until the second command completes successfully on a safe machine.

## Bootstrap and deployment requirements

Do not restart the current application simply to apply this patch. Schedule and approve rollout after disposable-database acceptance and a tested backup.

1. Preserve the existing `.env` and keys. For a genuinely new installation, generate a private random ASCII administrator key of at least 32 characters and store it securely. A password manager or local `secrets.token_urlsafe(32)` is suitable. Do not commit its value.
2. Provision an isolated test database and run the opt-in acceptance suite before considering production grants or migration.
3. On a new empty database, or during approved maintenance with a restore-tested backup, use a **separate owner session** for the existing migration runner. It uses autocommit and can update legacy records; it is not an all-or-nothing migration. Do not run it using the normal runtime role.
4. Provision a dedicated `rag_app` role and secret outside the SQL file. Apply `sql/neon_least_privilege.sql` as the owner, to the explicitly selected database, in one transaction with stop-on-error. Review inherited privileges too. The script creates no role and embeds no password. It rejects administrative/owning roles and inherited schema CREATE rights. It does not silently revoke PUBLIC privileges on a shared database.
5. Configure the app's runtime connection to that least-privilege role. Keep `RUN_MIGRATIONS=false`, now also the code/template default. `REQUIRE_API_KEY=false` no longer permits anonymous operation. Use the same protected administrator key consistently across initialization and runtime.
6. Keep one API worker and one ingestion worker. Approve a resource policy based on measured Windows/Tally headroom, not the laptop's settings. This patch does not enable it automatically.
7. Verify loopback inference/database bindings, private authenticated HTTPS access, key rejection/rotation, read permissions, cache revocation, replacement failure, restart recovery and Tally response time in the planned environment.

No new database columns or tables are required by this patch; the updated grants depend on the current existing schema. The assessment's hosted-storage/privacy decision is still unresolved.

## Files and rollback

| File | Change |
| --- | --- |
| `app.py` | Auth, atomic activation, access rechecks, bounded ingestion/resource checks, cancellation and response timing/diagnostics |
| `document_processing.py` | Optional resource admission callback for extraction/PDF pages/OCR |
| `sql/neon_least_privilege.sql` | Current-schema runtime grants and role checks; no embedded secret |
| `.env.example` | Explicit migrations-off default; actual `.env` untouched |
| `README.md` | Safe routine startup, separate migration/bootstrap guidance, honest streaming description |
| `requirements-dev.txt` | Existing HTTP test-client dependency recorded for reproducibility |
| `test_phase1.py` | Offline regression and HTTP contract tests |
| `test_phase1_postgres.py` | Explicitly opt-in disposable database acceptance |
| `docs/PHASE1_HANDOFF.md` | Baseline, evidence, limits and operational handoff |

Before any deployment, keep a copy of the currently deployed build/configuration and a tested data backup. If the candidate fails acceptance, leave production on that previous build. To undo these uncommitted source changes, reverse only the Phase 1 edits/new files after preserving unrelated work; do not use a hard reset or overwrite the existing training changes. No live data/config rollback is needed for this task because none was changed. If grants are later applied, rollback must use the DBA's captured prior grants and approved deployment procedure, not a broad revoke on shared objects. Reverting the old authentication code reintroduces its fail-open risk and must not be treated as a safe security fix.

## Next decision

Phase 1 cannot be called production-approved on offline evidence alone. First approve an isolated PostgreSQL acceptance environment with adequate memory and run the pending four tests plus operational checks. After that handoff, obtain explicit approval for Phase 2 retrieval/grounding work. No generalized assistant modes, analytics connector, multi-tenant architecture or model training was implemented in this milestone.
