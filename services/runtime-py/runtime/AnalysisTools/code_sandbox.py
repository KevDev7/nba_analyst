from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .models import (
    AnalysisFinding,
    AnalysisTable,
    PythonCodeOperation,
)
from .operations import AnalysisOperationError, ControlledOperationResult


SANDBOX_ENABLED_ENV = "NBA_ENABLE_PYTHON_CODE_SANDBOX"
SANDBOX_RUNTIME_ID = "local_python_code_sandbox:v1"
SANDBOX_BACKEND = "macos_sandbox_exec"
SANDBOX_STATUS = "local_beta_only"
SANDBOX_PRODUCTION_READY = False


def run_python_code_operation(tables: list[AnalysisTable], operation: PythonCodeOperation) -> ControlledOperationResult:
    code_hash = _code_hash(operation.code)
    if not _sandbox_enabled():
        raise AnalysisOperationError(
            code="sandbox_disabled",
            message=f"python_code operations require {SANDBOX_ENABLED_ENV}=1.",
            metadata=_base_metadata(operation, code_hash),
        )
    sandbox_exec = shutil.which("sandbox-exec")
    if sandbox_exec is None:
        raise AnalysisOperationError(
            code="sandbox_unavailable",
            message="python_code operations require /usr/bin/sandbox-exec on this local runtime.",
            metadata=_base_metadata(operation, code_hash),
        )

    input_tables = [_table_payload(table) for table in tables if table.id in set(operation.input_table_ids)]
    payload = {
        "code": operation.code,
        "tables": {table["id"]: table for table in input_tables},
        "import_allowlist": operation.policy.import_allowlist,
    }
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="nba-analysis-sandbox-") as scratch:
        command = [
            sandbox_exec,
            "-p",
            _sandbox_profile(scratch),
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).with_name("sandbox_child.py")),
        ]
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=operation.policy.timeout_ms / 1000,
                cwd=scratch,
                env={"PYTHONNOUSERSITE": "1"},
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AnalysisOperationError(
                code="sandbox_timeout",
                message="python_code operation exceeded its timeout.",
                metadata=_metadata(operation, code_hash, int((time.monotonic() - started) * 1000), stdout=exc.stdout, stderr=exc.stderr, timed_out=True),
            ) from exc

    execution_ms = int((time.monotonic() - started) * 1000)
    result = _decode_child_result(completed, operation, code_hash, execution_ms)
    if not result.get("ok"):
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        raise AnalysisOperationError(
            code=str(error.get("code") or "sandbox_execution_failed"),
            message=str(error.get("message") or "python_code operation failed."),
            metadata=_metadata(operation, code_hash, execution_ms, stdout=result.get("stdout"), stderr=result.get("stderr")),
        )

    outputs = result.get("outputs")
    if not isinstance(outputs, dict):
        raise AnalysisOperationError(
            code="invalid_sandbox_output",
            message="python_code operation did not return structured outputs.",
            metadata=_metadata(operation, code_hash, execution_ms, stdout=result.get("stdout"), stderr=result.get("stderr")),
        )

    output_tables = _validate_output_tables(outputs.get("tables", []), operation)
    findings = _validate_findings(outputs.get("findings", []))
    metrics = outputs.get("metrics", [])
    if not isinstance(metrics, list):
        raise AnalysisOperationError(
            code="invalid_sandbox_output",
            message="python_code metrics output must be a list.",
            metadata=_metadata(operation, code_hash, execution_ms, stdout=result.get("stdout"), stderr=result.get("stderr")),
        )

    metadata = _metadata(operation, code_hash, execution_ms, stdout=result.get("stdout"), stderr=result.get("stderr"))
    metadata["output_table_ids"] = [table.id for table in output_tables]
    metadata["metrics"] = metrics
    return ControlledOperationResult(
        tables=output_tables,
        findings=findings,
        metadata=metadata,
    )


