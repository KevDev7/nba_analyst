from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


class LinkedFilterReachableAttributeTests(unittest.TestCase):
    def test_recent_metric_query_with_player_full_name_linked_filter_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Player", "attribute": "full_name", "value": "sample"}
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
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["targetObjectName"], "Player")
        self.assertEqual(resolved_filter["filterColumn"], "full_name")
        self.assertEqual(resolved_filter["filterValue"], "sample")

    def test_recent_object_query_with_game_date_linked_filter_succeeds(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Team",
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["total_points"],
                    "dimensions": ["team_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Game", "attribute": "game_date", "value": "2025-01-01"}
                    ],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": 5,
                    "assumptions": [],
                },
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["targetObjectName"], "Game")
        self.assertEqual(resolved_filter["filterColumn"], "game_date")
        self.assertEqual(resolved_filter["filterValue"], "2025-01-01")

    def test_season_metric_query_with_player_full_name_linked_filter_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeason",
                    "metrics": ["points_per_game"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "linkedFilters": [
                        {"targetObject": "Player", "attribute": "full_name", "value": "sample"}
                    ],
                    "orders": [{"kind": "desc", "metric": "points_per_game"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["targetObjectName"], "Player")
        self.assertEqual(resolved_filter["filterColumn"], "full_name")

    def test_unreachable_linked_filter_target_fails_with_path_message(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamSeason",
                    "metrics": ["wins"],
                    "dimensions": ["team_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "linkedFilters": [
                        {"targetObject": "Game", "attribute": "game_date", "value": "2025-01-01"}
                    ],
                    "orders": [{"kind": "desc", "metric": "wins"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn("No valid ontology path from 'TeamSeason' to 'Game'.", str(context.exception))

    def test_reachable_target_with_non_dimension_attribute_fails_clearly(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Player", "attribute": "person_id", "value": "123"}
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

        self.assertIn(
            "Linked filters support public dimension attributes on reachable ontology objects only.",
            str(context.exception),
        )

if __name__ == "__main__":
    unittest.main()
