from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


class QueryShapeValidationTests(unittest.TestCase):
    def test_ranking_query_without_dimension_is_rejected_with_family_specific_reason(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": [],
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
            "Ranking queries require at least one business grouping dimension.",
            str(context.exception),
        )

    def test_object_query_without_dimension_is_rejected_with_family_specific_reason(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": [],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "rowObject": "Player",
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn(
            "Object queries require exactly one row dimension.",
            str(context.exception),
        )

    def test_trend_with_multiple_dimensions_is_supported_when_ontology_resolves_them(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name", "season_type"],
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

        planner_output = call_plan_query_json(payload)

        self.assertEqual(
            planner_output["execution_plan"]["grouping_columns"],
            [
                {"column_key": "group_1", "label": "team_name"},
                {"column_key": "group_2", "label": "season_type"},
            ],
        )

    def test_multi_metric_ranking_query_is_supported_with_one_primary_order_metric(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points", "average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)

        self.assertEqual(
            planner_output["execution_plan"]["display_metrics"],
            [
                {"column_key": "metric_value", "label": "total_points", "metric": "total_points"},
                {"column_key": "metric_2", "label": "average_points", "metric": "average_points"},
            ],
        )

    def test_multi_metric_trend_query_is_rejected_with_trend_specific_reason(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["total_points", "average_points"],
                    "dimensions": [],
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

        self.assertIn(
            "Trend queries require exactly one selected metric.",
            str(context.exception),
        )

if __name__ == "__main__":
    unittest.main()
