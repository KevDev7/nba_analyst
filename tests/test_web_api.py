from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.assistant.pipeline import AssistantResult
from apps.web import server as web_server
from apps.web.server import app


class WebApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_root_does_not_serve_legacy_static_ui(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not Found"})

    def test_allowed_origins_are_read_from_env(self) -> None:
        with patch.dict(
            "os.environ",
            {"NBA_ALLOWED_ORIGINS": "https://ui.onrender.com, http://localhost:5173 "},
            clear=True,
        ):
            self.assertEqual(
                web_server._allowed_origins_from_env(),
                ["https://ui.onrender.com", "http://localhost:5173"],
            )

    def test_public_debug_flag_is_disabled_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(web_server._public_debug_enabled())
            self.assertFalse(web_server._effective_debug_requested(True))

    def test_public_debug_flag_accepts_explicit_truthy_values(self) -> None:
        for value in ["1", "true", "TRUE", "yes", "on"]:
            with self.subTest(value=value):
                with patch.dict("os.environ", {"NBA_ENABLE_PUBLIC_DEBUG": value}, clear=True):
                    self.assertTrue(web_server._public_debug_enabled())
                    self.assertTrue(web_server._effective_debug_requested(True))
                    self.assertFalse(web_server._effective_debug_requested(False))

    def test_public_debug_flag_rejects_falsey_or_unknown_values(self) -> None:
        for value in ["", "0", "false", "no", "off", "please"]:
            with self.subTest(value=value):
                with patch.dict("os.environ", {"NBA_ENABLE_PUBLIC_DEBUG": value}, clear=True):
                    self.assertFalse(web_server._public_debug_enabled())
                    self.assertFalse(web_server._effective_debug_requested(True))

    def test_max_question_chars_defaults_to_public_beta_limit(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(web_server._max_question_chars(), 250)

    def test_max_question_chars_uses_positive_integer_override(self) -> None:
        with patch.dict("os.environ", {"NBA_MAX_QUESTION_CHARS": "10"}, clear=True):
            self.assertEqual(web_server._max_question_chars(), 10)

    def test_max_question_chars_ignores_invalid_override(self) -> None:
        for value in ["", "0", "-1", "abc", "12abc", "1.5"]:
            with self.subTest(value=value):
                with patch.dict("os.environ", {"NBA_MAX_QUESTION_CHARS": value}, clear=True):
                    self.assertEqual(web_server._max_question_chars(), 250)

    def test_cors_preflight_allows_configured_frontend_origin(self) -> None:
        cors_app = FastAPI()

        @cors_app.post("/api/chat")
        def chat() -> dict[str, bool]:
            return {"ok": True}

        with patch.dict(
            "os.environ",
            {"NBA_ALLOWED_ORIGINS": "https://nba-analyst-ui.onrender.com"},
            clear=True,
        ):
            web_server._configure_cors(cors_app)

        response = TestClient(cors_app).options(
            "/api/chat",
            headers={
                "Origin": "https://nba-analyst-ui.onrender.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "https://nba-analyst-ui.onrender.com",
        )

    def test_cors_preflight_rejects_unconfigured_frontend_origin(self) -> None:
        cors_app = FastAPI()

        @cors_app.post("/api/chat")
        def chat() -> dict[str, bool]:
            return {"ok": True}

        with patch.dict(
            "os.environ",
            {"NBA_ALLOWED_ORIGINS": "https://nba-analyst-ui.onrender.com"},
            clear=True,
        ):
            web_server._configure_cors(cors_app)

        response = TestClient(cors_app).options(
            "/api/chat",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_healthz_returns_ready_when_runtime_assets_exist(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".duckdb") as snapshot:
            with (
                patch.dict("os.environ", {}, clear=True),
                patch.object(web_server.load_gold_snapshot, "DB_PATH", Path(snapshot.name)),
                patch(
                    "apps.web.server.load_gold_snapshot._snapshot_is_current",
                    return_value=True,
                ),
            ):
                response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "status": "ready", "checks": []})

    def test_healthz_reports_missing_planner_binary(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".duckdb") as snapshot:
            with (
                patch.dict(
                    "os.environ",
                    {"NBA_ONTOLOGY_PLANNER_BIN": "/tmp/nba-analyst-missing-planner"},
                    clear=True,
                ),
                patch.object(web_server.load_gold_snapshot, "DB_PATH", Path(snapshot.name)),
                patch(
                    "apps.web.server.load_gold_snapshot._snapshot_is_current",
                    return_value=True,
                ),
            ):
                response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"ok": False, "status": "unready", "checks": ["planner_binary_missing"]},
        )

    def test_healthz_reports_missing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_snapshot = Path(temp_dir) / "missing.duckdb"
            with (
                patch.dict("os.environ", {}, clear=True),
                patch.object(web_server.load_gold_snapshot, "DB_PATH", missing_snapshot),
            ):
                response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"ok": False, "status": "unready", "checks": ["duckdb_snapshot_missing"]},
        )

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
    def test_chat_allows_question_at_character_limit(self, mock_run_assistant) -> None:
        question = "x" * 250
        mock_run_assistant.return_value = AssistantResult(answer="At limit")

        with patch.dict("os.environ", {}, clear=True):
            response = self.client.post("/api/chat", json={"question": question, "debug": False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "At limit")
        mock_run_assistant.assert_called_once_with(question, debug=False)

    @patch("apps.web.server.assistant_pipeline.run_assistant")
    def test_chat_rejects_question_over_character_limit(self, mock_run_assistant) -> None:
        question = "x" * 251

        with patch.dict("os.environ", {}, clear=True):
            response = self.client.post("/api/chat", json={"question": question, "debug": False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": False,
                "answer": None,
                "error": "Question is too long. Please keep it under 250 characters.",
                "artifacts": [],
                "debug": None,
            },
        )
        mock_run_assistant.assert_not_called()

    @patch("apps.web.server.assistant_pipeline.run_assistant")
    def test_chat_counts_trimmed_question_toward_character_limit(self, mock_run_assistant) -> None:
        question = f"  {'x' * 250}  "
        mock_run_assistant.return_value = AssistantResult(answer="Trimmed limit")

        with patch.dict("os.environ", {}, clear=True):
            response = self.client.post("/api/chat", json={"question": question, "debug": False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Trimmed limit")
        mock_run_assistant.assert_called_once_with("x" * 250, debug=False)

    @patch("apps.web.server.assistant_pipeline.run_assistant")
    def test_chat_uses_configured_character_limit(self, mock_run_assistant) -> None:
        with patch.dict("os.environ", {"NBA_MAX_QUESTION_CHARS": "10"}, clear=True):
            response = self.client.post("/api/chat", json={"question": "x" * 11, "debug": False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["error"],
            "Question is too long. Please keep it under 10 characters.",
        )
        mock_run_assistant.assert_not_called()

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
    def test_chat_ignores_debug_request_by_default(self, mock_run_assistant) -> None:
        mock_run_assistant.return_value = AssistantResult(answer="Safe answer")

        with patch.dict("os.environ", {}, clear=True):
            response = self.client.post(
                "/api/chat",
                json={"question": "Show me players by points", "debug": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "answer": "Safe answer",
                "error": None,
                "artifacts": [],
                "debug": None,
            },
        )
        mock_run_assistant.assert_called_once_with("Show me players by points", debug=False)

    @patch("apps.web.server.assistant_pipeline.run_assistant")
    def test_chat_returns_debug_payload_when_public_debug_enabled(self, mock_run_assistant) -> None:
        mock_run_assistant.return_value = AssistantResult(
            answer="Debug answer",
            debug={"semantic_draft": {"task": "rank"}},
        )

        with patch.dict("os.environ", {"NBA_ENABLE_PUBLIC_DEBUG": "1"}, clear=True):
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
