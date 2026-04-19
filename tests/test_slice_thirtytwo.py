from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from apps.cli.main import ROOT
from apps.cli.semantic_interpreter import interpret_question_to_planner_query
from scripts.generate_interpreter_capabilities import build_capability_artifact


HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"


def call_query_model(question: str) -> dict:
    command = [
        "cabal",
        "run",
        "-v0",
        "ontology-hs",
        "--",
        "query-model-json",
        "--ontology",
        str(ONTOLOGY_PATH),
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

    def test_haskell_query_model_handles_recent_player_metric_ranking(self) -> None:
        payload = call_query_model(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(payload["status"], "ok")
        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(payload["query"]["kind"], "metric_query")
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(shared["limit"], 10)

    def test_haskell_query_model_handles_season_player_metric(self) -> None:
        payload = call_query_model(
            "Show me players by average points in the 2025-26 regular season"
        )

        self.assertEqual(payload["status"], "ok")
        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )

    def test_haskell_query_model_handles_recent_team_metric(self) -> None:
        payload = call_query_model("Show me teams by average points over the last 10 games")

        self.assertEqual(payload["status"], "ok")
        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])

    def test_haskell_query_model_handles_monthly_trend(self) -> None:
        payload = call_query_model("What are the monthly average points over the past year?")

        self.assertEqual(payload["status"], "ok")
        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], [])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(shared["filters"], [{"kind": "past_year"}])
        self.assertEqual(shared["orders"], [])

    def test_haskell_query_model_handles_recent_linked_filter_metric(self) -> None:
        payload = call_query_model(
            "Show me players by average points for the Lakers over the last 10 games"
        )

        self.assertEqual(payload["status"], "ok")
        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(
            shared["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}],
        )

    def test_haskell_query_model_handles_season_linked_filter_metric(self) -> None:
        payload = call_query_model(
            "Show me players by average points for the Lakers in the 2025-26 regular season"
        )

        self.assertEqual(payload["status"], "ok")
        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeasonTeam")
        self.assertEqual(
            shared["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}],
        )

    def test_haskell_query_model_handles_object_query(self) -> None:
        payload = call_query_model("Show me players and their total points over the last 10 games")

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(payload["query"]["spec"]["rowObject"], "Player")
        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])

    def test_haskell_query_model_handles_comparison_query(self) -> None:
        payload = call_query_model("Compare Brunson and Tatum scoring over the last 10 games")

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["query"]["kind"], "metric_query")
        comparison = payload["query"]["spec"]["comparison"]
        self.assertEqual(comparison["targetObject"], "Player")
        self.assertEqual([entity["entityName"] for entity in comparison["entities"]], ["Jalen Brunson", "Jayson Tatum"])

    def test_haskell_query_model_reports_single_entity_metric_request_as_unsupported(self) -> None:
        payload = call_query_model("Show me Jaylen Brown average scoring in the last 5 games")

        self.assertEqual(payload["status"], "unsupported")
        self.assertIn("single-entity", payload["reason"])

    def test_haskell_query_model_chooses_shape_from_capability_truth(self) -> None:
        recent_payload = call_query_model("Show me players by average points over the last 10 games")
        season_payload = call_query_model(
            "Show me players by average points in the 2025-26 regular season"
        )
        season_team_payload = call_query_model(
            "Show me players by average points for the Lakers in the 2025-26 regular season"
        )

        self.assertEqual(
            recent_payload["query"]["spec"]["sharedQuery"]["coreFactObject"], "PlayerGame"
        )
        self.assertEqual(
            season_payload["query"]["spec"]["sharedQuery"]["coreFactObject"], "PlayerSeason"
        )
        self.assertEqual(
            season_team_payload["query"]["spec"]["sharedQuery"]["coreFactObject"],
            "PlayerSeasonTeam",
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_interpreter_uses_haskell_querymodel_before_gemini(self, mock_call_gemini) -> None:
        payload = interpret_question_to_planner_query(
            "Show me players by average points over the last 10 games"
        )

        self.assertEqual(payload["kind"], "metric_query")
        self.assertEqual(payload["spec"]["sharedQuery"]["metrics"], ["average_points"])
        mock_call_gemini.assert_not_called()

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_interpreter_falls_back_only_after_structured_unsupported(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 5}],
            "orders": [{"kind": "desc", "metric": "total_points"}],
            "entity_filters": [],
            "comparison": null,
            "assumptions": []
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me Jaylen Brown average scoring in the last 5 games"
        )

        self.assertEqual(payload["kind"], "metric_query")
        mock_call_gemini.assert_called_once()

    def test_capability_artifact_still_contains_supported_player_recent_metric_family(self) -> None:
        artifact = build_capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["query_kind"] == "metric_query"
            and family["core_fact_object"] == "PlayerGame"
            and family["dimensions"] == ["player_name"]
            and family["required_filter_kinds"] == ["last_n_games"]
            and not family["comparison"]["enabled"]
        ]

        self.assertTrue(matching)


if __name__ == "__main__":
    unittest.main()
