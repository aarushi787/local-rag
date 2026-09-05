"""Build a non-serving BGE-M3 shadow index without changing active retrieval."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv
from pgvector import Vector
from pgvector.psycopg import register_vector


PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    database_url = os.environ["DATABASE_URL"]
    ollama_url = os.getenv("EMBEDDING_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("SHADOW_EMBEDDING_MODEL", "bge-m3")
    processed = 0
    with psycopg.connect(database_url) as conn:
        register_vector(conn)
        while not args.limit or processed < args.limit:
            take = min(args.batch_size, args.limit - processed) if args.limit else args.batch_size
            rows = conn.execute(
                """SELECT c.id, c.content FROM rag_chunks c
                   LEFT JOIN rag_shadow_embeddings s ON s.chunk_id = c.id
                   WHERE s.chunk_id IS NULL ORDER BY c.id LIMIT %s""",
                (take,),
            ).fetchall()
            if not rows:
                break
            response = requests.post(
                f"{ollama_url}/api/embed",
                json={"model": model, "input": [row[1] for row in rows], "keep_alive": "30m"},
                timeout=600,
            )
            response.raise_for_status()
            vectors = response.json()["embeddings"]
            if any(len(vector) != 1024 for vector in vectors):
                raise RuntimeError(f"{model} did not return 1024-dimensional vectors")
            conn.executemany(
                """INSERT INTO rag_shadow_embeddings (chunk_id, embedding, embedding_model)
                   VALUES (%s, %s, %s) ON CONFLICT (chunk_id) DO NOTHING""",
                [(row[0], Vector(vector), model) for row, vector in zip(rows, vectors, strict=True)],
            )
            conn.commit()
            processed += len(rows)
            print(f"Indexed {processed} chunks into the shadow index")
    print(f"Shadow index complete: {processed} new chunks. Active retrieval was not changed.")


if __name__ == "__main__":
    main()
