from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query
from apps.cli.semantic_interpreter import _capability_artifact, _capability_prompt_summary


class SliceTwentySevenTests(unittest.TestCase):
    def test_recent_metric_query_with_team_conference_linked_filter_succeeds(self) -> None:
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
                        {"targetObject": "Team", "attribute": "conference", "value": "Western"}
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

        self.assertEqual(resolved_filter["targetObjectName"], "Team")
        self.assertEqual(resolved_filter["filterColumn"], "conference")
        self.assertEqual(resolved_filter["filterValue"], "Western")

    def test_recent_object_query_with_team_division_linked_filter_succeeds(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Player",
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "division", "value": "Pacific"}
                    ],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": 5,
                    "assumptions": [],
                },
            },
        }

        planner_output = call_haskell_planner_for_query(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["filterColumn"], "division")
        self.assertEqual(resolved_filter["filterValue"], "Pacific")

    def test_season_metric_query_with_team_abbreviation_linked_filter_succeeds(self) -> None:
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
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_abbreviation", "value": "LAL"}
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

        self.assertEqual(resolved_filter["filterColumn"], "team_abbreviation")
        self.assertEqual(resolved_filter["filterValue"], "LAL")

    def test_team_name_linked_filter_still_works(self) -> None:
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
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["filterColumn"], "team_name")
        self.assertEqual(resolved_filter["filterValue"], "Lakers")

    def test_non_team_target_player_display_name_now_succeeds(self) -> None:
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

    def test_more_than_one_linked_filter_still_fails(self) -> None:
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
                        {"targetObject": "Team", "attribute": "conference", "value": "Western"},
                        {"targetObject": "Team", "attribute": "division", "value": "Pacific"},
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

        self.assertIn("Query currently supports at most one linked filter.", str(context.exception))

    def test_trend_still_rejects_linked_filters(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name"],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "conference", "value": "Western"}
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
            call_haskell_planner_for_query(payload)

        self.assertIn("Trend queries currently do not support linked filters.", str(context.exception))

    def test_comparison_still_rejects_linked_filters(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "conference", "value": "Western"}
                    ],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [
                    {"personId": 1628973, "playerName": "Jalen Brunson"},
                    {"personId": 1628369, "playerName": "Jayson Tatum"},
                ],
                "comparison": {
                    "kind": "compare_entities",
                    "entities": [
                        {"personId": 1628973, "playerName": "Jalen Brunson"},
                        {"personId": 1628369, "playerName": "Jayson Tatum"},
                    ],
                },
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Comparison queries currently do not support linked filters.",
            str(context.exception),
        )

    def test_capability_artifact_includes_team_dimensions_beyond_team_name(self) -> None:
        artifact = _capability_artifact()
        linked_filter_attributes = {
            family["linked_filters"][0]["attribute"]
            for family in artifact["families"]
            if family["linked_filters"]
        }
        linked_filter_targets = {
            family["linked_filters"][0]["target_object"]
            for family in artifact["families"]
            if family["linked_filters"]
        }

        self.assertIn("team_name", linked_filter_attributes)
        self.assertIn("conference", linked_filter_attributes)
        self.assertIn("division", linked_filter_attributes)
        self.assertIn("Team", linked_filter_targets)
        self.assertIn("Player", linked_filter_targets)
        self.assertIn("Game", linked_filter_targets)

    def test_prompt_summary_reflects_broader_team_linked_filter_surface(self) -> None:
        summary = _capability_prompt_summary()

        self.assertIn("Supported linked-filter targets and public dimensions:", summary)
        self.assertIn("- Team: [", summary)
        self.assertIn("- Player: [", summary)
        self.assertIn("conference", summary)
        self.assertIn("division", summary)
        self.assertIn("team_name", summary)
        self.assertIn("linked filters: Team public dimensions", summary)

    def test_player_game_season_metric_linked_filters_remain_absent_for_game_targets(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["query_kind"] == "metric_query"
            and family["core_fact_object"] == "PlayerGame"
            and family["required_filter_kinds"] == ["exact_season", "season_type"]
            and family["linked_filters"]
            and family["linked_filters"][0]["target_object"] == "Game"
            and "average_points" in family["metrics"]
        ]

        self.assertEqual(matching, [])


if __name__ == "__main__":
    unittest.main()
