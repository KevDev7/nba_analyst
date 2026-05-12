from __future__ import annotations

import unittest

from apps.assistant.trace import (
    AssistantTrace,
    ExecutionStepProvenance,
    ToolCallTrace,
    ToolProvenance,
    model_to_dict,
)


class TraceSchemaTests(unittest.TestCase):
    def test_trace_serializes_redacted_sql_provenance(self) -> None:
        trace = AssistantTrace(
            run_id="run_test",
            created_at="2026-05-12T00:00:00Z",
            question="Show top players by points",
            route="deterministic_fast_path",
            status="ok",
            tool_calls=[
                ToolCallTrace(
                    tool_call_id="tc_test",
                    tool_name="semantic_query.plan_execute",
                    status="ok",
                    input={"question": "Show top players by points", "semantic_draft_hash": None},
                    output={"query_id": "sq_test", "result_shape": "ranking", "row_count": 10},
                    provenance=ToolProvenance(
                        planner="ontology-hs",
                        planner_mode="plan-semantic-draft-json",
                        execution_steps=[
                            ExecutionStepProvenance(
                                step_id="sq_test.step_1",
                                kind="run_sql",
                                sql_hash="sha256:abc",
                                sql_redacted=True,
                                row_count=10,
                            )
                        ],
                    ),
                )
            ],
        )

        payload = model_to_dict(trace)

        self.assertEqual(payload["schema_version"], "assistant_trace.v1")
        self.assertEqual(payload["run_id"], "run_test")
        self.assertEqual(payload["route"], "deterministic_fast_path")
        self.assertEqual(payload["tool_calls"][0]["tool_name"], "semantic_query.plan_execute")
        step = payload["tool_calls"][0]["provenance"]["execution_steps"][0]
        self.assertEqual(step["sql_hash"], "sha256:abc")
        self.assertTrue(step["sql_redacted"])
        self.assertNotIn("sql", step)


if __name__ == "__main__":
    unittest.main()
