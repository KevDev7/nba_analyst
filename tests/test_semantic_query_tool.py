from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute
from tests.test_cli_pipeline import SAMPLE_DRAFT, SAMPLE_EXECUTION_PLAN


class SemanticQueryToolTests(unittest.TestCase):
    @patch("apps.assistant.tools.semantic_query.format_response", return_value="Formatted answer")
    @patch("apps.assistant.tools.semantic_query.synthesize_answer")
    @patch("apps.assistant.tools.semantic_query.package_results", return_value=object())
    @patch("apps.assistant.tools.semantic_query.execute_plan")
    @patch(
        "apps.assistant.pipeline.plan_question",
        return_value=(SAMPLE_DRAFT, {"execution_plan": SAMPLE_EXECUTION_PLAN}),
    )
    @patch("apps.assistant.tools.semantic_query.load_database")
    def test_plan_execute_wraps_current_pipeline_with_trace(
        self,
        _mock_load_database,
        mock_plan_question,
        mock_execute_plan,
        _mock_package_results,
        mock_synthesize_answer,
        _mock_format_response,
    ) -> None:
        from tests.answer_context_helpers import build_final_answer

        mock_execute_plan.return_value.raw_rows = [{"entity_name": "Jalen Brunson"}]
        mock_synthesize_answer.return_value = build_final_answer(
            summary="Rows are shown below.",
            interpretation="Players ranked by total points.",
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="total_points",
            window_games=10,
            limit=10,
            rows=[],
        )

        result = plan_execute(
            SemanticQueryRequest(
                question="Show me top players by points",
                request_id="sq_test",
                include_debug=True,
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.query_id, "sq_test")
        self.assertEqual(result.answer_text, "Formatted answer")
        self.assertEqual(result.result_shape, "ranking")
        self.assertEqual(result.trace.route, "deterministic_fast_path")
        self.assertEqual(result.trace.tool_calls[0].tool_name, "semantic_query.plan_execute")
        self.assertEqual(result.trace.tool_calls[0].provenance.execution_steps[0].kind, "run_sql")
        self.assertTrue(result.trace.tool_calls[0].provenance.execution_steps[0].sql_redacted)
        self.assertIsNotNone(result.debug)
        mock_plan_question.assert_called_once_with("Show me top players by points")

    def test_request_requires_exactly_one_question_or_semantic_draft(self) -> None:
        with self.assertRaises(ValueError):
            SemanticQueryRequest(question="Show players", semantic_draft={"task": "rank"})
        with self.assertRaises(ValueError):
            SemanticQueryRequest()


if __name__ == "__main__":
    unittest.main()
