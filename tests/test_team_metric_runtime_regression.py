# Purpose:
# Prove newly exposed team-grain metrics run through planner, runtime, and answer formatting.
#
# Uses:
# - mocked semantic drafts for deterministic CLI coverage
# - Haskell semantic planner
# - Python runtime over the DuckDB snapshot
#
# Produces:
# - regression coverage for TeamGame and TeamSeason metric expansion
#
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import duckdb

from apps.assistant.pipeline import call_haskell_planner_for_semantic_draft
from apps.assistant.semantic.interpreter import interpret_question_to_semantic_draft
from apps.cli.main import run_cli
from runtime.AnalysisRuntime.models import ExecutionPlan
from runtime.AnalysisRuntime.runner import execute_plan
from runtime.AnswerSynthesis.format_response import format_response
from runtime.AnswerSynthesis.package_results import package_results
from runtime.AnswerSynthesis.synthesize import synthesize_answer
from scripts.load_gold_snapshot import load_database


def semantic_response(draft: dict[str, object]) -> str:
    return json.dumps({"status": "ok", "draft": draft})


def base_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "aggregate",
        "subject": "teams",
        "measure": "average assists",
        "measures": ["average assists"],
        "dimensions": ["team"],
        "filters": [],
        "time_window": {"kind": "last_n_games", "value": 10},
        "grain": None,
        "order": [],
        "limit": None,
        "sort": None,
        "entities": [],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


def run_draft(draft: dict[str, object]):
    planner_output = call_haskell_planner_for_semantic_draft(draft)
    if hasattr(ExecutionPlan, "model_validate"):
        execution_plan = ExecutionPlan.model_validate(planner_output["execution_plan"])
    else:
        execution_plan = ExecutionPlan.parse_obj(planner_output["execution_plan"])
    runtime_result = execute_plan(execution_plan)
    formatted = format_response(synthesize_answer(package_results(runtime_result)))
    return planner_output, runtime_result, formatted


class TeamMetricRuntimeRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database_path = load_database()
        cls.conn = duckdb.connect(str(database_path), read_only=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.conn.close()

    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_team_game_average_assists_and_rebounds_cli_matches_snapshot_truth(self) -> None:
        draft = base_draft(
            measure="average assists",
            measures=["average assists", "average rebounds"],
            dimensions=["team"],
        )
        expected_name, expected_games, expected_start, expected_end, expected_assists, expected_rebounds = (
            self.conn.execute(
                """
                WITH recent_rows AS (
                  SELECT
                    tg.team_id,
                    t.team_name,
                    tg.game_date,
                    tg.assists,
                    tg.total_rebounds,
                    ROW_NUMBER() OVER (
                      PARTITION BY tg.team_id
                      ORDER BY tg.game_date DESC
                    ) AS game_rank
                  FROM team_game tg
                  JOIN team t ON tg.team_id = t.team_id
                )
                SELECT
                  team_name,
                  COUNT(*) AS games_played,
                  MIN(game_date) AS date_start,
                  MAX(game_date) AS date_end,
                  ROUND(AVG(assists), 1) AS average_assists,
                  ROUND(AVG(total_rebounds), 1) AS average_rebounds
                FROM recent_rows
                WHERE game_rank <= 10
                GROUP BY team_id, team_name
                ORDER BY team_name ASC
                LIMIT 1
                """
            ).fetchone()
        )

        with patch("apps.assistant.semantic.interpreter._call_gemini") as mock_call_gemini:
            mock_call_gemini.return_value = semantic_response(draft)
            output = run_cli("Calculate average assists and rebounds by team over the last 10 games")

        self.assertIn(
            "Interpreted as: Average assists and average rebounds by team over the last 10 games.",
            output,
        )
        self.assertIn("Team | Games Played | Date Range | Average Assists | Average Rebounds", output)
        self.assertIn(
            f"{expected_name} | {expected_games} | {expected_start} to {expected_end} | "
            f"{expected_assists:.1f} | {expected_rebounds:.1f}",
            output,
        )

    def test_team_game_rebounds_ranking_runtime_matches_snapshot_truth(self) -> None:
        draft = base_draft(
            task="rank",
            measure="rebounds",
            measures=["rebounds"],
            dimensions=[],
            limit=5,
            sort="desc",
        )
        expected = [
            (index + 1, row[0], row[1], float(row[2]))
            for index, row in enumerate(
                self.conn.execute(
                    """
                    WITH recent_rows AS (
                      SELECT
                        tg.team_id,
                        t.team_name,
                        t.team_abbreviation,
                        tg.game_date,
                        tg.total_rebounds,
                        ROW_NUMBER() OVER (
                          PARTITION BY tg.team_id
                          ORDER BY tg.game_date DESC
                        ) AS game_rank
                      FROM team_game tg
                      JOIN team t ON tg.team_id = t.team_id
                    )
                    SELECT team_name, team_abbreviation, SUM(total_rebounds) AS total_rebounds
                    FROM recent_rows
                    WHERE game_rank <= 10
                    GROUP BY team_id, team_name, team_abbreviation
                    ORDER BY total_rebounds DESC, team_name ASC
                    LIMIT 5
                    """
                ).fetchall()
            )
        ]

        planner_output, runtime_result, formatted = run_draft(draft)

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["metrics"],
            ["total_rebounds"],
        )
        self.assertEqual(
            [(row.rank, row.entity_name, row.context_value, row.metric_value) for row in runtime_result.rows],
            expected,
        )
        self.assertIn("Rank | Team | Abbrev | Games Played | Date Range | Rebounds", formatted)
        self.assertIn(
            f"1 | {expected[0][1]} | {expected[0][2]} | 10 |",
            formatted,
        )

    def test_team_season_assists_ranking_runtime_matches_snapshot_truth(self) -> None:
        draft = base_draft(
            task="rank",
            measure="assists",
            measures=["assists"],
            dimensions=[],
            filters=[{"field": "season type", "op": "=", "value": "regular season"}],
            time_window={"kind": "season", "value": "2025-26"},
            limit=5,
            sort="desc",
        )
        expected = [
            (index + 1, row[0], row[1], float(row[2]))
            for index, row in enumerate(
                self.conn.execute(
                    """
                    SELECT t.team_name, t.team_abbreviation, ts.assists_total
                    FROM team_season ts
                    JOIN team t ON ts.team_id = t.team_id
                    WHERE ts.season_year = '2025-26'
                      AND ts.season_type = 'regular_season'
                    ORDER BY ts.assists_total DESC, t.team_name ASC
                    LIMIT 5
                    """
                ).fetchall()
            )
        ]

        planner_output, runtime_result, formatted = run_draft(draft)

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"],
            "TeamSeason",
        )
        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["metrics"],
            ["assists_total"],
        )
        self.assertEqual(
            [(row.rank, row.entity_name, row.context_value, row.metric_value) for row in runtime_result.rows],
            expected,
        )
        self.assertIn("Rank | Team | Abbrev | Season | Season Type | Games Played | Assists", formatted)
        self.assertIn(f"1 | {expected[0][1]} | {expected[0][2]} | 2025-26 | Regular Season |", formatted)

    def test_team_season_multi_metric_object_cli_renders_expanded_metrics(self) -> None:
        draft = base_draft(
            task="object",
            measure="points",
            measures=["points", "assists", "rebounds"],
            dimensions=[],
            filters=[{"field": "season type", "op": "=", "value": "regular season"}],
            time_window={"kind": "season", "value": "2025-26"},
            limit=3,
            sort="desc",
        )

        with patch("apps.assistant.semantic.interpreter._call_gemini") as mock_call_gemini:
            mock_call_gemini.return_value = semantic_response(draft)
            output = run_cli("Show teams and their points, assists, and rebounds in the 2025-26 regular season")

        self.assertIn(
            "Interpreted as: Teams and their total points, assists, and rebounds in the 2025-26 regular season.",
            output,
        )
        self.assertIn(
            "Team | Abbrev | Season | Season Type | Games Played | Total Points | Assists | Rebounds",
            output,
        )

    def test_find_games_can_display_new_team_game_boxscore_measures(self) -> None:
        draft = base_draft(
            task="find",
            subject="games",
            measure=None,
            measures=[],
            dimensions=["game date", "score", "assists", "rebounds"],
            filters=[
                {"field": "team", "op": "=", "value": "Lakers"},
                {"field": "points", "op": ">", "value": 120},
            ],
            time_window={"kind": "all", "value": None},
            order=[{"by": "date", "direction": "desc"}],
            limit=5,
            sort=None,
            entities=["Lakers"],
        )
        expected_date, expected_score, expected_assists, expected_rebounds = self.conn.execute(
            """
            SELECT g.game_date, tg.score, tg.assists, tg.total_rebounds
            FROM team_game tg
            JOIN game g ON tg.game_id = g.game_id
            JOIN team t ON tg.team_id = t.team_id
            WHERE t.team_name = 'Lakers'
              AND tg.score > 120
            ORDER BY g.game_date DESC
            LIMIT 1
            """
        ).fetchone()

        with patch("apps.assistant.semantic.interpreter._call_gemini") as mock_call_gemini:
            mock_call_gemini.return_value = semantic_response(draft)
            output = run_cli("Find Lakers games over 120 points and show date, score, assists, rebounds")

        self.assertIn("Matching games are shown below.", output)
        self.assertIn("Game Date | Score | Assists | Total Rebounds | Team Name", output)
        self.assertIn(
            f"{expected_date} | {expected_score} | {expected_assists} | {expected_rebounds} | Lakers",
            output,
        )


if __name__ == "__main__":
    unittest.main()
