from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.code_sandbox import E2B_BACKEND_ID, SANDBOX_BACKEND_ENV, SANDBOX_ENABLED_ENV
from runtime.AnalysisTools.local_worker import run_analysis_request
from tests.test_python_code_sandbox import SUCCESS_CODE, code_request


LIVE_E2B_ENABLED = (
    os.getenv("NBA_RUN_LIVE_E2B_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}
    and bool(os.getenv("E2B_API_KEY"))
)


@unittest.skipUnless(LIVE_E2B_ENABLED, "live E2B smoke test requires NBA_RUN_LIVE_E2B_TESTS=1 and E2B_API_KEY")
class E2BSandboxLiveTests(unittest.TestCase):
    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1", SANDBOX_BACKEND_ENV: E2B_BACKEND_ID})
    def test_live_e2b_backend_runs_structured_python_code(self) -> None:
        result = run_analysis_request(code_request(SUCCESS_CODE, timeout_ms=5000))

        self.assertTrue(result.ok, result.error.message if result.error else "")
        self.assertEqual(result.metadata["backend_id"], E2B_BACKEND_ID)
        self.assertEqual(result.metadata["sandbox_backend"], "e2b_cloud")
        self.assertTrue(result.metadata["production_ready"])
        self.assertEqual(result.metadata["output_table_ids"], ["analysis.out"])


if __name__ == "__main__":
    unittest.main()
