from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.cli.semantic_interpreter import (
    SemanticInterpreterError,
    _semantic_draft_prompt_preamble,
    interpret_question_to_semantic_draft,
)


SAMPLE_DRAFT = {
    "task": "rank",
    "subject": "players",
    "measure": "points",
    "time_window": {"kind": "last_n_games", "value": 10},
    "limit": 10,
    "sort": "desc",
    "assumptions": [],
}


class SemanticInterpreterTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_prompt_requests_loose_draft_not_planner_ir(self) -> None:
        prompt = _semantic_draft_prompt_preamble()

        self.assertIn("loose semantic draft", prompt)
        self.assertIn("Do not output ontology object names", prompt)
        self.assertIn('"draft"', prompt)
        self.assertNotIn('"coreFactObject"', prompt)
        self.assertNotIn('"query_kind"', prompt)
        self.assertNotIn("Capability summary", prompt)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_interpreter_returns_basic_validated_semantic_draft(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": SAMPLE_DRAFT})

        draft = interpret_question_to_semantic_draft(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(draft, SAMPLE_DRAFT)
        sent_prompt = mock_call_gemini.call_args.args[0]
        self.assertIn("User question:", sent_prompt)
        self.assertIn("top 10 players", sent_prompt)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_interpreter_raises_for_unsupported_draft_response(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "unsupported", "reason": "team rankings are outside Slice 36"}
        )

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_semantic_draft("Show me teams by points over the last 10 games")

        self.assertIn("team rankings are outside Slice 36", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_interpreter_rejects_invalid_basic_shape(self, mock_call_gemini) -> None:
        invalid = dict(SAMPLE_DRAFT)
        invalid["time_window"] = {"kind": "last_month", "value": 1}
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": invalid})

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_semantic_draft(
                "Show me the top 10 players by points over the last month"
            )

        self.assertIn("invalid semantic draft", str(context.exception))


if __name__ == "__main__":
    unittest.main()
