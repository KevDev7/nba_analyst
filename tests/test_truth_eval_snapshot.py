from __future__ import annotations

import unittest

import duckdb

from apps.cli.main import plan_question
from runtime.AnalysisRuntime.models import ExecutionPlan
from runtime.AnalysisRuntime.runner import execute_plan
from runtime.AnswerSynthesis.format_response import format_response
from runtime.AnswerSynthesis.package_results import package_results
from runtime.AnswerSynthesis.synthesize import synthesize_answer
from scripts.load_gold_snapshot import load_database


class TruthEvalSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database_path = load_database()
        cls.conn = duckdb.connect(str(database_path), read_only=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.conn.close()

    def _run_question(self, question: str):
        interpreted_query, planner_output = plan_question(question)
        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(planner_output["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(planner_output["execution_plan"])
        runtime_result = execute_plan(execution_plan)
        formatted = format_response(synthesize_answer(package_results(runtime_result)))
        return interpreted_query, planner_output, runtime_result, formatted

    def _fetchall(self, sql: str):
        return self.conn.execute(sql).fetchall()

    def _metric_value(self, value) -> float:
        return round(float(value), 1)

    def _ranking_rows(self, runtime_result, count: int):
        return [
            (
                row.rank,
                row.entity_name,
                row.context_value,
                self._metric_value(row.metric_value),
            )
            for row in runtime_result.rows[:count]
        ]

    def _object_rows(self, runtime_result, count: int):
        return [
            (
                row.entity_id,
                row.entity_name,
                row.context_value,
                self._metric_value(row.metric_value),
            )
            for row in runtime_result.object_rows[:count]
        ]

    def _time_series_rows(self, runtime_result, count: int):
        return [
            (
                row.time_bucket,
                row.series_name,
                self._metric_value(row.metric_value),
            )
            for row in runtime_result.time_series_rows[:count]
        ]

    def _display_metric(self, value) -> str:
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.1f}"

    def _display_number(self, value) -> str:
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.1f}"

    def _display_season_type(self, value: str) -> str:
        return value.replace("_", " ").title()

    def _time_cells(self, runtime_result) -> list[str]:
        cells: list[str] = []
        if runtime_result.season_label:
            cells.append(runtime_result.season_label)
        if runtime_result.season_type:
            cells.append(self._display_season_type(runtime_result.season_type))
        return cells

    def _display_metadata_value(self, key: str, value) -> str:
        if key == "games_played":
            return self._display_number(value)
        if key == "minutes":
            return f"{float(value):.1f}"
        return str(value)

    def _metadata_cells(self, runtime_result, row) -> list[str]:
        cells: list[str] = []
        for metadata in runtime_result.display_metadata:
            display_values = getattr(row, "display_values", {})
            value = display_values.get(metadata.column_key)
            if value is None:
                value = getattr(row, metadata.column_key, None)
            if value is not None:
                cells.append(self._display_metadata_value(metadata.column_key, value))
        return cells

    def _rendered_ranking_row(self, runtime_result, row) -> str:
        cells = [str(row.rank), row.entity_name]
        if row.context_value:
            cells.append(row.context_value)
        cells.extend(self._time_cells(runtime_result))
        cells.extend(self._metadata_cells(runtime_result, row))
        cells.append(self._display_metric(row.metric_value))
        return " | ".join(cells)

    def _rendered_object_row(self, runtime_result, row) -> str:
        cells = [row.entity_name]
        if row.context_value:
            cells.append(row.context_value)
        cells.extend(self._time_cells(runtime_result))
        cells.extend(self._metadata_cells(runtime_result, row))
        cells.append(self._display_metric(row.metric_value))
        return " | ".join(cells)

    def test_top_players_by_points_recent_matches_snapshot_truth(self) -> None:
        question = "Show me the top 10 players by points over the last 10 games"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected = [
            (index + 1, row[0], row[1], self._metric_value(row[2]))
            for index, row in enumerate(
                self._fetchall(
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
                    LIMIT 10
                    """
                )
            )
        ]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"], "PlayerGame"
        )
        self.assertEqual(self._ranking_rows(runtime_result, 10), expected)
        self.assertIn(self._rendered_ranking_row(runtime_result, runtime_result.rows[0]), formatted)

    def test_team_average_points_recent_matches_snapshot_truth(self) -> None:
        question = "Show me teams by average points over the last 10 games"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected = [
            (index + 1, row[0], row[1], self._metric_value(row[2]))
            for index, row in enumerate(
                self._fetchall(
                    """
                    WITH recent_rows AS (
                      SELECT
                        tg.team_id,
                        t.team_name,
                        t.team_abbreviation,
                        tg.game_date,
                        tg.score,
                        ROW_NUMBER() OVER (
                          PARTITION BY tg.team_id
                          ORDER BY tg.game_date DESC
                        ) AS game_rank
                      FROM team_game tg
                      JOIN team t ON tg.team_id = t.team_id
                    )
                    SELECT team_name, team_abbreviation, AVG(score) AS metric_value
                    FROM recent_rows
                    WHERE game_rank <= 10
                    GROUP BY team_id, team_name, team_abbreviation
                    ORDER BY metric_value DESC, team_name ASC
                    LIMIT 5
                    """
                )
            )
        ]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"], "TeamGame"
        )
        self.assertEqual(self._ranking_rows(runtime_result, 5), expected)
        self.assertIn(self._rendered_ranking_row(runtime_result, runtime_result.rows[0]), formatted)

    def test_player_object_totals_recent_matches_snapshot_truth(self) -> None:
        question = "Show me players and their total points over the last 10 games"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected = [
            (row[0], row[1], row[2], self._metric_value(row[3]))
            for row in self._fetchall(
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
                SELECT person_id, full_name, team_abbreviation, SUM(points) AS metric_value
                FROM recent_rows
                WHERE game_rank <= 10
                GROUP BY person_id, full_name, team_abbreviation
                ORDER BY metric_value DESC, full_name ASC
                LIMIT 5
                """
            )
        ]

        self.assertEqual(planner_output["query"]["kind"], "object_query")
        self.assertEqual(self._object_rows(runtime_result, 5), expected)
        self.assertIn(self._rendered_object_row(runtime_result, runtime_result.object_rows[0]), formatted)

    def test_player_average_points_season_matches_snapshot_truth(self) -> None:
        question = "Show me players by average points in the 2025-26 regular season"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected = [
            (index + 1, row[0], None, self._metric_value(row[1]))
            for index, row in enumerate(
                self._fetchall(
                    """
                    SELECT p.full_name, ps.points_per_game AS average_points
                    FROM player_season ps
                    JOIN player p ON ps.person_id = p.person_id
                    WHERE ps.season_year = '2025-26'
                      AND ps.season_type = 'regular_season'
                    ORDER BY ps.points_per_game DESC, p.full_name ASC
                    LIMIT 5
                    """
                )
            )
        ]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"], "PlayerSeason"
        )
        self.assertEqual(self._ranking_rows(runtime_result, 5), expected)
        self.assertIn(self._rendered_ranking_row(runtime_result, runtime_result.rows[0]), formatted)

    def test_team_wins_season_matches_snapshot_truth(self) -> None:
        question = "Show me teams by wins in the 2025-26 regular season"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected = [
            (index + 1, row[0], row[1], self._metric_value(row[2]))
            for index, row in enumerate(
                self._fetchall(
                    """
                    SELECT t.team_name, t.team_abbreviation, ts.wins
                    FROM team_season ts
                    JOIN team t ON ts.team_id = t.team_id
                    WHERE ts.season_year = '2025-26'
                      AND ts.season_type = 'regular_season'
                    ORDER BY ts.wins DESC, t.team_name ASC
                    LIMIT 5
                    """
                )
            )
        ]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"], "TeamSeason"
        )
        self.assertEqual(self._ranking_rows(runtime_result, 5), expected)
        self.assertIn(self._rendered_ranking_row(runtime_result, runtime_result.rows[0]), formatted)

    def test_lakers_recent_average_points_matches_snapshot_truth(self) -> None:
        question = "Show me players by average points for the Lakers over the last 10 games"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected = [
            (index + 1, row[0], row[1], self._metric_value(row[2]))
            for index, row in enumerate(
                self._fetchall(
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
                      JOIN team t ON pg.team_id = t.team_id
                      WHERE t.team_name = 'Lakers'
                    )
                    SELECT full_name, team_abbreviation, AVG(points) AS metric_value
                    FROM recent_rows
                    WHERE game_rank <= 10
                    GROUP BY person_id, full_name, team_abbreviation
                    ORDER BY metric_value DESC, full_name ASC
                    LIMIT 5
                    """
                )
            )
        ]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"], "PlayerGame"
        )
        self.assertEqual(self._ranking_rows(runtime_result, 5), expected)
        self.assertIn(self._rendered_ranking_row(runtime_result, runtime_result.rows[0]), formatted)

    def test_knicks_recent_object_totals_matches_snapshot_truth(self) -> None:
        question = "Show me the top 5 players and their total points for the Knicks over the last 10 games"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected = [
            (row[0], row[1], row[2], self._metric_value(row[3]))
            for row in self._fetchall(
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
                  JOIN team t ON pg.team_id = t.team_id
                  WHERE t.team_name = 'Knicks'
                )
                SELECT person_id, full_name, team_abbreviation, SUM(points) AS metric_value
                FROM recent_rows
                WHERE game_rank <= 10
                GROUP BY person_id, full_name, team_abbreviation
                ORDER BY metric_value DESC, full_name ASC
                LIMIT 5
                """
            )
        ]

        self.assertEqual(planner_output["query"]["kind"], "object_query")
        self.assertEqual(self._object_rows(runtime_result, 5), expected)
        self.assertIn(self._rendered_object_row(runtime_result, runtime_result.object_rows[0]), formatted)

    def test_lakers_season_average_points_matches_snapshot_truth(self) -> None:
        question = "Show me players by average points for the Lakers in the 2025-26 regular season"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected = [
            (index + 1, row[0], row[1], self._metric_value(row[2]))
            for index, row in enumerate(
                self._fetchall(
                    """
                    SELECT p.full_name, t.team_abbreviation, pst.points_per_game AS average_points
                    FROM player_season_team pst
                    JOIN player p ON pst.person_id = p.person_id
                    JOIN team t ON pst.team_id = t.team_id
                    WHERE pst.season_year = '2025-26'
                      AND pst.season_type = 'regular_season'
                      AND t.team_name = 'Lakers'
                    ORDER BY pst.points_per_game DESC, p.full_name ASC
                    LIMIT 5
                    """
                )
            )
        ]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"],
            "PlayerSeasonTeam",
        )
        self.assertEqual(self._ranking_rows(runtime_result, 5), expected)
        self.assertIn(self._rendered_ranking_row(runtime_result, runtime_result.rows[0]), formatted)

    def test_brunson_tatum_comparison_matches_snapshot_truth(self) -> None:
        question = "Compare Brunson and Tatum scoring over the last 10 games"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected_rows = [
            (row[0], row[1], str(row[2]), self._metric_value(row[3]))
            for row in self._fetchall(
                """
                WITH recent_rows AS (
                  SELECT
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
                  WHERE p.full_name IN ('Jalen Brunson', 'Jayson Tatum')
                )
                SELECT full_name, team_abbreviation, game_date, points
                FROM recent_rows
                WHERE game_rank <= 10
                ORDER BY full_name ASC, game_date DESC
                """
            )
        ]
        brunson_total, brunson_games = self._fetchall(
            """
            WITH recent_rows AS (
              SELECT pg.points
              FROM player_game pg
              JOIN player p ON pg.person_id = p.person_id
              WHERE p.full_name = 'Jalen Brunson'
              ORDER BY pg.game_date DESC
              LIMIT 10
            )
            SELECT SUM(points), COUNT(*) FROM recent_rows
            """
        )[0]
        tatum_total, tatum_games = self._fetchall(
            """
            WITH recent_rows AS (
              SELECT pg.points
              FROM player_game pg
              JOIN player p ON pg.person_id = p.person_id
              WHERE p.full_name = 'Jayson Tatum'
              ORDER BY pg.game_date DESC
              LIMIT 10
            )
            SELECT SUM(points), COUNT(*) FROM recent_rows
            """
        )[0]

        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        self.assertIsNotNone(runtime_result.comparison)
        self.assertEqual(runtime_result.comparison.leader, "Jalen Brunson")
        self.assertEqual(self._metric_value(runtime_result.comparison.metric_differential), 54.0)
        self.assertEqual(self._metric_value(runtime_result.comparison.entity_a.metric_value), self._metric_value(tatum_total))
        self.assertEqual(self._metric_value(runtime_result.comparison.entity_b.metric_value), self._metric_value(brunson_total))
        self.assertEqual(runtime_result.comparison.entity_a.games_count, tatum_games)
        self.assertEqual(runtime_result.comparison.entity_b.games_count, brunson_games)
        actual_rows = [
            (
                row.entity_name,
                row.context_value,
                row.game_date,
                self._metric_value(row.metric_value),
            )
            for row in runtime_result.comparison.per_game_rows
        ]
        self.assertEqual(sorted(actual_rows), sorted(expected_rows))
        self.assertIn("Jalen Brunson led in total points over the last 10 games by 54 total points.", formatted)

    def test_monthly_team_trend_matches_snapshot_truth(self) -> None:
        question = "What are the monthly average points by team over the past year?"
        _interpreted_query, planner_output, runtime_result, formatted = self._run_question(question)

        expected = [
            (row[0], row[1], self._metric_value(row[2]))
            for row in self._fetchall(
                """
                WITH monthly AS (
                  SELECT
                    STRFTIME(tg.game_date, '%Y-%m') AS time_bucket,
                    t.team_name,
                    AVG(tg.score) AS metric_value
                  FROM team_game tg
                  JOIN team t ON tg.team_id = t.team_id
                  WHERE tg.game_date >= (
                    SELECT MAX(game_date) - INTERVAL '1 year'
                    FROM team_game
                  )
                  GROUP BY 1, 2
                )
                SELECT time_bucket, team_name, metric_value
                FROM monthly
                ORDER BY time_bucket ASC, team_name ASC
                LIMIT 12
                """
            )
        ]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"], "TeamGame"
        )
        self.assertEqual(self._time_series_rows(runtime_result, 12), expected)
        self.assertIn(
            f"{expected[0][0]} | {expected[0][1]} | {self._display_metric(expected[0][2])}",
            formatted,
        )


if __name__ == "__main__":
    unittest.main()
