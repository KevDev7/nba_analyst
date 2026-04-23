from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


class SliceNineteenTests(unittest.TestCase):
    def test_monthly_average_points_trend_query_stays_green(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
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

        planner_output = call_plan_query_json(payload)

        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], [])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(shared["filters"], [{"kind": "past_year"}])
        self.assertEqual(shared["orders"], [])
        self.assertIsNone(shared["limit"])

    def test_monthly_average_points_by_team_trend_query_stays_green(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name"],
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

        planner_output = call_plan_query_json(payload)

        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(shared["filters"], [{"kind": "past_year"}])
        self.assertEqual(shared["orders"], [])
        self.assertIsNone(shared["limit"])

    def test_player_game_monthly_trend_is_now_supported(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
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

        planner_output = call_plan_query_json(payload)
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(resolved["factTableName"], "player_game")
        self.assertEqual(resolved["timeGrain"], "month")

    def test_non_team_grouped_trend_is_now_supported_when_reachable(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["game_label"],
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

        planner_output = call_plan_query_json(payload)
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(resolved["seriesObjectName"], "Game")
        self.assertEqual(resolved["seriesName"]["columnName"], "game_label")

    def test_linked_filter_trend_is_rejected(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": [],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}
                    ],
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
            "Trend queries currently do not support linked filters.",
            str(context.exception),
        )

    def test_explicit_order_trend_is_rejected(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": [],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
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
            "Trend queries currently do not accept explicit ordering.",
            str(context.exception),
        )

    def test_limit_trend_is_rejected(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": [],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
                    "linkedFilters": [],
                    "orders": [],
                    "limit": 5,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn(
            "Trend queries currently do not support limit.",
            str(context.exception),
        )


if __name__ == "__main__":
    unittest.main()
