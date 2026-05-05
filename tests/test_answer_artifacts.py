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
    PlanDisplayMetric,
    PlanGroupingColumn,
    RankingRow,
    TimeSeriesRow,
)
from runtime.AnswerSynthesis.artifacts import build_artifacts
from runtime.AnswerSynthesis.response_models import FinalAnswer
from tests.answer_context_helpers import build_final_answer


def base_answer(**overrides: object) -> FinalAnswer:
    values = {
        "summary": "Rows are shown below.",
        "interpretation": "Players ranked by total points.",
        "query_kind": "metric_query",
        "result_shape": "ranking",
        "entity_label_singular": "Player",
        "entity_label_plural": "Players",
        "context_label": "Team",
        "metric": "total_points",
        "window_games": 10,
        "limit": 10,
        "rows": [],
    }
    values.update(overrides)
    return build_final_answer(**values)


class AnswerArtifactTests(unittest.TestCase):
    def _table(self, answer: FinalAnswer) -> dict[str, object]:
        artifacts = build_artifacts(answer)
        table = next(artifact for artifact in artifacts if artifact["kind"] == "table")
        return table

    def test_ranking_answer_builds_text_and_table_artifacts_from_structured_rows(self) -> None:
        answer = base_answer(
            assumptions=["Assumed regular season."],
            rows=[
                RankingRow(rank=1, entity_name="Jalen Brunson", context_value="NYK", metric_value=312),
                RankingRow(rank=2, entity_name="Jayson Tatum", context_value="BOS", metric_value=298),
            ],
        )

        artifacts = build_artifacts(answer)
        table = next(artifact for artifact in artifacts if artifact["kind"] == "table")

        self.assertEqual(
            [artifact["role"] for artifact in artifacts if artifact["kind"] == "text"],
            ["interpretation", "summary", "assumptions"],
        )
        self.assertEqual(
            table["columns"],
            [
                {"id": "rank", "label": "Rank", "type": "integer"},
                {"id": "entity_name", "label": "Player", "type": "text"},
                {"id": "context_value", "label": "Team", "type": "text"},
                {"id": "metric_value", "label": "Total Points", "type": "number"},
            ],
        )
        self.assertEqual(
            table["rows"][0],
            {
                "rank": 1,
                "entity_name": "Jalen Brunson",
                "context_value": "NYK",
                "metric_value": 312.0,
            },
        )
        self.assertEqual(table["row_count"], 2)
        self.assertEqual(table["displayed_row_count"], 2)

    def test_time_series_artifact_preserves_grouping_and_multiple_metric_columns(self) -> None:
        answer = base_answer(
            result_shape="time_series",
            rows=[],
            metric="total_points",
            time_grain="month",
            grouping_columns=[PlanGroupingColumn(column_key="team_name", label="team_name")],
            display_metrics=[
                PlanDisplayMetric(column_key="metric_1", metric="total_points", label="Total Points"),
                PlanDisplayMetric(column_key="metric_2", metric="total_assists", label="Assists"),
            ],
            time_series_rows=[
                TimeSeriesRow(
                    time_bucket="2026-01",
                    group_values={"team_name": "Lakers"},
                    display_values={"metric_1": 1200, "metric_2": 300},
                    metric_value=1200,
                )
            ],
        )

        table = self._table(answer)

        self.assertEqual(
            table["columns"],
            [
                {"id": "time_bucket", "label": "Month", "type": "date"},
                {"id": "team_name", "label": "Team", "type": "text"},
                {"id": "metric_1", "label": "Total Points", "type": "number"},
                {"id": "metric_2", "label": "Assists", "type": "number"},
            ],
        )
        self.assertEqual(
            table["rows"][0],
            {
                "time_bucket": "2026-01",
                "team_name": "Lakers",
                "metric_1": 1200,
                "metric_2": 300,
            },
        )

    def test_find_rows_artifact_uses_requested_display_columns(self) -> None:
        answer = base_answer(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            rows=[],
            find_rows=[
                {
                    "game_date": "2026-01-15",
                    "opponent": "Warriors",
                    "score": 128,
                    "margin": 7,
                }
            ],
        )

        table = self._table(answer)

        self.assertEqual(
            table["columns"],
            [
                {"id": "game_date", "label": "Game Date", "type": "date"},
                {"id": "opponent", "label": "Opponent", "type": "text"},
                {"id": "score", "label": "Score", "type": "number"},
                {"id": "margin", "label": "Margin", "type": "number"},
            ],
        )

    def test_comparison_artifact_uses_entity_rows_for_table_payload(self) -> None:
        brunson = ComparisonEntityStats(
            entity_id=1628973,
            entity_name="Jalen Brunson",
            context_value="NYK",
            display_values={"metric_1": 312, "metric_2": 74},
            metric_value=312,
            games_count=10,
        )
        tatum = ComparisonEntityStats(
            entity_id=1628369,
            entity_name="Jayson Tatum",
            context_value="BOS",
            display_values={"metric_1": 298, "metric_2": 81},
            metric_value=298,
            games_count=10,
        )
        answer = base_answer(
            result_shape="comparison",
            rows=[],
            display_metrics=[
                PlanDisplayMetric(column_key="metric_1", metric="total_points", label="Total Points"),
                PlanDisplayMetric(column_key="metric_2", metric="total_assists", label="Assists"),
            ],
            comparison=ComparisonResult(
                leader="Jalen Brunson",
                metric_differential=14,
                entity_a=brunson,
                entity_b=tatum,
                entities=[brunson, tatum],
            ),
        )

        table = self._table(answer)

        self.assertEqual(
            table["columns"],
            [
                {"id": "entity_name", "label": "Player", "type": "text"},
                {"id": "context_value", "label": "Team", "type": "text"},
                {"id": "games", "label": "Games", "type": "integer"},
                {"id": "metric_1", "label": "Total Points", "type": "number"},
                {"id": "metric_2", "label": "Assists", "type": "number"},
            ],
        )
        self.assertEqual(table["rows"][1]["metric_2"], 81)


if __name__ == "__main__":
    unittest.main()
