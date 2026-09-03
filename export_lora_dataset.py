"""Export only administrator-approved conversations into redacted JSONL splits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import random
from pathlib import Path

import psycopg


REDACTIONS = (
    (re.compile(r"postgres(?:ql)?://[^\s]+", re.IGNORECASE), "[REDACTED_DATABASE_URL]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b(?:api[_ -]?key|password|secret|token)\s*[:=]\s*\S+"), "[REDACTED_SECRET]"),
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)"), "[REDACTED_PHONE]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
)


def redact(value: str, extra_terms: list[str]) -> str:
    cleaned = value
    for pattern, replacement in REDACTIONS:
        cleaned = pattern.sub(replacement, cleaned)
    for term in sorted(extra_terms, key=len, reverse=True):
        if term.strip():
            cleaned = re.sub(re.escape(term.strip()), "[REDACTED_PERSONAL_DATA]", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def split_records(records: list[dict], seed: int) -> dict[str, list[dict]]:
    shuffled = records[:]
    random.Random(seed).shuffle(shuffled)
    count = len(shuffled)
    test_count = max(1, round(count * 0.1)) if count >= 3 else 0
    validation_count = max(1, round(count * 0.1)) if count >= 3 else 0
    return {
        "test": shuffled[:test_count],
        "validation": shuffled[test_count : test_count + validation_count],
        "train": shuffled[test_count + validation_count :],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export administrator-approved, redacted conversations for human review"
    )
    parser.add_argument("--output", type=Path, default=Path("training-data/review"))
    parser.add_argument(
        "--redact-terms",
        type=Path,
        help="Optional UTF-8 file containing one name or private term per line",
    )
    parser.add_argument("--seed", type=int, default=20260903)
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is not configured")
    extra_terms = []
    if args.redact_terms:
        extra_terms = [
            line.strip()
            for line in args.redact_terms.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    with psycopg.connect(database_url, connect_timeout=10) as conn:
        rows = conn.execute(
            """
            SELECT c.id, m.role, m.content
            FROM rag_conversations c
            JOIN rag_messages m ON m.conversation_id = c.id
            WHERE c.training_approved = TRUE AND m.role IN ('user', 'assistant')
            ORDER BY c.id, m.created_at, m.id
            """
        ).fetchall()

    grouped: dict[str, list[dict[str, str]]] = {}
    for conversation_id, role, content in rows:
        grouped.setdefault(str(conversation_id), []).append(
            {"role": role, "content": redact(content, extra_terms)}
        )

    records = []
    for conversation_id, messages in grouped.items():
        if not any(item["role"] == "user" for item in messages):
            continue
        if not any(item["role"] == "assistant" for item in messages):
            continue
        records.append(
            {
                "id": hashlib.sha256(conversation_id.encode()).hexdigest()[:16],
                "messages": messages,
            }
        )

    if not records:
        raise SystemExit("No approved conversations with complete user/assistant turns were found")

    args.output.mkdir(parents=True, exist_ok=True)
    splits = split_records(records, args.seed)
    manifest = {"version": 1, "seed": args.seed, "redacted": True, "counts": {}}
    for split_name, split_rows in splits.items():
        destination = args.output / f"{split_name}.jsonl"
        destination.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in split_rows),
            encoding="utf-8",
        )
        manifest["counts"][split_name] = len(split_rows)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print("Export complete. Review every JSONL record before moving it into training-data/reviewed.")
    print("Records:", sum(manifest["counts"].values()))


if __name__ == "__main__":
    main()

