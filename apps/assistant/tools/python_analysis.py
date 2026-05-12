# Purpose:
# Expose controlled Python analysis as an assistant tool over approved tables.
#
# Uses:
# - runtime.AnalysisTools typed request contracts
# - local trusted controlled-operation worker
#
# Produces:
# - structured derived tables/artifacts/findings with provenance

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.local_worker import run_analysis_request
from runtime.AnalysisTools.models import AnalysisRequest

from apps.assistant.trace import model_to_dict, new_id


class PythonAnalysisToolRequest(BaseModel):
    request_id: Optional[str] = None
    analysis_request: AnalysisRequest


class PythonAnalysisToolResult(BaseModel):
    ok: bool
    analysis_id: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    logs: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    error: Optional[dict[str, Any]] = None


def run(request: PythonAnalysisToolRequest) -> PythonAnalysisToolResult:
    analysis_id = request.request_id or new_id("analysis")
    result = run_analysis_request(request.analysis_request)
    parent_table_ids = [table.id for table in request.analysis_request.tables]
    operation = request.analysis_request.operation
    return PythonAnalysisToolResult(
        ok=result.ok,
        analysis_id=analysis_id,
        outputs={
            "tables": [model_to_dict(table) for table in result.tables],
            "artifacts": [model_to_dict(artifact) for artifact in result.artifacts],
            "findings": [model_to_dict(finding) for finding in result.findings],
        },
        logs=[model_to_dict(log) for log in result.logs],
        provenance={
            "runtime": request.analysis_request.runtime,
            "operation_kind": operation.kind,
            "parent_table_ids": parent_table_ids,
            "tool": "python_analysis.run",
        },
        error=model_to_dict(result.error) if result.error is not None else None,
    )
