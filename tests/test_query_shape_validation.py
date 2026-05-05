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
                    "coreFactObject": "PlayerGame",
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
            planner_output["execution_plan"]["answer_context"]["display"]["grouping_columns"],
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
            planner_output["execution_plan"]["answer_context"]["display"]["metrics"],
            [
                {"column_key": "metric_value", "label": "total_points", "metric": "total_points", "aggregation": "sum"},
                {"column_key": "metric_2", "label": "average_points", "metric": "average_points", "aggregation": "avg"},
            ],
        )

    def test_multi_metric_trend_query_is_supported_with_display_metric_columns(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points", "total_assists", "total_rebounds"],
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

        planner_output = call_plan_query_json(payload)
        execution_plan = planner_output["execution_plan"]
        sql = execution_plan["execution"]["steps"][0]["sql"]

        self.assertEqual(
            execution_plan["answer_context"]["display"]["metrics"],
            [
                {"column_key": "metric_value", "label": "total_points", "metric": "total_points", "aggregation": "sum"},
                {"column_key": "metric_2", "label": "total_assists", "metric": "total_assists", "aggregation": "sum"},
                {"column_key": "metric_3", "label": "total_rebounds", "metric": "total_rebounds", "aggregation": "sum"},
            ],
        )
        self.assertIn("f.assists AS __metric_2_source", sql)
        self.assertIn("f.total_rebounds AS __metric_3_source", sql)
        self.assertIn("SUM(__metric_2_source) AS metric_2", sql)
        self.assertIn("SUM(__metric_3_source) AS metric_3", sql)
        self.assertIn("  metric_2,\n  metric_3,\n  metric_value", sql)

if __name__ == "__main__":
    unittest.main()
