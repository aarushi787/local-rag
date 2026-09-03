"""Fast local tests that do not contact Ollama or Neon."""

from __future__ import annotations

import unittest
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

import app
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request
from drive_sync import safe_extract_zip
from document_processing import DocumentPage, TextBlock, extract_document, union_bbox
from extract_ocr import result_lines
from inference_queue import InferenceCancelledError, InferenceQueue, QueueFullError


class ChunkingTests(unittest.TestCase):
    def test_chunks_overlap_and_keep_page_number(self) -> None:
        page = DocumentPage(number=7, text=" ".join(f"word{n}" for n in range(100)))
        chunks = app.chunk_pages([page], size=120, overlap=20)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk["page_number"] == 7 for chunk in chunks))
        self.assertEqual([chunk["chunk_index"] for chunk in chunks], list(range(1, len(chunks) + 1)))

    def test_overlap_must_be_smaller_than_size(self) -> None:
        with self.assertRaises(ValueError):
            app.chunk_text("some words", size=10, overlap=10)

    def test_structural_chunks_keep_parent_and_heading(self) -> None:
        page = DocumentPage(number=2, text="LEAVE POLICY\nEmployees receive annual leave.")
        chunks = app.chunk_pages([page], size=200, overlap=20)
        self.assertEqual(chunks[0]["section_title"], "LEAVE POLICY")
        self.assertEqual(chunks[0]["parent_content"], "Employees receive annual leave.")
        self.assertTrue(chunks[0]["parent_key"].startswith("2:"))


class DocumentProcessingTests(unittest.TestCase):
    def test_text_extraction(self) -> None:
        parsed = extract_document(
            b"first line\nsecond line",
            "notes.txt",
            "text/plain",
            Path.cwd(),
        )
        self.assertEqual(parsed.pages[0].number, 1)
        self.assertIn("second line", parsed.text)

    def test_json_records_become_readable_evidence(self) -> None:
        parsed = extract_document(
            b'[{"headline":"Industry grows","year":2026}]',
            "records.json",
            "application/json",
            Path.cwd(),
        )
        self.assertIn("Record 1", parsed.text)
        self.assertIn("headline: Industry grows", parsed.text)
        self.assertIn("year: 2026", parsed.text)


class DriveSyncTests(unittest.TestCase):
    def test_zip_extracts_only_supported_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("2026/article.txt", "news clipping")
                bundle.writestr("2026/program.exe", b"ignored")
            extracted = safe_extract_zip(archive, root / "output")
            self.assertEqual([path.name for path in extracted], ["article.txt"])
            self.assertEqual(extracted[0].read_text(), "news clipping")

    def test_zip_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../outside.txt", "unsafe")
            with self.assertRaises(ValueError):
                safe_extract_zip(archive, root / "output")


class DocumentProcessingAdditionalTests(unittest.TestCase):
    def test_docx_extraction(self) -> None:
        from docx import Document

        stream = BytesIO()
        document = Document()
        document.add_paragraph("Employee leave policy")
        document.save(stream)
        parsed = extract_document(
            stream.getvalue(), "policy.docx", None, Path.cwd()
        )
        self.assertIn("Employee leave policy", parsed.text)

    def test_xlsx_extraction_preserves_sheet_and_rows(self) -> None:
        from openpyxl import Workbook

        stream = BytesIO()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Clippings"
        sheet.append(["Headline", "Publisher"])
        sheet.append(["Industry update", "Daily News"])
        workbook.save(stream)
        workbook.close()
        parsed = extract_document(
            stream.getvalue(), "clippings.xlsx", None, Path.cwd()
        )
        self.assertIn("Sheet: Clippings", parsed.text)
        self.assertIn("Industry update | Daily News", parsed.text)

    def test_pdf_page_numbers(self) -> None:
        import pymupdf

        document = pymupdf.open()
        first = document.new_page()
        first.insert_text((72, 72), "First page has enough readable policy text.")
        second = document.new_page()
        second.insert_text((72, 72), "Second page has enough readable procedure text.")
        parsed = extract_document(
            document.tobytes(), "policy.pdf", "application/pdf", Path.cwd()
        )
        document.close()
        self.assertEqual([page.number for page in parsed.pages], [1, 2])
        self.assertIn("Second page", parsed.pages[1].text)

    def test_ocr_result_preserves_bbox(self) -> None:
        lines = result_lines(
            {
                "res": {
                    "rec_texts": ["Policy title"],
                    "rec_boxes": [[10, 20, 100, 40]],
                }
            }
        )
        self.assertEqual(lines[0]["bbox"], [10.0, 20.0, 100.0, 40.0])

    def test_bbox_union(self) -> None:
        result = union_bbox(
            [
                TextBlock("one", [10, 20, 30, 40]),
                TextBlock("two", [5, 25, 50, 60]),
            ]
        )
        self.assertEqual(result, [5, 20, 50, 60])


