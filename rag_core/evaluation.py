"""Reviewed dataset contracts and explicit-denominator evaluation metrics."""
from __future__ import annotations
import hashlib
import json
import math
from collections import Counter
from datetime import datetime

CATEGORIES = (
    "factual", "multi_hop", "multi_document", "numeric", "identifier", "long_document",
    "conflict", "superseded", "ocr", "ambiguous", "follow_up", "refusal", "no_evidence",
    "injection", "similar_entities", "temporal",
)


def item_digest(item: dict) -> str:
    material = {k: v for k, v in item.items() if k != "review"}
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def validate_item(item: dict, require_review: bool = True) -> list[str]:
    errors = []
    for field in ("id", "question", "answer_notes"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            errors.append(f"{field}: nonempty text required")
    if item.get("category") not in CATEGORIES:
        errors.append("category: unsupported or missing")
    if item.get("difficulty") not in {"easy", "medium", "hard"}:
        errors.append("difficulty: easy, medium or hard required")
    if type(item.get("should_refuse")) is not bool:
        errors.append("should_refuse: boolean required")
    for field in ("expected_documents", "required_facts", "forbidden_claims"):
        value = item.get(field)
        if not isinstance(value, list) or any(not isinstance(s, str) or not s.strip() for s in value):
            errors.append(f"{field}: list of nonempty strings required")
    pages = item.get("expected_pages")
    if not isinstance(pages, list) or any(not isinstance(p, dict) or
            p.get("document") not in (item.get("expected_documents") or []) or
            type(p.get("page")) is not int or p["page"] < 1 for p in pages):
        errors.append("expected_pages: document/page objects required")
    if item.get("should_refuse") is False and (not item.get("expected_documents") or not item.get("required_facts")):
        errors.append("answerable items need source documents and required facts")
    if require_review:
        review = item.get("review") or {}
        if not isinstance(review, dict):
            review = {}
        if review.get("status") != "approved" or not str(review.get("reviewer", "")).strip():
            errors.append("human approval with reviewer required")
        try:
            reviewed_at = datetime.fromisoformat(str(review.get("reviewed_at", "")).replace("Z", "+00:00"))
            if reviewed_at.tzinfo is None:
                raise ValueError()
        except (ValueError, TypeError):
            errors.append("reviewed_at: timezone-aware ISO date required")
        if review.get("item_sha256") != item_digest(item):
            errors.append("review hash missing or stale; changed ground truth requires re-review")
    return errors


def coverage(items: list[dict], minimum: int = 150) -> dict:
    ids, questions, counts, errors = set(), set(), Counter(), []
    for n, item in enumerate(items, 1):
        problems = validate_item(item)
        question = " ".join(str(item.get("question", "")).casefold().split())
        identity = str(item.get("id", ""))
        if identity in ids or question in questions:
            problems.append("duplicate id or normalized question")
        ids.add(identity)
        questions.add(question)
        if problems:
            errors.append({"row": n, "errors": problems})
        else:
            counts[item["category"]] += 1
    reviewed = sum(counts.values())
    missing = [c for c in CATEGORIES if counts[c] == 0]
    return {"ready": reviewed >= minimum and not errors and not missing,
            "reviewed": reviewed, "total": len(items), "minimum": minimum,
            "categories": dict(counts), "missing_categories": missing, "errors": errors}


def retrieval_metrics(expected: list[str], retrieved: list[str], ks=(1, 3, 5)) -> dict:
    """Binary document relevance. Deduplicate chunks of the same document first."""
    relevant = set(expected)
    ranked = list(dict.fromkeys(retrieved))
    if not relevant:
        return {"applicable": False, "mrr": None, **{
            f"{metric}@{k}": None for metric in ("recall", "precision", "ndcg") for k in ks}}
    rank = next((i for i, doc in enumerate(ranked, 1) if doc in relevant), None)
    result = {"applicable": True, "mrr": 1 / rank if rank else 0.0}
    for k in ks:
        if k < 1:
            raise ValueError("k must be positive")
        hits = [int(doc in relevant) for doc in ranked[:k]]
        result[f"recall@{k}"] = sum(hits) / len(relevant)
        result[f"precision@{k}"] = sum(hits) / k
        dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
        ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
        result[f"ndcg@{k}"] = dcg / ideal
    return result


def generation_metrics(claims: list[dict], required_fact_count: int,
                       supported_fact_indexes: list[int]) -> dict:
    """HUMAN judgments only: each claim has supported:bool, citations:list[bool]."""
    if required_fact_count < 0 or any(type(i) is not int or not 0 <= i < required_fact_count
                                     for i in supported_fact_indexes):
        raise ValueError("fact index outside reviewed ground truth")
    if any(type(c.get("supported")) is not bool or not isinstance(c.get("citations"), list)
           or any(type(v) is not bool for v in c["citations"]) for c in claims):
        raise ValueError("each claim needs human support and citation judgments")
    citations = [v for c in claims for v in c["citations"]]
    ratio = lambda n, d: n / d if d else None
    return {"faithfulness": ratio(sum(c["supported"] for c in claims), len(claims)),
            "unsupported_claim_rate": ratio(sum(not c["supported"] for c in claims), len(claims)),
            "citation_precision": ratio(sum(citations), len(citations)),
            "citation_recall": ratio(sum(c["supported"] and any(c["citations"]) for c in claims), len(claims)),
            "answer_completeness": ratio(len(set(supported_fact_indexes)), required_fact_count)}


def refusal_metrics(expected: list[bool], actual: list[bool]) -> dict:
    if len(expected) != len(actual) or any(type(x) is not bool for x in expected + actual):
        raise ValueError("aligned boolean refusal judgments required")
    tp = sum(e and a for e, a in zip(expected, actual))
    predicted, positives = sum(actual), sum(expected)
    return {"precision": tp / predicted if predicted else None,
            "recall": tp / positives if positives else None,
            "accuracy": sum(e == a for e, a in zip(expected, actual)) / len(expected) if expected else None,
            "tp": tp, "fp": predicted - tp, "fn": positives - tp, "n": len(expected)}
