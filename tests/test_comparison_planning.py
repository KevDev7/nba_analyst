from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.cli.main import plan_question, run_cli
from apps.cli.semantic_interpreter import interpret_question_to_semantic_draft
from tests.planner_helpers import call_plan_query_json


class ComparisonPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_recent_player_comparison_validates(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": {
                    "task": "compare",
                    "subject": "players",
                    "measure": "scoring",
                    "time_window": {"kind": "last_n_games", "value": 10},
                    "entities": ["Brunson", "Tatum"],
                    "assumptions": ["Interpreted 'scoring' as points."],
                },
            }
        )

        semantic_draft, planner_output = plan_question(
            "Compare Brunson and Tatum scoring over the last 10 games"
        )

        self.assertEqual(semantic_draft["resolved_entities"][0]["entityName"], "Jalen Brunson")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [])
        self.assertEqual(planner_output["query"]["spec"]["comparison"]["targetObject"], "Player")
        self.assertEqual(
            [entity["entityName"] for entity in planner_output["query"]["spec"]["comparison"]["entities"]],
            ["Jalen Brunson", "Jayson Tatum"],
        )

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(
            [entity["entityName"] for entity in resolved["comparisonEntities"]],
            ["Jalen Brunson", "Jayson Tatum"],
        )

    def test_season_player_comparison_validates(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeason",
                    "metrics": ["points_total"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": {
                    "kind": "compare_entities",
                    "targetObject": "Player",
                    "entities": [
                        {"entityId": 1628973, "entityName": "Jalen Brunson"},
                        {"entityId": 1628369, "entityName": "Jayson Tatum"},
                    ],
                },
            },
        }

        planner_output = call_plan_query_json(payload)
        shared = planner_output["query"]["spec"]["sharedQuery"]
        resolved = planner_output["resolved_query"]["resolved"]
        execution_plan = planner_output["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(shared["filters"], [
            {"kind": "exact_season", "value": "2025-26"},
            {"kind": "season_type", "value": "regular_season"},
        ])
        self.assertEqual(resolved["factTableName"], "player_season")
        self.assertEqual(execution_plan["metric_aggregation"], "identity")
        self.assertEqual(execution_plan["season_label"], "2025-26")
        self.assertIn("WITH season_rows AS", sql)
        self.assertIn("f.points_total AS metric_value", sql)
        self.assertNotIn("game_rank <=", sql)

    def test_season_team_comparison_validates(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamSeason",
                    "metrics": ["wins"],
                    "dimensions": ["team_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": {
                    "kind": "compare_entities",
                    "targetObject": "Team",
                    "entities": [
                        {"entityId": 1610612747, "entityName": "Lakers"},
                        {"entityId": 1610612738, "entityName": "Celtics"},
                    ],
                },
            },
        }

        planner_output = call_plan_query_json(payload)
        self.assertEqual(planner_output["resolved_query"]["resolved"]["factTableName"], "team_season")
        self.assertEqual(planner_output["execution_plan"]["metric"], "wins")
        self.assertIn("f.wins AS metric_value", planner_output["execution_plan"]["steps"][0]["sql"])

    def test_time_bucketed_comparison_validates(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": {
                    "kind": "compare_entities",
                    "targetObject": "Player",
                    "entities": [
                        {"entityId": 1628973, "entityName": "Jalen Brunson"},
                        {"entityId": 1628369, "entityName": "Jayson Tatum"},
                    ],
                },
            },
        }

        planner_output = call_plan_query_json(payload)
        execution_plan = planner_output["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(execution_plan["result_shape"], "comparison")
        self.assertEqual(execution_plan["time_grain"], "month")
        self.assertIn("AS time_bucket", sql)

    def test_average_points_comparison_is_now_supported(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": {
                    "kind": "compare_entities",
                    "targetObject": "Player",
                    "entities": [
                        {"entityId": 1628973, "entityName": "Jalen Brunson"},
                        {"entityId": 1628369, "entityName": "Jayson Tatum"},
                    ],
                },
            },
        }

        planner_output = call_plan_query_json(payload)
        self.assertEqual(planner_output["execution_plan"]["metric"], "average_points")
        self.assertEqual(planner_output["execution_plan"]["metric_aggregation"], "avg")

    def test_non_full_name_dimension_comparison_is_rejected(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["primary_position"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": {
                    "kind": "compare_entities",
                    "targetObject": "Player",
                    "entities": [
                        {"entityId": 1628973, "entityName": "Jalen Brunson"},
                        {"entityId": 1628369, "entityName": "Jayson Tatum"},
                    ],
                },
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn(
            "Comparison queries require a comparison identity dimension on the target object.",
            str(context.exception),
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_recent_player_comparison_output_stays_green(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": {
                    "task": "compare",
                    "subject": "players",
                    "measure": "scoring",
                    "time_window": {"kind": "last_n_games", "value": 10},
                    "entities": ["Brunson", "Haliburton"],
                    "assumptions": ["Interpreted 'scoring' as points."],
                },
            }
        )

        output = run_cli("Compare Brunson and Haliburton scoring over the last 10 games")

        self.assertIn("Jalen Brunson led in total points", output)
        self.assertIn("Differential: 110 total points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_compare_without_time_scope_defaults_to_current_regular_season(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": {
                    "task": "compare",
                    "subject": "players",
                    "measure": "points",
                    "time_window": None,
                    "entities": ["Jalen Brunson", "Jayson Tatum"],
                    "assumptions": [],
                },
            }
        )

        semantic_draft, planner_output = plan_question("Compare Jalen Brunson and Jayson Tatum points")

        self.assertEqual(semantic_draft["time_window"], {"kind": "season", "value": "2025-26"})
        self.assertEqual(
            semantic_draft["assumptions"],
            [
                "Assumed season year is 2025-26.",
                "Assumed season type is regular season.",
            ],
        )
        self.assertEqual(planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"], "PlayerSeason")
        self.assertEqual(planner_output["execution_plan"]["season_label"], "2025-26")


if __name__ == "__main__":
    unittest.main()
