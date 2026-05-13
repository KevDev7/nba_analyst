from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from apps.assistant.routes.correlation import CorrelationPlan, execute_correlation_plan
from apps.assistant.routes.period_delta import PeriodSpec
from apps.assistant.tools.python_analysis import PythonAnalysisToolResult
from apps.assistant.tools.semantic_query import SemanticQueryTable
from apps.assistant.trace import AssistantTrace, ToolCallTrace


def semantic_result(query_id: str, rows: list[dict[str, object]]):
    return SimpleNamespace(
        ok=True,
        error=None,
        query_id=query_id,
        tables=[
            SemanticQueryTable(
                id=f"{query_id}.primary",
                title="Metric",
                columns=[
                    {"id": "entity_name", "label": "Entity", "type": "text"},
                    {"id": "metric_value", "label": "Metric", "type": "number"},
                ],
                rows=rows,
                row_count=len(rows),
                displayed_row_count=len(rows),
            )
        ],
        trace=AssistantTrace(
            question=None,
            route="deterministic_fast_path",
            status="ok",
            tool_calls=[
                ToolCallTrace(
                    tool_call_id=f"tc_{query_id}",
                    tool_name="semantic_query.plan_execute",
                    status="ok",
                    output={"query_id": query_id},
                )
            ],
        ),
    )


class CorrelationPlanTests(unittest.TestCase):
    @patch("apps.assistant.routes.correlation.render_artifacts")
    @patch("apps.assistant.routes.correlation.run_python_analysis")
    @patch("apps.assistant.routes.correlation.plan_execute")
    def test_correlation_plan_executes_governed_tool_sequence(
        self,
        mock_plan_execute,
        mock_run_python_analysis,
        mock_render_artifacts,
    ) -> None:
        plan = CorrelationPlan(
            subject="players",
            x_measure="average points",
            y_measure="average assists",
            period=PeriodSpec(season="2024-25", season_type="regular_season"),
        )
        mock_plan_execute.side_effect = [
            semantic_result("sq_x", [{"entity_name": "A", "metric_value": 1}, {"entity_name": "B", "metric_value": 2}]),
            semantic_result("sq_y", [{"entity_name": "A", "metric_value": 10}, {"entity_name": "B", "metric_value": 20}]),
        ]
        mock_run_python_analysis.return_value = PythonAnalysisToolResult(
            ok=True,
            analysis_id="analysis_corr",
            outputs={
                "tables": [
                    {
                        "id": "correlation",
                        "title": "Correlation",
                        "columns": [
                            {"id": "left_metric", "label": "Left Metric", "type": "text"},
                            {"id": "right_metric", "label": "Right Metric", "type": "text"},
                            {"id": "method", "label": "Method", "type": "text"},
                            {"id": "correlation", "label": "Correlation", "type": "number"},
                            {"id": "paired_row_count", "label": "Matched Rows", "type": "integer"},
                        ],
                        "rows": [
                            {
                                "left_metric": "average_points",
                                "right_metric": "average_assists",
                                "method": "pearson",
                                "correlation": 1.0,
                                "paired_row_count": 2,
                            }
                        ],
                        "row_count": 1,
                    }
                ],
                "artifacts": [],
                "findings": [],
            },
            provenance={
                "operation_kind": "correlation",
                "parent_table_ids": ["correlation_x", "correlation_y"],
                "derived_from_table_ids": ["correlation_x", "correlation_y"],
                "output_table_ids": ["correlation"],
            },
        )
        mock_render_artifacts.return_value = SimpleNamespace(
            ok=True,
            artifacts=[{"kind": "table", "title": "Correlation"}],
            artifact_count=1,
            error=None,
        )

        result = execute_correlation_plan("Are points and assists related?", plan, debug=True)

        self.assertIn("correlation between average points and average assists", result.answer)
        self.assertEqual(mock_plan_execute.call_count, 2)
        mock_run_python_analysis.assert_called_once()
        mock_render_artifacts.assert_called_once()
        trace_tools = [call["tool_name"] for call in result.debug["trace"]["tool_calls"]]
        self.assertEqual(
            trace_tools,
            [
                "semantic_query.plan_execute",
                "semantic_query.plan_execute",
                "python_analysis.run",
                "artifact_renderer.render",
            ],
        )


if __name__ == "__main__":
    unittest.main()
