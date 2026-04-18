from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query
from apps.cli.semantic_interpreter import _capability_artifact, _capability_prompt_summary


class SliceTwentyNineTests(unittest.TestCase):
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
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(resolved["factTableName"], "player_game")
        self.assertIsNone(resolved["seriesObjectName"])
        self.assertEqual(resolved["timeGrain"], "month")

    def test_player_game_monthly_trend_by_player_name_now_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
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
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(resolved["seriesObjectName"], "Player")
        self.assertEqual(resolved["seriesName"]["columnName"], "player_name")

    def test_fact_without_monthly_trend_surface_fails_with_fact_surface_reason(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeason",
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

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Trend queries currently require a fact surface that exposes game_date and a derived game_year_month time bucket.",
            str(context.exception),
        )

    def test_reachable_non_dimension_grouping_attribute_fails_clearly(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["person_id"],
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
            call_haskell_planner_for_query(payload)

        self.assertIn("Trend grouping currently supports reachable public dimension attributes only.", str(context.exception))

    def test_capability_artifact_now_includes_player_game_trend_families(self) -> None:
        artifact = _capability_artifact()
        trend_families = [family for family in artifact["families"] if family["time_grain"] == "month"]

        self.assertTrue(any(family["core_fact_object"] == "PlayerGame" for family in trend_families))
        self.assertTrue(any(family["core_fact_object"] == "TeamGame" for family in trend_families))

    def test_prompt_summary_reflects_broader_monthly_trend_support(self) -> None:
        summary = _capability_prompt_summary()

        self.assertIn("player_game_monthly_metric", summary)
        self.assertIn("team_game_monthly_metric", summary)


if __name__ == "__main__":
    unittest.main()
