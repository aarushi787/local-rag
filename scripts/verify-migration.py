"""Read-only canonical row/checksum/vector comparison. Never performs cutover.

DATABASE_URL is the source; LOCAL_DATABASE_URL must identify a loopback target.
Pause ingestion externally for a stable comparison; this script stops no services.
"""
from __future__ import annotations
import hashlib
import json
import os
from urllib.parse import urlsplit

import psycopg
from psycopg import sql, IsolationLevel
from dotenv import load_dotenv


def assert_local(url):
    target = urlsplit(url)
    if target.scheme not in {"postgres", "postgresql"} or target.hostname not in {
        "127.0.0.1", "::1", "localhost"
    } or target.query or target.fragment or target.path in {"", "/"}:
        raise ValueError("Target must be a named loopback PostgreSQL URL without query overrides")


def snapshot(url):
    result = {}
    with psycopg.connect(url, connect_timeout=10) as conn:
        conn.read_only = True
        conn.isolation_level = IsolationLevel.REPEATABLE_READ
        tables = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'rag\\_%' ORDER BY tablename").fetchall()
        if not tables:
            raise ValueError("No RAG tables found")
        for (table,) in tables:
            digest, count = hashlib.sha256(), 0
            with conn.cursor(name="verify_rows") as cursor:
                cursor.execute(sql.SQL("SELECT to_jsonb(t)::text FROM {} t ORDER BY to_jsonb(t)::text").format(sql.Identifier("public", table)))
                for (row,) in cursor:
                    value = row.encode("utf-8")
                    digest.update(len(value).to_bytes(8, "big"))
                    digest.update(value)
                    count += 1
            result[table] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def main():
    load_dotenv()
    source, target = os.environ["DATABASE_URL"], os.environ["LOCAL_DATABASE_URL"]
    assert_local(target)
    if source == target:
        raise ValueError("Source and target must differ")
    before, local, after = snapshot(source), snapshot(target), snapshot(source)
    stable = before == after
    matches = stable and before == local
    print(json.dumps({"source_stable": stable, "matches": matches,
                      "source": before, "target": local,
                      "note": "Includes stored embeddings, metadata, permissions and checksums; does not validate retrieval quality or sequence ownership."}, indent=2))
    raise SystemExit(0 if matches else 1)


if __name__ == "__main__":
    try:
        main()
    except (psycopg.Error, ValueError, KeyError) as exc:
        # Connection exceptions may contain credentials or hostnames.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1)