class RerankingTests(unittest.TestCase):
    def test_lexical_query_uses_or_terms_for_precise_matches(self) -> None:
        query = app.lexical_tsquery("What does record PG2473 say about its status?")
        self.assertIn("pg2473", query)
        self.assertIn(" | ", query)

    def test_exact_record_identifier_becomes_literal_pattern(self) -> None:
        self.assertEqual(app.exact_identifier_patterns("Find PG2473 please"), ["%pg2473%"])
        self.assertEqual(app.exact_identifier_patterns("ordinary question"), [])

    def test_exact_record_excerpt_excludes_adjacent_records(self) -> None:
        text = (
            '{"id":"PG2454","status":"Verified"}, '
            '{"id":"PG2473","publisher":"Maharashtra Times","status":"Unverified"}, '
            '{"id":"PG2504","status":"Verified"}'
        )
        excerpt = app.exact_record_excerpt(text, ["%pg2473%"])
        self.assertIn('"status":"Unverified"', excerpt)
        self.assertNotIn("PG2454", excerpt)
        self.assertNotIn("PG2504", excerpt)

    def test_follow_up_question_keeps_previous_topic(self) -> None:
        messages = [
            app.ChatMessage(role="user", content="Which publisher covered the expo?"),
            app.ChatMessage(role="assistant", content="The Daily News."),
            app.ChatMessage(role="user", content="What date was it?"),
        ]
        query = app.contextualized_question(messages)
        self.assertIn("Which publisher covered the expo?", query)
        self.assertIn("What date was it?", query)

    def test_broad_questions_retrieve_more_evidence(self) -> None:
        self.assertEqual(app.retrieval_depth("List all publishers", 3), 5)
        self.assertEqual(app.retrieval_depth("Who published this?", 3), 3)

    def test_context_packing_respects_budget(self) -> None:
        rows = [
            {"id": index, "content": "x" * 3000, "context_content": "x" * 3000}
            for index in range(4)
        ]
        packed = app.pack_context_rows(rows, 1536)
        self.assertLessEqual(
            sum(len(row["context_content"]) + 180 for row in packed),
            max(4200, 1536 * 3),
        )

    def test_relevant_lexical_candidate_is_promoted(self) -> None:
        rows = [
            {
                "content": "unrelated weather report",
                "similarity": 0.7,
                "hybrid_score": 0.02,
            },
            {
                "content": "PaddleOCR is the primary OCR model in the workflow",
                "similarity": 0.68,
                "hybrid_score": 0.02,
            },
        ]
        ranked = app.rerank_candidates("Which primary OCR model is used?", rows, 2)
        self.assertIn("PaddleOCR", ranked[0]["content"])

    def test_duplicate_candidate_content_is_removed(self) -> None:
        rows = [
            {"content": "same evidence", "similarity": 0.8, "hybrid_score": 0.02},
            {"content": "same evidence", "similarity": 0.7, "hybrid_score": 0.01},
        ]
        self.assertEqual(len(app.rerank_candidates("evidence", rows, 3)), 1)

    def test_mmr_prefers_diverse_evidence(self) -> None:
        rows = [
            {"content": "OCR model scans pages", "similarity": 0.9, "rerank_score": 0.9},
            {"content": "OCR model scans every page", "similarity": 0.89, "rerank_score": 0.89},
            {"content": "Vector search retrieves chunks", "similarity": 0.8, "rerank_score": 0.8},
        ]
        selected = app.mmr_select(rows, 2, diversity=0.55)
        self.assertIn("Vector search", selected[1]["content"])

    def test_greetings_bypass_document_retrieval(self) -> None:
        for message in ("hello", "Hello chat!", "good morning", "thank you"):
            self.assertTrue(app.is_conversational_message(message))

    def test_knowledge_question_does_not_bypass_retrieval(self) -> None:
        self.assertFalse(app.is_conversational_message("What is the model workflow?"))

    def test_summary_intent_is_detected(self) -> None:
        self.assertTrue(app.is_summary_request("Summarize my uploaded document"))
        self.assertFalse(app.is_summary_request("Which model is used?"))

    def test_summary_prompt_treats_context_as_the_document(self) -> None:
        messages = [app.ChatMessage(role="user", content="Summarize my document")]
        rows = [{"source": "policy.pdf", "page_number": 1, "content": "Leave policy"}]
        outgoing = app.grounded_messages(messages, rows, summary_mode=True)
        self.assertIn("text of the document", outgoing[0]["content"])
        self.assertIn("Leave policy", outgoing[-1]["content"])

    def test_history_is_bounded_for_small_models(self) -> None:
        messages = [
            app.ChatMessage(role="user", content=f"message {index} " + "x" * 1000)
            for index in range(10)
        ]
        history = app.bounded_history(messages)
        self.assertLessEqual(len(history), app.MAX_HISTORY_MESSAGES)
        self.assertLessEqual(sum(len(item["content"]) for item in history), app.MAX_HISTORY_CHARS)
        self.assertIn("message 9", history[-1]["content"])


