# Grounding and refusal contract

## Serving contract

- Only server-authored system instructions are privileged. Caller-supplied system messages are omitted from bounded history; clients cannot override the private-document contract.
- Retrieved source text is untrusted evidence, not instructions. The existing prompt explicitly rejects embedded commands and requests source-backed claims, conflict disclosure, exact figures, labelled inferences and explicit unknowns.
- Each factual statement must cite its supporting source immediately. A topically related citation is insufficient.
- Full `evidence_text` contains the exact packed evidence supplied to the model. `quote` remains the 500-character UI preview for API compatibility.
- With STRICT_CITATION_GATE=true, all grounded profiles, including requests without a profile, buffer factual output until validation. Conversation-only responses retain streaming behavior. No repeated regeneration loop was added.
- Invalid output becomes the fixed refusal: "I couldn't find that information in the available documents." Cancellation never caches an incomplete answer.

## Validation

The new helper parses statements and citations, checks each source ID and requires the statement's meaningful tokens in order within a single evidence statement with matching negation presence. Uncited short claims, invented numbers, unrelated extra citations, missing evidence and mixed-refusal answers fail the regression tests. Citations immediately after punctuation attach to the preceding statement.

This is a conservative lexical guard, NOT semantic entailment. It can reject valid paraphrases, headings or multilingual statements; it can still miss semantic errors such as subtle qualifiers, hypothetical language or misleading excerpts. support_score is a rule outcome, not a probability. Human-reviewed generation and refusal evaluation must measure both false acceptances and false refusals before production release.

Structured claim details remain associated with the authenticated response, not emitted into diagnostic logs by this module. Pages refer to the source page; expanded same-page evidence omits misleading child bounding boxes. OCR page-level boxes and synthetic DOCX pages are not exact visual provenance guarantees.

## Trade-offs and rollback

Validated factual answers have later first displayed text. Latency must distinguish model token arrival from user-visible delivery. The UI now uses "time to displayed answer". The current metrics still need fuller cache/stream lifecycle tracing. STRICT_CITATION_GATE=false restores unvalidated streaming but is not a safe production fallback. Revert the reviewed code change in a controlled branch to restore prior behavior; do not reset unrelated work. The cache contract discriminator prevents old unvalidated cache entries from being reused under this candidate.
