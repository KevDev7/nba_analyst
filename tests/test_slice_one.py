# Purpose:
# Verify the gold-first total-points ranking path and its supported variants.
#
# Uses:
# - the CLI entrypoint
# - the Haskell semantic core
# - the Python runtime and answer synthesis layers
#
# Produces:
# - regression coverage for the total-points MetricQuery slice
#
# Next:
# - future broader slice tests

from __future__ import annotations

import unittest

from apps.cli.main import run_cli


class SliceOneTests(unittest.TestCase):
    def test_canonical_question(self) -> None:
        output = run_cli("Show me the top 10 players by points over the last 10 games")
        self.assertIn("Luka Dončić", output)
        self.assertIn("Shai Gilgeous-Alexander", output)
        self.assertIn("366", output)
        self.assertIn("312", output)

    def test_scorers_variant(self) -> None:
        output = run_cli("Who are the top 10 scorers over the last 10 games?")
        self.assertIn("Interpreted 'scorers' as players ranked by total points.", output)
        self.assertIn("Luka Dončić", output)

    def test_pts_variant(self) -> None:
        output = run_cli("Show me the top 10 players by pts over the last 10 games")
        self.assertIn("Interpreted 'pts' as total points.", output)
        self.assertIn("Luka Dončić", output)

    def test_limit_variant(self) -> None:
        output = run_cli("Show me the top 5 players by points over the last 10 games")
        self.assertIn("Top 5 players", output)
        self.assertIn("Kevin Durant", output)
        self.assertNotIn("6 | Jalen Brunson | NYK | 245", output)

    def test_unsupported_shape(self) -> None:
        with self.assertRaises(RuntimeError):
            run_cli("What is the trend in points over the last month?")


if __name__ == "__main__":
    unittest.main()
