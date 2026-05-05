from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisRuntime.models import (
    ComparisonEntityStats,
    ComparisonResult,
    ExecutionPlan,
    RankingRow,
    RuntimeResult,
    TimeSeriesRow,
    ObjectRow,
)
from runtime.AnswerSynthesis.format_response import format_response
from runtime.AnswerSynthesis.package_results import package_results
from runtime.AnswerSynthesis.response_models import SynthesisPayload
from runtime.AnswerSynthesis.synthesize import synthesize_answer
from pydantic import ValidationError


def answer_context(
    *,
    query_kind: str = "metric_query",
    result_shape: str = "ranking",
    singular: str = "Team",
    plural: str = "Teams",
    context_label: str = "Abbrev",
    metric: str = "defensive_rating",
    aggregation: str = "avg",
    order_direction: str = "ASC",
    rank_intent: str | None = "best",
    limit: int = 3,
    window_games: int = 0,
    time_grain: str | None = None,
    time_filter: str | None = None,
    time_window_days: int | None = None,
    time_start_date: str | None = None,
    time_end_date: str | None = None,
    season_label: str | None = "2025-26",
    season_type: str | None = "regular_season",
    find_predicate_tree: dict[str, object] | None = None,
    find_filters: list[dict[str, object]] | None = None,
    find_orders: list[dict[str, object]] | None = None,
    row_predicate: dict[str, object] | None = None,
    result_predicate: dict[str, object] | None = None,
    grouping_columns: list[dict[str, object]] | None = None,
    display_metadata: list[dict[str, object]] | None = None,
    display_metrics: list[dict[str, object]] | None = None,
    assumptions: list[str] | None = None,
) -> dict[str, object]:
    return {
        "query_kind": query_kind,
        "result_shape": result_shape,
        "subject": {
            "singular": singular,
            "plural": plural,
            "context_label": context_label,
        },
        "metric": {
            "key": metric,
            "aggregation": aggregation,
            "order_direction": order_direction,
        },
        "time": {
            "window_games": window_games,
            "grain": time_grain,
            "filter": time_filter,
            "window_days": time_window_days,
            "start_date": time_start_date,
            "end_date": time_end_date,
            "season_label": season_label,
            "season_type": season_type,
        },
        "ranking": {"intent_label": rank_intent, "limit": limit},
        "find": {
            "predicate_tree": find_predicate_tree,
            "filters": find_filters or [],
            "orders": find_orders or [],
        },
        "predicates": {"row": row_predicate, "result": result_predicate},
        "display": {
            "grouping_columns": grouping_columns or [],
            "metadata": display_metadata or [],
            "metrics": display_metrics or [],
        },
        "assumptions": assumptions or [],
    }


def payload_from_context(context: dict[str, object], **overrides: object) -> SynthesisPayload:
    values = {
        "rows": [],
        "answer_context": context,
    }
    values.update(overrides)
    return SynthesisPayload(**values)


