from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.cli.main import call_haskell_planner_for_semantic_draft, run_cli
from apps.cli.semantic_interpreter import interpret_question_to_semantic_draft


def ranking_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "rank",
        "subject": "teams",
        "measure": "average points",
        "measures": ["average points"],
        "dimensions": ["team", "season type"],
        "filters": [],
        "time_window": {"kind": "last_n_games", "value": 10},
        "grain": None,
        "order": [],
        "limit": 5,
        "sort": "desc",
        "entities": [],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


def object_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "object",
        "subject": "players",
        "measure": "points",
        "measures": ["points"],
        "dimensions": ["player", "team"],
        "filters": [],
        "time_window": {"kind": "last_n_games", "value": 10},
        "grain": None,
        "order": [],
        "limit": 5,
        "sort": "desc",
        "entities": [],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


def trend_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "trend",
        "subject": "teams",
        "measure": "average points",
        "measures": ["average points"],
        "dimensions": ["team", "season type"],
        "filters": [],
        "time_window": {"kind": "past_year", "value": None},
        "grain": "month",
        "order": [],
        "limit": None,
        "sort": None,
        "entities": [],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


def compare_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "compare",
        "subject": "players",
        "measure": "average points",
        "measures": ["average points"],
        "dimensions": ["season type"],
        "filters": [],
        "time_window": {"kind": "last_n_games", "value": 10},
        "grain": None,
        "order": [],
        "limit": None,
        "sort": None,
        "entities": ["Jalen Brunson", "Jayson Tatum"],
        "resolved_entities": [
            {"entityId": 1628973, "entityName": "Jalen Brunson"},
            {"entityId": 1628369, "entityName": "Jayson Tatum"},
        ],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


class MultiDimensionalGroupingTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_haskell_grounds_multi_dimensional_ranking(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(ranking_draft())

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["dimensions"], ["team_name", "season_type"])
        self.assertEqual(resolved["metricResultShape"], "ranking")
        self.assertEqual(
            execution_plan["grouping_columns"],
            [
                {"column_key": "group_1", "label": "team_name"},
                {"column_key": "group_2", "label": "season_type"},
            ],
        )
        self.assertIn("g1.team_name AS group_1", sql)
        self.assertIn("f.season_type AS group_2", sql)
        self.assertIn("GROUP BY entity_id, group_1, group_2", sql)
        self.assertIn("ROW_NUMBER() OVER (ORDER BY metric_value DESC", sql)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_runs_multi_dimensional_ranking_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "ok", "draft": ranking_draft()}
        )

        output = run_cli("Rank teams by average points by season type over the last 10 games")

        self.assertIn(
            "Interpreted as: Top 5 team and season type combinations by average points over the last 10 games.",
            output,
        )
        self.assertIn("Rank | Team | Season Type | Abbrev | Games Played | Date Range | Average Points", output)

    def test_object_draft_keeps_one_row_per_object_shape(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(object_draft())

        shared = payload["query"]["spec"]["sharedQuery"]
        execution_plan = payload["execution_plan"]

        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(execution_plan["result_shape"], "object_rows")
        self.assertEqual(execution_plan["grouping_columns"], [])

    def test_haskell_grounds_multi_dimensional_trend(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(trend_draft())

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["dimensions"], ["team_name", "season_type"])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(resolved["trendGroupingDimensions"][0]["groupingLabel"], "team_name")
        self.assertEqual(resolved["trendGroupingDimensions"][1]["groupingLabel"], "season_type")
        self.assertEqual(
            execution_plan["grouping_columns"],
            [
                {"column_key": "group_1", "label": "team_name"},
                {"column_key": "group_2", "label": "season_type"},
            ],
        )
        self.assertIn("g1.team_name AS group_1", sql)
        self.assertIn("f.season_type AS group_2", sql)
        self.assertIn("GROUP BY time_bucket, group_1, group_2", sql)
        self.assertIn("ORDER BY time_bucket ASC, group_1 ASC, group_2 ASC", sql)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_runs_multi_dimensional_trend_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "ok", "draft": trend_draft()}
        )

        output = run_cli("Trend average points by team and season type by month over the past year")

        self.assertIn(
            "Interpreted as: Average points by team and season type by month over the past year.",
            output,
        )
        self.assertIn("Monthly average points by team and season type over the past year are shown below.", output)
        self.assertIn("Month | Team | Season Type | Average Points", output)

    def test_haskell_grounds_multi_dimensional_comparison(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(compare_draft())

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["dimensions"], ["full_name", "season_type"])
        self.assertEqual(resolved["metricResultShape"], "comparison")
        self.assertEqual(
            execution_plan["grouping_columns"],
            [{"column_key": "group_1", "label": "season_type"}],
        )
        self.assertIn("f.season_type AS group_1", sql)
        self.assertIn("ORDER BY entity_id ASC, group_1 ASC, game_date DESC", sql)

    def test_haskell_grounds_time_bucketed_comparison(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            compare_draft(
                dimensions=[],
                time_window={"kind": "past_year", "value": None},
                grain="month",
            )
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(execution_plan["time_grain"], "month")
        self.assertIn("AS time_bucket", sql)
        self.assertIn("ORDER BY entity_id ASC, time_bucket ASC, game_date DESC", sql)

    def test_comparison_deduplicates_time_bucket_dimensions(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            compare_draft(
                dimensions=["game month"],
                time_window={"kind": "past_year", "value": None},
                grain="month",
            )
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        execution_plan = payload["execution_plan"]

        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(execution_plan["grouping_columns"], [])
        self.assertEqual(execution_plan["time_grain"], "month")

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_runs_multi_dimensional_comparison_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "ok", "draft": compare_draft(resolved_entities=[])}
        )

        output = run_cli("Compare Brunson and Tatum by average points by season type over the last 10 games")

        self.assertIn(
            "Interpreted as: Jayson Tatum and Jalen Brunson compared by average points by season type over the last 10 games.",
            output,
        )
        self.assertIn("Average points comparison by season type over the last 10 games is shown below.", output)
        self.assertIn("Player | Team | Season Type | Games | Average Points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_runs_time_bucketed_comparison_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": compare_draft(
                    resolved_entities=[],
                    dimensions=[],
                    time_window={"kind": "past_year", "value": None},
                    grain="month",
                ),
            }
        )

        output = run_cli("Compare Brunson and Tatum by average points by month over the past year")

        self.assertIn(
            "Interpreted as: Jayson Tatum and Jalen Brunson compared by average points by month over the past year.",
            output,
        )
        self.assertIn("Average points comparison by month over the past year is shown below.", output)
        self.assertIn("Month | Player | Team | Games | Average Points", output)
