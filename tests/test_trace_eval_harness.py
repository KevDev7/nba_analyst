from __future__ import annotations

from pathlib import Path
import unittest

from tests.orchestrator_eval_helpers import (
    assert_artifact_kinds,
    assert_claims_have_evidence,
    assert_expected_tool_sequence,
    assert_forbidden_tools_absent,
    assert_no_raw_sql_or_private_debug,
    load_eval_cases,
)


ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = ROOT / "evals" / "orchestrator_trace_eval_bank.json"


class TraceEvalHarnessTests(unittest.TestCase):
    def test_trace_eval_bank_covers_required_categories(self) -> None:
        cases = load_eval_cases(EVAL_PATH)
        categories = {case["category"] for case in cases}

        self.assertTrue(
            {"simple", "multi_step", "unsupported", "adversarial", "artifact", "sandbox"}.issubset(categories)
        )

    def test_trace_eval_cases_enforce_governed_tool_policy(self) -> None:
        for case in load_eval_cases(EVAL_PATH):
            with self.subTest(case=case["name"]):
                trace = case["trace"]
                self.assertEqual(trace["route"], case["expected_route"])
                assert_expected_tool_sequence(self, trace, case["expected_tools"])
                assert_forbidden_tools_absent(self, trace, case["forbidden_tools"])
                assert_no_raw_sql_or_private_debug(self, trace)
                assert_artifact_kinds(self, trace.get("artifacts", []), case["expected_artifacts"])
                if case.get("require_claim_evidence"):
                    assert_claims_have_evidence(self, trace)


if __name__ == "__main__":
    unittest.main()