class AnswerContextSynthesisTests(unittest.TestCase):
    def test_package_results_and_rank_summary_prefer_answer_context(self) -> None:
        context = answer_context()
        runtime_result = RuntimeResult(
            rows=[RankingRow(rank=1, entity_name="Thunder", context_value="OKC", metric_value=106.2)],
            answer_context=context,
        )

        payload = package_results(runtime_result)
        answer = synthesize_answer(payload)

        self.assertEqual(payload.metric, "defensive_rating")
        self.assertEqual(payload.entity_label_plural, "Teams")
        self.assertEqual(payload.rank_intent_label, "best")
        self.assertEqual(
            answer.summary,
            "Best 3 teams by defensive rating in the 2025-26 regular season: Thunder ranks first with 106 defensive rating.",
        )
        self.assertNotIn("Wrong", answer.summary)

    def test_trend_summary_and_formatting_prefer_answer_context(self) -> None:
        context = answer_context(
            result_shape="time_series",
            metric="total_points",
            aggregation="sum",
            order_direction="DESC",
            rank_intent=None,
            limit=0,
            time_grain="month",
            time_filter="past_year",
            season_label=None,
            season_type=None,
        )
        payload = payload_from_context(
            context,
            time_series_rows=[
                TimeSeriesRow(time_bucket="2026-01", series_name="Lakers", metric_value=1210)
            ],
        )

        answer = synthesize_answer(payload)
        formatted = format_response(answer)

        self.assertEqual(
            answer.summary,
            "Monthly total points by team over the past year are shown below.",
        )
        self.assertIn("Month | Team | Total Points", formatted)
        self.assertNotIn("Wrong Entity", formatted)

    def test_comparison_summary_prefers_context_display_metrics(self) -> None:
        context = answer_context(
            result_shape="comparison",
            singular="Player",
            plural="Players",
            context_label="Team",
            metric="total_points",
            aggregation="sum",
            order_direction="DESC",
            rank_intent=None,
            limit=0,
            window_games=10,
            season_label=None,
            season_type=None,
            display_metrics=[
                {
                    "column_key": "metric_1",
                    "metric": "total_points",
                    "label": "Total Points",
                    "aggregation": "sum",
                },
                {
                    "column_key": "metric_2",
                    "metric": "total_assists",
                    "label": "Assists",
                    "aggregation": "sum",
                },
            ],
        )
        brunson = ComparisonEntityStats(
            entity_id=1628973,
            entity_name="Jalen Brunson",
            metric_value=312,
            games_count=10,
        )
        tatum = ComparisonEntityStats(
            entity_id=1628369,
            entity_name="Jayson Tatum",
            metric_value=298,
            games_count=10,
        )
        payload = payload_from_context(
            context,
            comparison=ComparisonResult(
                leader="Jalen Brunson",
                metric_differential=14,
                entity_a=brunson,
                entity_b=tatum,
                entities=[brunson, tatum],
            ),
        )

        answer = synthesize_answer(payload)

        self.assertEqual(
            answer.summary,
            "Total points and assists comparison over the last 10 games is shown below.",
        )
        self.assertEqual([metric.metric for metric in answer.display_metrics], ["total_points", "total_assists"])

    def test_object_summary_prefers_context_metric_and_time(self) -> None:
        context = answer_context(
            query_kind="object_query",
            result_shape="object_rows",
            singular="Player",
            plural="Players",
            context_label="Team",
            metric="total_points",
            aggregation="sum",
            order_direction="DESC",
            rank_intent=None,
            limit=0,
            window_games=10,
            season_label=None,
            season_type=None,
        )
        payload = payload_from_context(
            context,
            object_rows=[ObjectRow(entity_id=201939, entity_name="Stephen Curry", metric_value=302)],
        )

        answer = synthesize_answer(payload)

        self.assertEqual(
            answer.summary,
            "Players ordered by total points over the last 10 games: Stephen Curry leads with 302 total points.",
        )
        self.assertEqual(answer.metric, "total_points")

    def test_find_interpretation_prefers_context_filters_and_orders(self) -> None:
        context = answer_context(
            query_kind="find_query",
            result_shape="find_rows",
            singular="Game",
            plural="Games",
            context_label="",
            metric="",
            aggregation="",
            order_direction="",
            rank_intent=None,
            limit=0,
            window_games=0,
            season_label=None,
            season_type=None,
            find_predicate_tree={
                "kind": "leaf",
                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                "operator": "equals",
                "value": {"kind": "scalar", "value": "Lakers"},
            },
            find_filters=[{"filter_kind": "last_n_games", "filter_value": 5}],
            find_orders=[{"order_field": "game_date", "order_direction": "descending"}],
        )
        payload = payload_from_context(
            context,
            find_rows=[{"game_date": "2026-01-15", "opponent": "Warriors"}],
        )

        answer = synthesize_answer(payload)

        self.assertEqual(
            answer.interpretation,
            "Games where team name equals Lakers over the last 5 games sorted by game date descending.",
        )
        self.assertEqual(answer.summary, "Matching games are shown below.")

    def test_boundary_models_reject_stale_flat_answer_fields(self) -> None:
        context = answer_context()

        with self.assertRaises(ValidationError):
            ExecutionPlan(
                execution={"plan_type": "single_sql", "steps": []},
                answer_context=context,
                metric="stale_flat_metric",
            )

        with self.assertRaises(ValidationError):
            RuntimeResult(
                answer_context=context,
                rows=[],
                metric="stale_flat_metric",
            )

        with self.assertRaises(ValidationError):
            SynthesisPayload(
                answer_context=context,
                rows=[],
                metric="stale_flat_metric",
            )


if __name__ == "__main__":
    unittest.main()
