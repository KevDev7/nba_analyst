from __future__ import annotations

import unittest

from apps.assistant.eval_gates import evaluate_trace_gates
from scripts.run_architecture_gates import main as run_architecture_gates


class ReleaseGateTests(unittest.TestCase):
    def test_architecture_gate_runner_passes_current_eval_banks(self) -> None:
        self.assertEqual(run_architecture_gates(), 0)

    def test_eval_gate_detects_forbidden_tool_failure(self) -> None:
        result = evaluate_trace_gates(
            {
                "route": "bad",
                "status": "ok",
                "tool_calls": [{"tool_name": "raw_sql", "status": "ok"}],
            }
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("forbidden tools" in failure for failure in result.failures))


if __name__ == "__main__":
    unittest.main()
