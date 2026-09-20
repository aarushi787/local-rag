import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

from training.prepare_drive_review import SOURCES, make_candidate, prepare


class ReviewPackTests(unittest.TestCase):
    def test_unverified_and_future_dated_never_approved(self):
        item = make_candidate({"id": "A", "status": "Unverified", "date": "2099-01-01"},
                              "records.json", 0, "hash", date(2026, 9, 7))
        self.assertFalse(item["training_approved"])
        self.assertIn("future_date", item["review_flags"])
        self.assertIn("source_not_fully_verified", item["review_flags"])
        self.assertEqual(item["grounded_answer"], "")

    def test_ocr_confidence_does_not_override_image_review(self):
        item = make_candidate({"quality": "Low", "ocrConfidence": 99, "date": None},
                              "clippings.json", 0, "hash", date(2026, 9, 7))
        self.assertIn("low_quality_image", item["review_flags"])
        self.assertIn("unresolved_date", item["review_flags"])
        self.assertIn("ocr_must_be_checked_against_image", item["review_flags"])

    def test_dedup_provenance_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in SOURCES:
                (root / name).write_text(json.dumps([{"id": "X"}, {"id": "X"}]), encoding="utf-8")
            result = prepare(root, root / "review")
            self.assertEqual(result["counts"]["review_candidates"], 2)
            self.assertEqual(result["counts"]["exact_duplicate_rows_skipped"], 2)
            self.assertEqual(len(result["inputs"][0]["sha256"]), 64)
            self.assertFalse(result["model_training_started"])
            with self.assertRaises(FileExistsError):
                prepare(root, root / "review")

    def test_invalid_schema_does_not_mark_pack_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in SOURCES:
                (root / name).write_text('{}', encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare(root, root / "review")
            self.assertFalse((root / "review/manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
