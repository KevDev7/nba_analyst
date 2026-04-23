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
    def test_interpreter_returns_draft_without_legacy_haskell_question_parser(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": SAMPLE_DRAFT})

        draft = interpret_question_to_semantic_draft(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(draft, SAMPLE_DRAFT)

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


if __name__ == "__main__":
    unittest.main()
