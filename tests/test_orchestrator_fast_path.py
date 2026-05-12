from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from apps.assistant.models import AssistantResult
from apps.assistant.orchestrator import run_assistant
from apps.assistant.routes.period_delta import maybe_build_period_delta_plan
from apps.assistant.tools.python_analysis import PythonAnalysisToolResult
from apps.assistant.tools.semantic_query import SemanticQueryTable
from apps.assistant.trace import AssistantTrace, ToolCallTrace


def _semantic_result(query_id: str, rows: list[dict[str, object]]):
    return SimpleNamespace(
        ok=True,
        error=None,
        query_id=query_id,
        tables=[
            SemanticQueryTable(
                id=f"{query_id}.primary",
                title="Team average points",
                columns=[
                    {"id": "entity_name", "label": "Team", "type": "text"},
                    {"id": "metric_value", "label": "Average Points", "type": "number"},
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


class OrchestratorFastPathTests(unittest.TestCase):
    @patch("apps.assistant.orchestrator.plan_execute")
    def test_orchestrator_calls_semantic_query_once(self, mock_plan_execute) -> None:
        mock_plan_execute.return_value.ok = True
        mock_plan_execute.return_value.error = None
        mock_plan_execute.return_value.to_assistant_result.return_value = AssistantResult(
            answer="Formatted answer",
            artifacts=[{"kind": "text", "role": "summary", "text": "Formatted answer"}],
        )

        result = run_assistant("Show me top players by points", debug=True)

        self.assertEqual(result.answer, "Formatted answer")
        mock_plan_execute.assert_called_once()
        request = mock_plan_execute.call_args.args[0]
        self.assertEqual(request.question, "Show me top players by points")
        self.assertTrue(request.include_debug)
        self.assertEqual(request.caller, "orchestrator")

    @patch("apps.assistant.orchestrator.plan_execute")
    def test_orchestrator_raises_tool_error_message(self, mock_plan_execute) -> None:
        mock_plan_execute.return_value.ok = False
        mock_plan_execute.return_value.error.message = "Could not resolve metric"

        with self.assertRaises(RuntimeError) as context:
            run_assistant("Show me made up metric")

        self.assertIn("Could not resolve metric", str(context.exception))

    def test_period_delta_plan_parses_subject_measure_and_periods(self) -> None:
        plan = maybe_build_period_delta_plan(
            "Which players had the biggest increase in average assists from 2023-24 regular season to 2024-25 playoffs?"
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan.subject, "players")
        self.assertEqual(plan.measure, "average assists")
        self.assertEqual(plan.periods[0].season, "2023-24")
        self.assertEqual(plan.periods[0].season_type, "regular_season")
        self.assertEqual(plan.periods[1].season, "2024-25")
        self.assertEqual(plan.periods[1].season_type, "playoffs")

    @patch("apps.assistant.routes.period_delta.run_python_analysis")
    @patch("apps.assistant.routes.period_delta.plan_execute")
    def test_orchestrator_can_run_team_points_delta_multi_call_route(
        self,
        mock_plan_execute,
        mock_run_python_analysis,
    ) -> None:
        mock_plan_execute.side_effect = [
            _semantic_result(
                "sq_left",
                [
                    {"entity_name": "Pacers", "metric_value": 123.3},
                    {"entity_name": "Magic", "metric_value": 110.5},
                ],
            ),
            _semantic_result(
                "sq_right",
                [
                    {"entity_name": "Pacers", "metric_value": 117.4},
                    {"entity_name": "Magic", "metric_value": 116.1},
                ],
            ),
        ]
        mock_run_python_analysis.return_value = PythonAnalysisToolResult(
            ok=True,
            analysis_id="analysis_test",
            outputs={
                "tables": [
                    {
                        "id": "team_points_left_team_points_right_increase",
                        "title": "Biggest increases in team average points per game",
                        "columns": [
                            {"id": "entity", "label": "Team", "type": "text"},
                            {"id": "avg_points_2023_24", "label": "2023-24 Avg Points", "type": "number"},
                            {"id": "avg_points_2024_25", "label": "2024-25 Avg Points", "type": "number"},
                            {"id": "delta", "label": "Delta", "type": "number"},
                        ],
                        "rows": [
                            {
                                "entity": "Magic",
                                "avg_points_2023_24": 110.5,
                                "avg_points_2024_25": 116.1,
                                "delta": 5.6,
                            }
                        ],
                        "row_count": 1,
                    }
                ],
                "artifacts": [],
                "findings": [],
            },
            provenance={
                "operation_kind": "join_and_delta",
                "parent_table_ids": ["team_points_left", "team_points_right"],
            },
        )

        result = run_assistant(
            "Which teams had the biggest increase in average points per game from 2023-24 regular season to 2024-25 regular season?"
        )

        self.assertIn("Magic", result.answer)
        self.assertIn("5.6", result.answer)
        self.assertEqual([artifact["kind"] for artifact in result.artifacts], ["text", "text", "table"])
        self.assertEqual(result.artifacts[2]["rows"][0]["entity"], "Magic")
        self.assertEqual(mock_plan_execute.call_count, 2)
        left_request = mock_plan_execute.call_args_list[0].args[0]
        right_request = mock_plan_execute.call_args_list[1].args[0]
        self.assertEqual(left_request.semantic_draft["time_window"]["value"], "2023-24")
        self.assertEqual(right_request.semantic_draft["time_window"]["value"], "2024-25")
        self.assertEqual(left_request.question_context[:11], "Which teams")
        self.assertEqual(left_request.semantic_draft_state, "prepared")
        analysis_request = mock_run_python_analysis.call_args.args[0].analysis_request
        self.assertEqual(analysis_request.operation.kind, "join_and_delta")
        self.assertEqual(analysis_request.operation.output_metric, "delta")


if __name__ == "__main__":
    unittest.main()
