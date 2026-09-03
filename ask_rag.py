"""Retrieve relevant Neon chunks and answer with a local Ollama model."""

from __future__ import annotations

import argparse
import os

import psycopg
import requests
from pgvector import Vector
from pgvector.psycopg import register_vector


def ollama_post(base_url: str, path: str, payload: dict, timeout: int = 300) -> dict:
    response = requests.post(
        f"{base_url.rstrip('/')}{path}", json=payload, timeout=timeout
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask a question using document chunks stored in Neon."
    )
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:8080")
    parser.add_argument("--embedding-model", default="embeddinggemma")
    parser.add_argument("--chat-model", default="gemma4:e2b-it-qat")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not configured in this PowerShell session.")

    embed_result = ollama_post(
        args.ollama_url,
        "/api/embed",
        {"model": args.embedding_model, "input": args.question},
        timeout=180,
    )
    query_vector = embed_result["embeddings"][0]
    if len(query_vector) != 768:
        raise SystemExit(
            f"Expected a 768-dimensional query vector, received {len(query_vector)}."
        )

    with psycopg.connect(database_url) as conn:
        register_vector(conn)
        rows = conn.execute(
            """
            SELECT source, content, 1 - (embedding <=> %s) AS similarity
            FROM rag_chunks
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (Vector(query_vector), Vector(query_vector), args.top_k),
        ).fetchall()

    if not rows:
        raise SystemExit("No chunks are stored in rag_chunks. Ingest a document first.")

    context = "\n\n".join(
        f"[Source {index}: {source}]\n{content}"
        for index, (source, content, _) in enumerate(rows, start=1)
    )
    prompt = f"""Answer the question using only the supplied context.
If the context does not contain the answer, say: I don't know from the supplied documents.
Keep the answer concise and cite sources as [Source 1], [Source 2], and so on.

Context:
{context}

Question: {args.question}
"""

    chat_result = ollama_post(
        args.ollama_url,
        "/api/chat",
        {
            "model": args.chat_model,
            "messages": [{"role": "user", "content": prompt}],
            "think": False,
            "stream": False,
            "options": {
                "num_ctx": 2048,
                "num_predict": 250,
                "temperature": 0.2,
            },
        },
    )

    print("\nRetrieved chunks:")
    for index, (source, _, similarity) in enumerate(rows, start=1):
        print(f"  Source {index}: {source} (similarity {similarity:.3f})")

    print("\nAnswer:\n")
    print(chat_result["message"]["content"].strip())


if __name__ == "__main__":
    main()
