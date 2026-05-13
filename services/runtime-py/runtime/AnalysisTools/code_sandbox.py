from __future__ import annotations

import hashlib
from typing import Any

from .sandbox_backends import (
    E2B_BACKEND_ID,
    E2B_LIVE_TEST_ENV,
    LOCAL_BACKEND_ID,
    LOCAL_RUNTIME_ID,
    LOCAL_SANDBOX_BACKEND,
    LOCAL_SANDBOX_STATUS,
    MOCK_E2B_BACKEND_ID,
    SANDBOX_BACKEND_ENV,
    SANDBOX_ENABLED_ENV,
    get_sandbox_backend,
    sandbox_enabled,
)
from .models import (
    AnalysisFinding,
    AnalysisTable,
    PythonCodeOperation,
)
from .operations import AnalysisOperationError, ControlledOperationResult


SANDBOX_RUNTIME_ID = LOCAL_RUNTIME_ID
SANDBOX_BACKEND = LOCAL_SANDBOX_BACKEND
SANDBOX_STATUS = LOCAL_SANDBOX_STATUS
SANDBOX_PRODUCTION_READY = False


def run_python_code_operation(tables: list[AnalysisTable], operation: PythonCodeOperation) -> ControlledOperationResult:
    code_hash = _code_hash(operation.code)
    try:
        backend = get_sandbox_backend()
    except ValueError as exc:
        raise AnalysisOperationError(
            code="sandbox_backend_unknown",
            message=str(exc),
            metadata={
                "operation_kind": operation.kind,
                "code_hash": code_hash,
                "parent_table_ids": operation.input_table_ids,
                "backend_id": None,
            },
        ) from exc
    if not sandbox_enabled():
        raise AnalysisOperationError(
            code="sandbox_disabled",
            message=f"python_code operations require {SANDBOX_ENABLED_ENV}=1.",
            metadata=_base_metadata(operation, code_hash, backend),
        )
    input_tables = [_table_payload(table) for table in tables if table.id in set(operation.input_table_ids)]
    payload = {
        "code": operation.code,
        "tables": {table["id"]: table for table in input_tables},
        "import_allowlist": operation.policy.import_allowlist,
    }
    execution = backend.run(payload, operation, code_hash)
    if not execution.ok:
        raise AnalysisOperationError(
            code=execution.error_code or "sandbox_execution_failed",
            message=execution.error_message or "python_code operation failed.",
            metadata=execution.base_metadata(),
        )

    outputs = execution.outputs
    if not isinstance(outputs, dict):
        raise AnalysisOperationError(
            code="invalid_sandbox_output",
            message="python_code operation did not return structured outputs.",
            metadata=execution.base_metadata(),
        )

    metadata = execution.base_metadata()
    output_tables = _validate_output_tables(outputs.get("tables", []), operation, metadata)
    findings = _validate_findings(outputs.get("findings", []))
    metrics = outputs.get("metrics", [])
    if not isinstance(metrics, list):
        raise AnalysisOperationError(
            code="invalid_sandbox_output",
            message="python_code metrics output must be a list.",
            metadata=execution.base_metadata(),
        )

    metadata["output_table_ids"] = [table.id for table in output_tables]
    metadata["metrics"] = metrics
    return ControlledOperationResult(
        tables=output_tables,
        findings=findings,
        metadata=metadata,
    )


def _validate_output_tables(raw_tables: Any, operation: PythonCodeOperation, provenance: dict[str, Any]) -> list[AnalysisTable]:
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
                    **provenance,
                    "operation_kind": operation.kind,
                    "parent_table_ids": operation.input_table_ids,
                    "code_hash": _code_hash(operation.code),
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


def _base_metadata(
    operation: PythonCodeOperation,
    code_hash: str,
    backend: Any,
) -> dict[str, Any]:
    return {
        "backend_id": getattr(backend, "backend_id", None),
        "runtime": getattr(backend, "runtime_id", SANDBOX_RUNTIME_ID),
        "sandbox_backend": getattr(backend, "sandbox_backend", SANDBOX_BACKEND),
        "sandbox_status": getattr(backend, "sandbox_status", SANDBOX_STATUS),
        "production_ready": getattr(backend, "production_ready", SANDBOX_PRODUCTION_READY),
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


def _code_hash(code: str) -> str:
    return "sha256:" + hashlib.sha256(code.encode("utf-8")).hexdigest()
