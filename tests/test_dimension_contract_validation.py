from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


class DimensionContractValidationTests(unittest.TestCase):
    def test_supported_metric_query_plans_with_string_dimension_ref(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": 5,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        shared = planner_output["query"]["spec"]["sharedQuery"]

        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(
            planner_output["resolved_query"]["resolved"]["displayName"]["columnName"],
            "full_name",
        )

    def test_nonexistent_dimension_fails_with_ontology_resolution_error(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["made_up_dimension"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn(
            "No valid ontology path from 'PlayerGame' reaches a displayed dimension attribute 'made_up_dimension'.",
            str(context.exception),
        )

    def test_public_primary_key_dimension_is_valid_grouping_context(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["person_id"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)

        self.assertEqual(
            planner_output["execution_plan"]["answer_context"]["display"]["grouping_columns"],
            [{"column_key": "group_1", "label": "person_id"}],
        )
        sql = planner_output["execution_plan"]["execution"]["steps"][0]["sql"]
        self.assertIn("f.person_id AS group_1", sql)
        self.assertIn("PARTITION BY f.person_id", sql)

    def test_comparison_requires_identity_dimension_on_target_object(self) -> None:
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

    def test_trend_grouping_requires_reachable_public_dimension(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn("No valid ontology path from 'TeamGame' reaches a displayed dimension attribute 'full_name'.", str(context.exception))

if __name__ == "__main__":
    unittest.main()
