# Purpose:
# Verify the gold-first object-query path over the live Player -> PlayerGame link.
#
# Uses:
# - the CLI entrypoint
# - the Haskell semantic core
# - the Python runtime and answer synthesis layers
#
# Produces:
# - regression coverage for the first executed ObjectQuery slice
#
# Next:
# - future broader linked-object slices

from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner, run_cli


class SliceThreeTests(unittest.TestCase):
    def test_object_query_root(self) -> None:
        planner_output = call_haskell_planner(
            "Show me players and their total points over the last 10 games"
        )
        self.assertEqual(planner_output["query"]["kind"], "object_query")
        self.assertEqual(planner_output["resolved_query"]["kind"], "object_query")

    def test_object_query_resolves_live_link(self) -> None:
        planner_output = call_haskell_planner(
            "Show me players and their total points over the last 10 games"
        )
        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["rowTableName"], "player")
        self.assertEqual(resolved["factTableName"], "player_game")
        self.assertEqual(resolved["joinPath"]["factJoinKey"], "person_id")
        self.assertEqual(resolved["joinPath"]["rowJoinKey"], "person_id")

    def test_object_query_output(self) -> None:
        output = run_cli("Show me players and their total points over the last 10 games")
        self.assertIn("Players ordered by total points", output)
        self.assertIn("Luka Dončić | LAL | 366", output)
        self.assertIn("Jalen Brunson | NYK | 245", output)

    def test_object_query_variant(self) -> None:
        output = run_cli("Show me players with their scoring totals over the last 10 games")
        self.assertIn("Interpreted 'scoring' as total points.", output)
        self.assertIn("Shai Gilgeous-Alexander | OKC | 312", output)

    def test_assists_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            run_cli("Show me players and their assists over the last 10 games")

    def test_games_and_players_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            run_cli("Show me games and their players")


if __name__ == "__main__":
    unittest.main()
