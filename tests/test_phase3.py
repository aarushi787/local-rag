"""Offline contracts for explicit assistant modes; no database or model calls."""
import unittest
import uuid
from unittest.mock import patch

import app


class AssistantModeTests(unittest.TestCase):
    def request(self, mode: str, document_id=None):
        return app.ChatCompletionRequest(
            assistant_mode=mode,
            document_id=document_id,
            messages=[app.ChatMessage(role="user", content="Help me write a payment reminder")],
        )

    def test_general_mode_never_calls_private_retrieval(self):
        principal = app.Principal(uuid.uuid4(), "Reader", "user")
        with patch.object(app, "retrieve_for_question") as retrieve:
            rows, grounded = app.retrieve_for_assistant_mode(
                "general", self.request("general").messages, 3, None, principal, {}
            )
        self.assertEqual(rows, [])
        self.assertFalse(grounded)
        retrieve.assert_not_called()

    def test_general_mode_rejects_document_scope_before_retrieval(self):
        with self.assertRaises(app.HTTPException) as raised:
            app.validate_assistant_mode_request(self.request("general", uuid.uuid4()))
        self.assertEqual(raised.exception.status_code, 422)

    def test_analytics_is_unavailable_before_database_or_model_work(self):
        with self.assertRaises(app.HTTPException) as raised:
            app.validate_assistant_mode_request(self.request("business_analytics"))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("read-only", raised.exception.detail)

    def test_general_prompt_labels_unverified_assistance(self):
        messages = self.request("general").messages
        outgoing = app.grounded_messages(messages, [], grounded=False, assistant_mode="general")
        self.assertIn("General assistance", outgoing[0]["content"])
        self.assertIn("Do not search", outgoing[0]["content"])

    def test_company_mode_still_uses_existing_retrieval_path(self):
        principal = app.Principal(uuid.uuid4(), "Reader", "user")
        with patch.object(app, "retrieve_for_question", return_value=([{"id": 1}], True)) as retrieve:
            rows, grounded = app.retrieve_for_assistant_mode(
                "company_knowledge", self.request("company_knowledge").messages, 3, None, principal, {}
            )
        self.assertEqual(rows, [{"id": 1}])
        self.assertTrue(grounded)
        retrieve.assert_called_once()


if __name__ == "__main__":
    unittest.main()
