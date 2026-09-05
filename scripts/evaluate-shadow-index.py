"""Compare active and BGE-M3 shadow source recall using the approved eval set."""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv
from pgvector import Vector
from pgvector.psycopg import register_vector


PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")


def normalize(value: str) -> str:
    return " ".join(value.lower().replace("\\", "/").split())


def main() -> None:
    dataset = [json.loads(line) for line in (PROJECT_DIR / "evaluation_questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    factual = [item for item in dataset if item.get("expected_source") and not item.get("should_refuse")]
    ollama_url = os.getenv("EMBEDDING_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("SHADOW_EMBEDDING_MODEL", "bge-m3")
    hits = {1: 0, 3: 0, 5: 0}
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)
        indexed = conn.execute("SELECT COUNT(*) FROM rag_shadow_embeddings").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
        if indexed < total:
            raise RuntimeError(f"Shadow index is incomplete: {indexed}/{total} chunks")
        for item in factual:
            response = requests.post(
                f"{ollama_url}/api/embed",
                json={"model": model, "input": item["question"], "keep_alive": "30m"},
                timeout=300,
            )
            response.raise_for_status()
            vector = response.json()["embeddings"][0]
            rows = conn.execute(
                """SELECT d.source_name FROM rag_shadow_embeddings s
                   JOIN rag_chunks c ON c.id = s.chunk_id
                   JOIN rag_documents d ON d.id = c.document_id
                   WHERE d.lifecycle_status = 'active'
                   ORDER BY s.embedding <=> %s LIMIT 5""",
                (Vector(vector),),
            ).fetchall()
            sources = [normalize(row[0]) for row in rows]
            expected = normalize(item["expected_source"])
            for k in hits:
                if any(expected in source or source in expected for source in sources[:k]):
                    hits[k] += 1
    count = len(factual)
    print(json.dumps({"questions": count, **{f"recall_at_{k}": round(hits[k] / count, 4) if count else 0 for k in hits}}, indent=2))


if __name__ == "__main__":
    main()
