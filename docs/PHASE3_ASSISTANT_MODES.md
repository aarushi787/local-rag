# Phase 3 assistant modes

**Status: code-only implementation. Not deployed; no accounting connector, database migration, model change, or production configuration change was made.**

| Mode | Current behaviour | Data access | Status |
| --- | --- | --- | --- |
| Company Knowledge | Retrieves only authorized active company evidence and requires source-grounded answers. | PostgreSQL retrieval with existing lifecycle and permission filters. | Implemented offline. |
| General Assistant | Drafting, explanation and brainstorming without any retrieval request. The system prompt requires the `General assistance —` label. | No company-document search or selected document scope. | Implemented offline. |
| Business Analytics | Refuses with HTTP 409 before cache, retrieval, model or database work. | None. No SQL is generated or executed. | Deliberately unavailable. |

The frontend reads `/v1/assistant-modes`, presents the three choices, and disables the unavailable Analytics choice. Selecting General Assistant clears and disables the document scope selector. The backend remains authoritative: a direct API request cannot use General Assistant with a selected document and cannot activate Analytics.

## Analytics admission requirements

Do not enable Business Analytics until an approved read-only data source and server-side semantic layer exist. Each supported analytical request must define company/tenant, period, currency, filters, freshness, completeness and authorization. It must use validated query templates or an approved semantic layer—not model-generated SQL—and show coverage/freshness in the result. Tally integration remains limited to an approved read-only export or supported interface; it must never write accounting records.

## Limitations and next validation

General mode isolation means no *new* company document retrieval occurs. A user can still see their own earlier conversation messages, including prior Company Knowledge answers; revoking document access cannot retroactively erase information already revealed in a conversation. Conversation-level mode history is not yet persisted as a dedicated database field, so clients should show the mode returned in response metrics once a live deployment is approved.

Run the disposable PostgreSQL suite before production approval, then add human-reviewed mode-isolation, multilingual and refusal cases to the held-out evaluation set. Do not claim broad answer quality until the minimum reviewed dataset requirement is met.
