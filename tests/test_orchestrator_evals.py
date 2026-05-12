from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from apps.assistant.orchestrator import run_assistant
from apps.assistant.tools.python_analysis import PythonAnalysisToolResult
from apps.assistant.tools.semantic_query import SemanticQueryTable
from apps.assistant.trace import AssistantTrace, ToolCallTrace


ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = ROOT / "evals" / "orchestrator_question_bank.json"


def semantic_result(query_id: str, rows: list[dict[str, object]]):
    return SimpleNamespace(
        ok=True,
        error=None,
        query_id=query_id,
        tables=[
            SemanticQueryTable(
                id=f"{query_id}.primary",
                title="Average points",
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


class OrchestratorEvalTests(unittest.TestCase):
    @patch("apps.assistant.routes.period_delta.run_python_analysis")
    @patch("apps.assistant.routes.period_delta.plan_execute")
    def test_orchestrator_eval_expected_tool_sequence(self, mock_plan_execute, mock_run_python_analysis) -> None:
        cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        case = cases[0]
        mock_plan_execute.side_effect = [
            semantic_result("sq_left", [{"entity_name": "Magic", "metric_value": 110.5}]),
            semantic_result("sq_right", [{"entity_name": "Magic", "metric_value": 116.1}]),
        ]
        mock_run_python_analysis.return_value = PythonAnalysisToolResult(
            ok=True,
            analysis_id="analysis_eval",
            outputs={
                "tables": [
                    {
                        "id": "period_delta",
                        "title": "Biggest increases",
                        "columns": [
                            {"id": "entity", "label": "Team", "type": "text"},
                            {"id": "delta", "label": "Delta", "type": "number"},
                        ],
                        "rows": [{"entity": "Magic", "delta": 5.6}],
                        "row_count": 1,
                    }
                ],
                "artifacts": [],
                "findings": [],
            },
            provenance={
                "operation_kind": "join_and_delta",
                "parent_table_ids": ["period_delta_left", "period_delta_right"],
                "derived_from_table_ids": ["period_delta_left", "period_delta_right"],
                "output_table_ids": ["period_delta"],
            },
        )

        result = run_assistant(case["question"], debug=True)

        self.assertIsNotNone(result.debug)
        trace = result.debug["trace"]
        self.assertEqual(trace["route"], case["expected_route"])
        self.assertEqual(
            [tool_call["tool_name"] for tool_call in trace["tool_calls"]],
            case["expected_tools"],
        )
        tool_names = {tool_call["tool_name"] for tool_call in trace["tool_calls"]}
        self.assertTrue(tool_names.isdisjoint(case["forbidden_tools"]))
        artifact_kinds = {artifact["kind"] for artifact in result.artifacts}
        for expected_artifact in case["expected_artifacts"]:
            self.assertIn(expected_artifact, artifact_kinds)


if __name__ == "__main__":
    unittest.main()
