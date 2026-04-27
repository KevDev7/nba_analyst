from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

import duckdb

from apps.cli.main import ROOT, run_cli
from apps.cli.semantic_interpreter import interpret_question_to_semantic_draft
from scripts.load_gold_snapshot import load_database


HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"

SAMPLE_DRAFT = {
    "task": "rank",
    "subject": "players",
    "measure": "points",
    "time_window": {"kind": "last_n_games", "value": 10},
    "limit": 10,
    "sort": "desc",
    "assumptions": [],
}


def call_plan_semantic_draft(draft: dict) -> dict:
    result = subprocess.run(
        [
            "cabal",
            "run",
            "-v0",
            "--builddir=/tmp/nba-analyst-slice36-cabal",
            "ontology-hs",
            "--",
            "plan-semantic-draft-json",
            "--ontology",
            str(ONTOLOGY_PATH),
            "--draft-json",
            json.dumps(draft),
        ],
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    payload_text = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        raise AssertionError(payload_text)
    return json.loads(payload_text)


class SliceThirtySixTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_haskell_plans_semantic_draft_into_current_ontology_ir(self) -> None:
        payload = call_plan_semantic_draft(SAMPLE_DRAFT)

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(shared["limit"], 10)
        self.assertEqual(payload["resolved_query"]["resolved"]["displayName"]["columnName"], "full_name")
        self.assertEqual(payload["execution_plan"]["result_shape"], "ranking")

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_interpreter_returns_semantic_draft(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": SAMPLE_DRAFT})

        draft = interpret_question_to_semantic_draft(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(draft["task"], SAMPLE_DRAFT["task"])
        self.assertEqual(draft["subject"], SAMPLE_DRAFT["subject"])
        self.assertEqual(draft["measure"], SAMPLE_DRAFT["measure"])
        self.assertEqual(draft["time_window"], SAMPLE_DRAFT["time_window"])
        self.assertEqual(draft["limit"], SAMPLE_DRAFT["limit"])

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_runs_draft_to_haskell_to_runtime_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": SAMPLE_DRAFT})
        database_path = load_database()
        with duckdb.connect(str(database_path), read_only=True) as conn:
            expected_name, expected_team, expected_points = conn.execute(
                """
                WITH recent_rows AS (
                  SELECT
                    pg.person_id,
                    p.full_name,
                    t.team_abbreviation,
                    pg.game_date,
                    pg.points,
                    ROW_NUMBER() OVER (
                      PARTITION BY pg.person_id
                      ORDER BY pg.game_date DESC
                    ) AS game_rank
                  FROM player_game pg
                  JOIN player p ON pg.person_id = p.person_id
                  LEFT JOIN team t ON pg.team_id = t.team_id
                )
                SELECT full_name, team_abbreviation, SUM(points) AS metric_value
                FROM recent_rows
                WHERE game_rank <= 10
                GROUP BY person_id, full_name, team_abbreviation
                ORDER BY metric_value DESC, full_name ASC
                LIMIT 1
                """
            ).fetchone()

        output = run_cli("Show me the top 10 players by points over the last 10 games")

        self.assertIn("Top 10 players by total points over the last 10 games", output)
        self.assertIn("Rank | Player | Team | Total Points", output)
        self.assertIn(
            f"1 | {expected_name} | {expected_team} | {int(expected_points)}",
            output,
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_rank_wording_variation_uses_ontology_grounding(self, mock_call_gemini) -> None:
        varied_draft = {
            **SAMPLE_DRAFT,
            "subject": "nba players",
            "limit": 7,
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": varied_draft})

        output = run_cli("What are the top 7 nba players by points these last ten games")

        self.assertIn("Top 7 players by total points over the last 10 games", output)
        self.assertIn("Rank | Player | Team | Total Points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_rank_season_draft_reaches_existing_season_surface(self, mock_call_gemini) -> None:
        season_draft = {
            "task": "rank",
            "subject": "players",
            "measure": "average points",
            "time_window": {"kind": "season", "value": "2025-26"},
            "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
            "limit": 10,
            "sort": "desc",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": season_draft})

        output = run_cli("Show me players by average points in the 2025-26 regular season")

        self.assertIn("Top 10 players by average points in the 2025-26 regular season", output)
        self.assertIn("Rank | Player | Average Points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_trend_draft_runs_to_time_series_answer(self, mock_call_gemini) -> None:
        trend_draft = {
            "task": "trend",
            "subject": "teams",
            "measure": "average points",
            "dimensions": ["team"],
            "filters": [],
            "time_window": {"kind": "past_year", "value": None},
            "grain": "month",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": trend_draft})

        output = run_cli("What are the monthly average points by team over the past year?")

        self.assertIn("Monthly average points by team over the past year are shown below.", output)
        self.assertIn("Month | Team | Average Points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_weekly_trend_uses_calendar_week_bucket(self, mock_call_gemini) -> None:
        trend_draft = {
            "task": "trend",
            "subject": "teams",
            "measure": "average points",
            "dimensions": ["team"],
            "filters": [],
            "time_window": {"kind": "past_year", "value": None},
            "grain": "week",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": trend_draft})

        output = run_cli("Show weekly average points by team over the past year")

        self.assertIn("Weekly average points by team over the past year are shown below.", output)
        self.assertIn("Week | Team | Average Points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_compare_resolves_entities_and_runs_multi_step_plan(self, mock_call_gemini) -> None:
        compare_draft = {
            "task": "compare",
            "subject": "players",
            "measure": "points",
            "time_window": {"kind": "last_n_games", "value": 10},
            "entities": ["Brunson", "Tatum"],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": compare_draft})

        output = run_cli("Compare Brunson and Tatum scoring over the last 10 games")

        self.assertIn("led in total points over the last 10 games", output)
        self.assertIn("Comparison", output)
        self.assertIn("Jalen Brunson", output)
        self.assertIn("Jayson Tatum", output)


if __name__ == "__main__":
    unittest.main()
