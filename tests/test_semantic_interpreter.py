from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.cli.semantic_interpreter import (
    SemanticInterpreterError,
    interpret_question_to_planner_query,
)


class SemanticInterpreterTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_planner_query.cache_clear()

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_valid_metric_query_template_normalizes_to_haskell_query_json(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "orders": [{"kind": "desc", "metric": "total_points"}],
            "limit": 10,
            "entity_filters": [],
            "comparison": null,
            "assumptions": []
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(payload["kind"], "metric_query")
        self.assertEqual(payload["spec"]["sharedQuery"]["coreFactObject"], "PlayerGame")
        self.assertEqual(payload["spec"]["sharedQuery"]["metrics"], ["total_points"])
        self.assertEqual(payload["spec"]["sharedQuery"]["dimensions"], ["player_name"])
        self.assertEqual(
            payload["spec"]["sharedQuery"]["filters"],
            [{"kind": "last_n_games", "value": 10}],
        )
        self.assertEqual(
            payload["spec"]["sharedQuery"]["orders"],
            [{"kind": "desc", "metric": "total_points"}],
        )
        self.assertEqual(payload["spec"]["sharedQuery"]["limit"], 10)
        self.assertEqual(payload["spec"]["entityFilters"], [])
        self.assertIsNone(payload["spec"]["comparison"])

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_valid_object_query_template_normalizes_to_haskell_query_json(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "object_query",
            "core_fact_object": "PlayerSeason",
            "row_object": "Player",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [
              {"kind": "exact_season", "value": "2025-26"},
              {"kind": "season_type", "value": "regular_season"}
            ],
            "orders": [{"kind": "desc", "metric": "total_points"}],
            "assumptions": []
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me players and their total points in the 2025-26 regular season"
        )

        self.assertEqual(payload["kind"], "object_query")
        self.assertEqual(payload["spec"]["rowObject"], "Player")
        self.assertEqual(payload["spec"]["sharedQuery"]["coreFactObject"], "PlayerSeason")
        self.assertEqual(
            payload["spec"]["sharedQuery"]["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertIsNone(payload["spec"]["sharedQuery"]["limit"])

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_malformed_json_is_rejected_clearly(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = "{not valid json"

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "Show me the top 10 players by points over the last 10 games"
            )

        self.assertIn("malformed JSON", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_unsupported_values_are_rejected_clearly(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "Game",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "orders": [{"kind": "desc", "metric": "total_points"}]
          }
        }
        """

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "Show me the top 10 players by points over the last 10 games"
            )

        self.assertIn("invalid supported query template", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_omitted_optional_fields_normalize_cleanly(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["average_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}]
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me players by average points over the last 10 games"
        )

        self.assertEqual(payload["kind"], "metric_query")
        self.assertIsNone(payload["spec"]["sharedQuery"]["timeGrain"])
        self.assertEqual(payload["spec"]["sharedQuery"]["orders"], [])
        self.assertIsNone(payload["spec"]["sharedQuery"]["limit"])
        self.assertEqual(payload["spec"]["sharedQuery"]["assumptions"], [])
        self.assertEqual(payload["spec"]["entityFilters"], [])
        self.assertIsNone(payload["spec"]["comparison"])

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_unsupported_response_raises_clear_reason(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "unsupported",
          "reason": "last month trend is not supported by the current live contract"
        }
        """

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "What is the trend in points over the last month?"
            )

        self.assertIn("last month trend", str(context.exception))


if __name__ == "__main__":
    unittest.main()
