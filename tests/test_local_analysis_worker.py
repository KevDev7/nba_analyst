from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.local_worker import run_analysis_request
from runtime.AnalysisTools.models import AnalysisRequest, AnalysisTable, AnalysisTableColumn


def sample_monthly_table() -> AnalysisTable:
    return AnalysisTable(
        id="monthly_team_points",
        title="Monthly team points",
        columns=[
            AnalysisTableColumn(id="month", label="Month", type="date"),
            AnalysisTableColumn(id="team", label="Team", type="text"),
            AnalysisTableColumn(id="average_points", label="Average Points", type="number"),
        ],
        rows=[
            {"month": "2026-01", "team": "Lakers", "average_points": 118.4},
            {"month": "2026-02", "team": "Lakers", "average_points": 120.1},
            {"month": "2026-01", "team": "Warriors", "average_points": 116.9},
        ],
    )


class LocalAnalysisWorkerTests(unittest.TestCase):
    def test_line_chart_operation_returns_vega_lite_artifact(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_monthly_table()],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "monthly_team_points",
                    "x": "month",
                    "y": "average_points",
                    "series": "team",
                    "title": "Monthly average points by team",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.artifacts), 1)
        artifact = result.artifacts[0]
        self.assertEqual(artifact.kind, "chart")
        self.assertEqual(artifact.renderer, "vega_lite")
        self.assertEqual(artifact.title, "Monthly average points by team")
        self.assertEqual(artifact.spec["mark"]["type"], "line")
        self.assertTrue(artifact.spec["mark"]["point"])
        self.assertEqual(artifact.spec["encoding"]["x"]["field"], "month")
        self.assertEqual(artifact.spec["encoding"]["x"]["type"], "temporal")
        self.assertEqual(artifact.spec["encoding"]["y"]["field"], "average_points")
        self.assertEqual(artifact.spec["encoding"]["y"]["type"], "quantitative")
        self.assertEqual(artifact.spec["encoding"]["color"]["field"], "team")
        self.assertIn("datasets", artifact.spec)
        chart_rows = next(iter(artifact.spec["datasets"].values()))
        self.assertEqual(chart_rows[0]["month"], "2026-01-01T00:00:00")
        self.assertEqual(artifact.metadata["source_table_id"], "monthly_team_points")
        self.assertEqual(artifact.data["row_count"], 3)

    def test_bar_chart_operation_returns_bar_mark(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_monthly_table()],
                operation={
                    "kind": "bar_chart",
                    "input_table_id": "monthly_team_points",
                    "x": "team",
                    "y": "average_points",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.artifacts[0].spec["mark"]["type"], "bar")
        self.assertEqual(result.artifacts[0].spec["encoding"]["x"]["field"], "team")

    def test_unsupported_renderer_returns_structured_error(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_monthly_table()],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "monthly_team_points",
                    "x": "month",
                    "y": "average_points",
                    "renderer": "plotly",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code if result.error else None, "unsupported_renderer")
        self.assertEqual(result.logs[0].level, "error")

    def test_non_numeric_y_axis_returns_structured_error(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_monthly_table()],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "monthly_team_points",
                    "x": "month",
                    "y": "team",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "invalid_chart_operation")
        self.assertIn("must be numeric", result.error.message if result.error else "")

    def test_invalid_numeric_values_return_structured_error(self) -> None:
        bad_table = AnalysisTable(
            id="bad_points",
            columns=[
                AnalysisTableColumn(id="team", label="Team", type="text"),
                AnalysisTableColumn(id="average_points", label="Average Points", type="number"),
            ],
            rows=[{"team": "Lakers", "average_points": "not a number"}],
        )

        result = run_analysis_request(
            AnalysisRequest(
                tables=[bad_table],
                operation={
                    "kind": "bar_chart",
                    "input_table_id": "bad_points",
                    "x": "team",
                    "y": "average_points",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "invalid_numeric_column")

    def test_invalid_temporal_values_return_structured_error(self) -> None:
        bad_table = AnalysisTable(
            id="bad_months",
            columns=[
                AnalysisTableColumn(id="month", label="Month", type="date"),
                AnalysisTableColumn(id="average_points", label="Average Points", type="number"),
            ],
            rows=[{"month": "not a month", "average_points": 118.4}],
        )

        result = run_analysis_request(
            AnalysisRequest(
                tables=[bad_table],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "bad_months",
                    "x": "month",
                    "y": "average_points",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "invalid_temporal_column")

    def test_empty_table_still_returns_empty_chart_artifact(self) -> None:
        empty_table = AnalysisTable(
            id="empty_monthly_points",
            columns=[
                AnalysisTableColumn(id="month", label="Month", type="date"),
                AnalysisTableColumn(id="average_points", label="Average Points", type="number"),
            ],
            rows=[],
        )

        result = run_analysis_request(
            AnalysisRequest(
                tables=[empty_table],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "empty_monthly_points",
                    "x": "month",
                    "y": "average_points",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.artifacts[0].data["row_count"], 0)
        self.assertEqual(result.artifacts[0].spec["encoding"]["x"]["type"], "temporal")
        self.assertEqual(result.artifacts[0].spec["encoding"]["y"]["type"], "quantitative")


if __name__ == "__main__":
    unittest.main()
