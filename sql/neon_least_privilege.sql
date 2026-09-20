-- Run explicitly as the database/schema owner AFTER migrations.
-- Provision rag_app separately with a unique secret; never put a password here.
-- This script creates no roles, changes no credentials, and performs no cutover.
-- It applies to the CURRENT database (local PostgreSQL or hosted PostgreSQL).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_app') THEN
        RAISE EXCEPTION 'Provision the dedicated rag_app runtime role first';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_app'
               AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) THEN
        RAISE EXCEPTION 'rag_app must not have administrative privileges';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
               WHERE r.rolname = 'rag_app' AND c.relnamespace = 'public'::regnamespace) THEN
        RAISE EXCEPTION 'rag_app must not own application objects';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rag_app', current_database());
END $$;

GRANT USAGE ON SCHEMA public TO rag_app;
REVOKE CREATE ON SCHEMA public FROM rag_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    rag_users,
    rag_documents,
    rag_chunk_parents,
    rag_chunks,
    rag_document_permissions,
    rag_ingestion_jobs,
    rag_structured_records,
    rag_conversations,
    rag_messages,
    rag_answer_cache,
    rag_evaluation_runs,
    rag_evaluation_results
TO rag_app;
GRANT SELECT, UPDATE ON TABLE rag_corpus_state TO rag_app;
GRANT SELECT ON TABLE rag_shadow_embeddings TO rag_app;
GRANT USAGE, SELECT ON SEQUENCE
    rag_chunks_id_seq, rag_structured_records_id_seq, rag_evaluation_results_id_seq
TO rag_app;
GRANT EXECUTE ON FUNCTION rag_bump_corpus_version() TO rag_app;

DO $$
BEGIN
    IF has_schema_privilege('rag_app', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'rag_app inherits schema CREATE; review PUBLIC/membership grants before deployment';
    END IF;
END $$;

-- No grants on future tables or all public tables: update this allowlist with schema changes.
-- Runtime: RUN_MIGRATIONS=false. Migration/shadow-index maintenance uses a separate owner role.
-- Have the DBA review inherited role/database privileges too. Execute this entire
-- file in one transaction (psql --single-transaction --set ON_ERROR_STOP=1 --file ...).
