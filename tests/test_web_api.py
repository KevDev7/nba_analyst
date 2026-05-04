from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.assistant.pipeline import AssistantResult
from apps.web.server import app


class WebApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_root_does_not_serve_legacy_static_ui(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not Found"})

    @patch("apps.web.server.assistant_pipeline.run_assistant")
    def test_chat_returns_answer_from_shared_assistant_boundary(self, mock_run_assistant) -> None:
        artifacts = [{"kind": "text", "role": "summary", "text": "Top players table"}]
        mock_run_assistant.return_value = AssistantResult(
            answer="Top players table",
            artifacts=artifacts,
        )

        response = self.client.post(
            "/api/chat",
            json={
                "question": "Show me the top 10 players by points over the last 10 games",
                "debug": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "answer": "Top players table",
                "error": None,
                "artifacts": artifacts,
                "debug": None,
            },
        )
        mock_run_assistant.assert_called_once_with(
            "Show me the top 10 players by points over the last 10 games",
            debug=False,
        )

    @patch("apps.web.server.assistant_pipeline.run_assistant")
    def test_chat_returns_clear_error_when_assistant_fails(self, mock_run_assistant) -> None:
        mock_run_assistant.side_effect = RuntimeError(
            "Could not resolve metric 'assists' against the ontology."
        )

        response = self.client.post(
            "/api/chat",
            json={"question": "Show me assists", "debug": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIsNone(payload["answer"])
        self.assertIn("Could not resolve metric", payload["error"])
        self.assertEqual(payload["artifacts"], [])
        self.assertIsNone(payload["debug"])

    @patch("apps.web.server.assistant_pipeline.run_assistant")
    def test_chat_returns_debug_payload_when_requested(self, mock_run_assistant) -> None:
        mock_run_assistant.return_value = AssistantResult(
            answer="Debug answer",
            debug={"semantic_draft": {"task": "rank"}},
        )

        response = self.client.post(
            "/api/chat",
            json={"question": "Show me players by points", "debug": True},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["answer"], "Debug answer")
        self.assertEqual(payload["artifacts"], [])
        self.assertEqual(payload["debug"], {"semantic_draft": {"task": "rank"}})
        mock_run_assistant.assert_called_once_with("Show me players by points", debug=True)

    @patch("apps.web.server.assistant_pipeline.run_assistant")
    def test_chat_rejects_empty_question_before_pipeline(self, mock_run_assistant) -> None:
        response = self.client.post("/api/chat", json={"question": "   ", "debug": False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": False,
                "answer": None,
                "error": "Question is required.",
                "artifacts": [],
                "debug": None,
            },
        )
        mock_run_assistant.assert_not_called()


if __name__ == "__main__":
    unittest.main()
