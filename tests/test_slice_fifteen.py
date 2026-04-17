from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query, plan_question, run_cli


class SliceFifteenTests(unittest.TestCase):
    def test_recent_metric_query_is_accepted(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players by average points over the last 10 games"
        )

        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "average_points"}])

    def test_season_metric_query_is_accepted(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players by average points in the 2025-26 regular season"
        )

        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "average_points"}])

    def test_player_game_season_team_filter_metric_query_is_rejected(self) -> None:
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

        self.assertIn(
            "Season-scoped linked team filters currently support PlayerSeasonTeam only.",
            str(context.exception),
        )

    def test_player_season_team_filter_metric_query_is_accepted(self) -> None:
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

    def test_season_team_filter_metric_query_output(self) -> None:
        output = run_cli(
            "Show me players by average points for the Lakers in the 2025-26 regular season"
        )

        self.assertIn("Players ranked by average points in the 2025-26 regular season", output)
        self.assertIn("Rank | Player | Team | Average Points", output)
        self.assertIn("1 | Luka Dončić | LAL | 33.7", output)


if __name__ == "__main__":
    unittest.main()
