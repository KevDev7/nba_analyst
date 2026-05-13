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