class ResponseProfileTests(unittest.TestCase):
    def test_fast_profile_caps_tokens_and_selects_model(self) -> None:
        request = app.ChatCompletionRequest(
            messages=[app.ChatMessage(role="user", content="hello")],
            profile="fast",
            max_tokens=500,
        )
        settings = app.response_settings(request)
        self.assertEqual(settings["model"], "gemma3:1b-it-qat")
        self.assertEqual(settings["max_tokens"], 120)
        self.assertEqual(settings["top_k"], 2)

    def test_legacy_request_keeps_explicit_model(self) -> None:
        request = app.ChatCompletionRequest(
            model="custom-model",
            messages=[app.ChatMessage(role="user", content="hello")],
            max_tokens=75,
        )
        settings = app.response_settings(request)
        self.assertIsNone(settings["profile"])
        self.assertEqual(settings["model"], "custom-model")
        self.assertEqual(settings["max_tokens"], 75)

    def test_auto_profile_routes_summary_to_quality(self) -> None:
        request = app.ChatCompletionRequest(
            messages=[app.ChatMessage(role="user", content="Summarize this policy")],
            profile="auto",
        )
        settings = app.response_settings(request, "Summarize this policy")
        self.assertEqual(settings["profile"], "quality")

    def test_auto_profile_routes_normal_question_to_balanced(self) -> None:
        self.assertEqual(app.adaptive_profile("Which model creates embeddings?"), "balanced")


class InferenceQueueTests(unittest.TestCase):
    def test_queue_reports_active_and_releases(self) -> None:
        queue = InferenceQueue(max_waiting=2, wait_timeout=1)
        queue.acquire()
        self.assertEqual(queue.snapshot()["active"], 1)
        queue.release()
        self.assertEqual(queue.snapshot()["active"], 0)

    def test_zero_capacity_rejects_a_waiter(self) -> None:
        queue = InferenceQueue(max_waiting=0, wait_timeout=1)
        queue.acquire()
        with self.assertRaises(QueueFullError):
            queue.acquire()
        queue.release()

    def test_cancelled_waiter_is_removed(self) -> None:
        import threading

        queue = InferenceQueue(max_waiting=1, wait_timeout=1)
        queue.acquire()
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(InferenceCancelledError):
            queue.acquire(cancelled)
        self.assertEqual(queue.snapshot()["waiting"], 0)
        queue.release()


class ProductionBoundaryTests(unittest.TestCase):
    @staticmethod
    def request(path: str = "/v1/models", forwarded_proto: str = "http") -> Request:
        return Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [(b"x-forwarded-proto", forwarded_proto.encode())],
                "client": ("127.0.0.1", 50000),
                "server": ("127.0.0.1", 8000),
            }
        )

    def test_security_headers_and_hsts_are_applied(self) -> None:
        response = JSONResponse({"ok": True})
        app.apply_security_headers(response, self.request(forwarded_proto="https"))
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("max-age=31536000", response.headers["strict-transport-security"])

    def test_rate_limiter_does_not_store_raw_api_key(self) -> None:
        original_requests = app.RATE_LIMIT_REQUESTS
        original_window = app.RATE_LIMIT_WINDOW_SECONDS
        try:
            app.RATE_LIMIT_REQUESTS = 2
            app.RATE_LIMIT_WINDOW_SECONDS = 60
            app.RATE_LIMIT_BUCKETS.clear()
            self.assertIsNone(app.take_rate_limit_slot("key:hashed", now=100))
            self.assertIsNone(app.take_rate_limit_slot("key:hashed", now=101))
            self.assertGreater(app.take_rate_limit_slot("key:hashed", now=102), 0)
            self.assertNotIn("raw-secret", app.RATE_LIMIT_BUCKETS)
        finally:
            app.RATE_LIMIT_REQUESTS = original_requests
            app.RATE_LIMIT_WINDOW_SECONDS = original_window
            app.RATE_LIMIT_BUCKETS.clear()

    def test_master_api_key_authentication_and_missing_key(self) -> None:
        original_key = app.API_KEY
        original_required = app.REQUIRE_API_KEY
        try:
            app.API_KEY = "test-master-key"
            app.REQUIRE_API_KEY = True
            principal = app.require_api_key("test-master-key")
            self.assertTrue(principal.is_admin)
            with self.assertRaises(HTTPException) as raised:
                app.require_api_key(None)
            self.assertEqual(raised.exception.status_code, 401)
        finally:
            app.API_KEY = original_key
            app.REQUIRE_API_KEY = original_required


if __name__ == "__main__":
    unittest.main()
