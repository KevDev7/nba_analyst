from __future__ import annotations

import unittest

import duckdb

from apps.cli.main import ROOT, plan_question, run_cli
from scripts.load_gold_snapshot import load_database


class SeasonQueryTests(unittest.TestCase):
    def test_player_season_average_points_query(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players by average points in the 2025-26 regular season"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")

        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(shared["metrics"], ["points_per_game"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["factTableName"], "player_season")
        self.assertEqual(resolved["rowObjectName"], "Player")
        self.assertEqual(resolved["rowPath"]["steps"][0]["linkName"], "player_season_player")
        self.assertEqual(resolved["metricFormula"]["metricKey"], "points_per_game")
        self.assertEqual(resolved["seasonLabel"], "2025-26")
        self.assertEqual(resolved["seasonType"], "regular_season")

        execution_plan = planner_output["execution_plan"]
        self.assertEqual(execution_plan["season_label"], "2025-26")
        self.assertEqual(execution_plan["season_type"], "regular_season")

    def test_player_season_average_points_output(self) -> None:
        output = run_cli("Show me players by average points in the 2025-26 regular season")
        self.assertIn("Players ranked by average points in the 2025-26 regular season", output)
        self.assertIn("Rank | Player | Season | Season Type | Games Played | Minutes | Average Points", output)
        self.assertIn("1 | Luka Dončić | 2025-26 | Regular Season | 62 | 36.0 | 33.7", output)

    def test_team_season_wins_query(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me teams by wins in the 2025-26 regular season"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")

        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamSeason")
        self.assertEqual(shared["metrics"], ["wins"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["factTableName"], "team_season")
        self.assertEqual(resolved["rowObjectName"], "Team")
        self.assertEqual(resolved["rowPath"]["steps"][0]["linkName"], "team_season_team")
        self.assertEqual(resolved["metricFormula"]["metricKey"], "wins")

    def test_team_season_wins_output(self) -> None:
        output = run_cli("Show me teams by wins in the 2025-26 regular season")
        self.assertIn("Teams ranked by wins in the 2025-26 regular season", output)
        self.assertIn("Rank | Team | Abbrev | Season | Season Type | Games Played | Wins", output)
        self.assertIn("1 | Thunder | OKC | 2025-26 | Regular Season | 76 | 60", output)

    def test_player_season_object_query(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players and their total points in the 2025-26 regular season"
        )
        self.assertEqual(planner_output["query"]["kind"], "object_query")
        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["factTableName"], "player_season")
        self.assertEqual(resolved["rowObjectName"], "Player")
        self.assertEqual(resolved["rowPath"]["steps"][0]["linkName"], "player_season_player")
        self.assertEqual(resolved["metricFormula"]["metricKey"], "points_total")
        self.assertEqual(resolved["seasonLabel"], "2025-26")
        self.assertEqual(resolved["seasonType"], "regular_season")

        output = run_cli("Show me players and their total points in the 2025-26 regular season")
        self.assertIn("Players ordered by total points in the 2025-26 regular season", output)
        self.assertIn("Player | Season | Season Type | Games Played | Minutes | Total Points", output)
        self.assertIn("Luka Dončić | 2025-26 | Regular Season | 62 | 36.0 | 2089", output)

    def test_player_season_team_reconciliation_for_james_harden(self) -> None:
        database_path = load_database()
        conn = duckdb.connect(str(database_path), read_only=True)
        try:
            season_rows = conn.execute(
                """
                SELECT p.full_name, ps.games_played, ps.points_total
                FROM player_season ps
                JOIN player p ON ps.person_id = p.person_id
                WHERE ps.person_id = 201935
                  AND ps.season_year = '2025-26'
                  AND ps.season_type = 'regular_season'
                """
            ).fetchall()
            team_rows = conn.execute(
                """
                SELECT t.team_abbreviation, pst.games_played, pst.points_total
                FROM player_season_team pst
                JOIN team t ON pst.team_id = t.team_id
                WHERE pst.person_id = 201935
                  AND pst.season_year = '2025-26'
                  AND pst.season_type = 'regular_season'
                ORDER BY t.team_abbreviation ASC
                """
            ).fetchall()
        finally:
            conn.close()

        self.assertEqual(season_rows, [("James Harden", 65, 1547)])
        self.assertEqual(team_rows, [("CLE", 21, 429), ("LAC", 44, 1118)])
        self.assertEqual(sum(row[1] for row in team_rows), season_rows[0][1])
        self.assertEqual(sum(row[2] for row in team_rows), season_rows[0][2])


if __name__ == "__main__":
    unittest.main()
