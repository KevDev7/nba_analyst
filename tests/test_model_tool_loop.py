from __future__ import annotations

import unittest
from unittest.mock import patch
from types import SimpleNamespace

from apps.assistant.model_orchestration.tool_loop import (
    build_default_registry,
    ToolRegistry,
    ToolContext,
    ToolResult,
    ToolSpec,
    run_model_tool_loop,
)
from apps.assistant.model_orchestration.answer_composer import ComposedAnswer
from apps.assistant.models import AssistantResult
from apps.assistant.orchestrator import run_assistant
from apps.assistant.tools.semantic_query import SemanticQueryTable
from apps.assistant.trace import AssistantTrace, ToolCallTrace
from tests.orchestrator_eval_helpers import assert_no_raw_sql_or_private_debug


def fake_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="ontology_catalog.inspect", description="fake catalog"),
        lambda _payload, _context: ToolResult(
            ok=True,
            tool_name="ontology_catalog.inspect",
            output={"metrics": [{"label": "Net Rating"}], "sql": "SELECT hidden"},
        ),
    )
    return registry


class ModelToolLoopTests(unittest.TestCase):
    def test_tool_loop_executes_mocked_tool_and_final_answer(self) -> None:
        responses = iter(
            [
                """
                {
                  "action": "tool_call",
                  "tool_name": "ontology_catalog.inspect",
                  "purpose": "inspect metrics",
                  "arguments": {"facets": ["metrics"], "search": "net rating"}
                }
                """,
                """
                {
                  "action": "final",
                  "answer": "Net rating is available in the catalog."
                }
                """,
            ]
        )

        result = run_model_tool_loop(
            "Can I ask about net rating?",
            debug=True,
            call_model=lambda _prompt: next(responses),
            registry=fake_registry(),
        )

        self.assertEqual(result.answer, "I need grounded evidence from a governed retrieval before giving a final answer.")
        trace = result.debug["trace"]
        self.assertEqual(trace["route"], "model_tool_loop_beta")
        self.assertEqual([call["tool_name"] for call in trace["tool_calls"]], ["ontology_catalog.inspect", "answer_composer.compose"])
        assert_no_raw_sql_or_private_debug(self, trace)

    @patch("apps.assistant.model_orchestration.tool_loop.plan_execute")
    def test_semantic_query_tool_stores_tables_in_workspace(self, mock_plan_execute) -> None:
        mock_plan_execute.return_value = _semantic_result()
        registry = build_default_registry()
        context = ToolContext(question="Show teams by points")

        result = registry.execute("semantic_query.plan_execute", {"question": "Show teams by points"}, context)

        self.assertTrue(result.ok)
        self.assertIn("sq.primary", context.workspace.tables)
        self.assertEqual(result.output["tables"][0]["table_id"], "sq.primary")
        self.assertIn("sample_rows", result.output["tables"][0])

    def test_python_analysis_consumes_workspace_table_id(self) -> None:
        registry = build_default_registry()
        context = ToolContext(question="Rank table")
        context.workspace.add_table(_analysis_table())

        result = registry.execute(
            "python_analysis.run",
            {
                "table_ids": ["sq.primary"],
                "operation": {
                    "kind": "rank_extremes",
                    "input_table_id": "sq.primary",
                    "metric": "metric_value",
                    "limit": 1,
                },
            },
            context,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.output["tables"][0]["table_id"], "sq.primary_metric_value_ranked")
        self.assertIn("sq.primary_metric_value_ranked", context.workspace.tables)

    def test_python_analysis_rejects_inline_analysis_request_tables(self) -> None:
        registry = build_default_registry()
        context = ToolContext(question="Rank inline table")

        result = registry.execute(
            "python_analysis.run",
            {
                "analysis_request": {
                    "runtime": "local_trusted",
                    "tables": [_analysis_table().model_dump()],
                    "operation": {
                        "kind": "rank_extremes",
                        "input_table_id": "sq.primary",
                        "metric": "metric_value",
                    },
                }
            },
            context,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "tool_execution_failed")
        self.assertIn("table_ids", result.error["message"])

    def test_chart_generation_consumes_workspace_table_id(self) -> None:
        registry = build_default_registry()
        context = ToolContext(question="Chart it")
        context.workspace.add_table(_analysis_table())

        result = registry.execute(
            "chart_generation.run",
            {"table_ids": ["sq.primary"], "chart_intent": "bar chart"},
            context,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.output["artifact_count"], 1)
        self.assertTrue(context.workspace.artifacts)

    def test_chart_generation_rejects_inline_table_payloads(self) -> None:
        registry = build_default_registry()
        context = ToolContext(question="Chart inline table")

        result = registry.execute(
            "chart_generation.run",
            {"tables": [_analysis_table().model_dump()], "chart_intent": "bar chart"},
            context,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "inline_tables_not_allowed_in_tool_loop")

    def test_artifact_renderer_rejects_inline_table_payloads(self) -> None:
        registry = build_default_registry()
        context = ToolContext(question="Render inline table")

        result = registry.execute(
            "artifact_renderer.render",
            {"tables": [_analysis_table().model_dump()], "allowed_artifact_kinds": ["table"]},
            context,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "inline_tables_not_allowed_in_tool_loop")

    def test_artifact_renderer_consumes_workspace_table_id(self) -> None:
        registry = build_default_registry()
        context = ToolContext(question="Render table")
        context.workspace.add_table(_analysis_table())

        result = registry.execute(
            "artifact_renderer.render",
            {"table_ids": ["sq.primary"], "allowed_artifact_kinds": ["table"]},
            context,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.output["artifact_count"], 1)

    def test_unknown_workspace_table_id_fails_closed(self) -> None:
        registry = build_default_registry()
        result = registry.execute(
            "python_analysis.run",
            {
                "table_ids": ["missing"],
                "operation": {
                    "kind": "rank_extremes",
                    "input_table_id": "missing",
                    "metric": "metric_value",
                },
            },
            ToolContext(question="Rank missing"),
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "tool_execution_failed")

    def test_model_visible_chart_generation_rejects_sandbox_code(self) -> None:
        registry = build_default_registry()
        context = ToolContext(question="Chart it")
        context.workspace.add_table(_analysis_table())

        result = registry.execute(
            "chart_generation.run",
            {
                "table_ids": ["sq.primary"],
                "generation_mode": "sandbox",
                "sandbox_code": "outputs = {}",
            },
            context,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "sandbox_chart_generation_not_model_visible")

    def test_final_numeric_answer_without_evidence_does_not_pass_through(self) -> None:
        result = run_model_tool_loop(
            "Who scored 120?",
            call_model=lambda _prompt: """
            {
              "action": "final",
              "answer": "The Thunder scored 120."
            }
            """,
            registry=fake_registry(),
        )

        self.assertNotEqual(result.answer, "The Thunder scored 120.")
        self.assertIn("grounded evidence", result.answer)

    def test_final_nonnumeric_answer_without_evidence_does_not_pass_through(self) -> None:
        result = run_model_tool_loop(
            "Who was the most balanced team?",
            call_model=lambda _prompt: """
            {
              "action": "final",
              "answer": "The Celtics were the most balanced team."
            }
            """,
            registry=fake_registry(),
        )

        self.assertNotEqual(result.answer, "The Celtics were the most balanced team.")
        self.assertIn("grounded evidence", result.answer)

    @patch("apps.assistant.model_orchestration.tool_loop.compose_grounded_answer")
    def test_final_answer_after_workspace_evidence_uses_composer(self, mock_compose) -> None:
        responses = iter(
            [
                """
                {
                  "action": "tool_call",
                  "tool_name": "semantic_query.plan_execute",
                  "purpose": "retrieve teams",
                  "arguments": {"question": "Show teams by points"}
                }
                """,
                """
                {
                  "action": "final",
                  "answer": "The Thunder scored 120."
                }
                """,
            ]
        )
        mock_compose.return_value = ComposedAnswer(answer="Validated answer", claims=[], limitations=[])

        with patch("apps.assistant.model_orchestration.tool_loop.plan_execute", return_value=_semantic_result()):
            result = run_model_tool_loop(
                "Who scored 120?",
                debug=True,
                call_model=lambda _prompt: next(responses),
                registry=build_default_registry(),
            )

        self.assertEqual(result.answer, "Validated answer")
        mock_compose.assert_called_once()
        trace_tool_names = [call["tool_name"] for call in result.debug["trace"]["tool_calls"]] if result.debug else []
        self.assertIn("answer_composer.compose", trace_tool_names)

    @patch("apps.assistant.model_orchestration.tool_loop.compose_grounded_answer")
    def test_composer_failure_falls_back_to_deterministic_semantic_answer(self, mock_compose) -> None:
        responses = iter(
            [
                """
                {
                  "action": "tool_call",
                  "tool_name": "semantic_query.plan_execute",
                  "purpose": "retrieve teams",
                  "arguments": {"question": "Show teams by points"}
                }
                """,
                """
                {
                  "action": "final",
                  "answer": "The Celtics were the most balanced team."
                }
                """,
            ]
        )
        mock_compose.return_value = ComposedAnswer(answer="Teams by points", claims=[], limitations=[])

        with patch("apps.assistant.model_orchestration.tool_loop.plan_execute", return_value=_semantic_result()):
            result = run_model_tool_loop(
                "Who was best?",
                debug=True,
                call_model=lambda _prompt: next(responses),
                registry=build_default_registry(),
            )

        self.assertEqual(result.answer, "Teams by points")
        self.assertEqual(result.debug["composer_fallback_reason"], "deterministic_tool_answer_fallback")

    @patch("apps.assistant.model_orchestration.tool_loop.compose_grounded_answer")
    def test_composer_failure_with_table_only_returns_safe_message(self, mock_compose) -> None:
        responses = iter(
            [
                """
                {
                  "action": "tool_call",
                  "tool_name": "ontology_catalog.inspect",
                  "purpose": "store a non-semantic table in test workspace",
                  "arguments": {"facets": ["coverage"]}
                }
                """,
                """
                {
                  "action": "final",
                  "answer": "The Celtics were the most balanced team."
                }
                """,
            ]
        )
        mock_compose.return_value = ComposedAnswer(
            answer="I gathered grounded results, but could not validate a final narrative. See the table and artifacts below.",
            claims=[],
            limitations=[],
        )
        registry = ToolRegistry()

        def store_table(_payload, context):
            context.workspace.add_table(_analysis_table(), source_tool_name="test.synthetic")
            return ToolResult(ok=True, tool_name="ontology_catalog.inspect", output={"tables": [{"table_id": "sq.primary"}]})

        registry.register(ToolSpec(name="ontology_catalog.inspect", description="store test table"), store_table)

        def call_model(prompt: str) -> str:
            return next(responses)

        result = run_model_tool_loop("Rank this table", debug=True, call_model=call_model, registry=registry)

        self.assertIn("could not validate a final narrative", result.answer)
        self.assertEqual(result.debug["composer_fallback_reason"], "validated_narrative_unavailable")

    def test_tool_loop_rejects_forbidden_tool(self) -> None:
        with self.assertRaises(ValueError):
            run_model_tool_loop(
                "Run raw SQL",
                call_model=lambda _prompt: """
                {
                  "action": "tool_call",
                  "tool_name": "raw_sql",
                  "purpose": "forbidden",
                  "arguments": {"sql": "SELECT 1"}
                }
                """,
                registry=fake_registry(),
            )

    def test_tool_loop_rejects_non_model_visible_answer_composer_tool(self) -> None:
        with self.assertRaises(ValueError):
            run_model_tool_loop(
                "Compose directly",
                call_model=lambda _prompt: """
                {
                  "action": "tool_call",
                  "tool_name": "answer_composer.compose",
                  "purpose": "direct compose",
                  "arguments": {}
                }
                """,
                registry=build_default_registry(),
            )

    def test_tool_loop_rejects_sql_authoring_payload(self) -> None:
        with self.assertRaises(ValueError):
            run_model_tool_loop(
                "Run SQL through a governed tool",
                call_model=lambda _prompt: """
                {
                  "action": "tool_call",
                  "tool_name": "semantic_query.plan_execute",
                  "purpose": "forbidden SQL",
                  "arguments": {"question": "Run SELECT * FROM team_game"}
                }
                """,
                registry=fake_registry(),
            )

    def test_tool_loop_enforces_max_turns(self) -> None:
        with self.assertRaises(RuntimeError):
            run_model_tool_loop(
                "Keep inspecting forever",
                call_model=lambda _prompt: """
                {
                  "action": "tool_call",
                  "tool_name": "ontology_catalog.inspect",
                  "purpose": "inspect",
                  "arguments": {"facets": ["coverage"]}
                }
                """,
                registry=fake_registry(),
            )

    @patch.dict("os.environ", {"NBA_ENABLE_MODEL_ORCHESTRATOR": "1", "NBA_ENABLE_MODEL_TOOL_LOOP": "1"})
    @patch("apps.assistant.orchestrator.run_model_tool_loop")
    @patch("apps.assistant.orchestrator.plan_question_with_model")
    def test_orchestrator_uses_tool_loop_only_when_gated(self, mock_plan_question, mock_tool_loop) -> None:
        mock_tool_loop.return_value = AssistantResult(answer="loop answer", artifacts=[], debug={})

        result = run_assistant("Use the beta loop")

        self.assertEqual(result.answer, "loop answer")
        mock_tool_loop.assert_called_once()
        mock_plan_question.assert_not_called()


