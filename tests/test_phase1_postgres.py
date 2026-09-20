"""Opt-in integration tests: EMPTY disposable loopback PostgreSQL only.

Never uses DATABASE_URL. No models, downloads, public DBs or persistent role changes.
Set LOCAL_RAG_TEST_DATABASE_URL and LOCAL_RAG_TEST_DISPOSABLE=YES after provisioning
an empty database named rag_phase1_test_<name> with pgvector available. The owner
must be able to create the schema and a temporary role. All test DDL/DML rolls back.
"""
import ast
import hashlib
import inspect
import os
from pathlib import Path
import unittest
import uuid
from contextlib import contextmanager, ExitStack
from unittest.mock import patch
from urllib.parse import urlsplit

import psycopg
from psycopg import sql
from pgvector.psycopg import register_vector
import app


class PostgreSQLPhase1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.getenv("LOCAL_RAG_TEST_DATABASE_URL", "")
        if not value or os.getenv("LOCAL_RAG_TEST_DISPOSABLE") != "YES":
            raise unittest.SkipTest("Disposable local PostgreSQL not explicitly configured; no connection attempted")
        target = urlsplit(value)
        if (target.scheme not in {"postgres", "postgresql"}
                or target.hostname not in {"localhost", "127.0.0.1", "::1"}
                or not target.path.removeprefix("/").startswith("rag_phase1_test_")
                or target.query or target.fragment):
            raise RuntimeError("Integration tests require a named loopback rag_phase1_test_ database without URL overrides")
        try:
            cls.conn = psycopg.connect(value, connect_timeout=3)
        except psycopg.Error as exc:
            raise RuntimeError("Disposable database connection failed; credentials omitted") from None
        cls.addClassCleanup(cls.conn.close)
        cls.addClassCleanup(cls.conn.rollback)
        tables = cls.conn.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]
        if tables:
            raise RuntimeError("Refusing a non-empty public schema; provision a new disposable database")
        # Older PostgreSQL defaults grant CREATE to PUBLIC. This is an empty,
        # explicitly disposable database; even this change is rolled back.
        cls.conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        # Use the application's actual schema statements without executing its
        # autocommit migration runner or contacting its configured database.
        tree = ast.parse(inspect.getsource(app._initialize_database_once))
        assignment = next(node for node in tree.body[0].body if isinstance(node, ast.Assign))
        statements = ast.literal_eval(assignment.value)
        for statement in statements:
            cls.conn.execute(statement)
        register_vector(cls.conn)
        cls.role = "rag_phase1_test_role_" + uuid.uuid4().hex[:12]
        cls.conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(cls.role)))
        # SET ROLE requires membership even when the temporary role has no LOGIN.
        # Both the role and its membership disappear with the outer rollback.
        cls.conn.execute(sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(cls.role)))
        cls.conn.execute("INSERT INTO rag_users (id,name,api_key_hash,role) VALUES (%s,'Fixture admin',%s,'admin')",
                         (app.MASTER_USER_ID, app.api_key_hash("fixture-only-master")))

    def setUp(self):
        self.conn.execute("SAVEPOINT phase1_case")
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(app, "db_connection", self.database))
        self.stack.enter_context(patch.object(app, "ensure_generation_resources", return_value={}))
        self.stack.enter_context(patch.object(app, "create_embedding", return_value=[0.0] * 768))
        self.stack.enter_context(patch.object(app, "MEMORY_ANSWER_CACHE", {}))
        self.stack.enter_context(patch.object(app, "RATE_LIMIT_BUCKETS", {}))
        self.stack.enter_context(patch.object(app, "API_KEY", "fixture-only-master-key-" + "x" * 32))

    def tearDown(self):
        self.stack.close()
        self.conn.execute("ROLLBACK TO SAVEPOINT phase1_case")
        self.conn.execute("RELEASE SAVEPOINT phase1_case")

    @contextmanager
    def database(self):
        with self.conn.transaction():
            yield self.conn

    def store(self, text="old content", replace=False):
        return app.store_document(filename="fixture.txt", source="fixture.txt", media_type="text/plain",
            raw_data=text.encode(), pages=[app.DocumentPage(1, text)], chunk_size=900, overlap=120, replace=replace)

    def test_runtime_role_can_use_current_schema_without_ddl_privileges(self):
        grant_text = Path("sql/neon_least_privilege.sql").read_text(encoding="utf-8").replace("rag_app", self.role)
        self.conn.execute(grant_text)
        self.conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(self.role)))
        try:
            item = self.store()
            self.assertEqual(item["status"], "ready")
            created = app.create_user(app.UserRequest(name="Fixture user"), app.Principal(app.MASTER_USER_ID, "Admin", "admin"))
            self.assertEqual(app.require_api_key(created["api_key"]).name, "Fixture user")
            self.assertFalse(self.conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0])
            self.assertFalse(self.conn.execute("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()[0])
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.conn.execute("CREATE TABLE public.forbidden_fixture(id int)")
        finally:
            self.conn.execute("RESET ROLE")

    def test_real_auth_rejects_expired_inactive_and_rotated_keys(self):
        master = app.Principal(app.MASTER_USER_ID, "Admin", "admin")
        created = app.create_user(app.UserRequest(name="Fixture user"), master)
        key, user_id = created["api_key"], uuid.UUID(created["id"])
        self.assertEqual(app.require_api_key(key).id, user_id)
        self.conn.execute("UPDATE rag_users SET expires_at=NOW()-INTERVAL '1 minute' WHERE id=%s", (user_id,))
        with self.assertRaises(app.HTTPException) as failure:
            app.require_api_key(key)
        self.assertEqual(failure.exception.status_code, 401)
        self.conn.execute("UPDATE rag_users SET expires_at=NULL WHERE id=%s", (user_id,))
        rotated = app.rotate_user_key(user_id, master)
        with self.assertRaises(app.HTTPException):
            app.require_api_key(key)
        self.assertEqual(app.require_api_key(rotated["api_key"]).id, user_id)
        app.deactivate_user(user_id, master)
        with self.assertRaises(app.HTTPException):
            app.require_api_key(rotated["api_key"])

    def test_replacement_failure_really_rolls_back_and_preserves_permissions(self):
        old = self.store()
        document_id = uuid.UUID(old["id"])
        before = self.conn.execute("SELECT content FROM rag_chunks WHERE document_id=%s", (document_id,)).fetchall()
        permissions = self.conn.execute("SELECT user_id,can_read,can_write FROM rag_document_permissions WHERE document_id=%s", (document_id,)).fetchall()
        # Trigger a real PostgreSQL failure after replacement has changed content.
        self.conn.execute("""CREATE FUNCTION phase1_reject_activation() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.status='ready' AND NEW.extracted_text='new content' THEN
                RAISE EXCEPTION 'synthetic activation failure'; END IF; RETURN NEW; END $$""")
        self.conn.execute("CREATE TRIGGER phase1_fail BEFORE UPDATE ON rag_documents FOR EACH ROW EXECUTE FUNCTION phase1_reject_activation()")
        with self.assertRaises(psycopg.Error):
            self.store("new content", True)
        self.assertEqual(self.conn.execute("SELECT content FROM rag_chunks WHERE document_id=%s", (document_id,)).fetchall(), before)
        self.assertEqual(self.conn.execute("SELECT user_id,can_read,can_write FROM rag_document_permissions WHERE document_id=%s", (document_id,)).fetchall(), permissions)
        self.assertEqual(self.conn.execute("SELECT status FROM rag_documents WHERE id=%s", (document_id,)).fetchone()[0], "ready")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM rag_ingestion_jobs WHERE status='failed'").fetchone()[0], 1)
        self.conn.execute("DROP TRIGGER phase1_fail ON rag_documents")
        replaced = self.store("new content", True)
        self.assertEqual(replaced["id"], old["id"])

    def test_permission_revocation_invalidates_real_cached_evidence(self):
        master = app.Principal(app.MASTER_USER_ID, "Admin", "admin")
        item = self.store()
        document_id = uuid.UUID(item["id"])
        created = app.create_user(app.UserRequest(name="Reader"), master)
        user_id = uuid.UUID(created["id"])
        user = app.Principal(user_id, "Reader", "user")
        app.set_document_permission(document_id, app.PermissionRequest(user_id=user_id, can_read=True), master)
        version = app.current_corpus_version(force_refresh=True)
        cached = {"answer": "old content", "sources": [{"document_id": str(document_id)}], "metrics": {}}
        app.remember_answer("fixture-cache", cached)
        self.assertIsNotNone(app.get_cached_answer("fixture-cache", user))
        # Direct database revocation bypasses local invalidation: recheck must still deny.
        self.conn.execute("UPDATE rag_document_permissions SET can_read=FALSE WHERE document_id=%s AND user_id=%s", (document_id, user_id))
        self.assertGreater(app.current_corpus_version(force_refresh=True), version)
        self.assertIsNone(app.get_cached_answer("fixture-cache", user))


if __name__ == "__main__":
    unittest.main()
