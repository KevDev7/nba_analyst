from __future__ import annotations

import sys
from pathlib import Path
import unittest

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.models import (
    AnalysisLog,
    AnalysisRequest,
    AnalysisResult,
    AnalysisTable,
    AnalysisTableColumn,
    AnalysisToolError,
    ChartArtifact,
)


def sample_table() -> AnalysisTable:
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
        ],
    )


class AnalysisToolContractTests(unittest.TestCase):
    def test_valid_chart_analysis_request_parses(self) -> None:
        request = AnalysisRequest(
            tables=[sample_table()],
            operation={
                "kind": "line_chart",
                "input_table_id": "monthly_team_points",
                "x": "month",
                "y": "average_points",
                "series": "team",
                "title": "Monthly average points by team",
            },
        )

        self.assertEqual(request.tool, "python_analysis")
        self.assertEqual(request.runtime, "local_trusted")
        self.assertEqual(request.operation.kind, "line_chart")
        self.assertEqual(request.operation.renderer, "vega_lite")

    def test_request_rejects_unknown_operation_kind(self) -> None:
        with self.assertRaises(ValidationError) as context:
            AnalysisRequest(
                tables=[sample_table()],
                operation={
                    "kind": "execute_python",
                    "input_table_id": "monthly_team_points",
                    "code": "print('not part of the contract')",
                },
            )

        self.assertIn("union_tag_invalid", str(context.exception))

    def test_request_rejects_unknown_table_reference(self) -> None:
        with self.assertRaises(ValidationError) as context:
            AnalysisRequest(
                tables=[sample_table()],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "missing_table",
                    "x": "month",
                    "y": "average_points",
                },
            )

        self.assertIn("Operation references unknown table", str(context.exception))

    def test_request_rejects_unknown_column_reference(self) -> None:
        with self.assertRaises(ValidationError) as context:
            AnalysisRequest(
                tables=[sample_table()],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "monthly_team_points",
                    "x": "month",
                    "y": "made_up_metric",
                },
            )

        self.assertIn("Operation references unknown columns", str(context.exception))

    def test_table_rejects_rows_with_undeclared_columns(self) -> None:
        with self.assertRaises(ValidationError) as context:
            AnalysisTable(
                id="bad_table",
                columns=[AnalysisTableColumn(id="team", label="Team")],
                rows=[{"team": "Lakers", "hidden_sql_column": 123}],
            )

        self.assertIn("Rows contain undeclared columns", str(context.exception))

    def test_chart_artifact_is_provider_neutral(self) -> None:
        artifact = ChartArtifact(
            renderer="vega_lite",
            title="Monthly average points",
            spec={
                "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
                "mark": "line",
                "encoding": {},
            },
            metadata={"source_table_id": "monthly_team_points"},
        )

        self.assertEqual(artifact.kind, "chart")
        self.assertEqual(artifact.renderer, "vega_lite")
        self.assertEqual(artifact.metadata["source_table_id"], "monthly_team_points")

    def test_analysis_result_success_and_failure_shapes_are_explicit(self) -> None:
        success = AnalysisResult(
            ok=True,
            artifacts=[
                ChartArtifact(
                    renderer="vega_lite",
                    title="Monthly average points",
                    spec={"mark": "line"},
                )
            ],
            logs=[AnalysisLog(message="Built chart artifact.")],
        )

        failure = AnalysisResult(
            ok=False,
            error=AnalysisToolError(
                code="unsupported_operation",
                message="Operation 'scatter_matrix' is not supported.",
            ),
        )

        self.assertTrue(success.ok)
        self.assertEqual(success.logs[0].message, "Built chart artifact.")
        self.assertFalse(failure.ok)
        self.assertEqual(failure.error.code if failure.error else None, "unsupported_operation")

    def test_analysis_result_rejects_ambiguous_error_state(self) -> None:
        with self.assertRaises(ValidationError):
            AnalysisResult(
                ok=True,
                error=AnalysisToolError(code="unexpected", message="Should not be present."),
            )

        with self.assertRaises(ValidationError):
            AnalysisResult(ok=False)


if __name__ == "__main__":
    unittest.main()
