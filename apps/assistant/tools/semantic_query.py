# Purpose:
# Wrap the current ontology-grounded assistant path as a governed semantic query tool.
#
# Uses:
# - existing pipeline planning helpers
# - Python runtime execution
# - answer synthesis and artifact generation
#
# Produces:
# - structured semantic query results plus trace/provenance

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisRuntime.models import ExecutionPlan
from runtime.AnalysisRuntime.runner import execute_plan
from runtime.AnswerSynthesis.format_response import format_response
from runtime.AnswerSynthesis.package_results import package_results
from runtime.AnswerSynthesis.synthesize import synthesize_answer

from apps.assistant.models import AssistantResult
from apps.assistant.predicate_observability import build_predicate_trace
from apps.assistant.trace import (
    AssistantTrace,
    ArtifactTrace,
    ExecutionStepProvenance,
    ToolCallTrace,
    ToolProvenance,
    model_to_dict,
    new_id,
)
from apps.assistant.tools.artifact_renderer import ArtifactRenderRequest, render as render_artifacts
from apps.assistant.value_resolution_observability import build_value_resolution_trace
from scripts.load_gold_snapshot import DB_PATH, load_database


ALLOW_PRIVATE_SQL_ENV = "NBA_ALLOW_PRIVATE_SQL_TRACE"
PRIVATE_SQL_CALLERS = {"developer_test", "local_cli"}


class SemanticQueryRequest(BaseModel):
    request_id: Optional[str] = None
    question: Optional[str] = None
    semantic_draft: Optional[dict[str, Any]] = None
    question_context: Optional[str] = None
    semantic_draft_state: Literal["raw", "prepared"] = "raw"
    mode: Literal["plan_and_execute"] = "plan_and_execute"
    row_limit: int = Field(default=500, ge=1, le=5000)
    include_debug: bool = False
    include_private_sql: bool = False
    caller: str = "orchestrator"

    @model_validator(mode="after")
    def exactly_one_question_or_draft(self) -> "SemanticQueryRequest":
        has_question = bool((self.question or "").strip())
        has_draft = self.semantic_draft is not None
        if has_question == has_draft:
            raise ValueError("Exactly one of question or semantic_draft is required.")
        return self


class SemanticQueryError(BaseModel):
    code: str
    message: str
    stage: Optional[str] = None


class SemanticQueryTable(BaseModel):
    id: str
    title: str
    columns: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    displayed_row_count: int = 0
    provenance: dict[str, Any] = Field(default_factory=dict)


class SemanticQueryProvenance(BaseModel):
    ontology_path: Optional[str] = None
    snapshot_path: Optional[str] = None
    planner: str = "ontology-hs"
    planner_mode: str = "plan-semantic-draft-json"
    execution_steps: list[ExecutionStepProvenance] = Field(default_factory=list)
    row_limit_requested: int = 500
    row_limit_enforced: bool = False


class SemanticQueryResult(BaseModel):
    ok: bool
    query_id: str
    status: Literal["answered", "failed"]
    result_shape: Optional[str] = None
    answer_text: Optional[str] = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[SemanticQueryTable] = Field(default_factory=list)
    answer_context: Optional[dict[str, Any]] = None
    assumptions: list[str] = Field(default_factory=list)
    provenance: SemanticQueryProvenance = Field(default_factory=SemanticQueryProvenance)
    trace: AssistantTrace
    debug: Optional[dict[str, Any]] = None
    error: Optional[SemanticQueryError] = None

    def to_assistant_result(self) -> AssistantResult:
        debug = self.debug
        if debug is not None:
            debug = {**debug, "trace": model_to_dict(self.trace)}
        return AssistantResult(
            answer=self.answer_text or "",
            artifacts=self.artifacts,
            debug=debug,
        )


def plan_execute(request: SemanticQueryRequest) -> SemanticQueryResult:
    query_id = request.request_id or new_id("sq")
    tool_call_id = new_id("tc")
    question = (request.question or "").strip() or None

    try:
        result = _plan_execute_success(
            request=request,
            query_id=query_id,
            tool_call_id=tool_call_id,
            question=question,
        )
        return result
    except Exception as exc:
        trace = AssistantTrace(
            question=question,
            route="deterministic_fast_path",
            status="failed",
            tool_calls=[
                ToolCallTrace(
                    tool_call_id=tool_call_id,
                    tool_name="semantic_query.plan_execute",
                    status="failed",
                    input=_trace_input(request),
                    output={"query_id": query_id},
                )
            ],
            errors=[
                {
                    "code": "semantic_query_failed",
                    "message": str(exc),
                }
            ],
        )
        return SemanticQueryResult(
            ok=False,
            query_id=query_id,
            status="failed",
            trace=trace,
            error=SemanticQueryError(code="semantic_query_failed", message=str(exc)),
        )


