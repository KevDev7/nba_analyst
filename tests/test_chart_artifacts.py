from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from apps.assistant.chart_artifacts import append_chart_artifacts, append_requested_chart_artifacts
from apps.assistant.pipeline import run_assistant
from runtime.AnalysisRuntime.models import (
    AggregateRow,
    ComparisonBreakdownRow,
    ComparisonEntityStats,
    ComparisonResult,
    ObjectRow,
    PlanDisplayMetric,
    PlanGroupingColumn,
    RankingRow,
    TimeSeriesRow,
)
from runtime.AnswerSynthesis.artifacts import build_artifacts
from runtime.AnswerSynthesis.format_response import DISPLAY_ROW_LIMIT
from runtime.AnswerSynthesis.response_models import FinalAnswer


def base_answer(**overrides: object) -> FinalAnswer:
    values = {
        "summary": "Monthly average points by team are shown below.",
        "interpretation": "Average points by team by month.",
        "query_kind": "metric_query",
        "result_shape": "time_series",
        "entity_label_singular": "Team",
        "entity_label_plural": "Teams",
        "context_label": "",
        "metric": "average_points",
        "window_games": 0,
        "time_grain": "month",
        "limit": 0,
        "rows": [],
        "time_series_rows": [
            TimeSeriesRow(
                time_bucket="2026-01",
                group_values={"team_name": "Lakers"},
                display_values={"metric_1": 118.4},
                metric_value=118.4,
            ),
            TimeSeriesRow(
                time_bucket="2026-02",
                group_values={"team_name": "Lakers"},
                display_values={"metric_1": 120.1},
                metric_value=120.1,
            ),
        ],
        "grouping_columns": [PlanGroupingColumn(column_key="team_name", label="team_name")],
        "display_metrics": [
            PlanDisplayMetric(column_key="metric_1", metric="average_points", label="Average Points"),
        ],
    }
    values.update(overrides)
    return FinalAnswer(**values)


