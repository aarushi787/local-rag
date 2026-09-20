"""Phase 1 offline regressions. All documents, credentials and services are synthetic."""
import asyncio
import copy
import hashlib
import json
import threading
import time
import unittest
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import app
import document_processing
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware
from inference_queue import InferenceQueue, InferenceCancelledError


@contextmanager
def connection(conn):
    yield conn


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(app, "API_KEY", "synthetic-master-key-" + "x" * 32))
        self.conn = Mock()
        self.stack.enter_context(patch.object(app, "db_connection", lambda: connection(self.conn)))
        self.stack.enter_context(patch.object(app, "RATE_LIMIT_BUCKETS", {}))

    def test_no_key_never_creates_anonymous_admin(self):
        with patch.object(app, "API_KEY", ""), patch.object(app, "REQUIRE_API_KEY", False):
            with self.assertRaises(app.HTTPException) as failure:
                app.require_api_key(None)
        self.assertEqual(failure.exception.status_code, 503)
        self.conn.execute.assert_not_called()

    def test_startup_requires_strong_bootstrap_key_even_with_legacy_flag_false(self):
        with patch.object(app, "API_KEY", ""), patch.object(app, "REQUIRE_API_KEY", False):
            with self.assertRaisesRegex(RuntimeError, "anonymous access is disabled"):
                app.validate_configuration()

    def test_missing_credential_is_401_without_database(self):
        with self.assertRaises(app.HTTPException) as failure:
            app.require_api_key(None)
        self.assertEqual(failure.exception.status_code, 401)
        self.conn.execute.assert_not_called()

    def test_bootstrap_and_bearer_and_matching_headers(self):
        for supplied, bearer in ((app.API_KEY, None), (None, f"Bearer {app.API_KEY}"),
                                  (app.API_KEY, f"bearer {app.API_KEY}")):
            self.assertTrue(app.require_api_key(supplied, bearer).is_admin)
        self.conn.execute.assert_not_called()

    def test_conflicting_headers_are_rejected(self):
        with self.assertRaises(app.HTTPException) as failure:
            app.require_api_key(app.API_KEY, "Bearer another-key")
        self.assertEqual(failure.exception.status_code, 400)

    def test_malformed_bearer_is_rejected(self):
        for value in ("Basic abc", "Bearer ", "Bearer a b"):
            with self.subTest(value=value), self.assertRaises(app.HTTPException):
                app.require_api_key(None, value)

    def test_nonascii_credentials_return_401_not_server_error(self):
        for supplied, bearer in (("अवैध", None), ("अवैध", "Bearer fixture"), (None, "Bearer अवैध")):
            with self.subTest(supplied=supplied), self.assertRaises(app.HTTPException) as failure:
                app.require_api_key(supplied, bearer)
            self.assertEqual(failure.exception.status_code, 401)

    def test_regular_user_is_not_promoted(self):
        user_id = uuid.uuid4()
        self.conn.execute.return_value.fetchone.return_value = (user_id, "Fixture", "user", 30, 1, [])
        principal = app.require_api_key("synthetic-user-key")
        self.assertEqual(principal.id, user_id)
        self.assertFalse(principal.is_admin)
        query, params = self.conn.execute.call_args_list[0].args
        self.assertIn("AND active", query)
        self.assertIn("expires_at > NOW()", query)
        self.assertEqual(params, (app.api_key_hash("synthetic-user-key"),))

    def test_invalid_expired_inactive_and_rotated_keys_fail(self):
        # The database result models the active/hash/expiry predicate; integration
        # tests must separately establish that PostgreSQL enforces that predicate.
        self.conn.execute.return_value.fetchone.return_value = None
        for label in ("invalid", "expired", "inactive", "rotated-old"):
            with self.subTest(label=label), self.assertRaises(app.HTTPException) as failure:
                app.require_api_key("synthetic-" + label)
            self.assertEqual(failure.exception.status_code, 401)

    def test_rotation_and_deactivation_use_expected_predicates(self):
        user_id = uuid.uuid4()
        self.conn.execute.return_value.fetchone.return_value = ("Fixture",)
        result = app.rotate_user_key(user_id, app.Principal(app.MASTER_USER_ID, "Fixture", "admin"))
        sql, params = self.conn.execute.call_args.args
        self.assertIn("AND active", sql)
        self.assertEqual(params[0], app.api_key_hash(result["api_key"]))
        app.deactivate_user(user_id, app.Principal(app.MASTER_USER_ID, "Fixture", "admin"))
        self.assertIn("active = FALSE", self.conn.execute.call_args.args[0])

    def test_http_auth_contract_without_starting_application_services(self):
        isolated = FastAPI()
        @isolated.get("/me")
        def me(principal=Depends(app.require_api_key)):
            return {"role": principal.role}
        with TestClient(isolated) as client:
            self.assertEqual(client.get("/me").status_code, 401)
            self.assertEqual(client.get("/me", headers={"Authorization": f"Bearer {app.API_KEY}"}).json(), {"role": "admin"})

    def test_actual_cors_configuration_supports_patch(self):
        isolated = FastAPI()
        settings = {**app.CORS_OPTIONS, "allow_origins": ["https://fixture.invalid"]}
        isolated.add_middleware(CORSMiddleware, **settings)
        with TestClient(isolated) as client:
            headers = {"Origin": "https://fixture.invalid", "Access-Control-Request-Method": "PATCH",
                       "Access-Control-Request-Headers": "authorization,x-api-key"}
            self.assertEqual(client.options("/v1/conversations/test", headers=headers).status_code, 200)
            headers["Origin"] = "https://untrusted.invalid"
            self.assertEqual(client.options("/v1/conversations/test", headers=headers).status_code, 400)


