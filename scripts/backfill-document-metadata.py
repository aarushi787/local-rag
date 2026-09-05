"""Populate lifecycle metadata for documents ingested before the hardening release."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
import app  # noqa: E402


def main() -> None:
    updated = 0
    with app.connect_database_with_retry() as conn:
        rows = conn.execute(
            """SELECT id, original_filename, COALESCE(extracted_text, ''), metadata
               FROM rag_documents
               WHERE document_type IS NULL OR metadata IS NULL
                  OR NOT (metadata ? 'embedding_model')"""
        ).fetchall()
        updates = []
        for document_id, filename, text, existing in rows:
            metadata = app.infer_document_metadata(filename, text, [])
            merged = {**(existing or {}), **{key: value for key, value in metadata.items() if value is not None}}
            updates.append((metadata["document_version"], metadata["effective_date"],
                            metadata["department"], metadata["document_type"],
                            json.dumps(merged), document_id))
            updated += 1
        with conn.cursor() as cursor:
            cursor.executemany(
                """UPDATE rag_documents
                   SET document_version = COALESCE(document_version, %s),
                       effective_date = COALESCE(effective_date, %s::date),
                       department = COALESCE(department, %s),
                       document_type = COALESCE(document_type, %s),
                       metadata = %s::jsonb, updated_at = NOW()
                   WHERE id = %s""",
                updates,
            )
        conn.commit()
    print(f"Backfilled metadata for {updated} documents")


if __name__ == "__main__":
    main()
