# Security review — candidate, not sign-off

## Confirmed protections retained

Personal API keys are stored as hashes; document permission predicates and lifecycle filters are present in retrieval. Existing tests cover user/model limits, ZIP traversal, queue limits and selected access checks. No credentials or document contents were copied into benchmark reports. No external database mutation, port exposure, service restart, user creation or key change was performed.

## Fixes with offline regression coverage

| Issue | Change |
|---|---|
| Caller system messages privileged | Only server contract remains a system message |
| Refusal preamble hides invention | Whole-answer refusal matching |
| Uncited claims / missing quotes pass evaluation | Shared claim validator, missing evidence fails |
| Validation reads truncated preview | Full packed evidence is supplied separately |
| Only Quality enforces citations | All grounded streaming/nonstreaming profiles gated |
| Cache ignores output budget and sampling | Effective generation settings, contract/version, policy and principal included |
| Selected-document cache misses permission revision | Fresh corpus revision plus selected-document permission lookup |
| Cached expiry extended in memory | Memory TTL capped by database entry lifetime |
| Other account can cancel known request ID | Cancellation checks owner |
| Partial cross-encoder mutation | All scores validated before replacing rows |
| Wrong page/bounding box after enrichment | Same-page context expansion; omit stale child box |

Migration scripts reject remote targets/query overrides and use single-transaction restores. Backup directory checks now require a directory boundary. These guards were tested without running a restore.

## Important residual risks

1. There is no proof that lexical grounding defeats all document prompt injections or semantic hallucinations. Human adversarial evaluation is required.
2. Cache invalidation depends on corpus triggers. Direct chunk writes outside the application and cross-process changes require a complete trigger/permission-revision audit. Concurrent revocation during an already-running request is not fully addressed.
3. The existing least-privilege SQL omits newer objects/permissions. Do not call database privileges production-verified.
4. The environment's production resource policy is disabled for laptop testing; no Tally safety claim follows. OCR and ingestion need tighter resource admission control.
5. Health metadata, forwarded-address trust, log-message redaction, upload parsing, duplicate-upload ownership and background ingestion recovery need expanded security tests.
6. HTTP LAN access exposes bearer credentials to anyone who can observe that traffic. No TLS/VPN/network changes were made here.
7. New source evidence fields contain authorized document text. Treat API responses, caches and chat backups as sensitive.
8. Reviewed-data digests prevent accidental stale approvals, not forged human attestations. Protect evaluation files and review access.

No real two-user authorization acceptance test, secret-scan sign-off, restore rehearsal or production penetration test was completed. The current changes must not be labelled production-ready.
