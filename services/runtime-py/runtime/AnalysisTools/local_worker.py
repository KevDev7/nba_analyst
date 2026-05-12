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
    try:
        operation_result = run_controlled_operation(request.tables, request.operation)
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
        tables=operation_result.tables,
        artifacts=operation_result.artifacts,
        findings=operation_result.findings,
        logs=[
            AnalysisLog(
                message="Ran controlled analysis operation with local trusted Python worker.",
                metadata={
                    "operation_kind": request.operation.kind,
                    **operation_result.metadata,
                },
            )
        ],
        metadata={"runtime": request.runtime, **operation_result.metadata},
    )
