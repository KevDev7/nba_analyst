from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import duckdb

from apps.cli.main import call_haskell_planner_for_semantic_draft, run_cli
from apps.cli.semantic_interpreter import interpret_question_to_semantic_draft
from scripts.load_gold_snapshot import load_database


def aggregate_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "aggregate",
        "subject": "teams",
        "measure": "average points",
        "measures": ["average points"],
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


class AggregateQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_haskell_grounds_team_average_points_aggregate(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(aggregate_draft())

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        execution_plan = payload["execution_plan"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["orders"], [])
        self.assertEqual(resolved["metricResultShape"], "aggregate")
        self.assertEqual(execution_plan["result_shape"], "aggregate")
        self.assertEqual(execution_plan["plan_type"], "single_sql")

    def test_haskell_grounds_multi_metric_player_aggregate(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            aggregate_draft(
                subject="players",
                measure="average points",
                measures=["average points", "average assists", "average rebounds"],
                dimensions=["player"],
            )
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_points", "average_assists", "average_rebounds"])
        self.assertEqual(
            execution_plan["display_metrics"],
            [
                {"column_key": "metric_value", "label": "average_points", "metric": "average_points"},
                {"column_key": "metric_2", "label": "average_assists", "metric": "average_assists"},
                {"column_key": "metric_3", "label": "average_rebounds", "metric": "average_rebounds"},
            ],
        )
        self.assertIn("ROUND(AVG(__metric_2_source), 1) AS metric_2", sql)
        self.assertIn("ROUND(AVG(__metric_3_source), 1) AS metric_3", sql)

    def test_haskell_grounds_non_identity_team_dimension_from_ontology(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            aggregate_draft(dimensions=["conference"])
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["conference"])
        self.assertEqual(payload["execution_plan"]["result_shape"], "aggregate")

    def test_haskell_grounds_multi_dimensional_aggregate_grouping(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            aggregate_draft(dimensions=["team", "season type"])
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["dimensions"], ["team_name", "season_type"])
        self.assertEqual(
            execution_plan["grouping_columns"],
            [
                {"column_key": "group_1", "label": "team_name"},
                {"column_key": "group_2", "label": "season_type"},
            ],
        )
        self.assertEqual(
            [grouping["groupingLabel"] for grouping in resolved["groupingDimensions"]],
            ["team_name", "season_type"],
        )
        self.assertIn("g1.team_name AS group_1", sql)
        self.assertIn("f.season_type AS group_2", sql)
        self.assertIn("GROUP BY group_1, group_2", sql)
        self.assertIn("ORDER BY group_1 ASC, group_2 ASC", sql)

    def test_haskell_grounds_season_aggregate_when_year_is_in_filters(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            aggregate_draft(
                measure="wins",
                measures=["wins"],
                time_window={"kind": "season", "value": None},
                filters=[
                    {"field": "season", "op": "=", "value": "2025-26"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
            )
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(shared["coreFactObject"], "TeamSeason")
        self.assertEqual(shared["metrics"], ["wins"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(resolved["windowGames"], 0)
        self.assertEqual(resolved["seasonLabel"], "2025-26")
        self.assertIn("WITH season_rows AS", sql)
        self.assertNotIn("game_rank <=", sql)

    def test_haskell_grounds_player_average_minutes_aggregate(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            aggregate_draft(
                subject="players",
                measure="average minutes",
                measures=["average minutes"],
                dimensions=["player"],
                filters=[{"field": "team", "op": "=", "value": "Knicks"}],
                entities=["Knicks"],
            )
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        execution_plan = payload["execution_plan"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_minutes"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(
            shared["rowPredicate"],
            {
                "kind": "leaf",
                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                "operator": "equals",
                "value": {"kind": "scalar", "value": "Knicks"},
            },
        )
        self.assertEqual(execution_plan["metric"], "average_minutes")
        self.assertIn("AVG(metric_source)", execution_plan["steps"][0]["sql"])

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_runs_aggregate_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": aggregate_draft()})
        database_path = load_database()
        with duckdb.connect(str(database_path), read_only=True) as conn:
            expected_name, expected_games, expected_date_start, expected_date_end, expected_average = conn.execute(
                """
                WITH recent_rows AS (
                  SELECT
                    tg.team_id,
                    t.team_name,
                    tg.game_date,
                    tg.score,
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
                  ROUND(AVG(score), 1) AS metric_value
                FROM recent_rows
                WHERE game_rank <= 10
                GROUP BY team_id, team_name
                ORDER BY team_name ASC
                LIMIT 1
                """
            ).fetchone()

        output = run_cli("Calculate average points by team over the last 10 games")

        self.assertIn("Average points by team over the last 10 games are shown below.", output)
        self.assertIn("Team | Games Played | Date Range | Average Points", output)
        self.assertNotIn("Rank |", output)
        self.assertIn(
            f"{expected_name} | {expected_games} | {expected_date_start} to {expected_date_end} | {expected_average:.1f}",
            output,
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_runs_multi_dimensional_aggregate_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "ok", "draft": aggregate_draft(dimensions=["team", "season type"], limit=3)}
        )

        output = run_cli("Calculate average points by team and season type over the last 10 games")

        self.assertIn(
            "Interpreted as: Average points by team and season type over the last 10 games.",
            output,
        )
        self.assertIn(
            "Average points by team and season type over the last 10 games are shown below.",
            output,
        )
        self.assertIn("Team | Season Type | Games Played | Date Range | Average Points", output)
        self.assertNotIn("Rank |", output)


if __name__ == "__main__":
    unittest.main()