def _plan_execute_success(
    *,
    request: SemanticQueryRequest,
    query_id: str,
    tool_call_id: str,
    question: str | None,
) -> SemanticQueryResult:
    # Local import keeps pipeline as the public compatibility boundary without a module cycle.
    from apps.assistant import pipeline

    load_database()
    if request.semantic_draft is not None:
        semantic_draft = dict(request.semantic_draft)
        if request.semantic_draft_state == "raw":
            semantic_draft = pipeline.prepare_semantic_draft(request.question_context or "", semantic_draft)
        planner_output = pipeline.call_haskell_planner_for_semantic_draft(semantic_draft)
    else:
        if question is None:
            raise ValueError("Question is required when semantic_draft is not provided.")
        semantic_draft, planner_output = pipeline.plan_question(question)

    if hasattr(ExecutionPlan, "model_validate"):
        execution_plan = ExecutionPlan.model_validate(planner_output["execution_plan"])
    else:
        execution_plan = ExecutionPlan.parse_obj(planner_output["execution_plan"])

    runtime_result = execute_plan(execution_plan, row_limit=request.row_limit)
    packaged = package_results(runtime_result)
    answer = synthesize_answer(packaged)
    formatted = format_response(answer)
    artifact_result = render_artifacts(ArtifactRenderRequest(question=question or "", answer=answer))
    if not artifact_result.ok:
        message = artifact_result.error.get("message", "Artifact rendering failed.") if artifact_result.error else "Artifact rendering failed."
        raise RuntimeError(message)
    artifacts = artifact_result.artifacts

    answer_context = planner_output.get("execution_plan", {}).get("answer_context")
    result_shape = answer_context.get("result_shape") if isinstance(answer_context, dict) else None
    assumptions = _answer_assumptions(answer_context)
    provenance = SemanticQueryProvenance(
        ontology_path=str(pipeline.ONTOLOGY_PATH),
        snapshot_path=str(DB_PATH),
        row_limit_requested=request.row_limit,
        row_limit_enforced=_row_limit_enforced(runtime_result),
        execution_steps=_execution_step_provenance(query_id, planner_output, runtime_result),
    )
    tables = _tables_from_artifacts(query_id, tool_call_id, artifacts)
    debug = _debug_payload(
        request=request,
        formatted=formatted,
        semantic_draft=semantic_draft,
        planner_output=planner_output,
    )
    trace = AssistantTrace(
        question=question,
        route="deterministic_fast_path",
        status="ok",
        assumptions=assumptions,
        tool_calls=[
            ToolCallTrace(
                tool_call_id=tool_call_id,
                tool_name="semantic_query.plan_execute",
                status="ok",
                input=_trace_input(request),
                output={
                    "query_id": query_id,
                    "result_shape": result_shape,
                    "row_count": len(runtime_result.raw_rows),
                    "artifact_count": len(artifacts),
                    "row_limit_requested": request.row_limit,
                    "row_limit_enforced": provenance.row_limit_enforced,
                },
                provenance=ToolProvenance(**model_to_dict(provenance)),
            )
        ],
        artifacts=[
            ArtifactTrace(
                artifact_id=f"art_{index}",
                kind=str(artifact.get("kind", "")),
                source_tool_call_id=tool_call_id,
            )
            for index, artifact in enumerate(artifacts)
            if isinstance(artifact, dict)
        ],
    )
    if _private_sql_allowed(request):
        trace.private_debug = {
            "execution_plan": planner_output.get("execution_plan"),
        }

    return SemanticQueryResult(
        ok=True,
        query_id=query_id,
        status="answered",
        result_shape=result_shape,
        answer_text=formatted,
        artifacts=artifacts,
        tables=tables,
        answer_context=answer_context if isinstance(answer_context, dict) else None,
        assumptions=assumptions,
        provenance=provenance,
        trace=trace,
        debug=debug,
    )


