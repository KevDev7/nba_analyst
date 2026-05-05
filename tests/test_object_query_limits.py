from __future__ import annotations

import unittest

from apps.assistant.pipeline import plan_question
from apps.cli.main import run_cli


class ObjectQueryLimitTests(unittest.TestCase):
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
            shared["rowPredicate"],
            {
                "kind": "leaf",
                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                "operator": "equals",
                "value": {"kind": "scalar", "value": "Knicks"},
            },
        )
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(shared["limit"], 5)

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["factTableName"], "player_game")
        self.assertEqual(resolved["rowObjectName"], "Player")
        self.assertEqual(resolved["objectRowPredicateResolved"]["contents"]["rowPredicatePath"]["steps"][0]["linkName"], "player_game_team")
        self.assertEqual(resolved["objectRowPredicateResolved"]["contents"]["rowPredicateValue"]["value"], "Knicks")

        sql = planner_output["execution_plan"]["execution"]["steps"][0]["sql"]
        self.assertIn("JOIN team lf1", sql)
        self.assertIn("lf1.team_name = 'Knicks'", sql)
        self.assertIn("LIMIT 5", sql)

    def test_player_recent_object_totals_team_filter_limit_output(self) -> None:
        output = run_cli(
            "Show me the top 5 players and their total points for the Knicks over the last 10 games"
        )

        self.assertIn("Players ordered by total points over the last 10 games", output)
        self.assertIn("Player | Team | Games Played | Minutes | Date Range | Total Points", output)
        self.assertRegex(output, r"Jalen Brunson \| NYK \| 10 \| 37\.1 \| [0-9-]+ to [0-9-]+ \| 269")
        self.assertRegex(output, r"Julius Randle \| NYK \| 10 \| 34\.6 \| [0-9-]+ to [0-9-]+ \| 227")
        self.assertNotIn("Josh Hart | NYK |", output)


if __name__ == "__main__":
    unittest.main()
