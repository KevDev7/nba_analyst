# Purpose:
# Verify the gold-first comparison path on the corrected Query root.
#
# Uses:
# - the CLI entrypoint
# - the Haskell semantic core
# - the Python runtime and answer synthesis layers
#
# Produces:
# - regression coverage for comparison behavior on the unified architecture
#
# Next:
# - future broader slice tests

from __future__ import annotations

import unittest

from apps.cli.main import plan_question, run_cli


class SliceTwoTests(unittest.TestCase):
    def test_query_root_is_variant_tagged(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me the top 10 players by points over the last 10 games"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")

    def test_comparison_question(self) -> None:
        output = run_cli("Compare Brunson and Haliburton scoring over the last 10 games")
        self.assertIn("Jalen Brunson scored more total points", output)
        self.assertIn("245 total points", output)
        self.assertIn("0 total points", output)
        self.assertIn("Differential: 245 points", output)

    def test_comparison_full_names(self) -> None:
        output = run_cli(
            "Compare Jalen Brunson and Tyrese Haliburton scoring over the last 10 games"
        )
        self.assertIn("Jalen Brunson scored more total points", output)

    def test_comparison_pts_variant(self) -> None:
        output = run_cli("Compare Brunson and Haliburton pts over the last 10 games")
        self.assertIn("Jalen Brunson scored more total points", output)
        self.assertIn("Interpreted 'pts' as total points.", output)

    def test_three_player_comparison_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            run_cli("Compare Brunson, Haliburton, and Tatum scoring over the last 10 games")

    def test_object_style_question_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            run_cli("Show me all information about Brunson")


if __name__ == "__main__":
    unittest.main()
