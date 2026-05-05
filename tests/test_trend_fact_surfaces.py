from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


class TrendFactSurfaceTests(unittest.TestCase):
    def test_player_game_monthly_aggregate_trend_now_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
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
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(resolved["factTableName"], "player_game")
        self.assertIsNone(resolved["seriesObjectName"])
        self.assertEqual(resolved["timeGrain"], "month")

    def test_player_game_monthly_trend_by_full_name_now_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
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

        planner_output = call_plan_query_json(payload)
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(resolved["seriesObjectName"], "Player")
        self.assertEqual(resolved["seriesName"]["columnName"], "full_name")

    def test_fact_without_monthly_trend_surface_fails_with_fact_surface_reason(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeason",
                    "metrics": ["points_per_game"],
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
            "Past-year trend filters require an ontology-backed game_date attribute.",
            str(context.exception),
        )

    def test_reachable_public_primary_key_grouping_attribute_is_supported(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["person_id"],
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
            [{"column_key": "group_1", "label": "person_id"}],
        )
        self.assertEqual(
            planner_output["resolved_query"]["resolved"]["trendGroupingDimensions"][0]["groupingSource"]["tableRole"],
            "fact",
        )

if __name__ == "__main__":
    unittest.main()
