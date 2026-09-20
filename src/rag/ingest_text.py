"""Chunk text, embed it with Ollama, and store it in Neon pgvector."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
import requests
from pgvector import Vector
from pgvector.psycopg import register_vector


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start_word = 0
    while start_word < len(words):
        end_word = start_word
        length = 0
        while end_word < len(words):
            added = len(words[end_word]) + (1 if end_word > start_word else 0)
            if length and length + added > size:
                break
            length += added
            end_word += 1
        if end_word == start_word:
            end_word += 1
        chunks.append(" ".join(words[start_word:end_word]))
        if end_word >= len(words):
            break

        next_start = end_word
        overlap_length = 0
        while next_start > start_word and overlap_length < overlap:
            next_start -= 1
            overlap_length += len(words[next_start]) + 1
        start_word = next_start if next_start > start_word else end_word
    return chunks


def embed(base_url: str, model: str, text: str) -> list[float]:
    response = requests.post(
        f"{base_url.rstrip('/')}/api/embed",
        json={"model": model, "input": text},
        timeout=180,
    )
    response.raise_for_status()
    vector = response.json()["embeddings"][0]
    if len(vector) != 768:
        raise RuntimeError(f"Expected 768 embedding values, received {len(vector)}")
    return vector


def main() -> None:
    parser = argparse.ArgumentParser(description="Store a text document in Neon.")
    parser.add_argument("text_file", type=Path)
    parser.add_argument("--source", help="Source label; defaults to the filename")
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="embeddinggemma")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing rows with the same source before inserting",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not configured in this PowerShell session.")
    if args.overlap < 0 or args.overlap >= args.chunk_size:
        raise SystemExit("Overlap must be at least 0 and smaller than chunk size.")

    text_file = args.text_file.expanduser().resolve()
    if not text_file.is_file():
        raise SystemExit(f"Text file not found: {text_file}")

    source = args.source or text_file.name
    chunks = chunk_text(text_file.read_text(encoding="utf-8"), args.chunk_size, args.overlap)
    if not chunks:
        raise SystemExit("The input file contains no text.")

    with psycopg.connect(database_url) as conn:
        register_vector(conn)

        existing = conn.execute(
            "SELECT COUNT(*) FROM rag_chunks WHERE source = %s", (source,)
        ).fetchone()[0]
        if existing and not args.replace:
            raise SystemExit(
                f"Source {source!r} already has {existing} chunks. "
                "Use --replace to replace them."
            )
        if existing:
            conn.execute("DELETE FROM rag_chunks WHERE source = %s", (source,))

        for index, chunk in enumerate(chunks, start=1):
            vector = embed(args.ollama_url, args.model, chunk)
            conn.execute(
                """
                INSERT INTO rag_chunks (source, page_number, content, embedding, metadata)
                VALUES (%s, NULL, %s, %s, jsonb_build_object('chunk', %s))
                """,
                (source, chunk, Vector(vector), index),
            )
            print(f"Embedded chunk {index}/{len(chunks)}")

    print(f"Stored {len(chunks)} chunks in Neon with source: {source}")


if __name__ == "__main__":
    main()
