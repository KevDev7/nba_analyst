from __future__ import annotations

import unittest

from apps.cli.main import plan_question, run_cli


class SliceElevenTests(unittest.TestCase):
    def test_player_recent_average_points_team_filter_query(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players by average points for the Lakers over the last 10 games"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")

        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(
            shared["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}],
        )

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["factTableName"], "player_game")
        self.assertEqual(resolved["rowObjectName"], "Player")
        self.assertEqual(resolved["rowPath"]["steps"][0]["linkName"], "player_game_player")
        self.assertEqual(
            resolved["linkedFiltersResolved"][0]["filterPath"]["steps"][0]["linkName"],
            "player_game_team",
        )
        self.assertEqual(resolved["linkedFiltersResolved"][0]["targetObjectName"], "Team")
        self.assertEqual(resolved["linkedFiltersResolved"][0]["filterColumn"], "team_name")
        self.assertEqual(resolved["linkedFiltersResolved"][0]["filterValue"], "Lakers")

        sql = planner_output["execution_plan"]["steps"][0]["sql"]
        self.assertIn("JOIN team lf1", sql)
        self.assertIn("lf1.team_name = 'Lakers'", sql)

    def test_player_recent_object_totals_team_filter_query(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players and their total points for the Knicks over the last 10 games"
        )
        self.assertEqual(planner_output["query"]["kind"], "object_query")

        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(
            shared["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Knicks"}],
        )

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["factTableName"], "player_game")
        self.assertEqual(resolved["rowObjectName"], "Player")
        self.assertEqual(
            resolved["linkedFiltersResolved"][0]["filterPath"]["steps"][0]["linkName"],
            "player_game_team",
        )
        self.assertEqual(resolved["linkedFiltersResolved"][0]["filterValue"], "Knicks")

        sql = planner_output["execution_plan"]["steps"][0]["sql"]
        self.assertIn("JOIN team lf1", sql)
        self.assertIn("lf1.team_name = 'Knicks'", sql)

    def test_player_season_team_average_points_team_filter_query(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players by average points for the Lakers in the 2025-26 regular season"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")

        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeasonTeam")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(
            shared["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}],
        )

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["factTableName"], "player_season_team")
        self.assertEqual(resolved["rowObjectName"], "Player")
        self.assertEqual(
            resolved["rowPath"]["steps"][0]["linkName"], "player_season_team_player"
        )
        self.assertEqual(
            resolved["linkedFiltersResolved"][0]["filterPath"]["steps"][0]["linkName"],
            "player_season_team_team",
        )
        self.assertEqual(resolved["seasonLabel"], "2025-26")
        self.assertEqual(resolved["seasonType"], "regular_season")

        sql = planner_output["execution_plan"]["steps"][0]["sql"]
        self.assertIn("JOIN team lf1", sql)
        self.assertIn("lf1.team_name = 'Lakers'", sql)

    def test_player_recent_average_points_team_filter_output(self) -> None:
        output = run_cli("Show me players by average points for the Lakers over the last 10 games")
        self.assertIn("Players ranked by average points over the last 10 games", output)
        self.assertIn("Rank | Player | Team | Average Points", output)
        self.assertIn("1 | Luka Dončić | LAL | 36.6", output)

    def test_player_recent_object_totals_team_filter_output(self) -> None:
        output = run_cli("Show me players and their total points for the Knicks over the last 10 games")
        self.assertIn("Players ordered by total points over the last 10 games", output)
        self.assertIn("Player | Team | Total Points", output)
        self.assertIn("Jalen Brunson | NYK | 245", output)

    def test_player_season_team_average_points_team_filter_output(self) -> None:
        output = run_cli(
            "Show me players by average points for the Lakers in the 2025-26 regular season"
        )
        self.assertIn("Players ranked by average points in the 2025-26 regular season", output)
        self.assertIn("Rank | Player | Team | Average Points", output)
        self.assertIn("1 | Luka Dončić | LAL | 33.7", output)


if __name__ == "__main__":
    unittest.main()
