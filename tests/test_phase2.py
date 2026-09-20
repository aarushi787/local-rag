"""Offline Phase 2 retrieval contracts; no database, model, or OCR service is contacted."""
import unittest

import app


class MultilingualRetrievalTests(unittest.TestCase):
    def test_indic_words_survive_keyword_query_construction(self):
        query = app.lexical_tsquery("कंपनीची प्रवास धोरण काय आहे?")
        self.assertIn("कंपनीची", query)
        self.assertIn("प्रवास", query)
        self.assertIn("धोरण", query)

    def test_hindi_words_survive_keyword_query_construction(self):
        query = app.lexical_tsquery("कंपनी की यात्रा नीति क्या है?")
        self.assertIn("कंपनी", query)
        self.assertIn("यात्रा", query)
        self.assertIn("नीति", query)

    def test_dates_amounts_and_invoice_ids_are_protected_literals(self):
        patterns = app.exact_identifier_patterns(
            "Find invoice INV-204 dated 2026-09-04 for ₹12,500"
        )
        self.assertIn("%inv-204%", patterns)
        self.assertIn("%2026-09-04%", patterns)
        self.assertIn("%₹12,500%", patterns)


class ContextBudgetTests(unittest.TestCase):
    def test_evidence_packing_uses_estimated_tokens_not_character_budget(self):
        rows = [
            {"id": 1, "content": "First relevant sentence. " * 30},
            {"id": 2, "content": "Second relevant sentence. " * 30},
        ]
        messages = [app.ChatMessage(role="user", content="What does the policy permit?")]
        packed = app.pack_context_rows(rows, 700, messages, max_completion_tokens=200)
        budget = app.context_evidence_budget(700, messages, 200)
        used = sum(app.estimated_token_count(row["context_content"]) + 48 for row in packed)
        self.assertLessEqual(used, budget)

    def test_evidence_prefers_complete_sentence_boundaries(self):
        text = "First complete finding. Second complete finding."
        limit = app.estimated_token_count("First complete finding.")
        self.assertEqual(app.fit_evidence_to_token_budget(text, limit), "First complete finding.")

    def test_history_and_requested_output_reduce_evidence_budget(self):
        short = app.context_evidence_budget(2048, [], 120)
        long_history = [app.ChatMessage(role="user", content="Detailed history " * 80)]
        constrained = app.context_evidence_budget(2048, long_history, 300)
        self.assertLess(constrained, short)
        self.assertGreaterEqual(constrained, 128)


if __name__ == "__main__":
    unittest.main()
