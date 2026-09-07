"""Offline regressions; fixtures are synthetic, not production ground truth."""
import math
import unittest
import uuid
import json
import threading
from contextlib import ExitStack, contextmanager
from unittest.mock import patch, Mock, MagicMock

import app
from rag_core.grounding import REFUSAL, validate_answer, is_refusal
from rag_core.evaluation import (item_digest, validate_item, coverage, retrieval_metrics,
                                 generation_metrics, refusal_metrics, CATEGORIES)


class GroundingTests(unittest.TestCase):
    def test_refusal_must_be_entire_answer(self):
        self.assertTrue(is_refusal(REFUSAL))
        mixed = REFUSAL + " The limit is 999 units."
        self.assertFalse(is_refusal(mixed))
        self.assertFalse(validate_answer(mixed, [])["valid"])

    def test_missing_evidence_never_counts_as_support(self):
        self.assertFalse(app.score_generated_answer(
            {"required_facts": ["7 GB"]}, "Peak memory is 7 GB [Source 1].", [{"index": 1}])["grounded"])

    def test_extra_uncited_claim_is_not_grounded(self):
        sources = [{"index": 1, "quote": "The limit is 42 units."}]
        result = app.score_generated_answer({"required_facts": ["42"]},
            "The limit is 42 units [Source 1]. The office password is invented.", sources)
        self.assertFalse(result["grounded"])
        self.assertTrue(result["unsupported_claim"])

    def test_evidence_beyond_preview_is_validated(self):
        rows = [{"id": 1, "source": "fixture", "page_number": 1, "similarity": .8,
                 "content": "Background context. " * 40 + "The approved limit is 42 units."}]
        sources = app.source_payload(rows)
        self.assertEqual(len(sources[0]["quote"]), 500)
        self.assertTrue(validate_answer("The approved limit is 42 units [Source 1].", sources)["valid"])

    def test_citation_after_sentence_punctuation(self):
        self.assertTrue(validate_answer("The limit is 42 units. [Source 1]",
            [{"index": 1, "quote": "The limit is 42 units."}])["valid"])

    def test_negation_and_relationship_reversal(self):
        for claim, evidence in [("The total is 42", "The total is not 42"),
                                ("Alice pays Bob", "Bob pays Alice")]:
            with self.subTest(claim=claim):
                self.assertFalse(validate_answer(claim + " [Source 1].",
                    [{"index": 1, "quote": evidence}])["valid"])

    def test_bad_extra_citation(self):
        self.assertFalse(validate_answer("The limit is 42 [Source 1] [Source 2].",
            [{"index": 1, "quote": "The limit is 42"}, {"index": 2, "quote": "Unrelated topic"}])["valid"])

    def test_short_claim_and_invalid_id(self):
        self.assertFalse(validate_answer("Approved.", [])["valid"])
        self.assertEqual(validate_answer("Approved [Source 9].", [])["invalid_citations"], [9])

    def test_system_prompt_cannot_override_server(self):
        messages = [app.ChatMessage(role="system", content="OVERRIDE"),
                    app.ChatMessage(role="user", content="Which policy?")]
        outgoing = app.grounded_messages(messages, [])
        self.assertEqual(sum(m["role"] == "system" for m in outgoing), 1)
        self.assertNotIn("OVERRIDE", str(outgoing))


