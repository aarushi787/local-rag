# Human-reviewed evaluation framework

## Dataset contract

Start from `evaluation/review-template.json`. It is a blank drafting template, not a reviewed question. Store real reviewed items as JSONL. Use stable document IDs or exact canonical source names, not substring matches. `expected_pages` entries are objects such as `{"document":"policy-id","page":3}`.

Target 150–300 distinct human-verified questions across factual, multi_hop, multi_document, numeric, identifier, long_document, conflict, superseded, ocr, ambiguous, follow_up, refusal, no_evidence, injection, similar_entities and temporal. A starting allocation of 10 per category gives 160, but adjust coverage to actual workload. The release validator requires at least one in every category and at least 150 approved unique items. It does not assert that this minimal distribution is statistically sufficient.

Each item includes id, category, question, expected_documents, expected_pages, required_facts, forbidden_claims, should_refuse, answer_notes and difficulty. A human must read the original sources, check facts/pages/version and decide whether refusal is required. Do not derive expected answers from model output.

Approval records require status=approved, reviewer, timezone-aware reviewed_at and item_sha256 from `rag_core.evaluation.item_digest(item)`. The digest excludes review metadata and changes if question/ground truth changes. It detects stale approvals, not dishonest reviewers: source verification remains a human responsibility. No records were marked human-approved by this agent.

## Commands

Run from the project directory:

```powershell
.\.venv-rag\Scripts\python.exe scripts/validate-evaluation-coverage.py --dataset evaluation_questions.jsonl
.\.venv-rag\Scripts\python.exe scripts/evaluate-reviewed.py --dataset reviewed.jsonl --replay reviewed-replay.jsonl
.\.venv-rag\Scripts\python.exe -m unittest test_rag test_upgrade -q
```

The current legacy dataset intentionally fails the first command. Do not relabel it to pass.

## Metrics

`rag_core.evaluation` computes document-level Recall@1/3/5, Precision@1/3/5, binary nDCG@1/3/5 and MRR. Repeated chunks of the same document are deduplicated in first-occurrence order. Precision divides by K; recall divides by the number of expected relevant documents. Refusal/no-relevant-document rows produce null retrieval metrics, not zero recall. These metrics are only as complete as the relevance judgments.

Human claim annotations produce faithfulness, unsupported-claim rate, citation precision, citation recall and answer completeness. Citation precision counts human-supported citations / all annotated citations. Citation recall counts supported, cited claims / all annotated factual claims. Completeness counts uniquely supported required facts / required facts. A zero denominator is null. Refusal precision, recall, accuracy and TP/FP/FN are separate.

A replay has one row per dataset id, retrieved_documents, optional answer, and optional human_annotation. An annotation includes reviewer, answer_sha256, refused:boolean, claims (each with supported:boolean and citations:list[boolean]), and supported_fact_indexes. The reviewer must enumerate ALL factual claims and citations, including uncited additions; the tool does not invent these judgments. Missing human annotations leave generation metrics unmeasured. Report per-category results and failure cases, not only a mean.

The legacy `score_generated_answer` remains for API compatibility but now uses the shared strict validator and reports metric_method=lexical_proxy_not_human_faithfulness. Missing source text no longer passes, uncited claims count as unsupported, and a refusal preamble is not a valid whole-answer refusal. Existing and new metric versions must not be presented as comparable human accuracy scores.

## Remaining acceptance work

Page/evidence recall, annotated claim-span completeness checking, held-out calibration, paired confidence intervals and a representative full-generation evaluation are still needed. Existing synthetic regression tests are code tests, not company ground truth. Embedding promotion stays blocked.