class AtomicDocumentFixture:
    """Small transactional test double, not a substitute for PostgreSQL tests."""
    def __init__(self, fail=None):
        self.id = uuid.uuid4()
        self.state = {"text": "old usable document", "status": "ready", "chunks": ["old chunk"]}
        self.fail = fail
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def connection(self):
        snapshot = copy.deepcopy(self.state)
        try:
            yield self
            if self.fail == "commit":
                raise RuntimeError("synthetic commit failure")
        except Exception:
            self.state = snapshot
            self.rollbacks += 1
            raise
        else:
            self.commits += 1

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        cursor = Mock()
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None
        if "ORDER BY id FOR UPDATE" in sql:
            cursor.fetchall.return_value = [(self.id, "fixture.txt", "fixture.txt", "ready", 1, 1, "old-checksum")]
        if "DELETE FROM rag_chunks" in sql:
            self.state["chunks"] = []
        if "UPDATE rag_documents SET source_name" in sql:
            self.state.update(text=params[5], status="processing")
        if "INSERT INTO rag_chunks" in sql:
            if self.fail == "persistence":
                raise RuntimeError("synthetic persistence failure")
            self.state["chunks"].append(params[3])
        if "SET status = 'ready'" in sql:
            if self.fail == "activation":
                raise RuntimeError("synthetic activation failure")
            self.state["status"] = "ready"
        return cursor


