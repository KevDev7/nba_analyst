from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query
from apps.cli.semantic_interpreter import _capability_artifact
from runtime.AnalysisRuntime.models import ExecutionPlan
from runtime.AnalysisRuntime.runner import execute_plan
from runtime.AnswerSynthesis.format_response import format_response
from runtime.AnswerSynthesis.package_results import package_results
from runtime.AnswerSynthesis.synthesize import synthesize_answer


class SliceThirtyTests(unittest.TestCase):
    def test_player_average_points_comparison_is_generic_and_supported(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
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

        planner_output = call_haskell_planner_for_query(payload)
        self.assertEqual(planner_output["execution_plan"]["metric"], "average_points")
        self.assertEqual(planner_output["execution_plan"]["metric_aggregation"], "avg")
        self.assertEqual(
            planner_output["query"]["spec"]["comparison"]["targetObject"], "Player"
        )

    def test_team_average_points_comparison_runtime_stays_grounded(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
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

        planner_output = call_haskell_planner_for_query(payload)
        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(planner_output["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(planner_output["execution_plan"])
        runtime_result = execute_plan(execution_plan)
        formatted = format_response(synthesize_answer(package_results(runtime_result)))

        self.assertIn("Lakers led in average points", formatted)
        self.assertIn("Celtics (BOS)", formatted)
        self.assertIn("Lakers (LAL)", formatted)
        self.assertIn("Differential: 10.9 average points", formatted)

    def test_comparison_still_rejects_limit(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [],
                    "limit": 5,
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
            call_haskell_planner_for_query(payload)

        self.assertIn("Comparison queries currently do not support limit.", str(context.exception))

    def test_comparison_rejects_non_identity_team_dimension(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["conference"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
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

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Comparison queries currently require a comparison identity dimension on the target object.",
            str(context.exception),
        )

    def test_capability_artifact_derives_generic_comparison_targets(self) -> None:
        artifact = _capability_artifact()
        comparison_families = [
            family for family in artifact["families"] if family["comparison"]["enabled"]
        ]

        self.assertTrue(
            any(
                family["comparison"]["target_object"] == "Player"
                and family["dimensions"] == ["player_name"]
                and "average_points" in family["metrics"]
                for family in comparison_families
            )
        )
        self.assertTrue(
            any(
                family["comparison"]["target_object"] == "Team"
                and family["dimensions"] == ["team_name"]
                and "average_points" in family["metrics"]
                for family in comparison_families
            )
        )
        self.assertFalse(
            any(
                family["comparison"]["enabled"] and family["dimensions"] == ["conference"]
                for family in comparison_families
            )
        )


if __name__ == "__main__":
    unittest.main()
