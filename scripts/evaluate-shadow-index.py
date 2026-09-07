"""Read-only vector-only A/B benchmark. Requires a human-reviewed dataset."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

import psycopg
import requests
import psutil
from dotenv import load_dotenv
from pgvector import Vector
from pgvector.psycopg import register_vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rag_core.evaluation import coverage, retrieval_metrics


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation_questions.jsonl")
    args = parser.parse_args()
    items = [json.loads(s) for s in args.dataset.read_text(encoding="utf-8").splitlines() if s.strip()]
    gate = coverage(items)
    if not gate["ready"]:
        print(json.dumps({"status": "blocked", "coverage": gate}, indent=2))
        raise SystemExit(1)
    factual = [i for i in items if not i["should_refuse"]]
    if not factual:
        raise ValueError("No answerable reviewed questions; zero-question evaluation is invalid")
    endpoint = os.getenv("EMBEDDING_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    models = {"active": os.getenv("EMBEDDING_MODEL", "embeddinggemma"),
              "shadow": os.getenv("SHADOW_EMBEDDING_MODEL", "bge-m3")}
    output = {"status": "measured", "promotion_approved": False, "pipelines": {},
              "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
              "method": "vector-only document relevance, not serving hybrid retrieval"}
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as conn:
        conn.read_only = True
        register_vector(conn)
        conn.commit()
        missing = conn.execute("""SELECT count(*) FROM rag_chunks c
            LEFT JOIN rag_shadow_embeddings s ON s.chunk_id=c.id AND s.embedding_model=%s
            WHERE c.embedding_model=%s AND s.chunk_id IS NULL""",
            (models["shadow"], models["active"])).fetchone()[0]
        if missing:
            raise ValueError("Shadow index is incomplete for the active model")
        for pipeline, model in models.items():
            records = []
            for item in factual:
                if psutil.virtual_memory().available < 3 * 1024**3:
                    raise ValueError("Benchmark paused: at least 3 GiB available RAM required")
                started = time.perf_counter()
                response = requests.post(f"{endpoint}/api/embed",
                    json={"model": model, "input": item["question"], "keep_alive": "0"}, timeout=300)
                response.raise_for_status()
                vector = Vector(response.json()["embeddings"][0])
                embedding_ms = (time.perf_counter() - started) * 1000
                if pipeline == "active":
                    query = """SELECT d.id::text, d.source_name FROM rag_chunks c
                        JOIN rag_documents d ON d.id=c.document_id
                        WHERE c.embedding_model=%s AND d.lifecycle_status='active'
                        ORDER BY c.embedding <=> %s LIMIT 30"""
                else:
                    query = """SELECT d.id::text, d.source_name FROM rag_shadow_embeddings s
                        JOIN rag_chunks c ON c.id=s.chunk_id
                        JOIN rag_documents d ON d.id=c.document_id
                        WHERE s.embedding_model=%s AND d.lifecycle_status='active'
                        ORDER BY s.embedding <=> %s LIMIT 30"""
                rows = conn.execute(query, (model, vector)).fetchall()
                expected = item["expected_documents"]
                retrieved = [docid if docid in expected else name for docid, name in rows]
                records.append({"id": item["id"], "metrics": retrieval_metrics(expected, retrieved),
                                "embedding_ms": embedding_ms,
                                "total_ms": (time.perf_counter() - started) * 1000})
            output["pipelines"][pipeline] = {"model": model, "n": len(records), "records": records,
                "means": {key: statistics.mean(r["metrics"][key] for r in records)
                          for key in records[0]["metrics"] if key != "applicable"}}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, psycopg.Error, requests.RequestException) as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "promotion_approved": False}))
        raise SystemExit(1)
