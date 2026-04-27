from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


class SliceTwentyOneTests(unittest.TestCase):
    def test_recent_metric_linked_filter_shape_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
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

        planner_output = call_plan_query_json(payload)
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
                    "metrics": ["points_total"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}
                    ],
                    "orders": [{"kind": "desc", "metric": "points_total"}],
                    "limit": None,
                    "assumptions": [],
                },
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        message = str(context.exception)
        self.assertIn(
            "Recent object queries with linked filters require a fact surface that exposes game_date.",
            message,
        )
        self.assertNotIn("support PlayerGame only", message)

    def test_player_game_season_metric_linked_filter_fails_for_compile_truth_not_allowlist(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
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
            call_plan_query_json(payload)

        message = str(context.exception)
        self.assertIn(
            "Season-scoped metric queries with linked filters require a season-level fact surface rather than per-game rows.",
            message,
        )
        self.assertNotIn("support PlayerSeasonTeam only", message)

if __name__ == "__main__":
    unittest.main()
