from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.assistant.model_orchestration.tool_loop import (
    ToolRegistry,
    ToolResult,
    ToolSpec,
    run_model_tool_loop,
)
from apps.assistant.models import AssistantResult
from apps.assistant.orchestrator import run_assistant
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

        self.assertEqual(result.answer, "Net rating is available in the catalog.")
        trace = result.debug["trace"]
        self.assertEqual(trace["route"], "model_tool_loop_beta")
        self.assertEqual([call["tool_name"] for call in trace["tool_calls"]], ["ontology_catalog.inspect"])
        assert_no_raw_sql_or_private_debug(self, trace)

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


if __name__ == "__main__":
    unittest.main()
