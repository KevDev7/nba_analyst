from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json
from runtime.AnalysisRuntime.models import ExecutionPlan
from runtime.AnalysisRuntime.runner import execute_plan
from runtime.AnswerSynthesis.format_response import format_response
from runtime.AnswerSynthesis.package_results import package_results
from runtime.AnswerSynthesis.synthesize import synthesize_answer


class ComparisonGenericRuntimeTests(unittest.TestCase):
    def test_player_average_points_comparison_is_generic_and_supported(self) -> None:
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
        self.assertEqual(planner_output["execution_plan"]["answer_context"]["metric"]["key"], "average_points")
        self.assertEqual(planner_output["execution_plan"]["answer_context"]["metric"]["aggregation"], "avg")
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

    def test_player_multi_metric_comparison_runtime_aggregates_each_metric(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points", "total_assists", "total_rebounds"],
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
        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(planner_output["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(planner_output["execution_plan"])
        runtime_result = execute_plan(execution_plan)
        formatted = format_response(synthesize_answer(package_results(runtime_result)))

        self.assertIsNotNone(runtime_result.comparison)
        assert runtime_result.comparison is not None
        self.assertTrue(
            all("metric_2" in entity.display_values for entity in runtime_result.comparison.entities)
        )
        self.assertTrue(
            all("metric_3" in entity.display_values for entity in runtime_result.comparison.entities)
        )
        self.assertIn("Player | Team | Games | Total Points | Assists | Rebounds", formatted)
        self.assertIn("Jalen Brunson", formatted)
        self.assertIn("Jayson Tatum", formatted)
        self.assertNotIn("Differential:", formatted)

    def test_player_multi_metric_grouped_comparison_runtime_aggregates_each_metric(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points", "total_assists", "total_rebounds"],
                    "dimensions": ["full_name", "season_type"],
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
        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(planner_output["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(planner_output["execution_plan"])
        runtime_result = execute_plan(execution_plan)
        formatted = format_response(synthesize_answer(package_results(runtime_result)))

        self.assertIsNotNone(runtime_result.comparison)
        assert runtime_result.comparison is not None
        self.assertTrue(runtime_result.comparison.breakdown_rows)
        self.assertTrue(
            all("metric_2" in row.display_values for row in runtime_result.comparison.breakdown_rows)
        )
        self.assertTrue(
            all("metric_3" in row.display_values for row in runtime_result.comparison.breakdown_rows)
        )
        self.assertIn("Player | Team | Season Type | Games | Total Points | Assists | Rebounds", formatted)
        self.assertIn("Total points, assists, and rebounds comparison by season type over the last 10 games is shown below.", formatted)
        self.assertNotIn("Overall,", formatted)
        self.assertNotIn("Differential:", formatted)

    def test_comparison_rejects_limit(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
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
            call_plan_query_json(payload)

        self.assertIn("Comparison queries do not support limit.", str(context.exception))

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
            call_plan_query_json(payload)

        self.assertIn(
            "Comparison queries require a comparison identity dimension on the target object.",
            str(context.exception),
        )

if __name__ == "__main__":
    unittest.main()
