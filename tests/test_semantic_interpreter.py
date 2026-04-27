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
        self.assertIn('"rank" | "trend" | "aggregate" | "find" | "compare"', prompt)
        self.assertIn('"operations"', prompt)
        self.assertIn("positive integer", prompt)
        self.assertNotIn('"limit": 10 | 5 | 1 | null', prompt)
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

        self.assertEqual(draft["task"], SAMPLE_DRAFT["task"])
        self.assertEqual(draft["subject"], SAMPLE_DRAFT["subject"])
        self.assertEqual(draft["measure"], SAMPLE_DRAFT["measure"])
        self.assertEqual(draft["time_window"], SAMPLE_DRAFT["time_window"])
        self.assertEqual(draft["limit"], SAMPLE_DRAFT["limit"])
        sent_prompt = mock_call_gemini.call_args.args[0]
        self.assertIn("User question:", sent_prompt)
        self.assertIn("top 10 players", sent_prompt)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_interpreter_raises_for_non_analytics_unsupported_response(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "unsupported", "reason": "not an NBA analytics request"}
        )

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_semantic_draft("Write me a birthday card")

        self.assertIn("not an NBA analytics request", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_interpreter_does_not_gate_time_window_capabilities(self, mock_call_gemini) -> None:
        draft = dict(SAMPLE_DRAFT)
        draft["time_window"] = {"kind": "last_month", "value": 1}
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        interpreted = interpret_question_to_semantic_draft(
            "Show me the top 10 players by points over the last month"
        )

        self.assertEqual(interpreted["time_window"], {"kind": "last_month", "value": 1})


if __name__ == "__main__":
    unittest.main()
