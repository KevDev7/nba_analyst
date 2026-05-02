from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from apps.assistant.chart_artifacts import append_requested_chart_artifacts
from apps.assistant.pipeline import run_assistant
from runtime.AnalysisRuntime.models import PlanDisplayMetric, PlanGroupingColumn, TimeSeriesRow
from runtime.AnswerSynthesis.artifacts import build_artifacts
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
    def test_chart_intent_adds_vega_lite_chart_before_time_series_table(self) -> None:
        answer = base_answer()

        artifacts = append_requested_chart_artifacts(
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
        self.assertEqual(chart["spec"]["encoding"]["x"]["type"], "temporal")
        self.assertEqual(chart["spec"]["encoding"]["y"]["type"], "quantitative")
        self.assertEqual(chart["spec"]["encoding"]["color"]["field"], "team_name")

    def test_non_chart_question_keeps_artifacts_unchanged(self) -> None:
        answer = base_answer()
        artifacts = build_artifacts(answer)

        updated = append_requested_chart_artifacts(
            "Show monthly average points by team",
            answer,
            artifacts,
        )

        self.assertIs(updated, artifacts)
        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "text", "table"])

    def test_chart_intent_for_non_time_series_answer_does_not_crash_or_add_chart(self) -> None:
        answer = base_answer(
            result_shape="ranking",
            time_series_rows=[],
        )
        artifacts = build_artifacts(answer)

        updated = append_requested_chart_artifacts(
            "Show this as a chart",
            answer,
            artifacts,
        )

        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "text"])

    def test_chart_intent_without_numeric_metric_keeps_table_only(self) -> None:
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

        updated = append_requested_chart_artifacts("Visualize this", answer, artifacts)

        self.assertEqual([artifact["kind"] for artifact in updated], ["text", "table"])

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
