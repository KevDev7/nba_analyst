# Purpose:
# Verify the gold-first comparison path on the corrected Query root.
#
# Uses:
# - the CLI entrypoint
# - the Haskell semantic core
# - the Python runtime and answer synthesis layers
#
# Produces:
# - regression coverage for comparison behavior on the unified architecture
#
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.cli.main import plan_question, run_cli
from apps.cli.semantic_interpreter import interpret_question_to_semantic_draft


def rank_draft() -> str:
    return json.dumps(
        {
            "status": "ok",
            "draft": {
                "task": "rank",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": 10,
                "sort": "desc",
                "assumptions": [],
            },
        }
    )


def compare_draft(*entities: str, measure: str = "scoring") -> str:
    return json.dumps(
        {
            "status": "ok",
            "draft": {
                "task": "compare",
                "subject": "players",
                "measure": measure,
                "time_window": {"kind": "last_n_games", "value": 10},
                "entities": list(entities),
                "assumptions": [],
            },
        }
    )


class SliceTwoTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_query_root_is_variant_tagged(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = rank_draft()
        _interpreted_query, planner_output = plan_question(
            "Show me the top 10 players by points over the last 10 games"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_comparison_question(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = compare_draft("Brunson", "Haliburton")
        output = run_cli("Compare Brunson and Haliburton scoring over the last 10 games")
        self.assertIn("Jalen Brunson led in total points", output)
        self.assertIn("Tyrese Haliburton", output)
        self.assertIn("Differential:", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_comparison_full_names(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = compare_draft("Jalen Brunson", "Tyrese Haliburton")
        output = run_cli(
            "Compare Jalen Brunson and Tyrese Haliburton scoring over the last 10 games"
        )
        self.assertIn("Jalen Brunson led in total points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_comparison_pts_variant(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = compare_draft("Brunson", "Haliburton", measure="pts")
        output = run_cli("Compare Brunson and Haliburton pts over the last 10 games")
        self.assertIn("Jalen Brunson led in total points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_three_player_comparison_supported(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = compare_draft("Brunson", "Haliburton", "Tatum")
        output = run_cli("Compare Brunson, Haliburton, and Tatum scoring over the last 10 games")

        self.assertIn("Jalen Brunson led in total points", output)
        self.assertIn("Tyrese Haliburton", output)
        self.assertIn("Jayson Tatum", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_object_style_question_rejected(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "unsupported", "reason": "cannot be represented as a Scope 1 question"}
        )
        with self.assertRaises(RuntimeError):
            run_cli("Show me all information about Brunson")


if __name__ == "__main__":
    unittest.main()
