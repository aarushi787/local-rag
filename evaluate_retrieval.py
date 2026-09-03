"""Measure retrieval hit rate and reciprocal rank against a JSONL question set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app import retrieve


def normalize(value: str) -> str:
    return " ".join(value.lower().split())


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Neon hybrid RAG retrieval")
    parser.add_argument(
        "dataset",
        type=Path,
        nargs="?",
        default=Path("evaluation_questions.jsonl"),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    examples = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        examples = examples[: args.limit]
    if not examples:
        raise SystemExit("The evaluation dataset is empty")

    source_hits = 0
    evidence_hits = 0
    reciprocal_rank_total = 0.0
    for number, example in enumerate(examples, start=1):
        rows = retrieve(example["question"], top_k=args.top_k)
        expected_source = normalize(example["expected_source"])
        rank = next(
            (
                index
                for index, row in enumerate(rows, start=1)
                if expected_source in normalize(row["source"])
            ),
            None,
        )
        joined = normalize(" ".join(row["content"] for row in rows))
        expected_terms = [normalize(term) for term in example.get("expected_terms", [])]
        evidence_ok = all(term in joined for term in expected_terms)
        source_hits += int(rank is not None)
        evidence_hits += int(evidence_ok)
        reciprocal_rank_total += 1 / rank if rank else 0
        print(
            f"{number:02d}. {'PASS' if rank and evidence_ok else 'MISS'} "
            f"rank={rank or '-'} question={example['question']}"
        )

    count = len(examples)
    print("\nRetrieval evaluation")
    print(f"Questions: {count}")
    print(f"Source hit@{args.top_k}: {source_hits / count:.1%}")
    print(f"Evidence hit@{args.top_k}: {evidence_hits / count:.1%}")
    print(f"Mean reciprocal rank: {reciprocal_rank_total / count:.3f}")


if __name__ == "__main__":
    main()
