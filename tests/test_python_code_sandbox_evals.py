from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = ROOT / "evals" / "python_code_sandbox_question_bank.json"


class PythonCodeSandboxEvalTests(unittest.TestCase):
    def test_python_code_sandbox_eval_policy(self) -> None:
        cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))

        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertNotIn("raw_python", [case.get("allowed_tool")])
                self.assertNotIn("raw_sql", [case.get("allowed_tool")])
                self.assertIn("raw_python", case["forbidden_tools"])
                self.assertIn("raw_sql", case["forbidden_tools"])
                if case.get("allowed_operation_kind") == "python_code":
                    self.assertEqual(case["allowed_tool"], "python_analysis.run")
                    self.assertTrue(case["requires_python_code_sandbox"])
                if case.get("preferred_operation_kind") == "join_and_delta":
                    self.assertFalse(case["requires_python_code_sandbox"])
                if case.get("forbidden_operation_kind") == "python_code":
                    self.assertIsNone(case["allowed_tool"])


if __name__ == "__main__":
    unittest.main()
