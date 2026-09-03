-- Run as the Neon database owner after replacing the example password.
-- Prefer creating a separate Neon role in the dashboard and adapting this file.
CREATE ROLE rag_app LOGIN PASSWORD 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';

GRANT CONNECT ON DATABASE neondb TO rag_app;
GRANT USAGE ON SCHEMA public TO rag_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    rag_documents,
    rag_chunks,
    rag_conversations,
    rag_messages
TO rag_app;
GRANT USAGE, SELECT ON SEQUENCE rag_chunks_id_seq TO rag_app;

-- The application role does not receive CREATE, DROP, role-management, or
-- extension-management rights. Run schema migrations with the owner URL, then
-- use the rag_app pooled URL for normal API operation.
