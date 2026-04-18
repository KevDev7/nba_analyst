from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query
from apps.cli.semantic_interpreter import _capability_artifact, _capability_prompt_summary


class SliceTwentyEightTests(unittest.TestCase):
    def test_recent_metric_query_with_player_display_name_linked_filter_succeeds(self) -> None:
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
                        {"targetObject": "Player", "attribute": "display_name", "value": "sample"}
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
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["targetObjectName"], "Player")
        self.assertEqual(resolved_filter["filterColumn"], "display_name")
        self.assertEqual(resolved_filter["filterValue"], "sample")

    def test_recent_object_query_with_game_label_linked_filter_succeeds(self) -> None:
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
                        {"targetObject": "Game", "attribute": "game_label", "value": "sample"}
                    ],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": 5,
                    "assumptions": [],
                },
            },
        }

        planner_output = call_haskell_planner_for_query(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["targetObjectName"], "Game")
        self.assertEqual(resolved_filter["filterColumn"], "game_label")
        self.assertEqual(resolved_filter["filterValue"], "sample")

    def test_season_metric_query_with_player_display_name_linked_filter_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeason",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "linkedFilters": [
                        {"targetObject": "Player", "attribute": "display_name", "value": "sample"}
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
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["targetObjectName"], "Player")
        self.assertEqual(resolved_filter["filterColumn"], "display_name")

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
                        {"targetObject": "Game", "attribute": "game_label", "value": "sample"}
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
            call_haskell_planner_for_query(payload)

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
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Linked filters currently support public dimension attributes on reachable ontology objects only.",
            str(context.exception),
        )

    def test_capability_artifact_includes_non_team_linked_filter_targets(self) -> None:
        artifact = _capability_artifact()
        linked_filter_targets = {
            family["linked_filters"][0]["target_object"]
            for family in artifact["families"]
            if family["linked_filters"]
        }

        self.assertIn("Team", linked_filter_targets)
        self.assertIn("Player", linked_filter_targets)
        self.assertIn("Game", linked_filter_targets)

    def test_prompt_summary_groups_linked_filter_targets_and_dimensions(self) -> None:
        summary = _capability_prompt_summary()

        self.assertIn("Supported linked-filter targets and public dimensions:", summary)
        self.assertIn("- Team: [", summary)
        self.assertIn("- Player: [", summary)
        self.assertIn("- Game: [", summary)
        self.assertIn("linked filters: Player public dimensions", summary)

    def test_team_season_does_not_derive_unreachable_game_linked_filters(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["core_fact_object"] == "TeamSeason"
            and family["linked_filters"]
            and family["linked_filters"][0]["target_object"] == "Game"
        ]

        self.assertEqual(matching, [])


if __name__ == "__main__":
    unittest.main()