def _validate_output_tables(raw_tables: Any, operation: PythonCodeOperation) -> list[AnalysisTable]:
    if not isinstance(raw_tables, list):
        raise AnalysisOperationError(
            code="invalid_sandbox_output",
            message="python_code tables output must be a list.",
            metadata={"operation_kind": operation.kind},
        )
    schemas = {schema.id: schema for schema in operation.output_tables}
    output_tables: list[AnalysisTable] = []
    for raw_table in raw_tables:
        if not isinstance(raw_table, dict):
            raise AnalysisOperationError(code="invalid_sandbox_output", message="Each output table must be an object.")
        table_id = raw_table.get("id")
        schema = schemas.get(str(table_id))
        if schema is None:
            raise AnalysisOperationError(code="invalid_sandbox_output", message=f"Output table '{table_id}' was not declared.")
        rows = raw_table.get("rows", [])
        if not isinstance(rows, list):
            raise AnalysisOperationError(code="invalid_sandbox_output", message=f"Output table '{table_id}' rows must be a list.")
        if len(rows) > operation.policy.max_output_rows:
            raise AnalysisOperationError(code="sandbox_output_too_large", message=f"Output table '{table_id}' exceeds max_output_rows.")
        column_ids = {column.id for column in schema.columns}
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise AnalysisOperationError(code="invalid_sandbox_output", message=f"Output row {index} in '{table_id}' must be an object.")
            missing = sorted(column_ids - set(row))
            unknown = sorted(set(row) - column_ids)
            if missing or unknown:
                details = []
                if missing:
                    details.append(f"missing columns: {', '.join(missing)}")
                if unknown:
                    details.append(f"unknown columns: {', '.join(unknown)}")
                raise AnalysisOperationError(code="invalid_sandbox_output", message=f"Output row {index} in '{table_id}' has {'; '.join(details)}.")
        output_tables.append(
            AnalysisTable(
                id=schema.id,
                title=str(raw_table.get("title") or schema.title),
                columns=schema.columns,
                rows=rows,
                row_count=len(rows),
                metadata={
                    "operation_kind": operation.kind,
                    "parent_table_ids": operation.input_table_ids,
                    "code_hash": _code_hash(operation.code),
                    "sandbox_backend": SANDBOX_BACKEND,
                    "sandbox_status": SANDBOX_STATUS,
                    "production_ready": SANDBOX_PRODUCTION_READY,
                    **operation.metadata,
                },
            )
        )
    return output_tables


def _validate_findings(raw_findings: Any) -> list[AnalysisFinding]:
    if raw_findings in (None, []):
        return []
    if not isinstance(raw_findings, list):
        raise AnalysisOperationError(code="invalid_sandbox_output", message="python_code findings output must be a list.")
    return [AnalysisFinding.model_validate(finding) for finding in raw_findings]


def _decode_child_result(
    completed: subprocess.CompletedProcess[str],
    operation: PythonCodeOperation,
    code_hash: str,
    execution_ms: int,
) -> dict[str, Any]:
    if completed.returncode != 0 and not completed.stdout:
        raise AnalysisOperationError(
            code="sandbox_process_failed",
            message="python_code sandbox process failed before returning structured output.",
            metadata=_metadata(operation, code_hash, execution_ms, stdout=completed.stdout, stderr=completed.stderr),
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AnalysisOperationError(
            code="invalid_sandbox_output",
            message="python_code sandbox did not return JSON.",
            metadata=_metadata(operation, code_hash, execution_ms, stdout=completed.stdout, stderr=completed.stderr),
        ) from exc
    if completed.stderr:
        result["stderr"] = f"{result.get('stderr', '')}{completed.stderr}"
    return result


def _metadata(
    operation: PythonCodeOperation,
    code_hash: str,
    execution_ms: int,
    *,
    stdout: Any = "",
    stderr: Any = "",
    timed_out: bool = False,
) -> dict[str, Any]:
    return {
        **_base_metadata(operation, code_hash),
        "timeout_ms": operation.policy.timeout_ms,
        "execution_ms": execution_ms,
        "timed_out": timed_out,
        "stdout": stdout or "",
        "stderr": stderr or "",
    }


def _base_metadata(operation: PythonCodeOperation, code_hash: str) -> dict[str, Any]:
    return {
        "runtime": SANDBOX_RUNTIME_ID,
        "sandbox_backend": SANDBOX_BACKEND,
        "sandbox_status": SANDBOX_STATUS,
        "production_ready": SANDBOX_PRODUCTION_READY,
        "operation_kind": operation.kind,
        "code_hash": code_hash,
        "parent_table_ids": operation.input_table_ids,
        "derived_from_table_ids": operation.input_table_ids,
    }


def _table_payload(table: AnalysisTable) -> dict[str, Any]:
    return {
        "id": table.id,
        "title": table.title,
        "columns": [column.model_dump() if hasattr(column, "model_dump") else column.dict() for column in table.columns],
        "rows": table.rows,
        "row_count": table.row_count if table.row_count is not None else len(table.rows),
        "metadata": table.metadata,
    }


def _sandbox_profile(scratch: str) -> str:
    escaped = scratch.replace("\\", "\\\\").replace('"', '\\"')
    return f"""
(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "{escaped}"))
""".strip()


def _sandbox_enabled() -> bool:
    return os.getenv(SANDBOX_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _code_hash(code: str) -> str:
    return "sha256:" + hashlib.sha256(code.encode("utf-8")).hexdigest()