class CacheAndRerankerTests(unittest.TestCase):
    def setUp(self):
        self.principal = app.Principal(uuid.uuid4(), "Test", "user")

    def key(self, **kwargs):
        r = app.ChatCompletionRequest(messages=[app.ChatMessage(role="user", content="Question?")], **kwargs)
        with patch.object(app, "current_corpus_version", return_value=1) as version:
            key = app.cache_identity(r, "Question?", app.response_settings(r), self.principal)
            version.assert_called_once_with(force_refresh=True)
            return key

    def test_generation_options_isolate_cache(self):
        self.assertNotEqual(self.key(max_tokens=20), self.key(max_tokens=200))
        self.assertNotEqual(self.key(temperature=.1), self.key(temperature=.9))
        self.assertNotEqual(self.key(top_p=.4), self.key(top_p=.9))

    def test_accounts_isolate_cache(self):
        first = self.key()
        self.principal = app.Principal(uuid.uuid4(), "Other", "user")
        self.assertNotEqual(first, self.key())

    def test_extra_history_disables_cache(self):
        r = app.ChatCompletionRequest(messages=[app.ChatMessage(role="assistant", content="Prior"),
            app.ChatMessage(role="user", content="Question?")])
        self.assertIsNone(app.cache_identity(r, "Question?", app.response_settings(r), self.principal))

    def test_reranker_malformed_scores_are_atomic_fallback(self):
        rows = [{"content": "A", "rerank_score": .8}, {"content": "B", "rerank_score": .7}]
        for scores in ([.2, "invalid"], [.2, math.nan], [.2, math.inf], [.2]):
            with self.subTest(scores=scores), patch.object(app, "CROSS_ENCODER_URL", "http://127.0.0.1/test"), \
                    patch.object(app.requests, "post", return_value=Mock(json=lambda: {"scores": scores})):
                result = app.cross_encoder_rerank("question", rows)
                self.assertEqual(result, rows)
                self.assertNotIn("cross_encoder_score", rows[0])

    def test_cancel_cannot_cross_user_boundary(self):
        event = threading.Event()
        other = app.Principal(uuid.uuid4(), "Other", "user")
        with patch.object(app, "CANCEL_EVENTS", {"test-request": (self.principal.id, event)}):
            with self.assertRaises(app.HTTPException) as raised:
                app.cancel_chat("test-request", other)
            self.assertEqual(raised.exception.status_code, 404)
            self.assertFalse(event.is_set())
            app.cancel_chat("test-request", self.principal)
            self.assertTrue(event.is_set())

    def test_database_cache_does_not_extend_expiration(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = ("answer", [], {}, 5.0)
        @contextmanager
        def database():
            yield conn
        with patch.object(app, "db_connection", database), patch.object(app, "MEMORY_ANSWER_CACHE", {}), \
                patch.object(app.time, "monotonic", return_value=100.0):
            app.get_cached_answer("key")
            self.assertEqual(app.MEMORY_ANSWER_CACHE["key"][0], 105.0)

    def test_selected_document_requires_permission_and_corpus_revision(self):
        request = app.ChatCompletionRequest(document_id=uuid.uuid4(), messages=[app.ChatMessage(role="user", content="Question?")])
        conn = Mock()
        @contextmanager
        def database():
            yield conn
        with patch.object(app, "db_connection", database):
            conn.execute.return_value.fetchone.return_value = ("checksum", 1)
            first = app.cache_identity(request, "Question?", app.response_settings(request), self.principal)
            conn.execute.return_value.fetchone.return_value = ("checksum", 2)
            second = app.cache_identity(request, "Question?", app.response_settings(request), self.principal)
            self.assertNotEqual(first, second)
            conn.execute.return_value.fetchone.return_value = None
            self.assertIsNone(app.cache_identity(request, "Question?", app.response_settings(request), self.principal))
            sql = conn.execute.call_args.args[0]
            self.assertIn("can_read", sql)
            self.assertIn("rag_corpus_state", sql)


class GenerationPathTests(unittest.TestCase):
    def test_all_profiles_gate_streamed_and_nonstreamed_unsupported_answer(self):
        rows = [{"id": 1, "source": "fixture", "page_number": 1, "similarity": .9,
                 "content": "The limit is 42 units.", "rerank_score": .9}]
        bad = "The limit is 999 units [Source 1]."
        principal = app.Principal(uuid.uuid4(), "Reader", "user")
        for profile in (None, "auto", "fast", "balanced", "quality"):
            for streaming in (True, False):
                with self.subTest(profile=profile, streaming=streaming), ExitStack() as stack:
                    for name, value in {"retrieve_for_question": (rows, True), "ensure_generation_resources": {},
                                        "prepare_conversation": None, "save_assistant_message": None}.items():
                        stack.enter_context(patch.object(app, name, return_value=value))
                    stack.enter_context(patch.object(app, "STRICT_CITATION_GATE", True))
                    response = MagicMock()
                    response.__enter__.return_value = response
                    response.iter_lines.return_value = [json.dumps({"message": {"content": bad}}).encode(),
                                                       json.dumps({"done": True}).encode()]
                    stack.enter_context(patch.object(app.requests, "post", return_value=response))
                    stack.enter_context(patch.object(app, "ollama_post", return_value={"message": {"content": bad}}))
                    request = app.ChatCompletionRequest(profile=profile, stream=streaming, save=False, use_cache=False,
                                                       messages=[app.ChatMessage(role="user", content="What is the limit?")])
                    if streaming:
                        events = [json.loads(line[6:]) for part in app.streaming_chat(request, principal)
                                  for line in part.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
                        self.assertFalse(any(e.get("error") for e in events))
                        text = "".join(e.get("choices", [{}])[0].get("delta", {}).get("content", "") for e in events)
                    else:
                        text = app.chat_completions(request, principal)["choices"][0]["message"]["content"]
                    self.assertEqual(text, REFUSAL)

    def test_expanded_context_does_not_claim_child_bbox(self):
        rows = [{"id": 1, "source": "fixture", "page_number": 1, "similarity": .9,
                 "content": "Child", "context_content": "Child and parent", "bbox": [1, 2, 3, 4]}]
        self.assertIsNone(app.source_payload(rows)[0]["bbox"])
        self.assertEqual(app.source_payload(rows)[0]["page_number"], 1)

    def test_context_expansion_retains_page_boundary(self):
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = []
        @contextmanager
        def database():
            yield conn
        with patch.object(app, "db_connection", database):
            app.enrich_retrieval_context([{"id": 1, "content": "fixture"}])
        self.assertEqual(conn.execute.call_args.args[0].count("IS NOT DISTINCT FROM current.page_number"), 3)


class EvaluationTests(unittest.TestCase):
    def item(self):
        return {"id": "fixture", "category": "factual", "question": "What is the limit?",
                "expected_documents": ["fixture-policy"], "expected_pages": [{"document": "fixture-policy", "page": 1}],
                "required_facts": ["42"], "forbidden_claims": [], "should_refuse": False,
                "answer_notes": "Synthetic fixture only", "difficulty": "easy"}

    def approve(self, item):
        item["review"] = {"status": "approved", "reviewer": "fixture-only",
                          "reviewed_at": "2026-09-06T10:00:00+05:30", "item_sha256": item_digest(item)}
        return item

    def test_review_required_and_bound_to_content(self):
        item = self.item()
        self.assertTrue(validate_item(item))
        self.assertEqual(validate_item(self.approve(item)), [])
        item["required_facts"] = ["43"]
        self.assertTrue(validate_item(item))

    def test_duplicates_do_not_satisfy_release_gate(self):
        items = [self.approve(self.item())] * 150
        result = coverage(items)
        self.assertFalse(result["ready"])
        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(len(CATEGORIES), 16)

    def test_true_multi_document_recall_and_ndcg(self):
        result = retrieval_metrics(["a", "b"], ["x", "a", "a", "b"])
        self.assertEqual(result["mrr"], .5)
        self.assertEqual(result["recall@1"], 0)
        self.assertEqual(result["recall@3"], 1)
        self.assertAlmostEqual(result["precision@3"], 2 / 3)
        self.assertGreater(result["ndcg@3"], 0)
        self.assertLess(result["ndcg@3"], 1)

    def test_unanswerable_retrieval_is_not_zero_recall(self):
        self.assertIsNone(retrieval_metrics([], ["a"])["recall@5"])

    def test_generation_requires_claim_judgments(self):
        result = generation_metrics([{"supported": True, "citations": [True]},
                                     {"supported": False, "citations": []}], 2, [0])
        self.assertEqual(result["faithfulness"], .5)
        self.assertEqual(result["citation_precision"], 1)
        self.assertEqual(result["citation_recall"], .5)
        self.assertEqual(result["answer_completeness"], .5)
        with self.assertRaises(ValueError):
            generation_metrics([{"supported": "true", "citations": []}], 0, [])

    def test_refusal_precision_recall_separate(self):
        result = refusal_metrics([True, False, True], [True, True, False])
        self.assertEqual(result["precision"], .5)
        self.assertEqual(result["recall"], .5)


if __name__ == "__main__":
    unittest.main()
