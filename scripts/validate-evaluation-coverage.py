"""Fail CI until the human-reviewed RAG evaluation set has production coverage."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


DATASET = Path(__file__).resolve().parents[1] / "evaluation_questions.jsonl"
MINIMUM_TOTAL = 150
REQUIRED_CATEGORIES = {
    "factual": 60,
    "comparison": 20,
    "aggregation": 20,
    "summary": 15,
    "follow_up": 15,
    "refusal": 20,
}


def main() -> None:
    records = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    categories = Counter(
        record.get("category") or ("refusal" if record.get("should_refuse") else "factual")
        for record in records
    )
    errors = []
    if len(records) < MINIMUM_TOTAL:
        errors.append(f"need at least {MINIMUM_TOTAL} reviewed questions; found {len(records)}")
    for category, minimum in REQUIRED_CATEGORIES.items():
        if categories[category] < minimum:
            errors.append(f"{category}: need {minimum}, found {categories[category]}")
    if errors:
        raise SystemExit("Evaluation coverage is not release-ready:\n- " + "\n- ".join(errors))
    print(f"Evaluation coverage ready: {len(records)} questions across {len(categories)} categories")


if __name__ == "__main__":
    main()
