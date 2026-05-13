# Purpose:
# Define assistant trace and provenance models for governed tool calls.
#
# Uses:
# - deterministic orchestrator and semantic query tool
#
# Produces:
# - JSON-serializable trace records with redacted SQL provenance

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


TRACE_SCHEMA_VERSION = "assistant_trace.v1"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ExecutionStepProvenance(BaseModel):
    step_id: str
    kind: str
    sql_hash: Optional[str] = None
    sql_redacted: bool = True
    row_count: Optional[int] = None
    returned_row_count: Optional[int] = None
    row_limit_requested: Optional[int] = None
    row_limit_enforced: Optional[bool] = None
    truncated: Optional[bool] = None
    execution_ms: Optional[int] = None


class ToolProvenance(BaseModel):
    ontology_path: Optional[str] = None
    snapshot_path: Optional[str] = None
    planner: Optional[str] = None
    planner_mode: Optional[str] = None
    execution_steps: list[ExecutionStepProvenance] = Field(default_factory=list)
    row_limit_requested: Optional[int] = None
    row_limit_enforced: Optional[bool] = None
    default_scope_source: Optional[str] = None
    default_season_year: Optional[str] = None
    default_season_type: Optional[str] = None
    operation_kind: Optional[str] = None
    parent_table_ids: list[str] = Field(default_factory=list)
    output_table_ids: list[str] = Field(default_factory=list)
    derived_from_table_ids: list[str] = Field(default_factory=list)


class ToolCallTrace(BaseModel):
    tool_call_id: str
    tool_name: str
    status: Literal["ok", "failed"]
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    provenance: ToolProvenance = Field(default_factory=ToolProvenance)


class ArtifactTrace(BaseModel):
    artifact_id: str
    kind: str
    source_tool_call_id: Optional[str] = None


class TraceError(BaseModel):
    code: str
    message: str
    stage: Optional[str] = None


class AssistantTrace(BaseModel):
    schema_version: str = TRACE_SCHEMA_VERSION
    run_id: str = Field(default_factory=lambda: new_id("run"))
    created_at: str = Field(default_factory=utc_now_iso)
    question: Optional[str] = None
    route: str
    status: Literal["ok", "failed"]
    assumptions: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    artifacts: list[ArtifactTrace] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[TraceError] = Field(default_factory=list)
    private_debug: Optional[dict[str, Any]] = None


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def safe_trace_summary(trace: AssistantTrace | dict[str, Any]) -> dict[str, Any]:
    payload = model_to_dict(trace) if isinstance(trace, AssistantTrace) else trace
    tool_calls = [
        call
        for call in payload.get("tool_calls", [])
        if isinstance(call, dict)
    ]
    sandbox_backends = []
    sandbox_rejections = []
    sql_steps = []
    tool_durations = []
    chart_validation_failures = []
    chart_generation_modes = []
    for call in tool_calls:
        provenance = call.get("provenance") if isinstance(call.get("provenance"), dict) else {}
        if call.get("tool_name") == "chart_generation.run":
            if provenance.get("generation_mode"):
                chart_generation_modes.append(provenance.get("generation_mode"))
            if call.get("status") == "failed" or provenance.get("validation_status") in {"failed", "fallback_failed"}:
                chart_validation_failures.append(call.get("output", {}).get("error") if isinstance(call.get("output"), dict) else None)
        if provenance.get("sandbox_backend"):
            sandbox_backends.append(provenance.get("sandbox_backend"))
        if call.get("status") == "failed" and provenance.get("operation_kind") == "python_code":
            sandbox_rejections.append(call.get("output", {}).get("error") if isinstance(call.get("output"), dict) else None)
        for step in provenance.get("execution_steps", []) if isinstance(provenance.get("execution_steps"), list) else []:
            if not isinstance(step, dict):
                continue
            sql_steps.append(
                {
                    "kind": step.get("kind"),
                    "sql_hash": step.get("sql_hash"),
                    "sql_redacted": True,
                    "returned_row_count": step.get("returned_row_count"),
                    "row_limit_enforced": step.get("row_limit_enforced"),
                    "truncated": step.get("truncated"),
                    "execution_ms": step.get("execution_ms"),
                }
            )
            if step.get("execution_ms") is not None:
                tool_durations.append({"tool_name": call.get("tool_name"), "execution_ms": step.get("execution_ms")})
    return {
        "schema_version": payload.get("schema_version"),
        "run_id": payload.get("run_id"),
        "route": payload.get("route"),
        "status": payload.get("status"),
        "tool_names": [call.get("tool_name") for call in tool_calls],
        "tool_count": len(tool_calls),
        "artifact_count": len(payload.get("artifacts", []) or []),
        "claim_count": len(payload.get("claims", []) or []),
        "error_codes": [
            error.get("code")
            for error in payload.get("errors", [])
            if isinstance(error, dict)
        ],
        "sql_steps": sql_steps,
        "tool_durations": tool_durations,
        "sandbox_backends": sorted({str(value) for value in sandbox_backends if value}),
        "sandbox_rejections": [value for value in sandbox_rejections if value],
        "chart_generation_modes": sorted({str(value) for value in chart_generation_modes if value}),
        "chart_validation_failures": [value for value in chart_validation_failures if value],
        "has_private_debug": bool(payload.get("private_debug")),
    }
