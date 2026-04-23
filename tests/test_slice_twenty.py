from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


class SliceTwentyTests(unittest.TestCase):
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
                    "linkedFilters": [],
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
            "Ranking/aggregation metric queries currently require exactly one business grouping dimension.",
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
                    "linkedFilters": [],
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
            "Object queries currently require exactly one row dimension.",
            str(context.exception),
        )

    def test_trend_with_multiple_dimensions_is_rejected_with_trend_specific_reason(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name", "player_name"],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
                    "linkedFilters": [],
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
            "Trend queries currently support at most one business grouping dimension.",
            str(context.exception),
        )

    def test_multi_metric_ranking_query_is_rejected_with_family_specific_reason(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points", "average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
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
            "Ranking/aggregation metric queries currently require exactly one selected metric.",
            str(context.exception),
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
                    "linkedFilters": [],
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
            "Trend queries currently require exactly one selected metric.",
            str(context.exception),
        )

if __name__ == "__main__":
    unittest.main()
