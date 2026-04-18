from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from apps.cli.main import ROOT
from apps.cli.semantic_interpreter import interpret_question_to_planner_query


HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"


def call_query_model_recent_ranking(question: str) -> dict:
    command = [
        "cabal",
        "run",
        "-v0",
        "ontology-hs",
        "--",
        "query-model-ranking-json",
        "--question",
        question,
    ]
    result = subprocess.run(
        command,
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    payload_text = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(payload_text)
    return json.loads(payload_text)


class SliceThirtyTwoTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_planner_query.cache_clear()

    def test_haskell_query_model_handles_top_players_by_points(self) -> None:
        payload = call_query_model_recent_ranking(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(payload["kind"], "metric_query")
        shared = payload["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(shared["limit"], 10)

    def test_haskell_query_model_handles_scorers_variant(self) -> None:
        payload = call_query_model_recent_ranking(
            "Who are the top 10 scorers over the last 10 games?"
        )

        shared = payload["spec"]["sharedQuery"]
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["limit"], 10)

    def test_haskell_query_model_handles_pts_variant(self) -> None:
        payload = call_query_model_recent_ranking(
            "Show me the top 5 players by pts over the last 7 games"
        )

        shared = payload["spec"]["sharedQuery"]
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 7}])
        self.assertEqual(shared["limit"], 5)
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])

    def test_haskell_query_model_handles_average_points_variant(self) -> None:
        payload = call_query_model_recent_ranking(
            "Show me players by average points over the last 10 games"
        )

        shared = payload["spec"]["sharedQuery"]
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(
            shared["orders"], [{"kind": "desc", "metric": "average_points"}]
        )
        self.assertIsNone(shared["limit"])

    def test_haskell_query_model_handles_avg_points_variant(self) -> None:
        payload = call_query_model_recent_ranking(
            "Show me players by avg points over the last 10 games"
        )

        shared = payload["spec"]["sharedQuery"]
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(
            shared["orders"], [{"kind": "desc", "metric": "average_points"}]
        )

    def test_haskell_query_model_handles_highest_average_scoring_variant(self) -> None:
        payload = call_query_model_recent_ranking(
            "Who has the highest average scoring over the last 10 games?"
        )

        shared = payload["spec"]["sharedQuery"]
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(
            shared["orders"], [{"kind": "desc", "metric": "average_points"}]
        )
        self.assertEqual(shared["limit"], 1)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_live_fast_path_uses_haskell_for_recent_ranking(self, mock_call_gemini) -> None:
        payload = interpret_question_to_planner_query(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(payload["spec"]["sharedQuery"]["metrics"], ["total_points"])
        self.assertEqual(payload["spec"]["sharedQuery"]["assumptions"], [])
        mock_call_gemini.assert_not_called()

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_live_fast_path_preserves_python_owned_scorers_assumption(
        self, mock_call_gemini
    ) -> None:
        payload = interpret_question_to_planner_query(
            "Who are the top 10 scorers over the last 10 games?"
        )

        self.assertEqual(
            payload["spec"]["sharedQuery"]["assumptions"],
            ["Interpreted 'scorers' as players ranked by total points."],
        )
        mock_call_gemini.assert_not_called()

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_live_fast_path_uses_haskell_for_average_points_recent_ranking(
        self, mock_call_gemini
    ) -> None:
        payload = interpret_question_to_planner_query(
            "Show me players by average points over the last 10 games"
        )

        self.assertEqual(payload["spec"]["sharedQuery"]["metrics"], ["average_points"])
        self.assertEqual(payload["spec"]["sharedQuery"]["assumptions"], [])
        mock_call_gemini.assert_not_called()

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_live_fast_path_preserves_python_owned_avg_points_assumption(
        self, mock_call_gemini
    ) -> None:
        payload = interpret_question_to_planner_query(
            "Show me players by avg points over the last 10 games"
        )

        self.assertEqual(
            payload["spec"]["sharedQuery"]["assumptions"],
            ["Interpreted 'avg points' as average points."],
        )
        mock_call_gemini.assert_not_called()

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_live_fast_path_preserves_python_owned_average_scoring_assumption(
        self, mock_call_gemini
    ) -> None:
        payload = interpret_question_to_planner_query(
            "Who has the highest average scoring over the last 10 games?"
        )

        self.assertEqual(
            payload["spec"]["sharedQuery"]["assumptions"],
            ["Interpreted 'average scoring' as average points."],
        )
        mock_call_gemini.assert_not_called()

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_out_of_scope_queries_keep_using_gemini(self, mock_call_gemini) -> None:
        mock_call_gemini.side_effect = [
            """
            {
              "status": "ok",
              "query": {
                "query_kind": "metric_query",
                "core_fact_object": "PlayerSeason",
                "metrics": ["average_points"],
                "dimensions": ["player_name"],
                "filters": [
                  {"kind": "exact_season", "value": "2025-26"},
                  {"kind": "season_type", "value": "regular_season"}
                ],
                "orders": [{"kind": "desc", "metric": "average_points"}],
                "entity_filters": [],
                "comparison": null,
                "assumptions": []
              }
            }
            """,
            """
            {
              "status": "ok",
              "query": {
                "query_kind": "metric_query",
                "core_fact_object": "PlayerGame",
                "metrics": ["average_points"],
                "dimensions": ["player_name"],
                "filters": [{"kind": "last_n_games", "value": 10}],
                "linked_filters": [{"target_object": "Team", "attribute": "team_name", "value": "Lakers"}],
                "orders": [{"kind": "desc", "metric": "average_points"}],
                "entity_filters": [],
                "comparison": null,
                "assumptions": []
              }
            }
            """,
            """
            {
              "status": "ok",
              "query": {
                "query_kind": "object_query",
                "core_fact_object": "PlayerGame",
                "row_object": "Player",
                "metrics": ["total_points"],
                "dimensions": ["player_name"],
                "filters": [{"kind": "last_n_games", "value": 10}],
                "orders": [{"kind": "desc", "metric": "total_points"}],
                "assumptions": []
              }
            }
            """,
            """
            {
              "status": "ok",
              "query": {
                "query_kind": "metric_query",
                "core_fact_object": "PlayerGame",
                "metrics": ["total_points"],
                "dimensions": ["player_name"],
                "filters": [{"kind": "last_n_games", "value": 10}],
                "entity_filters": [],
                "comparison": {
                  "kind": "compare_entities",
                  "target_object": "Player",
                  "entities": ["Brunson", "Tatum"]
                },
                "assumptions": ["Interpreted 'scoring' as total points."]
              }
            }
            """,
        ]

        season_payload = interpret_question_to_planner_query(
            "Show me players by average points in the 2025-26 regular season"
        )
        linked_payload = interpret_question_to_planner_query(
            "Show me players by average points for the Lakers over the last 10 games"
        )
        object_payload = interpret_question_to_planner_query(
            "Show me players and their total points over the last 10 games"
        )
        comparison_payload = interpret_question_to_planner_query(
            "Compare Brunson and Tatum scoring over the last 10 games"
        )

        self.assertEqual(season_payload["kind"], "metric_query")
        self.assertEqual(linked_payload["kind"], "metric_query")
        self.assertEqual(object_payload["kind"], "object_query")
        self.assertEqual(comparison_payload["kind"], "metric_query")
        self.assertEqual(mock_call_gemini.call_count, 4)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    @patch(
        "apps.cli.semantic_interpreter._call_haskell_querymodel_recent_ranking",
        side_effect=RuntimeError("slice-32 failure"),
    )
    def test_querymodel_failure_falls_back_to_gemini(
        self, mock_haskell_querymodel, mock_call_gemini
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

        self.assertEqual(payload["spec"]["sharedQuery"]["metrics"], ["total_points"])
        mock_haskell_querymodel.assert_called_once()
        mock_call_gemini.assert_called_once()


if __name__ == "__main__":
    unittest.main()
