# Purpose:
# Execute controlled analysis operations in the local trusted Python runtime.
#
# Uses:
# - AnalysisRequest contracts from models.py
# - controlled operations from operations.py
#
# Produces:
# - AnalysisResult objects with chart artifacts, logs, or structured errors
#
# Next:
# - future assistant/runtime wiring that calls this tool boundary

from __future__ import annotations

from .models import AnalysisLog, AnalysisRequest, AnalysisResult, AnalysisToolError
from .operations import AnalysisOperationError, run_controlled_operation


def run_analysis_request(request: AnalysisRequest) -> AnalysisResult:
    table = _input_table_for_request(request)
    try:
        artifact = run_controlled_operation(table, request.operation)
    except AnalysisOperationError as exc:
        return AnalysisResult(
            ok=False,
            logs=[
                AnalysisLog(
                    level="error",
                    message=exc.message,
                    metadata=exc.metadata,
                )
            ],
            error=AnalysisToolError(
                code=exc.code,
                message=exc.message,
                metadata=exc.metadata,
            ),
            metadata={"runtime": request.runtime},
        )

    return AnalysisResult(
        ok=True,
        artifacts=[artifact],
        logs=[
            AnalysisLog(
                message="Built chart artifact with local trusted Python worker.",
                metadata={
                    "operation_kind": request.operation.kind,
                    "source_table_id": table.id,
                },
            )
        ],
        metadata={"runtime": request.runtime},
    )


def _input_table_for_request(request: AnalysisRequest):
    for table in request.tables:
        if table.id == request.operation.input_table_id:
            return table
    raise ValueError(f"Operation references unknown table: {request.operation.input_table_id}")