def _debug_payload(
    *,
    request: SemanticQueryRequest,
    formatted: str,
    semantic_draft: dict[str, Any],
    planner_output: dict[str, Any],
) -> dict[str, Any] | None:
    if not request.include_debug:
        return None
    payload = {
        "query_type": planner_output.get("query_type"),
        "semantic_draft": semantic_draft,
        "query": planner_output.get("query"),
        "resolved_query": planner_output.get("resolved_query"),
        "predicate_trace": build_predicate_trace(semantic_draft, planner_output),
        "value_resolution_trace": build_value_resolution_trace(semantic_draft, planner_output),
        "answer": formatted,
    }
    if _private_sql_allowed(request):
        payload["execution_plan"] = planner_output.get("execution_plan")
    else:
        payload["execution_plan"] = None
        payload["execution_plan_redacted"] = True
    return payload


def _trace_input(request: SemanticQueryRequest) -> dict[str, Any]:
    return {
        "question": request.question,
        "semantic_draft_hash": _stable_hash(request.semantic_draft) if request.semantic_draft is not None else None,
        "semantic_draft_state": request.semantic_draft_state if request.semantic_draft is not None else None,
        "mode": request.mode,
        "row_limit": request.row_limit,
        "caller": request.caller,
    }


def _private_sql_allowed(request: SemanticQueryRequest) -> bool:
    enabled = os.getenv(ALLOW_PRIVATE_SQL_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    return (
        request.include_private_sql
        and request.include_debug
        and enabled
        and request.caller in PRIVATE_SQL_CALLERS
    )


def _execution_step_provenance(
    query_id: str,
    planner_output: dict[str, Any],
    runtime_result: Any,
) -> list[ExecutionStepProvenance]:
    execution = planner_output.get("execution_plan", {}).get("execution", {})
    steps = execution.get("steps", []) if isinstance(execution, dict) else []
    runtime_metadata = [
        metadata
        for metadata in getattr(runtime_result, "execution_metadata", [])
        if isinstance(metadata, dict) and metadata.get("kind") == "run_sql"
    ]
    sql_metadata_index = 0
    step_provenance: list[ExecutionStepProvenance] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        is_sql = step.get("kind") == "run_sql"
        metadata = runtime_metadata[sql_metadata_index] if is_sql and sql_metadata_index < len(runtime_metadata) else {}
        if is_sql:
            sql_metadata_index += 1
        step_provenance.append(
            ExecutionStepProvenance(
                step_id=f"{query_id}.step_{index}",
                kind=str(step.get("kind", "")),
                sql_hash=str(metadata.get("sql_hash")) if metadata.get("sql_hash") is not None else None,
                sql_redacted=True,
                row_count=int(metadata.get("returned_row_count")) if metadata.get("returned_row_count") is not None else None,
                returned_row_count=int(metadata.get("returned_row_count")) if metadata.get("returned_row_count") is not None else None,
                row_limit_requested=int(metadata.get("row_limit_requested")) if metadata.get("row_limit_requested") is not None else None,
                row_limit_enforced=bool(metadata.get("row_limit_enforced")) if metadata.get("row_limit_enforced") is not None else None,
                truncated=bool(metadata.get("truncated")) if metadata.get("truncated") is not None else None,
                execution_ms=int(metadata.get("execution_ms")) if metadata.get("execution_ms") is not None else None,
            )
        )
    return step_provenance


def _row_limit_enforced(runtime_result: Any) -> bool:
    return any(
        bool(metadata.get("row_limit_enforced"))
        for metadata in getattr(runtime_result, "execution_metadata", [])
        if isinstance(metadata, dict)
    )


def _tables_from_artifacts(
    query_id: str,
    tool_call_id: str,
    artifacts: list[dict[str, Any]],
) -> list[SemanticQueryTable]:
    tables: list[SemanticQueryTable] = []
    for index, artifact in enumerate(artifacts):
        if artifact.get("kind") != "table":
            continue
        rows = [row for row in artifact.get("rows", []) if isinstance(row, dict)]
        tables.append(
            SemanticQueryTable(
                id=f"{query_id}.table_{index}",
                title=str(artifact.get("title") or ""),
                columns=[column for column in artifact.get("columns", []) if isinstance(column, dict)],
                rows=rows,
                row_count=int(artifact.get("row_count") or len(rows)),
                displayed_row_count=int(artifact.get("displayed_row_count") or len(rows)),
                provenance={
                    "query_id": query_id,
                    "source_tool_call_id": tool_call_id,
                },
            )
        )
    return tables


def _answer_assumptions(answer_context: object) -> list[str]:
    if not isinstance(answer_context, dict):
        return []
    assumptions = answer_context.get("assumptions", [])
    return [str(assumption) for assumption in assumptions] if isinstance(assumptions, list) else []


def _stable_hash(value: object) -> str:
    payload = str(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
