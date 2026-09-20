"""Prepare a private source-review queue; never train, call a model, or write a DB.

Inputs are the existing MCCIA dashboard snapshot, not arbitrary training messages.
Source strings are untrusted data. No source text is executed or used as instructions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

SOURCES = {
    "records.json": "1QHf2B5F_5f2oCBl3UR67F3bgoIY3DdkJ",
    "clippings.json": "1Zm8omc3wRlCuYISBJHoyY-eUZ-GrfRMG",
}
FIELDS = (
    "id", "date", "year", "publisher", "title", "language", "topic",
    "description", "status", "url", "sourceDataset", "quality",
    "ocrHeadline", "ocrExcerpt", "ocrConfidence", "ocrStatus",
    "matchedRecordId", "sha256", "originalFilename", "page",
)
MAX_INPUT_BYTES = 32 * 1024 * 1024


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def make_candidate(row: dict, filename: str, index: int, source_hash: str,
                   today: date) -> dict:
    evidence = {k: row[k] for k in FIELDS if k in row}
    canonical = json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode("utf-8")
    flags = ["rights_review_required", "privacy_review_required", "evidence_review_required"]
    if filename == "records.json":
        if row.get("status") not in {"Verified", "Clipping verified"}:
            flags.append("source_not_fully_verified")
        if not row.get("description"):
            flags.append("missing_description")
    else:
        flags.append("ocr_must_be_checked_against_image")
        if row.get("quality") == "Low":
            flags.append("low_quality_image")
        if not row.get("ocrExcerpt"):
            flags.append("missing_ocr_text")
    try:
        record_date = date.fromisoformat(str(row.get("date", "")))
        if record_date > today:
            flags.append("future_date")
    except ValueError:
        flags.append("unresolved_date")
    if not row.get("id"):
        flags.append("missing_record_id")
    content_hash = digest(canonical)
    return {
        "candidate_id": content_hash,
        "source": {
            "drive_url": f"https://drive.google.com/file/d/{SOURCES[filename]}/view",
            "snapshot_file": filename, "snapshot_sha256": source_hash,
            "json_pointer": f"/{index}", "record_id": row.get("id"),
            "freshness": "existing_local_cache_not_byte_verified_against_live_drive",
        },
        # This is only a suggested link. Duplicate articles/events need human grouping
        # before any held-out split, including records with different IDs or languages.
        "suggested_group": row.get("matchedRecordId") or row.get("id") or content_hash,
        "evidence": evidence,
        "review_flags": flags,
        "review_status": "pending",
        "training_approved": False,
        "question": "",
        "grounded_answer": "",
        "supporting_evidence": [],
        "reviewer": "",
    }


def prepare(snapshot: Path, output: Path, today: date | None = None) -> dict:
    today = today or date.today()
    # Validate every input before creating outputs. Never overwrite a previous review.
    for name in SOURCES:
        path = snapshot / name
        if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError(f"Missing or oversized input: {name}")
    if output.exists():
        raise FileExistsError("Choose a new output directory; existing reviews are preserved.")
    output.mkdir(parents=True, exist_ok=False)
    counts, flags, statuses, qualities = Counter(), Counter(), Counter(), Counter()
    manifests = []
    seen = set()
    # An incomplete run has no manifest.json. Never consume it as a finished pack.
    with (output / "source_review.jsonl").open("x", encoding="utf-8") as target:
        for name in SOURCES:
            raw = (snapshot / name).read_bytes()
            if len(raw) > MAX_INPUT_BYTES:
                raise ValueError(f"Input grew beyond size limit: {name}")
            source_hash = digest(raw)
            rows = json.loads(raw.decode("utf-8-sig"))
            del raw
            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                raise ValueError(f"Expected an array of objects: {name}")
            manifests.append({"file": name, "sha256": source_hash, "records": len(rows)})
            counts[f"input_{name}"] = len(rows)
            for index, row in enumerate(rows):
                item = make_candidate(row, name, index, source_hash, today)
                key = (name, item["candidate_id"])
                if key in seen:
                    counts["exact_duplicate_rows_skipped"] += 1
                    continue
                seen.add(key)
                flags.update(item["review_flags"])
                if name == "records.json":
                    statuses[str(row.get("status", "missing"))] += 1
                else:
                    qualities[str(row.get("quality", "missing"))] += 1
                target.write(json.dumps(item, ensure_ascii=False) + "\n")
                counts["review_candidates"] += 1
    report = {
        "version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "source review only, not an SFT dataset",
        "source_folder": "https://drive.google.com/drive/folders/105kcn3EBPbTF8Iy5JkWudlG7FUMmeGps",
        "inputs": manifests, "counts": dict(counts), "flags": dict(flags),
        "record_statuses": dict(statuses), "clipping_quality": dict(qualities),
        "approved_training_examples": 0, "model_training_started": False,
        "limitations": [
            "Only records.json and clippings.json from cached 2026-08-27 snapshot; not a full Drive sync.",
            "No OCR rerun, source verification, rights clearance, or privacy redaction performed.",
            "No synthetic answers, train/validation/test split, model loading, or database writes.",
            "Raw source evidence may contain private data; keep this directory local and out of Git.",
            "No automatic promotion: review edits do not trigger export or training.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=project / ".drive-cache/download/Dashboard Data Backups/2026-08-27 Dashboard Snapshot")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    private_root = (project / "training-data").resolve()
    if not output.is_relative_to(private_root) or output == private_root:
        parser.error("Output must be a new subdirectory of the ignored training-data directory.")
    result = prepare(args.snapshot, output)
    print(json.dumps({"counts": result["counts"], "approved_training_examples": 0}))


if __name__ == "__main__":
    main()