def _analysis_table():
    from runtime.AnalysisTools.models import AnalysisTable, AnalysisTableColumn

    return AnalysisTable(
        id="sq.primary",
        title="Teams by points",
        columns=[
            AnalysisTableColumn(id="entity_name", label="Team", type="text"),
            AnalysisTableColumn(id="metric_value", label="Points", type="number"),
        ],
        rows=[
            {"entity_name": "Thunder", "metric_value": 120.0},
            {"entity_name": "Celtics", "metric_value": 118.0},
        ],
        row_count=2,
    )


def _semantic_result():
    return SimpleNamespace(
        ok=True,
        error=None,
        query_id="sq",
        status="answered",
        result_shape="ranking",
        answer_text="Teams by points",
        artifacts=[],
        assumptions=[],
        provenance={},
        tables=[
            SemanticQueryTable(
                id="sq.primary",
                title="Teams by points",
                columns=[
                    {"id": "entity_name", "label": "Team", "type": "text"},
                    {"id": "metric_value", "label": "Points", "type": "number"},
                ],
                rows=[
                    {"entity_name": "Thunder", "metric_value": 120.0},
                    {"entity_name": "Celtics", "metric_value": 118.0},
                ],
                row_count=2,
                displayed_row_count=2,
            )
        ],
        trace=AssistantTrace(
            question="Show teams by points",
            route="deterministic_fast_path",
            status="ok",
            tool_calls=[
                ToolCallTrace(
                    tool_call_id="tc_semantic",
                    tool_name="semantic_query.plan_execute",
                    status="ok",
                )
            ],
        ),
    )


if __name__ == "__main__":
    unittest.main()
