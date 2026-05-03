from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from apps.assistant.chart_planner import plan_chart_operation
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
from runtime.AnswerSynthesis.artifacts import build_primary_table_artifact
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


class ChartPlannerTests(unittest.TestCase):
    def test_time_series_plan_matches_existing_operation_shape(self) -> None:
        answer = base_answer()
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(
            plan.operation if plan is not None else None,
            {
                "kind": "line_chart",
                "input_table_id": "primary_answer_table",
                "x": "time_bucket",
                "y": "metric_1",
                "series": "team_name",
                "title": "Monthly average points by team are shown below.",
                "renderer": "vega_lite",
                "metadata": {
                    "source_result_shape": "time_series",
                    "source_time_grain": "month",
                },
            },
        )

    def test_time_bucket_takes_precedence_over_other_date_columns(self) -> None:
        answer = base_answer()
        table = {
            "title": "Rows",
            "columns": [
                {"id": "game_date", "label": "Game Date", "type": "date"},
                {"id": "time_bucket", "label": "Month", "type": "date"},
                {"id": "metric_value", "label": "Average Points", "type": "number"},
            ],
            "rows": [],
        }

        plan = plan_chart_operation(answer, table)

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["x"] if plan is not None else None, "time_bucket")

    def test_first_date_column_is_used_when_time_bucket_is_missing(self) -> None:
        answer = base_answer()
        table = {
            "title": "Rows",
            "columns": [
                {"id": "game_date", "label": "Game Date", "type": "date"},
                {"id": "metric_value", "label": "Average Points", "type": "number"},
            ],
            "rows": [],
        }

        plan = plan_chart_operation(answer, table)

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["x"] if plan is not None else None, "game_date")

    def test_first_numeric_metric_excluding_x_is_used_for_y(self) -> None:
        answer = base_answer()
        table = {
            "title": "Rows",
            "columns": [
                {"id": "time_bucket", "label": "Month", "type": "date"},
                {"id": "games", "label": "Games", "type": "integer"},
                {"id": "metric_value", "label": "Average Points", "type": "number"},
            ],
            "rows": [],
        }

        plan = plan_chart_operation(answer, table)

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["y"] if plan is not None else None, "games")

    def test_first_text_column_excluding_axes_is_used_for_series(self) -> None:
        answer = base_answer()
        table = {
            "title": "Rows",
            "columns": [
                {"id": "time_bucket", "label": "Month", "type": "date"},
                {"id": "metric_value", "label": "Average Points", "type": "number"},
                {"id": "team_name", "label": "Team", "type": "text"},
                {"id": "conference", "label": "Conference", "type": "text"},
            ],
            "rows": [],
        }

        plan = plan_chart_operation(answer, table)

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["series"] if plan is not None else None, "team_name")

    def test_unsupported_result_shapes_do_not_plan_charts(self) -> None:
        answer = base_answer(result_shape="box_score")
        table = build_primary_table_artifact(base_answer(), row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNone(plan)

    def test_find_rows_with_date_and_numeric_metric_plan_line_chart(self) -> None:
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
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "line_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "game_date")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "score")
        self.assertIsNone(plan.operation["series"] if plan is not None else "not planned")

    def test_find_rows_with_category_and_numeric_metric_plan_horizontal_bar_chart(self) -> None:
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
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "bar_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "points")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "player_name")
        self.assertEqual(plan.operation["orientation"] if plan is not None else None, "horizontal")
        self.assertEqual(
            plan.operation["sort"] if plan is not None else None,
            {"channel": "y", "field": None, "order": None},
        )

    def test_find_rows_with_two_numeric_metrics_plan_point_chart(self) -> None:
        answer = base_answer(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            rows=[],
            time_series_rows=[],
            find_rows=[
                {"game_date": "2026-01-15", "opponent": "Warriors", "score": 128, "assists": 31},
                {"game_date": "2026-01-17", "opponent": "Celtics", "score": 121, "assists": 26},
            ],
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "point_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "score")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "assists")
        self.assertIsNone(plan.operation["series"] if plan is not None else "not planned")

    def test_text_only_find_rows_do_not_plan_charts(self) -> None:
        answer = base_answer(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Player",
            entity_label_plural="Players",
            rows=[],
            time_series_rows=[],
            find_rows=[
                {"player_name": "Jalen Brunson", "team_name": "Knicks"},
                {"player_name": "Jayson Tatum", "team_name": "Celtics"},
            ],
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNone(plan)

    def test_identifier_only_find_rows_do_not_plan_charts(self) -> None:
        answer = base_answer(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            rows=[],
            time_series_rows=[],
            find_rows=[
                {"game_date": "2026-01-15", "game_id": 101},
                {"game_date": "2026-01-17", "game_id": 102},
            ],
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNone(plan)

    def test_aggregate_answer_plans_horizontal_bar_chart_sorted_by_metric(self) -> None:
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
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "bar_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "metric_value")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "team_name")
        self.assertEqual(plan.operation["orientation"] if plan is not None else None, "horizontal")
        self.assertEqual(
            plan.operation["sort"] if plan is not None else None,
            {"channel": "y", "field": "metric_value", "order": "descending"},
        )

    def test_aggregate_time_bucket_answer_plans_line_chart(self) -> None:
        answer = base_answer(
            result_shape="aggregate",
            time_series_rows=[],
            display_metrics=[],
            grouping_columns=[PlanGroupingColumn(column_key="time_bucket", label="month")],
            aggregate_rows=[
                AggregateRow(entity_name="October", group_values={"time_bucket": "2025-10"}, metric_value=118.4),
                AggregateRow(entity_name="November", group_values={"time_bucket": "2025-11"}, metric_value=116.9),
            ],
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "line_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "time_bucket")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "metric_value")
        self.assertIsNone(plan.operation["series"] if plan is not None else "not planned")

    def test_aggregate_with_two_metrics_plans_point_chart(self) -> None:
        answer = base_answer(
            result_shape="aggregate",
            time_series_rows=[],
            time_grain=None,
            grouping_columns=[PlanGroupingColumn(column_key="team_name", label="team_name")],
            display_metrics=[
                PlanDisplayMetric(column_key="metric_1", metric="average_points", label="Average Points"),
                PlanDisplayMetric(column_key="metric_2", metric="average_assists", label="Average Assists"),
            ],
            aggregate_rows=[
                AggregateRow(
                    entity_name="Celtics",
                    group_values={"team_name": "Celtics"},
                    metric_value=121.3,
                    display_values={"metric_1": 121.3, "metric_2": 28.1},
                ),
                AggregateRow(
                    entity_name="Knicks",
                    group_values={"team_name": "Knicks"},
                    metric_value=116.2,
                    display_values={"metric_1": 116.2, "metric_2": 26.4},
                ),
            ],
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "point_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "metric_1")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "metric_2")
        self.assertIsNone(plan.operation["series"] if plan is not None else "not planned")

    def test_ranking_answer_plans_horizontal_bar_chart_sorted_by_rank(self) -> None:
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
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(
            plan.operation if plan is not None else None,
            {
                "kind": "bar_chart",
                "input_table_id": "primary_answer_table",
                "x": "metric_value",
                "y": "entity_name",
                "series": None,
                "orientation": "horizontal",
                "sort": {"channel": "y", "field": "rank", "order": "ascending"},
                "title": "Monthly average points by team are shown below.",
                "renderer": "vega_lite",
                "metadata": {
                    "source_result_shape": "ranking",
                    "source_time_grain": "month",
                    "source_metric_order_direction": "DESC",
                },
            },
        )

    def test_grouped_ranking_uses_grouping_column_as_category(self) -> None:
        answer = base_answer(
            result_shape="ranking",
            time_series_rows=[],
            grouping_columns=[PlanGroupingColumn(column_key="team_name", label="team_name")],
            rows=[
                RankingRow(
                    rank=1,
                    entity_name="Celtics",
                    group_values={"team_name": "Celtics"},
                    metric_value=312,
                ),
                RankingRow(
                    rank=2,
                    entity_name="Knicks",
                    group_values={"team_name": "Knicks"},
                    metric_value=298,
                ),
            ],
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["y"] if plan is not None else None, "team_name")

    def test_object_rows_with_two_metrics_plan_point_chart(self) -> None:
        answer = base_answer(
            query_kind="object_query",
            result_shape="object_rows",
            time_series_rows=[],
            display_metrics=[
                PlanDisplayMetric(column_key="metric_1", metric="points", label="Points"),
                PlanDisplayMetric(column_key="metric_2", metric="assists", label="Assists"),
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
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "point_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "metric_1")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "metric_2")
        self.assertIsNone(plan.operation["series"] if plan is not None else "not planned")
        self.assertEqual(
            plan.operation["metadata"] if plan is not None else None,
            {
                "source_result_shape": "object_rows",
                "source_time_grain": "month",
                "source_visual_task": "metric_relationship",
                "source_metric_count": 2,
            },
        )

    def test_object_rows_with_one_metric_plan_horizontal_bar_chart(self) -> None:
        answer = base_answer(
            query_kind="object_query",
            result_shape="object_rows",
            time_series_rows=[],
            display_metrics=[
                PlanDisplayMetric(column_key="metric_1", metric="points", label="Points"),
            ],
            object_rows=[
                ObjectRow(
                    entity_id=1,
                    entity_name="Jalen Brunson",
                    context_value="NYK",
                    metric_value=312,
                    display_values={"metric_1": 312},
                ),
                ObjectRow(
                    entity_id=2,
                    entity_name="Jayson Tatum",
                    context_value="BOS",
                    metric_value=298,
                    display_values={"metric_1": 298},
                ),
            ],
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "bar_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "metric_1")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "entity_name")
        self.assertEqual(plan.operation["orientation"] if plan is not None else None, "horizontal")

    def test_ranking_with_extra_metrics_keeps_primary_ranking_bar_chart(self) -> None:
        answer = base_answer(
            result_shape="ranking",
            time_series_rows=[],
            grouping_columns=[],
            display_metrics=[
                PlanDisplayMetric(column_key="metric_1", metric="points", label="Points"),
                PlanDisplayMetric(column_key="metric_2", metric="assists", label="Assists"),
            ],
            rows=[
                RankingRow(
                    rank=1,
                    entity_name="Jalen Brunson",
                    context_value="NYK",
                    metric_value=312,
                    display_values={"metric_1": 312, "metric_2": 74},
                ),
                RankingRow(
                    rank=2,
                    entity_name="Jayson Tatum",
                    context_value="BOS",
                    metric_value=298,
                    display_values={"metric_1": 298, "metric_2": 81},
                ),
            ],
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "bar_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "metric_1")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "entity_name")
        self.assertEqual(
            plan.operation["sort"] if plan is not None else None,
            {"channel": "y", "field": "rank", "order": "ascending"},
        )

    def test_comparison_entity_summary_plans_horizontal_bar_chart(self) -> None:
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
            display_metrics=[PlanDisplayMetric(column_key="metric_1", metric="total_points", label="Total Points")],
            comparison=ComparisonResult(
                leader="Jalen Brunson",
                metric_differential=14,
                entity_a=brunson,
                entity_b=tatum,
                entities=[brunson, tatum],
            ),
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "bar_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "metric_1")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "entity_name")
        self.assertEqual(plan.operation["orientation"] if plan is not None else None, "horizontal")
        self.assertEqual(
            plan.operation["sort"] if plan is not None else None,
            {"channel": "y", "field": None, "order": None},
        )

    def test_time_bucketed_comparison_breakdown_plans_line_chart_for_primary_metric(self) -> None:
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
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNotNone(plan)
        self.assertEqual(plan.operation["kind"] if plan is not None else None, "line_chart")
        self.assertEqual(plan.operation["x"] if plan is not None else None, "time_bucket")
        self.assertEqual(plan.operation["y"] if plan is not None else None, "metric_1")
        self.assertEqual(plan.operation["series"] if plan is not None else None, "entity_name")
        self.assertEqual(
            plan.operation["metadata"] if plan is not None else None,
            {
                "source_result_shape": "comparison",
                "source_time_grain": "month",
                "source_comparison_shape": "breakdown",
            },
        )

    def test_categorical_comparison_breakdown_stays_table_only_for_now(self) -> None:
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
            time_grain=None,
            grouping_columns=[PlanGroupingColumn(column_key="season_type", label="season_type")],
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
                        group_values={"season_type": "Regular Season"},
                        display_values={"metric_1": 30.1},
                        metric_value=30.1,
                        games_count=4,
                    ),
                    ComparisonBreakdownRow(
                        entity_id=2,
                        entity_name="Jayson Tatum",
                        context_value="BOS",
                        group_values={"season_type": "Regular Season"},
                        display_values={"metric_1": 28.4},
                        metric_value=28.4,
                        games_count=4,
                    ),
                ],
            ),
        )
        table = build_primary_table_artifact(answer, row_limit=None)

        plan = plan_chart_operation(answer, table or {})

        self.assertIsNone(plan)

    def test_missing_time_axis_returns_no_plan(self) -> None:
        answer = base_answer()
        table = {
            "title": "Rows",
            "columns": [
                {"id": "team_name", "label": "Team", "type": "text"},
                {"id": "metric_value", "label": "Average Points", "type": "number"},
            ],
            "rows": [],
        }

        plan = plan_chart_operation(answer, table)

        self.assertIsNone(plan)

    def test_missing_numeric_metric_returns_no_plan(self) -> None:
        answer = base_answer()
        table = {
            "title": "Rows",
            "columns": [
                {"id": "time_bucket", "label": "Month", "type": "date"},
                {"id": "team_name", "label": "Team", "type": "text"},
            ],
            "rows": [],
        }

        plan = plan_chart_operation(answer, table)

        self.assertIsNone(plan)

    def test_title_falls_back_to_table_title_then_chart(self) -> None:
        answer = base_answer(summary="")
        table = {
            "title": "Fallback Table Title",
            "columns": [
                {"id": "time_bucket", "label": "Month", "type": "date"},
                {"id": "metric_value", "label": "Average Points", "type": "number"},
            ],
            "rows": [],
        }

        table_title_plan = plan_chart_operation(answer, table)
        chart_title_plan = plan_chart_operation(answer, {**table, "title": ""})

        self.assertEqual(
            table_title_plan.operation["title"] if table_title_plan is not None else None,
            "Fallback Table Title",
        )
        self.assertEqual(
            chart_title_plan.operation["title"] if chart_title_plan is not None else None,
            "Chart",
        )


if __name__ == "__main__":
    unittest.main()