class ChartArtifactBridgeTests(unittest.TestCase):
    def _chart_rows(self, chart: dict[str, object]) -> list[dict[str, object]]:
        datasets = chart["spec"]["datasets"]
        return next(iter(datasets.values()))

    def test_legacy_chart_bridge_name_still_points_to_current_bridge(self) -> None:
        self.assertIs(append_requested_chart_artifacts, append_chart_artifacts)

    def test_chart_intent_adds_vega_lite_chart_before_time_series_table(self) -> None:
        answer = base_answer()

        artifacts = append_chart_artifacts(
            "Show monthly average points by team as a chart",
            answer,
            build_artifacts(answer),
        )

        self.assertEqual(
            [artifact["kind"] for artifact in artifacts],
            ["text", "text", "chart", "table"],
        )
        chart = artifacts[2]
        self.assertEqual(chart["renderer"], "vega_lite")
        self.assertEqual(chart["metadata"]["source_table_id"], "primary_answer_table")
        self.assertEqual(chart["metadata"]["x"], "time_bucket")
        self.assertEqual(chart["metadata"]["y"], "metric_1")
        self.assertEqual(chart["metadata"]["series"], "team_name")
        self.assertEqual(chart["metadata"]["chart_family"], "line")
        self.assertEqual(chart["metadata"]["source_result_shape"], "time_series")
        self.assertEqual(chart["metadata"]["source_time_grain"], "month")
        self.assertEqual(chart["metadata"]["x_type"], "date")
        self.assertEqual(chart["metadata"]["y_type"], "number")
        self.assertEqual(chart["metadata"]["series_count"], 1)
        self.assertEqual(chart["metadata"]["category_count"], 0)
        self.assertEqual(chart["spec"]["width"], "container")
        self.assertEqual(chart["spec"]["height"], 360)
        self.assertEqual(
            chart["spec"]["autosize"],
            {"contains": "padding", "resize": True, "type": "fit-x"},
        )
        self.assertEqual(chart["spec"]["encoding"]["x"]["type"], "temporal")
        self.assertEqual(chart["spec"]["encoding"]["y"]["type"], "quantitative")
        self.assertEqual(chart["spec"]["encoding"]["color"]["field"], "team_name")

    def test_chart_uses_full_time_series_rows_while_table_remains_display_limited(self) -> None:
        full_rows = [
            TimeSeriesRow(
                time_bucket=f"2026-{month:02d}",
                group_values={"team_name": f"Team {team}"},
                display_values={"metric_1": float(month * 10 + team)},
                metric_value=float(month * 10 + team),
            )
            for month in range(1, 7)
            for team in range(1, 11)
        ]
        answer = base_answer(time_series_rows=full_rows)

        artifacts = append_chart_artifacts(
            "Show monthly average points by team as a chart",
            answer,
            build_artifacts(answer),
        )

        chart = artifacts[2]
        table = artifacts[3]
        self.assertEqual(len(full_rows), DISPLAY_ROW_LIMIT + 10)
        self.assertEqual(table["row_count"], len(full_rows))
        self.assertEqual(table["displayed_row_count"], DISPLAY_ROW_LIMIT)
        self.assertEqual(len(table["rows"]), DISPLAY_ROW_LIMIT)
        self.assertEqual(chart["metadata"]["row_count"], len(full_rows))
        self.assertEqual(len(self._chart_rows(chart)), len(full_rows))
        self.assertEqual(self._chart_rows(chart)[-1]["time_bucket"], "2026-06-01T00:00:00")

    def test_time_series_question_without_chart_words_adds_chart(self) -> None:
        answer = base_answer()
        artifacts = build_artifacts(answer)

        updated = append_chart_artifacts(
            "Show monthly average points by team",
            answer,
            artifacts,
        )

        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "text", "chart", "table"])
        self.assertEqual(updated[2]["metadata"]["operation_kind"], "line_chart")
        self.assertEqual(updated[2]["metadata"]["x"], "time_bucket")
        self.assertEqual(updated[2]["metadata"]["y"], "metric_1")

    def test_chart_intent_adds_horizontal_bar_for_ranking_answer(self) -> None:
        answer = base_answer(
            result_shape="ranking",
            time_series_rows=[],
            grouping_columns=[],
            display_metrics=[],
            rows=[
                RankingRow(rank=1, entity_name="Jalen Brunson", context_value="NYK", metric_value=312),
                RankingRow(rank=2, entity_name="Jayson Tatum", context_value="BOS", metric_value=298),
            ],
        )

        artifacts = append_chart_artifacts(
            "Show the ranking as a chart",
            answer,
            build_artifacts(answer),
        )

        self.assertEqual(
            [artifact["kind"] for artifact in artifacts],
            ["text", "text", "chart", "table"],
        )
        chart = artifacts[2]
        self.assertEqual(chart["metadata"]["operation_kind"], "bar_chart")
        self.assertEqual(chart["metadata"]["chart_family"], "bar")
        self.assertEqual(chart["metadata"]["orientation"], "horizontal")
        self.assertEqual(chart["metadata"]["x"], "metric_value")
        self.assertEqual(chart["metadata"]["y"], "entity_name")
        self.assertEqual(chart["metadata"]["source_result_shape"], "ranking")
        self.assertEqual(chart["metadata"]["category_count"], 2)
        self.assertEqual(chart["spec"]["encoding"]["x"]["type"], "quantitative")
        self.assertEqual(chart["spec"]["encoding"]["y"]["field"], "entity_name")
        self.assertEqual(chart["spec"]["encoding"]["y"]["sort"]["field"], "rank")
        self.assertEqual(chart["spec"]["encoding"]["y"]["sort"]["order"], "ascending")

    def test_ranking_question_without_chart_words_adds_chart(self) -> None:
        answer = base_answer(
            result_shape="ranking",
            time_series_rows=[],
            grouping_columns=[],
            display_metrics=[],
            rows=[
                RankingRow(rank=1, entity_name="Jalen Brunson", context_value="NYK", metric_value=312),
            ],
        )
        artifacts = build_artifacts(answer)

        updated = append_chart_artifacts(
            "Show the top scorers",
            answer,
            artifacts,
        )

        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "text", "chart", "table"])
        self.assertEqual(updated[2]["metadata"]["operation_kind"], "bar_chart")
        self.assertEqual(updated[2]["metadata"]["orientation"], "horizontal")
        self.assertEqual(updated[2]["metadata"]["x"], "metric_value")
        self.assertEqual(updated[2]["metadata"]["y"], "entity_name")

    def test_object_row_question_with_two_metrics_adds_point_chart(self) -> None:
        answer = base_answer(
            query_kind="object_query",
            result_shape="object_rows",
            time_series_rows=[],
            display_metrics=[
                PlanDisplayMetric(column_key="metric_1", metric="total_points", label="Total Points"),
                PlanDisplayMetric(column_key="metric_2", metric="total_assists", label="Total Assists"),
            ],
            object_rows=[
                ObjectRow(
                    entity_id=1,
                    entity_name="Jalen Brunson",
                    context_value="NYK",
                    metric_value=312,
                    display_values={"metric_1": 312, "metric_2": 74},
                ),
                ObjectRow(
                    entity_id=2,
                    entity_name="Jayson Tatum",
                    context_value="BOS",
                    metric_value=298,
                    display_values={"metric_1": 298, "metric_2": 81},
                ),
            ],
        )

        artifacts = append_chart_artifacts(
            "Show players with points and assists",
            answer,
            build_artifacts(answer),
        )

        self.assertEqual([artifact["kind"] for artifact in artifacts], ["text", "text", "chart", "table"])
        chart = artifacts[2]
        self.assertEqual(chart["metadata"]["operation_kind"], "point_chart")
        self.assertEqual(chart["metadata"]["chart_family"], "point")
        self.assertEqual(chart["metadata"]["x"], "metric_1")
        self.assertEqual(chart["metadata"]["y"], "metric_2")
        self.assertEqual(chart["metadata"]["source_visual_task"], "metric_relationship")
        self.assertNotIn("color", chart["spec"]["encoding"])

    def test_chart_intent_adds_horizontal_bar_for_aggregate_answer(self) -> None:
        answer = base_answer(
            result_shape="aggregate",
            time_series_rows=[],
            display_metrics=[],
            grouping_columns=[PlanGroupingColumn(column_key="team_name", label="team_name")],
            aggregate_rows=[
                AggregateRow(entity_name="Celtics", group_values={"team_name": "Celtics"}, metric_value=121.3),
                AggregateRow(entity_name="Knicks", group_values={"team_name": "Knicks"}, metric_value=116.2),
            ],
        )

        artifacts = append_chart_artifacts(
            "Show average points by team as a chart",
            answer,
            build_artifacts(answer),
        )

        self.assertEqual(
            [artifact["kind"] for artifact in artifacts],
            ["text", "text", "chart", "table"],
        )
        chart = artifacts[2]
        self.assertEqual(chart["metadata"]["operation_kind"], "bar_chart")
        self.assertEqual(chart["metadata"]["orientation"], "horizontal")
        self.assertEqual(chart["metadata"]["x"], "metric_value")
        self.assertEqual(chart["metadata"]["y"], "team_name")
        self.assertEqual(chart["metadata"]["source_result_shape"], "aggregate")
        self.assertEqual(chart["metadata"]["category_count"], 2)
        self.assertEqual(chart["spec"]["encoding"]["y"]["sort"]["field"], "metric_value")
        self.assertEqual(chart["spec"]["encoding"]["y"]["sort"]["order"], "descending")

    def test_aggregate_question_without_chart_words_adds_chart(self) -> None:
        answer = base_answer(
            result_shape="aggregate",
            time_series_rows=[],
            display_metrics=[],
            grouping_columns=[PlanGroupingColumn(column_key="team_name", label="team_name")],
            aggregate_rows=[
                AggregateRow(entity_name="Celtics", group_values={"team_name": "Celtics"}, metric_value=121.3),
            ],
        )
        artifacts = build_artifacts(answer)

        updated = append_chart_artifacts(
            "Show average points by team",
            answer,
            artifacts,
        )

        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "text", "chart", "table"])
        self.assertEqual(updated[2]["metadata"]["operation_kind"], "bar_chart")
        self.assertEqual(updated[2]["metadata"]["x"], "metric_value")
        self.assertEqual(updated[2]["metadata"]["y"], "team_name")

    def test_chart_intent_adds_horizontal_bar_for_comparison_summary(self) -> None:
        brunson = ComparisonEntityStats(
            entity_id=1,
            entity_name="Jalen Brunson",
            context_value="NYK",
            display_values={"metric_1": 312},
            metric_value=312,
            games_count=10,
        )
        tatum = ComparisonEntityStats(
            entity_id=2,
            entity_name="Jayson Tatum",
            context_value="BOS",
            display_values={"metric_1": 298},
            metric_value=298,
            games_count=10,
        )
        answer = base_answer(
            result_shape="comparison",
            time_series_rows=[],
            time_grain=None,
            display_metrics=[PlanDisplayMetric(column_key="metric_1", metric="total_points", label="Total Points")],
            comparison=ComparisonResult(
                leader="Jalen Brunson",
                metric_differential=14,
                entity_a=brunson,
                entity_b=tatum,
                entities=[brunson, tatum],
            ),
        )

        artifacts = append_chart_artifacts(
            "Chart this comparison",
            answer,
            build_artifacts(answer),
        )

        self.assertEqual(
            [artifact["kind"] for artifact in artifacts],
            ["text", "text", "chart", "table"],
        )
        chart = artifacts[2]
        self.assertEqual(chart["metadata"]["operation_kind"], "bar_chart")
        self.assertEqual(chart["metadata"]["orientation"], "horizontal")
        self.assertEqual(chart["metadata"]["x"], "metric_1")
        self.assertEqual(chart["metadata"]["y"], "entity_name")
        self.assertIsNone(chart["spec"]["encoding"]["y"]["sort"])

    def test_chart_intent_adds_line_chart_for_time_bucketed_comparison_breakdown(self) -> None:
        brunson = ComparisonEntityStats(
            entity_id=1,
            entity_name="Jalen Brunson",
            context_value="NYK",
            display_values={"metric_1": 30.1},
            metric_value=30.1,
            games_count=4,
        )
        tatum = ComparisonEntityStats(
            entity_id=2,
            entity_name="Jayson Tatum",
            context_value="BOS",
            display_values={"metric_1": 28.4},
            metric_value=28.4,
            games_count=4,
        )
        answer = base_answer(
            result_shape="comparison",
            time_series_rows=[],
            time_grain="month",
            display_metrics=[PlanDisplayMetric(column_key="metric_1", metric="average_points", label="Average Points")],
            comparison=ComparisonResult(
                leader="Jalen Brunson",
                metric_differential=4,
                entity_a=brunson,
                entity_b=tatum,
                entities=[brunson, tatum],
                breakdown_rows=[
                    ComparisonBreakdownRow(
                        entity_id=1,
                        entity_name="Jalen Brunson",
                        context_value="NYK",
                        time_bucket="2026-01",
                        display_values={"metric_1": 30.1},
                        metric_value=30.1,
                        games_count=4,
                    ),
                    ComparisonBreakdownRow(
                        entity_id=2,
                        entity_name="Jayson Tatum",
                        context_value="BOS",
                        time_bucket="2026-01",
                        display_values={"metric_1": 28.4},
                        metric_value=28.4,
                        games_count=4,
                    ),
                ],
            ),
        )

        artifacts = append_chart_artifacts(
            "Show this comparison over time as a chart",
            answer,
            build_artifacts(answer),
        )

        self.assertEqual(
            [artifact["kind"] for artifact in artifacts],
            ["text", "text", "chart", "table"],
        )
        chart = artifacts[2]
        self.assertEqual(chart["metadata"]["operation_kind"], "line_chart")
        self.assertEqual(chart["metadata"]["x"], "time_bucket")
        self.assertEqual(chart["metadata"]["y"], "metric_1")
        self.assertEqual(chart["metadata"]["series"], "entity_name")
        self.assertEqual(chart["spec"]["encoding"]["y"]["field"], "metric_1")
        self.assertEqual(chart["spec"]["encoding"]["color"]["field"], "entity_name")

    def test_chart_intent_adds_line_chart_for_date_metric_find_rows(self) -> None:
        answer = base_answer(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            rows=[],
            time_series_rows=[],
            find_rows=[
                {"game_date": "2026-01-15", "opponent": "Warriors", "score": 128},
                {"game_date": "2026-01-17", "opponent": "Celtics", "score": 121},
            ],
        )

        artifacts = append_chart_artifacts(
            "Visualize these games",
            answer,
            build_artifacts(answer),
        )

        self.assertEqual(
            [artifact["kind"] for artifact in artifacts],
            ["text", "text", "chart", "table"],
        )
        chart = artifacts[2]
        self.assertEqual(chart["metadata"]["operation_kind"], "line_chart")
        self.assertEqual(chart["metadata"]["x"], "game_date")
        self.assertEqual(chart["metadata"]["y"], "score")
        self.assertIsNone(chart["metadata"]["series"])

    def test_chart_intent_adds_horizontal_bar_for_category_metric_find_rows(self) -> None:
        answer = base_answer(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Player",
            entity_label_plural="Players",
            rows=[],
            time_series_rows=[],
            find_rows=[
                {"player_name": "Jalen Brunson", "points": 38},
                {"player_name": "Jayson Tatum", "points": 34},
            ],
        )

        artifacts = append_chart_artifacts(
            "Show these rows as a chart",
            answer,
            build_artifacts(answer),
        )

        self.assertEqual(
            [artifact["kind"] for artifact in artifacts],
            ["text", "text", "chart", "table"],
        )
        chart = artifacts[2]
        self.assertEqual(chart["metadata"]["operation_kind"], "bar_chart")
        self.assertEqual(chart["metadata"]["orientation"], "horizontal")
        self.assertEqual(chart["metadata"]["x"], "points")
        self.assertEqual(chart["metadata"]["y"], "player_name")
        self.assertIsNone(chart["spec"]["encoding"]["y"]["sort"])

    def test_find_rows_question_without_chart_words_adds_chart_when_chartable(self) -> None:
        answer = base_answer(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            rows=[],
            time_series_rows=[],
            find_rows=[
                {"game_date": "2026-01-15", "opponent": "Warriors", "score": 128},
            ],
        )
        artifacts = build_artifacts(answer)

        updated = append_chart_artifacts(
            "Show these games",
            answer,
            artifacts,
        )

        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "text", "chart", "table"])
        self.assertEqual(updated[2]["metadata"]["operation_kind"], "line_chart")
        self.assertEqual(updated[2]["metadata"]["x"], "game_date")
        self.assertEqual(updated[2]["metadata"]["y"], "score")

    def test_non_chartable_find_rows_question_stays_table_only(self) -> None:
        answer = base_answer(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Player",
            entity_label_plural="Players",
            rows=[],
            time_series_rows=[],
            find_rows=[
                {"player_name": "Jalen Brunson", "team_name": "Knicks"},
            ],
        )
        artifacts = build_artifacts(answer)

        updated = append_chart_artifacts(
            "Show these players",
            answer,
            artifacts,
        )

        self.assertIs(updated, artifacts)
        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "text", "table"])

    def test_chart_intent_without_table_does_not_crash_or_add_chart(self) -> None:
        answer = base_answer(
            result_shape="ranking",
            time_series_rows=[],
        )
        artifacts = build_artifacts(answer)

        updated = append_chart_artifacts(
            "Show this as a chart",
            answer,
            artifacts,
        )

        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "text"])

    def test_chart_generation_uses_answer_rows_not_visible_table_columns(self) -> None:
        answer = base_answer()
        artifacts = [
            {"kind": "text", "role": "summary", "text": "Rows are shown below."},
            {
                "kind": "table",
                "title": "Rows",
                "columns": [
                    {"id": "time_bucket", "label": "Month", "type": "date"},
                    {"id": "team_name", "label": "Team", "type": "text"},
                ],
                "rows": [{"time_bucket": "2026-01", "team_name": "Lakers"}],
                "row_count": 1,
                "displayed_row_count": 1,
                "display_limit": 50,
            },
        ]

        updated = append_chart_artifacts("Visualize this", answer, artifacts)

        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "chart", "table"])
        chart = updated[1]
        self.assertEqual(chart["metadata"]["row_count"], len(answer.time_series_rows))
        self.assertEqual(chart["metadata"]["y"], "metric_1")

    @patch("apps.assistant.pipeline.format_response", return_value="Formatted answer")
    @patch("apps.assistant.pipeline.synthesize_answer")
    @patch("apps.assistant.pipeline.package_results", return_value=object())
    @patch("apps.assistant.pipeline.execute_plan", return_value=object())
    @patch(
        "apps.assistant.pipeline.plan_question",
        return_value=(
            {"task": "trend"},
            {
                "execution_plan": {
                    "plan_type": "single_sql",
                    "query_kind": "metric_query",
                    "result_shape": "time_series",
                    "entity_label_singular": "Team",
                    "entity_label_plural": "Teams",
                    "context_label": "",
                    "metric": "average_points",
                    "metric_aggregation": "avg",
                    "window_games": 0,
                    "time_grain": "month",
                    "limit": 0,
                    "steps": [{"kind": "run_sql", "sql": "SELECT 1"}],
                }
            },
        ),
    )
    @patch("apps.assistant.pipeline.load_database")
    def test_run_assistant_appends_chart_artifact_after_grounded_answer(
        self,
        _mock_load_database,
        _mock_plan_question,
        _mock_execute_plan,
        _mock_package_results,
        mock_synthesize_answer,
        _mock_format_response,
    ) -> None:
        mock_synthesize_answer.return_value = base_answer()

        result = run_assistant("Show monthly average points by team as a chart")

        self.assertEqual(result.answer, "Formatted answer")
        self.assertEqual(
            [artifact["kind"] for artifact in result.artifacts or []],
            ["text", "text", "chart", "table"],
        )


if __name__ == "__main__":
    unittest.main()
