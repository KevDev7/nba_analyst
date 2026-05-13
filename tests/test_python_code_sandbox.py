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

from apps.assistant.tools.python_analysis import PythonAnalysisToolRequest, run
from runtime.AnalysisTools.code_sandbox import (
    SANDBOX_BACKEND,
    SANDBOX_ENABLED_ENV,
    SANDBOX_PRODUCTION_READY,
    SANDBOX_STATUS,
)
from runtime.AnalysisTools.sandbox_child import CodeValidator, SandboxValidationError
from runtime.AnalysisTools.local_worker import run_analysis_request
from runtime.AnalysisTools.models import AnalysisRequest, AnalysisTable, AnalysisTableColumn


def sample_table() -> AnalysisTable:
    return AnalysisTable(
        id="approved.players",
        title="Approved player table",
        columns=[
            AnalysisTableColumn(id="player", label="Player", type="text"),
            AnalysisTableColumn(id="points", label="Points", type="number"),
        ],
        rows=[
            {"player": "A", "points": 10},
            {"player": "B", "points": 15},
        ],
    )


def code_request(code: str, *, max_output_rows: int = 10, timeout_ms: int = 5000) -> AnalysisRequest:
    return AnalysisRequest(
        runtime="local_sandbox",
        tables=[sample_table()],
        operation={
            "kind": "python_code",
            "code": code,
            "input_table_ids": ["approved.players"],
            "output_tables": [
                {
                    "id": "analysis.out",
                    "title": "Output",
                    "columns": [
                        {"id": "player", "label": "Player", "type": "text"},
                        {"id": "points", "label": "Points", "type": "number"},
                    ],
                }
            ],
            "policy": {
                "max_input_rows": 100,
                "max_output_rows": max_output_rows,
                "timeout_ms": timeout_ms,
            },
        },
    )


SUCCESS_CODE = """
rows = sorted(tables["approved.players"]["rows"], key=lambda row: row["points"], reverse=True)
print("computed", len(rows))
outputs["tables"] = [
  {
    "id": "analysis.out",
    "rows": [{"player": rows[0]["player"], "points": rows[0]["points"]}]
  }
]
outputs["findings"] = [
  {"kind": "ranked_extreme", "text": "B led the table.", "evidence_table_id": "analysis.out", "row_refs": [0]}
]
outputs["metrics"] = [{"id": "top_points", "value": rows[0]["points"]}]
"""


class PythonCodeSandboxStatusTests(unittest.TestCase):
    def test_python_code_sandbox_is_marked_local_beta_only(self) -> None:
        self.assertEqual(SANDBOX_BACKEND, "macos_sandbox_exec")
        self.assertEqual(SANDBOX_STATUS, "local_beta_only")
        self.assertFalse(SANDBOX_PRODUCTION_READY)


class PythonCodeSandboxStaticPolicyTests(unittest.TestCase):
    def assert_rejected_by_static_validator(self, code: str, expected: str) -> None:
        import ast

        with self.assertRaises(SandboxValidationError) as cm:
            CodeValidator({"math", "statistics", "json"}).visit(ast.parse(code, mode="exec"))
        self.assertIn(expected, str(cm.exception))

    def test_static_validator_rejects_database_imports(self) -> None:
        for module in ["duckdb", "sqlite3", "sqlalchemy"]:
            with self.subTest(module=module):
                self.assert_rejected_by_static_validator(f"import {module}\noutputs['tables'] = []", f"Import '{module}' is not allowed")

    def test_static_validator_rejects_sql_authoring_strings(self) -> None:
        self.assert_rejected_by_static_validator("query = 'SELECT * FROM team_game'\noutputs['tables'] = []", "SQL authoring is not allowed")

    def test_static_validator_rejects_database_execute_attributes(self) -> None:
        self.assert_rejected_by_static_validator("client.execute('anything')\noutputs['tables'] = []", "Attribute 'execute' is not allowed")


