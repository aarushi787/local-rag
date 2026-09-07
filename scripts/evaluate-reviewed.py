"""Evaluate a local retrieval replay and optional human answer annotations.

No model calls, database writes, or automatic ground-truth generation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rag_core.evaluation import coverage, retrieval_metrics, generation_metrics, refusal_metrics


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(items, replay):
    by_id = {item["id"]: item for item in items}
    if len({r["id"] for r in replay}) != len(replay) or set(r["id"] for r in replay) != set(by_id):
        raise ValueError("Replay must contain exactly one result for every dataset id")
    results, expected_refusals, actual_refusals = [], [], []
    for record in replay:
        item = by_id[record["id"]]
        retrieval = retrieval_metrics(item["expected_documents"], record["retrieved_documents"])
        result = {"id": item["id"], "category": item["category"], "retrieval": retrieval,
                  "generation": None, "error": record.get("error")}
        annotation = record.get("human_annotation")
        if annotation:
            digest = hashlib.sha256(str(record.get("answer", "")).encode()).hexdigest()
            if annotation.get("answer_sha256") != digest or not annotation.get("reviewer"):
                raise ValueError("Answer annotation must name its reviewer and match the answer hash")
            if type(annotation.get("refused")) is not bool:
                raise ValueError("Human refusal judgment must be boolean")
            result["generation"] = generation_metrics(annotation["claims"],
                len(item["required_facts"]), annotation["supported_fact_indexes"])
            expected_refusals.append(item["should_refuse"])
            actual_refusals.append(annotation["refused"])
        results.append(result)
    means = {}
    for section in ("retrieval", "generation"):
        collected = {}
        for result in results:
            for name, value in (result[section] or {}).items():
                if name != "applicable" and value is not None:
                    collected.setdefault(name, []).append(value)
        means[section] = {k: {"mean": statistics.mean(v), "n": len(v)} for k, v in collected.items()}
    return {"coverage": coverage(items), "metrics": means,
            "refusals": refusal_metrics(expected_refusals, actual_refusals),
            "generation_reviewed": len(actual_refusals), "n": len(items), "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--replay", required=True, type=Path)
    args = parser.parse_args()
    items = read_jsonl(args.dataset)
    gate = coverage(items)
    if not gate["ready"]:
        print(json.dumps({"status": "blocked", "coverage": gate}, indent=2))
        raise SystemExit(1)
    report = evaluate(items, read_jsonl(args.replay))
    report["dataset_sha256"] = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    report["replay_sha256"] = hashlib.sha256(args.replay.read_bytes()).hexdigest()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
