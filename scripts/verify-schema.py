"""Read-only verification for hardening-release database objects."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
import app  # noqa: E402


EXPECTED_COLUMNS = {
    "rag_users": {"requests_per_minute", "max_concurrent_requests", "allowed_models", "expires_at", "last_used_at"},
    "rag_documents": {"lifecycle_status", "document_version", "effective_date", "department", "document_type", "ocr_confidence", "supersedes_id"},
}
EXPECTED_TABLES = {"rag_structured_records", "rag_shadow_embeddings"}


def main() -> None:
    with app.connect_database_with_retry() as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()}
        columns = {
            table: {row[0] for row in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            ).fetchall()}
            for table in EXPECTED_COLUMNS
        }
    missing = sorted(EXPECTED_TABLES - tables)
    for table, required in EXPECTED_COLUMNS.items():
        missing.extend(f"{table}.{column}" for column in sorted(required - columns[table]))
    if missing:
        raise SystemExit("Missing schema objects: " + ", ".join(missing))
    print("Hardening schema verified")


if __name__ == "__main__":
    main()