@unittest.skipUnless(Path("/usr/bin/sandbox-exec").exists(), "python_code sandbox requires macOS sandbox-exec")
class PythonCodeSandboxTests(unittest.TestCase):
    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: ""})
    def test_code_operation_rejected_when_flag_off(self) -> None:
        result = run_analysis_request(code_request(SUCCESS_CODE))

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "sandbox_disabled")

    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1"})
    def test_code_operation_accepts_approved_tables_when_flag_on(self) -> None:
        result = run_analysis_request(code_request(SUCCESS_CODE))

        self.assertTrue(result.ok, result.error.message if result.error else "")
        self.assertEqual(result.tables[0].id, "analysis.out")
        self.assertEqual(result.tables[0].rows[0]["player"], "B")
        self.assertEqual(result.metadata["operation_kind"], "python_code")
        self.assertEqual(result.metadata["parent_table_ids"], ["approved.players"])
        self.assertEqual(result.metadata["output_table_ids"], ["analysis.out"])
        self.assertEqual(result.metadata["sandbox_backend"], "macos_sandbox_exec")
        self.assertEqual(result.metadata["sandbox_status"], "local_beta_only")
        self.assertFalse(result.metadata["production_ready"])
        self.assertTrue(str(result.metadata["code_hash"]).startswith("sha256:"))
        self.assertIn("computed 2", result.metadata["stdout"])

    def test_code_operation_rejects_unknown_input_table(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisRequest(
                runtime="local_sandbox",
                tables=[sample_table()],
                operation={
                    "kind": "python_code",
                    "code": SUCCESS_CODE,
                    "input_table_ids": ["missing"],
                    "output_tables": [{"id": "analysis.out", "columns": [{"id": "player", "label": "Player", "type": "text"}]}],
                },
            )

    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1", "SECRET_TOKEN": "nope"})
    def test_code_cannot_access_environment(self) -> None:
        result = run_analysis_request(code_request("import os\noutputs['tables'] = []"))

        self.assertFalse(result.ok)
        self.assertIn("Import 'os' is not allowed", result.error.message if result.error else "")

    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1"})
    def test_code_cannot_import_duckdb_or_database_modules(self) -> None:
        result = run_analysis_request(code_request("import duckdb\noutputs['tables'] = []"))

        self.assertFalse(result.ok)
        self.assertIn("Import 'duckdb' is not allowed", result.error.message if result.error else "")

    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1"})
    def test_code_cannot_open_files(self) -> None:
        result = run_analysis_request(code_request("open('/etc/passwd').read()\noutputs['tables'] = []"))

        self.assertFalse(result.ok)
        self.assertIn("Call to 'open' is not allowed", result.error.message if result.error else "")

    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1"})
    def test_code_cannot_use_network_imports(self) -> None:
        result = run_analysis_request(code_request("import socket\noutputs['tables'] = []"))

        self.assertFalse(result.ok)
        self.assertIn("Import 'socket' is not allowed", result.error.message if result.error else "")

    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1"})
    def test_timeout_is_enforced(self) -> None:
        result = run_analysis_request(code_request("while True:\n    pass", timeout_ms=100))

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "sandbox_timeout")
        self.assertTrue(result.error.metadata["timed_out"] if result.error else False)

    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1"})
    def test_output_schema_is_enforced(self) -> None:
        result = run_analysis_request(
            code_request(
                "outputs['tables'] = [{'id': 'analysis.out', 'rows': [{'player': 'A', 'points': 10, 'extra': 1}]}]"
            )
        )

        self.assertFalse(result.ok)
        self.assertIn("unknown columns: extra", result.error.message if result.error else "")

    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1"})
    def test_max_output_rows_is_enforced(self) -> None:
        result = run_analysis_request(
            code_request(
                "outputs['tables'] = [{'id': 'analysis.out', 'rows': [{'player': 'A', 'points': 1}, {'player': 'B', 'points': 2}]}]",
                max_output_rows=1,
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "sandbox_output_too_large")

    @patch.dict(os.environ, {SANDBOX_ENABLED_ENV: "1"})
    def test_assistant_wrapper_exposes_code_hash_and_metrics(self) -> None:
        result = run(PythonAnalysisToolRequest(request_id="analysis_code", analysis_request=code_request(SUCCESS_CODE)))

        self.assertTrue(result.ok)
        self.assertEqual(result.analysis_id, "analysis_code")
        self.assertEqual(result.provenance["operation_kind"], "python_code")
        self.assertTrue(result.provenance["code_hash"].startswith("sha256:"))
        self.assertEqual(result.provenance["sandbox_backend"], "macos_sandbox_exec")
        self.assertEqual(result.provenance["sandbox_status"], "local_beta_only")
        self.assertFalse(result.provenance["production_ready"])
        self.assertIn("computed 2", result.provenance["stdout"])
        self.assertEqual(result.outputs["metrics"][0]["id"], "top_points")


if __name__ == "__main__":
    unittest.main()
