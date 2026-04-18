from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query
from apps.cli.semantic_interpreter import _capability_artifact


class SliceTwentySixTests(unittest.TestCase):
    def test_supported_monthly_trend_still_plans_with_string_time_grain_ref(self) -> None:
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

        planner_output = call_haskell_planner_for_query(payload)
        shared = planner_output["query"]["spec"]["sharedQuery"]
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(resolved["timeGrain"], "month")
        self.assertEqual(resolved["timeFilterKind"], "past_year")
        self.assertIn("game_date", resolved["timeBucketExpression"])

    def test_unsupported_time_grain_fails_in_planner_not_ir_deserialization(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name"],
                    "timeGrain": "week",
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
            call_haskell_planner_for_query(payload)

        message = str(context.exception)
        self.assertIn("Trend queries currently support only the month time grain.", message)
        self.assertNotIn("Unknown time grain", message)

    def test_trend_still_only_accepts_past_year_filter(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": [],
                    "timeGrain": "month",
                    "filters": [{"kind": "last_n_games", "value": 10}],
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
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Trend queries currently require a PastYear filter.",
            str(context.exception),
        )

    def test_object_queries_still_reject_time_grain_usage(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": "month",
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "rowObject": "Player",
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Object queries currently do not support time-grain trends.",
            str(context.exception),
        )

    def test_comparison_queries_still_reject_time_grain_usage(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": "month",
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

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Comparison queries currently do not support time-grain trends.",
            str(context.exception),
        )

    def test_capability_artifact_still_emits_only_truthful_monthly_trend_families(self) -> None:
        artifact = _capability_artifact()
        trend_families = [
            family for family in artifact["families"] if family["time_grain"] is not None
        ]

        self.assertTrue(all(family["time_grain"] == "month" for family in trend_families))
        self.assertTrue(
            any(
                family["core_fact_object"] == "PlayerGame"
                and tuple(family["dimensions"]) == tuple()
                and tuple(family["required_filter_kinds"]) == ("past_year",)
                for family in trend_families
            )
        )
        self.assertTrue(
            any(
                family["core_fact_object"] == "TeamGame"
                and tuple(family["dimensions"]) == ("team_name",)
                and tuple(family["required_filter_kinds"]) == ("past_year",)
                for family in trend_families
            )
        )


if __name__ == "__main__":
    unittest.main()
