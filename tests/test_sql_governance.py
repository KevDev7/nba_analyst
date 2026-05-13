from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisRuntime.query_engine import run_sql_result


class SqlGovernanceTests(unittest.TestCase):
    def test_runtime_sql_execution_records_hash_counts_and_row_cap(self) -> None:
        result = run_sql_result("SELECT i FROM range(5) AS t(i)", row_limit=3)

        self.assertTrue(result.sql_hash.startswith("sha256:"))
        self.assertEqual(result.returned_row_count, 3)
        self.assertEqual(len(result.rows), 3)
        self.assertEqual(result.row_limit_requested, 3)
        self.assertTrue(result.row_limit_enforced)
        self.assertTrue(result.truncated)
        self.assertGreaterEqual(result.execution_ms, 0)

    def test_runtime_sql_execution_allows_single_statement_with_trailing_semicolon(self) -> None:
        result = run_sql_result("SELECT 1 AS value;", row_limit=10)

        self.assertEqual(result.rows, [{"value": 1}])
        self.assertFalse(result.truncated)

    def test_runtime_sql_execution_rejects_multi_statement_sql(self) -> None:
        with self.assertRaises(ValueError):
            run_sql_result("SELECT 1; SELECT 2", row_limit=10)


if __name__ == "__main__":
    unittest.main()
