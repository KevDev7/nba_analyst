from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute
from runtime.AnalysisRuntime.models import RankingRow
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
        mock_execute_plan.return_value.execution_metadata = [
            {
                "kind": "run_sql",
                "sql_hash": "sha256:runtime",
                "returned_row_count": 1,
                "row_limit_requested": 500,
                "row_limit_enforced": True,
                "truncated": False,
                "execution_ms": 12,
            }
        ]
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
        self.assertEqual(result.provenance.row_limit_requested, 500)
        self.assertTrue(result.provenance.row_limit_enforced)
        step = result.trace.tool_calls[0].provenance.execution_steps[0]
        self.assertEqual(step.sql_hash, "sha256:runtime")
        self.assertEqual(step.returned_row_count, 1)
        self.assertEqual(step.row_limit_requested, 500)
        self.assertTrue(step.row_limit_enforced)
        self.assertFalse(step.truncated)
        self.assertIsNotNone(result.debug)
        self.assertIsNone(result.debug["execution_plan"])
        self.assertTrue(result.debug["execution_plan_redacted"])
        mock_plan_question.assert_called_once_with("Show me top players by points")

    def test_request_requires_exactly_one_question_or_semantic_draft(self) -> None:
        with self.assertRaises(ValueError):
            SemanticQueryRequest(question="Show players", semantic_draft={"task": "rank"})
        with self.assertRaises(ValueError):
            SemanticQueryRequest()

    @patch("apps.assistant.tools.semantic_query.render_artifacts")
    @patch("apps.assistant.tools.semantic_query.format_response", return_value="Formatted answer")
    @patch("apps.assistant.tools.semantic_query.synthesize_answer")
    @patch("apps.assistant.tools.semantic_query.package_results", return_value=object())
    @patch("apps.assistant.tools.semantic_query.execute_plan")
    @patch(
        "apps.assistant.pipeline.plan_question",
        return_value=(SAMPLE_DRAFT, {"execution_plan": SAMPLE_EXECUTION_PLAN}),
    )
    @patch("apps.assistant.tools.semantic_query.load_database")
    def test_tables_are_built_from_final_answer_not_artifacts(
        self,
        _mock_load_database,
        _mock_plan_question,
        mock_execute_plan,
        _mock_package_results,
        mock_synthesize_answer,
        _mock_format_response,
        mock_render_artifacts,
    ) -> None:
        from tests.answer_context_helpers import build_final_answer

        mock_execute_plan.return_value.raw_rows = [{"entity_name": "Jalen Brunson", "metric_value": 312}]
        mock_execute_plan.return_value.execution_metadata = [
            {
                "kind": "run_sql",
                "sql_hash": "sha256:runtime",
                "returned_row_count": 1,
                "row_limit_requested": 500,
                "row_limit_enforced": True,
                "truncated": False,
                "execution_ms": 12,
            }
        ]
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
            rows=[
                RankingRow(rank=1, entity_name="Jalen Brunson", context_value="NYK", metric_value=312),
            ],
        )
        mock_render_artifacts.return_value = SimpleNamespace(
            ok=True,
            artifacts=[{"kind": "text", "role": "summary", "text": "No table artifact here."}],
            error=None,
        )

        result = plan_execute(SemanticQueryRequest(question="Show players", request_id="sq_table"))

        self.assertEqual([artifact["kind"] for artifact in result.artifacts], ["text"])
        self.assertEqual(len(result.tables), 1)
        self.assertEqual(result.tables[0].id, "sq_table.primary")
        self.assertEqual(result.tables[0].rows[0]["entity_name"], "Jalen Brunson")
        self.assertEqual(result.tables[0].provenance["source"], "final_answer")

    @patch("apps.assistant.tools.semantic_query.format_response", return_value="Formatted answer")
    @patch("apps.assistant.tools.semantic_query.synthesize_answer")
    @patch("apps.assistant.tools.semantic_query.package_results", return_value=object())
    @patch("apps.assistant.tools.semantic_query.execute_plan")
    @patch("apps.assistant.pipeline.call_haskell_planner_for_semantic_draft", return_value={"execution_plan": SAMPLE_EXECUTION_PLAN})
    @patch("apps.assistant.pipeline.prepare_semantic_draft", return_value={**SAMPLE_DRAFT, "prepared": True})
    @patch("apps.assistant.tools.semantic_query.load_database")
    def test_raw_semantic_draft_is_prepared_before_haskell_planning(
        self,
        _mock_load_database,
        mock_prepare,
        mock_call_haskell,
        mock_execute_plan,
        _mock_package_results,
        mock_synthesize_answer,
        _mock_format_response,
    ) -> None:
        from tests.answer_context_helpers import build_final_answer

        mock_execute_plan.return_value.raw_rows = []
        mock_synthesize_answer.return_value = build_final_answer(
            summary="Rows are shown below.",
            interpretation="Teams ranked by points.",
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Team",
            entity_label_plural="Teams",
            context_label="",
            metric="average_points",
            window_games=0,
            limit=0,
            rows=[],
        )

        result = plan_execute(
            SemanticQueryRequest(
                semantic_draft=SAMPLE_DRAFT,
                question_context="Show me teams by average points",
                request_id="sq_draft",
            )
        )

        self.assertTrue(result.ok)
        mock_prepare.assert_called_once_with("Show me teams by average points", SAMPLE_DRAFT)
        mock_call_haskell.assert_called_once_with({**SAMPLE_DRAFT, "prepared": True})

    @patch("apps.assistant.tools.semantic_query.format_response", return_value="Formatted answer")
    @patch("apps.assistant.tools.semantic_query.synthesize_answer")
    @patch("apps.assistant.tools.semantic_query.package_results", return_value=object())
    @patch("apps.assistant.tools.semantic_query.execute_plan")
    @patch("apps.assistant.pipeline.call_haskell_planner_for_semantic_draft", return_value={"execution_plan": SAMPLE_EXECUTION_PLAN})
    @patch("apps.assistant.pipeline.prepare_semantic_draft")
    @patch("apps.assistant.tools.semantic_query.load_database")
    def test_prepared_semantic_draft_bypasses_preparation(
        self,
        _mock_load_database,
        mock_prepare,
        mock_call_haskell,
        mock_execute_plan,
        _mock_package_results,
        mock_synthesize_answer,
        _mock_format_response,
    ) -> None:
        from tests.answer_context_helpers import build_final_answer

        mock_execute_plan.return_value.raw_rows = []
        mock_synthesize_answer.return_value = build_final_answer(
            summary="Rows are shown below.",
            interpretation="Teams ranked by points.",
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Team",
            entity_label_plural="Teams",
            context_label="",
            metric="average_points",
            window_games=0,
            limit=0,
            rows=[],
        )

        result = plan_execute(
            SemanticQueryRequest(
                semantic_draft=SAMPLE_DRAFT,
                semantic_draft_state="prepared",
                request_id="sq_prepared",
            )
        )

        self.assertTrue(result.ok)
        mock_prepare.assert_not_called()
        mock_call_haskell.assert_called_once_with(SAMPLE_DRAFT)

    @patch.dict("os.environ", {"NBA_ALLOW_PRIVATE_SQL_TRACE": "1"})
    @patch("apps.assistant.tools.semantic_query.format_response", return_value="Formatted answer")
    @patch("apps.assistant.tools.semantic_query.synthesize_answer")
    @patch("apps.assistant.tools.semantic_query.package_results", return_value=object())
    @patch("apps.assistant.tools.semantic_query.execute_plan")
    @patch("apps.assistant.pipeline.plan_question", return_value=(SAMPLE_DRAFT, {"execution_plan": SAMPLE_EXECUTION_PLAN}))
    @patch("apps.assistant.tools.semantic_query.load_database")
    def test_private_sql_requires_debug_env_gate_and_trusted_caller(
        self,
        _mock_load_database,
        _mock_plan_question,
        mock_execute_plan,
        _mock_package_results,
        mock_synthesize_answer,
        _mock_format_response,
    ) -> None:
        from tests.answer_context_helpers import build_final_answer

        mock_execute_plan.return_value.raw_rows = []
        mock_synthesize_answer.return_value = build_final_answer(
            summary="Rows are shown below.",
            interpretation="Players ranked by points.",
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="",
            metric="total_points",
            window_games=10,
            limit=10,
            rows=[],
        )

        result = plan_execute(
            SemanticQueryRequest(
                question="Show players",
                include_debug=True,
                include_private_sql=True,
                caller="developer_test",
            )
        )

        self.assertIsNotNone(result.trace.private_debug)
        self.assertEqual(result.debug["execution_plan"], SAMPLE_EXECUTION_PLAN)

    @patch.dict("os.environ", {"NBA_ALLOW_PRIVATE_SQL_TRACE": "1"})
    @patch("apps.assistant.tools.semantic_query.format_response", return_value="Formatted answer")
    @patch("apps.assistant.tools.semantic_query.synthesize_answer")
    @patch("apps.assistant.tools.semantic_query.package_results", return_value=object())
    @patch("apps.assistant.tools.semantic_query.execute_plan")
    @patch("apps.assistant.pipeline.plan_question", return_value=(SAMPLE_DRAFT, {"execution_plan": SAMPLE_EXECUTION_PLAN}))
    @patch("apps.assistant.tools.semantic_query.load_database")
    def test_private_sql_rejected_for_untrusted_caller(
        self,
        _mock_load_database,
        _mock_plan_question,
        mock_execute_plan,
        _mock_package_results,
        mock_synthesize_answer,
        _mock_format_response,
    ) -> None:
        from tests.answer_context_helpers import build_final_answer

        mock_execute_plan.return_value.raw_rows = []
        mock_synthesize_answer.return_value = build_final_answer(
            summary="Rows are shown below.",
            interpretation="Players ranked by points.",
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="",
            metric="total_points",
            window_games=10,
            limit=10,
            rows=[],
        )

        result = plan_execute(
            SemanticQueryRequest(
                question="Show players",
                include_debug=True,
                include_private_sql=True,
                caller="orchestrator",
            )
        )

        self.assertIsNone(result.trace.private_debug)
        self.assertIsNone(result.debug["execution_plan"])
        self.assertTrue(result.debug["execution_plan_redacted"])


if __name__ == "__main__":
    unittest.main()
