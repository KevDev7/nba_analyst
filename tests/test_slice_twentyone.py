from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query
from apps.cli.semantic_interpreter import _capability_artifact


class SliceTwentyOneTests(unittest.TestCase):
    def test_recent_metric_linked_filter_shape_still_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}
                    ],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_haskell_planner_for_query(payload)
        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        self.assertEqual(
            planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]["filterValue"],
            "Lakers",
        )

    def test_recent_object_linked_filter_rejection_is_no_longer_allowlist_based(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Player",
                "sharedQuery": {
                    "coreFactObject": "PlayerSeasonTeam",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}
                    ],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": None,
                    "assumptions": [],
                },
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        message = str(context.exception)
        self.assertIn(
            "Recent object queries with linked filters currently require a fact surface that exposes game_date.",
            message,
        )
        self.assertNotIn("currently support PlayerGame only", message)

    def test_player_game_season_metric_linked_filter_is_rejected_for_compile_truth_not_allowlist(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}
                    ],
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
            "Season-scoped metric queries with linked filters currently require a season-level fact surface rather than per-game rows.",
            message,
        )
        self.assertNotIn("currently support PlayerSeasonTeam only", message)

    def test_derived_capabilities_do_not_include_player_game_season_team_filter_metric_family(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["query_kind"] == "metric_query"
            and family["core_fact_object"] == "PlayerGame"
            and family["dimensions"] == ["player_name"]
            and family["required_filter_kinds"] == ["exact_season", "season_type"]
            and family["linked_filters"]
            and family["linked_filters"][0]["target_object"] == "Team"
            and family["linked_filters"][0]["attribute"] == "team_name"
            and "average_points" in family["metrics"]
        ]

        self.assertEqual(matching, [])


if __name__ == "__main__":
    unittest.main()
