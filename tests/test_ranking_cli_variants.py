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
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.cli.main import run_cli


def draft(limit: int, measure: str = "points", assumptions: list[str] | None = None) -> str:
    return json.dumps(
        {
            "status": "ok",
            "draft": {
                "task": "rank",
                "subject": "players",
                "measure": measure,
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": limit,
                "sort": "desc",
                "assumptions": assumptions or [],
            },
        }
    )


class RankingCliVariantTests(unittest.TestCase):
    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_canonical_question(self, _call_gemini) -> None:
        _call_gemini.return_value = draft(10)
        output = run_cli("Show me the top 10 players by points over the last 10 games")
        self.assertIn("Luka Dončić", output)
        self.assertIn("Shai Gilgeous-Alexander", output)
        self.assertIn("397", output)
        self.assertIn("312", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_scorers_variant(self, _call_gemini) -> None:
        _call_gemini.return_value = draft(
            10,
            measure="scoring",
            assumptions=["Interpreted 'scorers' as players ranked by points."],
        )
        output = run_cli("Who are the top 10 scorers over the last 10 games?")
        self.assertIn("Interpreted 'scorers' as players ranked by points.", output)
        self.assertIn("Luka Dončić", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_pts_variant(self, _call_gemini) -> None:
        _call_gemini.return_value = draft(
            10,
            measure="pts",
            assumptions=["Interpreted 'pts' as points."],
        )
        output = run_cli("Show me the top 10 players by pts over the last 10 games")
        self.assertIn("Interpreted 'pts' as points.", output)
        self.assertIn("Luka Dončić", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_limit_variant(self, _call_gemini) -> None:
        _call_gemini.return_value = draft(5)
        output = run_cli("Show me the top 5 players by points over the last 10 games")
        self.assertIn("Top 5 players", output)
        self.assertIn("Devin Booker", output)
        self.assertNotIn("6 | Tyrese Maxey | PHI | 285", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_non_analytics_request_is_rejected(self, _call_gemini) -> None:
        _call_gemini.return_value = (
            '{"status":"unsupported","reason":"not an NBA analytics request"}'
        )
        with self.assertRaises(RuntimeError):
            run_cli("Write me a birthday card")


if __name__ == "__main__":
    unittest.main()
