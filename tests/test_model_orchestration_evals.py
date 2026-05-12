from __future__ import annotations

import json
from pathlib import Path
import unittest

from apps.assistant.model_orchestration.executor import MAX_MODEL_TOOL_CALLS
from apps.assistant.model_orchestration.plans import ModelAnalysisPlan, planned_tool_names


ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = ROOT / "evals" / "model_orchestration_question_bank.json"


class ModelOrchestrationEvalTests(unittest.TestCase):
    def test_model_orchestration_eval_tool_sequences_are_governed(self) -> None:
        cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))

        for case in cases:
            with self.subTest(case=case["name"]):
                plan = ModelAnalysisPlan.model_validate(case["plan"])
                tool_names = planned_tool_names(plan)

                self.assertEqual(tool_names, case["expected_tools"])
                self.assertLessEqual(len(tool_names), case["max_tool_calls"])
                self.assertLessEqual(len(tool_names), MAX_MODEL_TOOL_CALLS)
                self.assertTrue(set(tool_names).isdisjoint(case["forbidden_tools"]))
                self.assertEqual(plan.plan.kind, case.get("expected_plan_kind", plan.plan.kind))


if __name__ == "__main__":
    unittest.main()
