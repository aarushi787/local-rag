"""Measure retrieval hit rate and reciprocal rank against a JSONL question set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app import open_database_pool, retrieve, retrieve_baseline, score_retrieval, shutdown


def normalize(value: str) -> str:
    return " ".join(value.lower().split())


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PostgreSQL hybrid RAG retrieval")
    parser.add_argument(
        "dataset",
        type=Path,
        nargs="?",
        default=Path("evaluation_questions.jsonl"),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--indices",
        help="Comma-separated one-based dataset rows to evaluate, for focused tuning",
    )
    parser.add_argument("--pipeline", choices=("baseline", "upgraded"), default="upgraded")
    parser.add_argument("--show-results", action="store_true")
    args = parser.parse_args()

    examples = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        examples = examples[: args.limit]
    if args.indices:
        selected = {int(value.strip()) for value in args.indices.split(",") if value.strip()}
        examples = [example for index, example in enumerate(examples, start=1) if index in selected]
    if not examples:
        raise SystemExit("The evaluation dataset is empty")

    # Reuse database connections just like the production API. Opening a new
    # TLS connection to remote PostgreSQL for every retrieval distorts latency.
    open_database_pool()
    top1_hits = 0
    top3_hits = 0
    top5_hits = 0
    evidence_hits = 0
    reciprocal_rank_total = 0.0
    retrieval_questions = 0
    refusal_cases = 0
    for number, example in enumerate(examples, start=1):
        rows = (
            retrieve_baseline(example["question"], top_k=args.top_k)
            if args.pipeline == "baseline"
            else retrieve(example["question"], top_k=args.top_k)
        )
        score = score_retrieval(example, rows)
        if args.show_results:
            for rank, row in enumerate(rows, start=1):
                excerpt = " ".join(row.get("content", "").split())[:180]
                print(f"    {rank}. {row.get('filename', row.get('source'))} | {excerpt}")
        if example.get("should_refuse", False):
            refusal_cases += 1
            print(f"{number:02d}. REFUSAL-CASE question={example['question']}")
            continue
        retrieval_questions += 1
        top1_hits += int(score["top1"])
        top3_hits += int(score["top3"])
        top5_hits += int(score["top5"])
        evidence_hits += int(score["evidence"])
        reciprocal_rank_total += score["reciprocal"]
        print(
            f"{number:02d}. {'PASS' if score['rank'] and score['evidence'] else 'MISS'} "
            f"rank={score['rank'] or '-'} question={example['question']}"
        )

    count = max(retrieval_questions, 1)
    print("\nRetrieval evaluation")
    print(f"Questions: {len(examples)} ({retrieval_questions} retrieval, {refusal_cases} refusal)")
    print(f"Dataset version: {examples[0].get('dataset_version', 'v1')}")
    print(f"Pipeline: {args.pipeline}")
    print(f"Recall@1: {top1_hits / count:.1%}")
    print(f"Recall@3: {top3_hits / count:.1%}")
    print(f"Recall@5: {top5_hits / count:.1%}")
    print(f"Evidence hit@{args.top_k}: {evidence_hits / count:.1%}")
    print(f"Mean reciprocal rank: {reciprocal_rank_total / count:.3f}")
    shutdown()


if __name__ == "__main__":
    main()
