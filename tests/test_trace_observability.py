from __future__ import annotations

import unittest

from apps.assistant.eval_gates import evaluate_trace_gates
from apps.assistant.trace import AssistantTrace, ToolCallTrace, ToolProvenance, ExecutionStepProvenance, safe_trace_summary
from tests.orchestrator_eval_helpers import assert_no_raw_sql_or_private_debug


def sample_trace() -> AssistantTrace:
    return AssistantTrace(
        question="Show top teams by net rating",
        route="deterministic_fast_path",
        status="ok",
        tool_calls=[
            ToolCallTrace(
                tool_call_id="tc_1",
                tool_name="semantic_query.plan_execute",
                status="ok",
                provenance=ToolProvenance(
                    execution_steps=[
                        ExecutionStepProvenance(
                            step_id="step_1",
                            kind="run_sql",
                            sql_hash="sha256:abc",
                            sql_redacted=True,
                            returned_row_count=10,
                            row_limit_enforced=True,
                            truncated=False,
                            execution_ms=12,
                        )
                    ]
                ),
            )
        ],
    )


class TraceObservabilityTests(unittest.TestCase):
    def test_safe_trace_summary_redacts_sql_and_counts_tool_shape(self) -> None:
        summary = safe_trace_summary(sample_trace())

        self.assertEqual(summary["route"], "deterministic_fast_path")
        self.assertEqual(summary["tool_names"], ["semantic_query.plan_execute"])
        self.assertEqual(summary["tool_count"], 1)
        self.assertEqual(summary["sql_steps"][0]["sql_hash"], "sha256:abc")
        self.assertNotIn("sql", summary["sql_steps"][0])
        assert_no_raw_sql_or_private_debug(self, summary)

    def test_eval_gate_passes_expected_trace(self) -> None:
        trace = sample_trace().model_dump()

        result = evaluate_trace_gates(
            trace,
            expected_tools=["semantic_query.plan_execute"],
            max_tool_calls=2,
        )

        self.assertTrue(result.ok, result.failures)

    def test_eval_gate_fails_forbidden_tool_and_private_debug(self) -> None:
        trace = {
            "route": "bad",
            "status": "ok",
            "tool_calls": [{"tool_name": "raw_sql", "status": "ok"}],
            "private_debug": {"execution_plan": {"sql": "SELECT hidden"}},
        }

        result = evaluate_trace_gates(trace)

        self.assertFalse(result.ok)
        self.assertTrue(any("forbidden tools" in failure for failure in result.failures))
        self.assertTrue(any("private debug" in failure for failure in result.failures))


if __name__ == "__main__":
    unittest.main()
