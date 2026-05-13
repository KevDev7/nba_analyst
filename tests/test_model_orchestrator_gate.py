from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.assistant.model_orchestration.answer_composer import ComposedAnswer, EvidenceRef, GroundedClaim
from apps.assistant.model_orchestration.executor import execute_model_plan
from apps.assistant.model_orchestration.plans import ModelAnalysisPlan
from apps.assistant.models import AssistantResult
from apps.assistant.orchestrator import model_orchestration_state, run_assistant
from apps.assistant.semantic.llm_transport import LlmTransportError
from apps.assistant.trace import AssistantTrace, ToolCallTrace


PLAN_JSON = """
{
  "plan": {
    "kind": "simple_semantic_query",
    "question": "Show top teams by net rating"
  },
  "tool_sequence": [
    {"tool_name": "semantic_query.plan_execute", "purpose": "retrieve grounded answer"}
  ]
}
"""

UNSUPPORTED_PLAN_JSON = """
{
  "plan": {
    "kind": "unsupported",
    "reason": "Lineup and on-off data are not exposed by the ontology.",
    "unsupported_surface": "lineups"
  },
  "tool_sequence": []
}
"""


class ModelOrchestratorGateTests(unittest.TestCase):
    @patch.dict("os.environ", {"NBA_ENABLE_MODEL_ORCHESTRATOR": "", "NBA_MODEL_ORCHESTRATOR_DRY_RUN": "", "NBA_ENABLE_MODEL_TOOL_LOOP": ""})
    def test_model_orchestration_state_defaults_off(self) -> None:
        self.assertEqual(model_orchestration_state(), "off")

    @patch.dict("os.environ", {"NBA_ENABLE_MODEL_ORCHESTRATOR": "1", "NBA_MODEL_ORCHESTRATOR_DRY_RUN": "1", "NBA_ENABLE_MODEL_TOOL_LOOP": ""})
    def test_model_orchestration_state_reports_dry_run(self) -> None:
        self.assertEqual(model_orchestration_state(), "dry_run")

    @patch.dict("os.environ", {"NBA_ENABLE_MODEL_ORCHESTRATOR": "1", "NBA_MODEL_ORCHESTRATOR_DRY_RUN": "", "NBA_ENABLE_MODEL_TOOL_LOOP": "1"})
    def test_model_orchestration_state_reports_tool_loop_beta(self) -> None:
        self.assertEqual(model_orchestration_state(), "tool_loop_beta")

    @patch.dict("os.environ", {"NBA_ENABLE_MODEL_ORCHESTRATOR": "1", "NBA_MODEL_ORCHESTRATOR_DRY_RUN": "1"})
    @patch("apps.assistant.model_orchestration.planner.call_gemini", return_value=PLAN_JSON)
    @patch("apps.assistant.orchestrator.plan_execute")
    def test_dry_run_returns_validated_plan_without_executing_tools(self, mock_plan_execute, _mock_call_gemini) -> None:
        result = run_assistant("Show top teams by net rating", debug=True)

        self.assertIn("dry run", result.answer)
        self.assertEqual(result.debug["model_orchestration"]["planned_tool_sequence"], ["semantic_query.plan_execute"])
        mock_plan_execute.assert_not_called()

    @patch.dict("os.environ", {"NBA_ENABLE_MODEL_ORCHESTRATOR": "1", "NBA_MODEL_ORCHESTRATOR_DRY_RUN": ""})
    @patch("apps.assistant.model_orchestration.planner.call_gemini", side_effect=LlmTransportError("provider down"))
    @patch("apps.assistant.orchestrator.plan_execute")
    def test_model_planner_failure_falls_back_to_deterministic_fast_path(self, mock_plan_execute, _mock_call_gemini) -> None:
        mock_plan_execute.return_value.ok = True
        mock_plan_execute.return_value.error = None
        mock_plan_execute.return_value.to_assistant_result.return_value = AssistantResult(answer="fallback answer", artifacts=[])

        result = run_assistant("Show top teams by net rating")

        self.assertEqual(result.answer, "fallback answer")
        mock_plan_execute.assert_called_once()

    @patch.dict("os.environ", {"NBA_ENABLE_MODEL_ORCHESTRATOR": "1", "NBA_MODEL_ORCHESTRATOR_DRY_RUN": ""})
    @patch("apps.assistant.model_orchestration.planner.call_gemini", return_value=PLAN_JSON)
    @patch("apps.assistant.model_orchestration.executor.plan_execute")
    def test_enabled_model_orchestrator_executes_only_governed_semantic_tool(self, mock_plan_execute, _mock_call_gemini) -> None:
        mock_plan_execute.return_value.ok = True
        mock_plan_execute.return_value.error = None
        mock_plan_execute.return_value.artifacts = [{"kind": "table", "rows": []}]
        mock_plan_execute.return_value.trace = AssistantTrace(
            question="Show top teams by net rating",
            route="deterministic_fast_path",
            status="ok",
            tool_calls=[
                ToolCallTrace(
                    tool_call_id="tc_semantic",
                    tool_name="semantic_query.plan_execute",
                    status="ok",
                )
            ],
        )
        mock_plan_execute.return_value.to_assistant_result.return_value = AssistantResult(
            answer="model orchestrated answer",
            artifacts=[{"kind": "table", "rows": []}],
            debug={},
        )

        result = run_assistant("Show top teams by net rating", debug=True)

        self.assertEqual(result.answer, "model orchestrated answer")
        mock_plan_execute.assert_called_once()
        request = mock_plan_execute.call_args.args[0]
        self.assertEqual(request.caller, "model_orchestrator")
        trace_tool_names = [call["tool_name"] for call in result.debug["trace"]["tool_calls"]]
        self.assertEqual(trace_tool_names, ["semantic_query.plan_execute"])

    @patch.dict("os.environ", {"NBA_ENABLE_MODEL_ORCHESTRATOR": "1", "NBA_MODEL_ORCHESTRATOR_DRY_RUN": ""})
    @patch("apps.assistant.model_orchestration.planner.call_gemini", return_value=UNSUPPORTED_PLAN_JSON)
    @patch("apps.assistant.orchestrator.plan_execute")
    def test_unsupported_model_plan_refuses_without_retrieval(self, mock_plan_execute, _mock_call_gemini) -> None:
        result = run_assistant("Which Lakers lineups had the best on-off numbers?", debug=True)

        self.assertIn("Lineup", result.answer)
        mock_plan_execute.assert_not_called()
        self.assertEqual(result.debug["model_plan"]["plan"]["kind"], "unsupported")

    @patch("apps.assistant.model_orchestration.executor.compose_grounded_answer")
    @patch("apps.assistant.model_orchestration.executor.execute_period_delta_plan")
    def test_model_answer_composer_uses_table_evidence(self, mock_execute_period_delta, mock_compose) -> None:
        plan = ModelAnalysisPlan(
            plan={
                "kind": "period_delta",
                "subject": "teams",
                "measure": "average points",
                "periods": [
                    {"season": "2023-24", "season_type": "regular_season"},
                    {"season": "2024-25", "season_type": "regular_season"},
                ],
                "join_key": "entity",
                "delta": "right_minus_left",
            }
        )
        mock_execute_period_delta.return_value = AssistantResult(
            answer="Fallback table-first answer",
            artifacts=[
                {
                    "kind": "table",
                    "id": "analysis.delta",
                    "columns": [{"id": "entity"}, {"id": "delta"}],
                    "rows": [{"entity": "Magic", "delta": 5.6}],
                }
            ],
            debug={},
        )
        mock_compose.return_value = ComposedAnswer(
            answer="The Magic had the largest increase.",
            claims=[
                GroundedClaim(
                    text="The Magic increased by 5.6.",
                    evidence_refs=[EvidenceRef(table_id="analysis.delta", row_index=0, columns=["entity", "delta"])],
                )
            ],
        )

        result = execute_model_plan("Who improved most?", plan, debug=True, compose_answer=True)

        self.assertEqual(result.answer, "The Magic had the largest increase.")
        self.assertEqual(result.debug["claims"][0]["evidence_refs"][0]["table_id"], "analysis.delta")
        evidence_tables = mock_compose.call_args.kwargs["evidence_tables"]
        self.assertEqual(evidence_tables[0]["id"], "analysis.delta")

    @patch("apps.assistant.model_orchestration.executor.execute_correlation_plan")
    def test_enabled_model_orchestrator_can_execute_correlation_plan(self, mock_execute_correlation) -> None:
        plan = ModelAnalysisPlan(
            plan={
                "kind": "correlation",
                "subject": "players",
                "x_measure": "average points",
                "y_measure": "average assists",
                "period": {"season": "2024-25", "season_type": "regular_season"},
                "join_key": "entity",
                "method": "pearson",
            }
        )
        mock_execute_correlation.return_value = AssistantResult(
            answer="Correlation answer",
            artifacts=[{"kind": "table"}],
            debug={},
        )

        result = execute_model_plan("Are points and assists related?", plan, debug=True)

        self.assertEqual(result.answer, "Correlation answer")
        mock_execute_correlation.assert_called_once()


if __name__ == "__main__":
    unittest.main()