class ReplacementTests(unittest.TestCase):
    def run_store(self, database, embedding_failure=False):
        def embed(_text):
            self.assertEqual(database.state["text"], "old usable document")
            self.assertEqual(database.statements, [])
            if embedding_failure:
                raise RuntimeError("synthetic embedding failure")
            return [0.0] * 768
        with patch.object(app, "db_connection", database.connection), \
             patch.object(app, "ensure_generation_resources", return_value={}), \
             patch.object(app, "create_embedding", side_effect=embed), \
             patch.object(app, "record_ingestion_failure") as failure, \
             patch.object(app, "invalidate_local_answer_caches") as invalidation:
            try:
                result = app.store_document(filename="fixture.txt", source="fixture.txt", media_type="text/plain",
                    raw_data=b"new approved content", pages=[app.DocumentPage(1, "new approved content")],
                    chunk_size=900, overlap=120, replace=True)
            except RuntimeError:
                failure.assert_called_once()
                invalidation.assert_not_called()
                raise
            failure.assert_not_called()
            invalidation.assert_called_once()
            return result

    def test_success_preserves_document_id_and_permissions(self):
        database = AtomicDocumentFixture()
        result = self.run_store(database)
        self.assertEqual(result["id"], str(database.id))
        self.assertEqual(database.state["status"], "ready")
        self.assertEqual(database.state["text"], "new approved content")
        self.assertEqual(database.commits, 1)
        sql = "\n".join(s for s, _ in database.statements)
        self.assertNotIn("DELETE FROM rag_documents", sql)
        self.assertNotIn("INSERT INTO rag_document_permissions", sql)
        self.assertNotIn("DELETE FROM rag_document_permissions", sql)

    def test_embedding_failure_never_writes_document(self):
        database = AtomicDocumentFixture()
        with self.assertRaises(RuntimeError):
            self.run_store(database, True)
        self.assertEqual(database.statements, [])
        self.assertEqual(database.state["text"], "old usable document")

    def test_persistence_activation_and_commit_failures_roll_back(self):
        for phase in ("persistence", "activation", "commit"):
            database = AtomicDocumentFixture(phase)
            with self.subTest(phase=phase), self.assertRaises(RuntimeError):
                self.run_store(database)
            self.assertEqual(database.state, {"text": "old usable document", "status": "ready", "chunks": ["old chunk"]})
            self.assertEqual(database.rollbacks, 1)

    def test_extraction_failure_records_attempt_without_store(self):
        with patch.object(app, "ensure_generation_resources", return_value={}), \
             patch.object(app, "extract_document", side_effect=ValueError("synthetic parse failure")), \
             patch.object(app, "store_document") as store, patch.object(app, "record_ingestion_failure") as failure:
            with self.assertRaises(ValueError):
                app.ingest_uploaded_data(b"fixture", "fixture.pdf", None, "fixture", True, 900, 120, uuid.uuid4())
            store.assert_not_called()
            failure.assert_called_once()

    def test_failure_record_does_not_include_exception_secrets(self):
        conn = Mock()
        with patch.object(app, "db_connection", lambda: connection(conn)):
            app.record_ingestion_failure("fixture", "fixture", uuid.uuid4(), RuntimeError("password=secret"))
        self.assertNotIn("password=secret", repr(conn.execute.call_args))
        self.assertIn("INSERT INTO rag_ingestion_jobs", conn.execute.call_args.args[0])

    def test_duplicate_cannot_grant_access_to_another_users_document(self):
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [(uuid.uuid4(), "fixture", "fixture", "ready", 1, 1, "hash")]
        conn.execute.return_value.fetchone.return_value = None
        with self.assertRaises(app.HTTPException) as failure:
            app.prepare_document_activation(conn, uuid.uuid4(), "fixture", "fixture", "hash", "text/plain",
                [], "text", {}, uuid.uuid4(), False)
        self.assertEqual(failure.exception.status_code, 409)
        self.assertFalse(any("INSERT INTO rag_document_permissions" in c.args[0] for c in conn.execute.call_args_list))

    def test_nonadmin_cannot_request_text_replacement(self):
        request = app.DocumentRequest(source="fixture", text="fixture", replace=True)
        with patch.object(app, "store_document") as store, self.assertRaises(app.HTTPException) as failure:
            app.ingest_document(request, app.Principal(uuid.uuid4(), "Reader", "user"))
        self.assertEqual(failure.exception.status_code, 403)
        store.assert_not_called()


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(app, "OFFICE_HOURS_POLICY", True))
        self.stack.enter_context(patch.object(app, "office_hours_active", return_value=True))
        self.stack.enter_context(patch.object(app, "RESOURCE_STATE", {"tripped_until": 0}))

    def test_missing_readings_fail_closed(self):
        for readings in ({"available_ram_gb": None, "cpu_percent": None},
                         {"available_ram_gb": float("nan"), "cpu_percent": 10}):
            with patch.object(app, "RESOURCE_STATE", {"tripped_until": 0}), \
                 patch.object(app, "system_resource_snapshot", return_value=readings), \
                 self.assertRaises(app.HTTPException) as failure:
                app.ensure_generation_resources()
            self.assertEqual(failure.exception.status_code, 503)
            self.assertIn("Retry-After", failure.exception.headers)

    def test_sensor_exception_fails_closed(self):
        with patch.object(app, "system_resource_snapshot", side_effect=OSError("synthetic")), \
             self.assertRaises(app.HTTPException):
            app.ensure_generation_resources()

    def test_low_memory_blocks_generation_and_embedding_before_http(self):
        for operation in (app.ollama_post, app.embedding_ollama_post):
            with patch.object(app, "system_resource_snapshot", return_value={"available_ram_gb": .1, "cpu_percent": 5}), \
                 patch.object(app.requests, "post") as post, self.assertRaises(app.HTTPException):
                operation("/api/chat", {})
            post.assert_not_called()

    def test_warmup_does_not_load_models_when_protection_trips(self):
        with patch.object(app, "ensure_generation_resources", side_effect=app.HTTPException(503, "busy")), \
             patch.object(app, "create_embedding") as embed, patch.object(app, "ollama_post") as chat:
            app.warm_local_models()
        embed.assert_not_called()
        chat.assert_not_called()

    def test_extraction_is_blocked_before_parser(self):
        with patch.object(app, "ensure_generation_resources", side_effect=app.HTTPException(503, "busy")), \
             patch.object(app, "_extract_document") as extract, self.assertRaises(app.HTTPException):
            app.extract_document(b"fixture", "fixture.txt", None, Path.cwd())
        extract.assert_not_called()

    def test_ocr_checks_resources_before_subprocess_or_model_paths(self):
        check = Mock(side_effect=app.HTTPException(503, "busy"))
        with patch.object(document_processing, "_ocr_paths") as paths, self.assertRaises(app.HTTPException):
            document_processing._ocr_image(b"fixture", ".png", 1, Path.cwd(), check)
        paths.assert_not_called()

    def test_ingestion_queue_full_returns_retry_and_does_not_enter(self):
        queue = InferenceQueue(max_waiting=0)
        queue.acquire()
        try:
            with patch.object(app, "INGESTION_QUEUE", queue), patch.object(app, "ensure_generation_resources", return_value={}), \
                 self.assertRaises(app.HTTPException) as failure:
                with app.ingestion_slot():
                    self.fail("must not enter")
            self.assertEqual(failure.exception.status_code, 429)
        finally:
            queue.release()

    def test_nested_ingestion_does_not_deadlock_and_releases_on_failure(self):
        queue = InferenceQueue()
        with patch.object(app, "INGESTION_QUEUE", queue), patch.object(app, "ensure_generation_resources", return_value={}):
            with self.assertRaises(ValueError):
                with app.ingestion_slot():
                    with app.ingestion_slot():
                        self.assertEqual(queue.snapshot()["active"], 1)
                        raise ValueError("fixture")
        self.assertEqual(queue.snapshot()["active"], 0)
        self.assertFalse(app.INGESTION_CONTEXT.active)


class CacheAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.user = app.Principal(uuid.uuid4(), "Fixture", "user")
        self.doc = uuid.uuid4()
        self.cached = {"answer": "private fixture", "sources": [{"document_id": str(self.doc)}],
                       "metrics": {"total_ms": 99999, "first_token_ms": 77777, "generation_tokens_per_second": 15}}

    def test_memory_cache_rechecks_revoked_permission(self):
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [(1,), (0,)]
        with patch.object(app, "MEMORY_ANSWER_CACHE", {"key": (time.monotonic()+60, self.cached)}), \
             patch.object(app, "db_connection", lambda: connection(conn)):
            self.assertEqual(app.get_cached_answer("key", self.user)["answer"], "private fixture")
            self.assertIsNone(app.get_cached_answer("key", self.user))
        sql, params = conn.execute.call_args.args
        self.assertIn("p.can_read", sql)
        self.assertIn("lifecycle_status = 'active'", sql)
        self.assertEqual(params[-1], self.user.id)

    def test_database_cache_rechecks_revoked_permission(self):
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [("private fixture", self.cached["sources"], {}, 60), (0,)]
        with patch.object(app, "MEMORY_ANSWER_CACHE", {}), patch.object(app, "db_connection", lambda: connection(conn)):
            self.assertIsNone(app.get_cached_answer("key", self.user))
            self.assertEqual(app.MEMORY_ANSWER_CACHE, {})

    def test_unverifiable_legacy_sources_are_not_served(self):
        self.assertFalse(app.sources_accessible([{"quote": "fixture"}], self.user))

    def test_cached_timings_are_new_and_do_not_mutate_original(self):
        with patch.object(app.time, "perf_counter", return_value=2):
            metrics = app.fresh_cache_metrics(self.cached, 1.99, 3)
        self.assertEqual(metrics["total_ms"], 10)
        self.assertEqual(metrics["first_visible_text_ms"], 10)
        self.assertEqual(metrics["generation_ms"], 0)
        self.assertIsNone(metrics["generation_tokens_per_second"])
        self.assertEqual(self.cached["metrics"]["total_ms"], 99999)

    def test_conversation_owner_check_precedes_message_read(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = None
        with patch.object(app, "db_connection", lambda: connection(conn)), self.assertRaises(app.HTTPException) as failure:
            app.get_conversation(uuid.uuid4(), self.user)
        self.assertEqual(failure.exception.status_code, 404)
        self.assertEqual(conn.execute.call_count, 1)
        self.assertIn("owner_user_id", conn.execute.call_args.args[0])

    def test_both_chat_paths_report_fresh_cache_timings(self):
        for streaming in (True, False):
            request = app.ChatCompletionRequest(messages=[app.ChatMessage(role="user", content="fixture?")], save=False)
            with self.subTest(streaming=streaming), patch.object(app, "cache_identity", return_value=("key", "fp")), \
                 patch.object(app, "get_cached_answer", return_value=self.cached) as cache:
                if streaming:
                    events = [json.loads(part[6:]) for part in app.streaming_chat(request, self.user) if part != "data: [DONE]\n\n"]
                    metrics = next(event["metrics"] for event in events if "metrics" in event)
                else:
                    metrics = app.chat_completions(request, self.user)["metrics"]
                cache.assert_called_once_with("key", self.user)
                self.assertNotEqual(metrics["total_ms"], 99999)
                self.assertEqual(metrics["generation_ms"], 0)
                self.assertTrue(metrics["cache_hit"])

    def test_empty_summary_does_not_report_zero_latency_as_measurement(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = (0, None, None, None, None)
        conn.execute.return_value.fetchall.return_value = []
        with patch.object(app, "db_connection", lambda: connection(conn)):
            metrics = app.metrics_summary(principal=app.Principal(app.MASTER_USER_ID, "Fixture", "admin"))
        self.assertEqual(metrics["samples"], 0)
        self.assertIsNone(metrics["total_ms"]["p50"])
        self.assertTrue(metrics["legacy_samples_excluded"])
        self.assertTrue(all("timing_scope" in call.args[0] for call in conn.execute.call_args_list))

    def test_lifecycle_failure_rolls_back_superseded_change(self):
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [(uuid.uuid4(),), None]
        rolled_back = []
        @contextmanager
        def transaction():
            try:
                yield conn
            except Exception:
                rolled_back.append(True)
                raise
        with patch.object(app, "db_connection", transaction), self.assertRaises(app.HTTPException):
            app.update_document_lifecycle(uuid.uuid4(), app.DocumentLifecycleRequest(lifecycle_status="active", supersedes_id=uuid.uuid4()),
                                          app.Principal(app.MASTER_USER_ID, "Fixture", "admin"))
        self.assertEqual(rolled_back, [True])


class StreamingTests(unittest.TestCase):
    def test_cancelled_buffered_answer_is_neither_emitted_nor_saved(self):
        user = app.Principal(uuid.uuid4(), "Fixture", "user")
        request = app.ChatCompletionRequest(messages=[app.ChatMessage(role="user", content="fixture?")], save=False, use_cache=False)
        response = MagicMock()
        response.__enter__.return_value = response
        def chunks():
            yield json.dumps({"message": {"content": "Unvalidated fixture content"}})
            with app.CANCEL_EVENTS_LOCK:
                next(iter(app.CANCEL_EVENTS.values()))[1].set()
            yield json.dumps({"done": True})
        response.iter_lines.side_effect = chunks
        with ExitStack() as stack:
            for name, value in {"ensure_generation_resources": {}, "retrieve_for_question": ([], True),
                                "prepare_conversation": None}.items():
                stack.enter_context(patch.object(app, name, return_value=value))
            saved = stack.enter_context(patch.object(app, "save_assistant_message"))
            cached = stack.enter_context(patch.object(app, "store_cached_answer"))
            stack.enter_context(patch.object(app.requests, "post", return_value=response))
            stack.enter_context(patch.object(app, "STRICT_CITATION_GATE", True))
            stack.enter_context(patch.object(app, "CANCEL_EVENTS", {}))
            output = "".join(app.streaming_chat(request, user))
            self.assertIn('"finish_reason": "cancelled"', output)
            self.assertNotIn("Unvalidated fixture content", output)
            saved.assert_not_called()
            cached.assert_not_called()
            self.assertEqual(app.CANCEL_EVENTS, {})
        self.assertEqual(app.MODEL_GATE.snapshot()["active"], 0)

    def test_queued_cancel_returns_cancelled_and_cleans_registry(self):
        user = app.Principal(uuid.uuid4(), "Fixture", "user")
        request = app.ChatCompletionRequest(messages=[app.ChatMessage(role="user", content="hi")], save=False, use_cache=False)
        queue = Mock()
        queue.position.return_value = 1
        queue.snapshot.return_value = {"waiting": 1}
        queue.acquire.side_effect = InferenceCancelledError("cancelled")
        with patch.object(app, "MODEL_GATE", queue), patch.object(app, "ensure_generation_resources", return_value={}), \
             patch.object(app, "CANCEL_EVENTS", {}):
            output = "".join(app.streaming_chat(request, user))
            self.assertIn('"finish_reason": "cancelled"', output)
            self.assertNotIn('"error"', output)
            self.assertEqual(app.CANCEL_EVENTS, {})
        queue.release.assert_not_called()
        self.assertNotIn(user.id, app.USER_GENERATION_COUNTS)

    def test_strict_stream_distinguishes_model_and_visible_text_time(self):
        user = app.Principal(uuid.uuid4(), "Fixture", "user")
        rows = [{"id": 1, "source": "fixture", "page_number": 1, "content": "The limit is 42 units.", "similarity": .9}]
        request = app.ChatCompletionRequest(messages=[app.ChatMessage(role="user", content="What is the limit?")], save=False, use_cache=False)
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_lines.return_value = [json.dumps({"message": {"content": "The limit is 42 units [Source 1]."}}), json.dumps({"done": True})]
        with ExitStack() as stack:
            for name, value in {"ensure_generation_resources": {}, "retrieve_for_question": (rows, True),
                                "prepare_conversation": None, "save_assistant_message": None}.items():
                stack.enter_context(patch.object(app, name, return_value=value))
            stack.enter_context(patch.object(app.requests, "post", return_value=response))
            stack.enter_context(patch.object(app, "STRICT_CITATION_GATE", True))
            events = [json.loads(part[6:]) for part in app.streaming_chat(request, user) if part != "data: [DONE]\n\n"]
        self.assertFalse(any("error" in event for event in events))
        metrics = next(event["metrics"] for event in events if "metrics" in event)
        self.assertGreaterEqual(metrics["first_visible_text_ms"], metrics["model_first_token_ms"])
        self.assertGreaterEqual(metrics["total_ms"], metrics["first_visible_text_ms"])
        self.assertGreaterEqual(metrics["validation_ms"], 0)
        self.assertTrue(metrics["buffered_for_validation"])


class GrantContractTests(unittest.TestCase):
    def test_runtime_grants_cover_schema_and_no_embedded_password(self):
        import re
        source = Path("app.py").read_text(encoding="utf-8")
        grants = Path("sql/neon_least_privilege.sql").read_text(encoding="utf-8")
        tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS (rag_\w+)", source))
        self.assertEqual(len(tables), 14)
        for table in tables:
            self.assertRegex(grants, rf"\b{table}\b")
        self.assertNotIn("PASSWORD '", grants)
        self.assertNotIn("ALL TABLES", grants)
        self.assertIn("rag_structured_records_id_seq", grants)
        self.assertIn("rag_evaluation_results_id_seq", grants)


if __name__ == "__main__":
    unittest.main()
