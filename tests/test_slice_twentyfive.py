from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query
from apps.cli.semantic_interpreter import _capability_artifact


class SliceTwentyFiveTests(unittest.TestCase):
    def test_supported_recent_metric_query_still_plans_with_filter_refs(self) -> None:
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
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": 5,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_haskell_planner_for_query(payload)
        shared = planner_output["query"]["spec"]["sharedQuery"]

        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(planner_output["resolved_query"]["resolved"]["windowGames"], 10)

    def test_supported_season_metric_query_still_plans_with_filter_refs(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeasonTeam",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "linkedFilters": [],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_haskell_planner_for_query(payload)
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(resolved["seasonLabel"], "2025-26")
        self.assertEqual(resolved["seasonType"], "regular_season")

    def test_supported_trend_query_still_plans_with_past_year_filter_ref(self) -> None:
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
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["filters"],
            [{"kind": "past_year"}],
        )
        self.assertEqual(resolved["timeFilterKind"], "past_year")

    def test_unknown_filter_kind_fails_in_planner_not_ir_deserialization(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "made_up_filter", "value": "anything"}],
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
            call_haskell_planner_for_query(payload)

        message = str(context.exception)
        self.assertIn(
            "Metric queries currently require either a positive LastNGames filter or an exact season plus season type filter bundle.",
            message,
        )
        self.assertNotIn("Unknown filter kind", message)

    def test_malformed_last_n_games_value_fails_at_contract_boundary(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": "ten"}],
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
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "last_n_games filters require a positive integer value.",
            str(context.exception),
        )

    def test_missing_season_type_still_fails_with_current_season_bundle_message(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeasonTeam",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "exact_season", "value": "2025-26"}],
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
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Metric queries currently require either a positive LastNGames filter or an exact season plus season type filter bundle.",
            str(context.exception),
        )

    def test_comparison_still_only_accepts_recent_window_filter_family(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
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
            "Comparison queries currently require a positive LastNGames filter.",
            str(context.exception),
        )

    def test_capability_artifact_still_contains_truthful_filter_families(self) -> None:
        artifact = _capability_artifact()

        player_recent = next(
            family
            for family in artifact["families"]
            if family["family_key"] == "player_game_recent_metric"
        )
        team_monthly = next(
            family
            for family in artifact["families"]
            if family["family_key"] == "team_game_monthly_metric"
        )
        player_season = next(
            family
            for family in artifact["families"]
            if family["family_key"] == "player_season_team_season_metric"
        )

        self.assertEqual(player_recent["required_filter_kinds"], ["last_n_games"])
        self.assertEqual(team_monthly["required_filter_kinds"], ["past_year"])
        self.assertEqual(player_season["required_filter_kinds"], ["exact_season", "season_type"])


if __name__ == "__main__":
    unittest.main()
