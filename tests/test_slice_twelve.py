from __future__ import annotations

import unittest

from apps.cli.main import plan_question, run_cli


class SliceTwelveTests(unittest.TestCase):
    def test_player_recent_object_totals_team_filter_limit_query(self) -> None:
        _semantic_draft, planner_output = plan_question(
            "Show me the top 5 players and their total points for the Knicks over the last 10 games"
        )

        self.assertEqual(planner_output["query"]["kind"], "object_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(
            shared["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Knicks"}],
        )
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(shared["limit"], 5)

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
        self.assertIn("LIMIT 5", sql)

    def test_player_recent_object_totals_team_filter_limit_output(self) -> None:
        output = run_cli(
            "Show me the top 5 players and their total points for the Knicks over the last 10 games"
        )

        self.assertIn("Players ordered by total points over the last 10 games", output)
        self.assertIn("Player | Team | Total Points", output)
        self.assertIn("Jalen Brunson | NYK | 245", output)
        self.assertIn("RJ Barrett | NYK | 168", output)
        self.assertNotIn("Josh Hart | NYK |", output)


if __name__ == "__main__":
    unittest.main()
