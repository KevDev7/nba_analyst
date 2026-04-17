from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query, plan_question, run_cli


class SliceSixteenTests(unittest.TestCase):
    def test_recent_metric_linked_filter_still_validates(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players by average points for the Lakers over the last 10 games"
        )

        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(
            shared["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}],
        )

    def test_season_metric_linked_filter_still_validates(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players by average points for the Lakers in the 2025-26 regular season"
        )

        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeasonTeam")
        self.assertEqual(
            shared["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}],
        )

    def test_season_object_linked_filter_on_player_game_validates(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Player",
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}
                    ],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": None,
                    "assumptions": [],
                },
            },
        }

        planner_output = call_haskell_planner_for_query(payload)
        self.assertEqual(planner_output["query"]["kind"], "object_query")
        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"], "PlayerGame"
        )
        self.assertEqual(
            planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]["filterValue"],
            "Lakers",
        )

    def test_season_object_linked_filter_on_player_season_team_validates(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Player",
                "sharedQuery": {
                    "coreFactObject": "PlayerSeasonTeam",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}
                    ],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": None,
                    "assumptions": [],
                },
            },
        }

        planner_output = call_haskell_planner_for_query(payload)
        self.assertEqual(planner_output["query"]["kind"], "object_query")
        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"],
            "PlayerSeasonTeam",
        )
        self.assertEqual(
            planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]["filterValue"],
            "Lakers",
        )

    def test_recent_object_linked_filter_on_player_season_team_is_rejected(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Player",
                "sharedQuery": {
                    "coreFactObject": "PlayerSeasonTeam",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "last_n_games", "value": 10},
                    ],
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

        self.assertIn(
            "Linked team filters on recent object queries currently support PlayerGame only.",
            str(context.exception),
        )

    def test_linked_filter_output_regression_still_green(self) -> None:
        output = run_cli("Show me players and their total points for the Knicks over the last 10 games")

        self.assertIn("Players ordered by total points over the last 10 games", output)
        self.assertIn("Player | Team | Total Points", output)
        self.assertIn("Jalen Brunson | NYK | 245", output)


if __name__ == "__main__":
    unittest.main()
