# Purpose:
# Run a gated iterative model/tool loop over governed assistant tools.
#
# Uses:
# - plain JSON tool specs
# - existing assistant tool wrappers
# - capped model turns and tool calls
#
# Produces:
# - AssistantResult values with trace/debug metadata, never raw SQL context

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from apps.assistant.model_orchestration.answer_composer import compose_grounded_answer
from apps.assistant.model_orchestration.plans import ALLOWED_TOOL_NAMES, FORBIDDEN_TOOL_NAMES
from apps.assistant.models import AssistantResult
from apps.assistant.semantic.interpreter import _load_interpreter_json, _strip_json_fences
from apps.assistant.semantic.llm_transport import call_gemini
from apps.assistant.tools.artifact_renderer import ArtifactRenderRequest, render as render_artifacts
from apps.assistant.tools.chart_generation import ChartGenerationRequest, run as run_chart_generation
from apps.assistant.tools.ontology_catalog import OntologyCatalogRequest, inspect as inspect_catalog
from apps.assistant.tools.python_analysis import PythonAnalysisToolRequest, run as run_python_analysis
from apps.assistant.tools.registry import MODEL_VISIBLE_TOOL_NAMES, ToolContext, ToolRegistry, ToolResult, ToolSpec
from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute
from apps.assistant.trace import AssistantTrace, ToolCallTrace, ToolProvenance, model_to_dict, new_id
from runtime.AnalysisTools.models import AnalysisFinding, AnalysisRequest, AnalysisTable, AnalysisTableColumn


MODEL_TOOL_LOOP_ENABLED_ENV = "NBA_ENABLE_MODEL_TOOL_LOOP"
MAX_LOOP_TURNS = 4
MAX_LOOP_TOOL_CALLS = 6
MAX_MODEL_VISIBLE_ROWS = 20
FORBIDDEN_SQL_AUTHORING_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bselect\b[\s\S]{0,120}\bfrom\b",
        r"\bwith\b[\s\S]{0,120}\bas\b",
        r"\b(insert\s+into|update\s+\w+\s+set|delete\s+from|drop\s+table|alter\s+table|create\s+table|copy\s+|attach\s+|pragma\s+|load\s+|install\s+)\b",
        r"\b(raw\s+sql|write\s+sql|generate\s+sql|author\s+sql|repair\s+sql|transform\s+sql)\b",
        r"\b(repair|fix|transform|rewrite)\b[\s\S]{0,40}\bsql\b",
        r"\b(inspect|list|show)\b[\s\S]{0,40}\b(warehouse|database)\b",
        r"\b(query|inspect|connect\s+to|access)\s+(duckdb|sqlite|database|warehouse)\b",
        r"\b(duckdb|sqlite_master|sqlite|sqlalchemy)\b",
    ]
]


class LoopDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    tool_name: Optional[str] = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    purpose: Optional[str] = None
    answer: Optional[str] = None

    @model_validator(mode="after")
    def validate_decision(self) -> "LoopDecision":
        if self.action == "tool_call":
            if not self.tool_name:
                raise ValueError("tool_call decisions require tool_name.")
            if self.tool_name in FORBIDDEN_TOOL_NAMES or self.tool_name not in MODEL_VISIBLE_TOOL_NAMES:
                raise ValueError(f"Tool '{self.tool_name}' is not allowed.")
            if _payload_mentions_forbidden_capability(self.arguments):
                raise ValueError("Tool arguments reference a forbidden raw capability.")
            return self
        if self.action == "final":
            if not self.answer:
                raise ValueError("final decisions require answer.")
            return self
        raise ValueError("Loop decision action must be tool_call or final.")


def model_tool_loop_enabled() -> bool:
    return os.getenv(MODEL_TOOL_LOOP_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def run_model_tool_loop(
    question: str,
    *,
    debug: bool = False,
    call_model: Callable[[str], str] = call_gemini,
    registry: Optional[ToolRegistry] = None,
) -> AssistantResult:
    registry = registry or build_default_registry()
    context = ToolContext(question=question, debug=debug)
    trace = AssistantTrace(question=question, route="model_tool_loop_beta", status="ok")
    model_decisions: list[dict[str, Any]] = []
    tool_outputs: list[dict[str, Any]] = []

    for turn_index in range(MAX_LOOP_TURNS):
        decision = _parse_decision(call_model(_loop_prompt(question, registry.specs, tool_outputs)))
        model_decisions.append(model_to_dict(decision))
        if decision.action == "final":
            return _finalize_with_workspace_evidence(
                question,
                decision,
                context,
                trace,
                model_decisions,
                debug=debug,
            )
        if len(trace.tool_calls) >= MAX_LOOP_TOOL_CALLS:
            raise RuntimeError("Model tool loop exceeded max tool calls.")
        result = registry.execute(decision.tool_name or "", decision.arguments, context)
        trace.tool_calls.append(_tool_call_trace(result, decision))
        if not result.ok:
            raise RuntimeError(result.error.get("message", "Tool call failed.") if result.error else "Tool call failed.")
        tool_outputs.append(
            {
                "turn": turn_index,
                "tool_name": result.tool_name,
                "output": _summarize_for_model(result.output),
            }
        )
    raise RuntimeError("Model tool loop exceeded max turns.")


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry(
        allowed_tools=ALLOWED_TOOL_NAMES,
        forbidden_tools=FORBIDDEN_TOOL_NAMES,
        forbidden_payload_checker=_payload_mentions_forbidden_capability,
    )
    registry.register(
        ToolSpec(
            name="ontology_catalog.inspect",
            description="Inspect ontology-backed subjects, fact surfaces, metrics, filters, and coverage.",
        ),
        _execute_catalog,
    )
    registry.register(
        ToolSpec(
            name="semantic_query.plan_execute",
            description="Run an ontology-grounded semantic query through Haskell and the governed runtime.",
        ),
        _execute_semantic_query,
    )
    registry.register(
        ToolSpec(
            name="python_analysis.run",
            description="Run controlled derived analysis over approved result tables.",
        ),
        _execute_python_analysis,
    )
    registry.register(
        ToolSpec(
            name="chart_generation.run",
            description="Create validated Vega-Lite chart artifacts from approved result tables.",
        ),
        _execute_chart_generation,
    )
    registry.register(
        ToolSpec(
            name="artifact_renderer.render",
            description="Render validated text/table/chart artifacts from grounded answer or analysis tables.",
        ),
        _execute_artifact_renderer,
    )
    registry.register(
        ToolSpec(
            name="answer_composer.compose",
            description="Compose final narrative from structured evidence and validated artifacts.",
            model_visible=False,
        ),
        _execute_answer_composer,
    )
    return registry


def _execute_catalog(payload: dict[str, Any], _context: ToolContext) -> ToolResult:
    result = inspect_catalog(OntologyCatalogRequest(**payload))
    return ToolResult(
        ok=result.ok,
        tool_name="ontology_catalog.inspect",
        output=_summarize_for_model(model_to_dict(result)),
        error=model_to_dict(result.error) if result.error is not None else None,
    )


def _execute_semantic_query(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    request = SemanticQueryRequest(
        **{
            **payload,
            "include_debug": False,
            "include_private_sql": False,
            "caller": "model_tool_loop",
        }
    )
    result = plan_execute(request)
    for table in result.tables:
        context.workspace.add_table(
            _analysis_table_from_semantic_table(table),
            source_tool_call_id=result.trace.tool_calls[0].tool_call_id if result.trace.tool_calls else None,
            source_tool_name="semantic_query.plan_execute",
            metadata={"query_id": result.query_id},
        )
    for artifact in result.artifacts:
        context.workspace.add_artifact(
            artifact,
            source_tool_call_id=result.trace.tool_calls[0].tool_call_id if result.trace.tool_calls else None,
            source_tool_name="semantic_query.plan_execute",
            parent_ids=[table.id for table in result.tables],
        )
    return ToolResult(
        ok=result.ok,
        tool_name="semantic_query.plan_execute",
        output=_summarize_semantic_result(result),
        provenance=_as_dict(result.provenance),
        error=model_to_dict(result.error) if result.error is not None else None,
    )


def _execute_python_analysis(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if _payload_mentions_python_code(payload):
        return ToolResult(
            ok=False,
            tool_name="python_analysis.run",
            error={"code": "python_code_not_allowed_in_tool_loop", "message": "Model tool loop cannot request code mode."},
        )
    result = run_python_analysis(PythonAnalysisToolRequest(analysis_request=_analysis_request_from_workspace(payload, context)))
    for table_payload in result.outputs.get("tables", []):
        table = _analysis_table_from_payload(table_payload)
        context.workspace.add_table(
            table,
            source_tool_call_id=None,
            source_tool_name="python_analysis.run",
            parent_ids=result.provenance.get("parent_table_ids", []),
            metadata={"analysis_id": result.analysis_id, "operation_kind": result.provenance.get("operation_kind")},
        )
    for index, finding_payload in enumerate(result.outputs.get("findings", [])):
        try:
            finding = AnalysisFinding(**finding_payload)
        except Exception:
            continue
        context.workspace.add_finding(
            finding,
            finding_id=f"{result.analysis_id}.finding_{index}",
            source_tool_name="python_analysis.run",
            parent_ids=result.provenance.get("parent_table_ids", []),
        )
    for artifact in result.outputs.get("artifacts", []):
        context.workspace.add_artifact(
            artifact,
            source_tool_name="python_analysis.run",
            parent_ids=result.provenance.get("parent_table_ids", []),
        )
    return ToolResult(
        ok=result.ok,
        tool_name="python_analysis.run",
        output={
            "tables": [_table_handle(context.workspace.resolve_table(table_id)) for table_id in result.provenance.get("output_table_ids", [])],
            "artifact_count": len(result.outputs.get("artifacts", [])),
            "finding_count": len(result.outputs.get("findings", [])),
            "analysis_id": result.analysis_id,
        },
        provenance=result.provenance,
        error=result.error,
    )


def _execute_chart_generation(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if "sandbox_code" in payload or payload.get("generation_mode") == "sandbox":
        return ToolResult(
            ok=False,
            tool_name="chart_generation.run",
            error={"code": "sandbox_chart_generation_not_model_visible", "message": "Model-visible chart generation cannot request sandbox code mode."},
        )
    if payload.get("generation_mode") not in {None, "deterministic", "model"}:
        return ToolResult(
            ok=False,
            tool_name="chart_generation.run",
            error={"code": "unsupported_chart_generation_mode", "message": "Model-visible chart generation supports deterministic mode, plus gated model mode."},
        )
    payload = {**payload, "tables": [model_to_dict(table) for table in _resolve_payload_tables(payload, context)]}
    if payload.get("generation_mode") is None:
        payload["generation_mode"] = "deterministic"
    result = run_chart_generation(ChartGenerationRequest(**payload))
    for artifact in result.artifacts:
        context.workspace.add_artifact(
            artifact,
            source_tool_call_id=result.provenance.get("tool_call_id"),
            source_tool_name="chart_generation.run",
            parent_ids=result.provenance.get("parent_table_ids", []),
            metadata={"generation_mode": result.provenance.get("generation_mode")},
        )
    return ToolResult(
        ok=result.ok,
        tool_name="chart_generation.run",
        output={"artifact_count": result.artifact_count, "artifacts": _artifact_summaries(result.artifacts)},
        provenance=result.provenance,
        error=result.error,
    )


def _execute_artifact_renderer(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if "table_ids" in payload and "tables" not in payload:
        payload = {**payload, "tables": [model_to_dict(table) for table in context.workspace.resolve_tables(payload.get("table_ids") or [])]}
    result = render_artifacts(ArtifactRenderRequest(**payload))
    for artifact in result.artifacts:
        context.workspace.add_artifact(
            artifact,
            source_tool_name="artifact_renderer.render",
            parent_ids=list(payload.get("table_ids") or []),
        )
    return ToolResult(
        ok=result.ok,
        tool_name="artifact_renderer.render",
        output={"artifact_count": result.artifact_count, "artifacts": _artifact_summaries(result.artifacts)},
        provenance=result.provenance,
        error=result.error,
    )


def _execute_answer_composer(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    evidence_tables = list(payload.get("evidence_tables") or [])
    if not evidence_tables:
        evidence_tables = [model_to_dict(table) for table in context.workspace.tables.values()]
    findings = list(payload.get("findings") or [])
    if not findings:
        findings = [model_to_dict(finding) for finding in context.workspace.findings.values()]
    artifacts = list(payload.get("artifacts") or [])
    if not artifacts:
        artifacts = list(context.workspace.artifacts.values())
    answer = compose_grounded_answer(
        question=str(payload.get("question") or ""),
        evidence_tables=evidence_tables,
        findings=findings,
        artifacts=artifacts,
        fallback_answer=str(payload.get("fallback_answer") or ""),
    )
    return ToolResult(
        ok=True,
        tool_name="answer_composer.compose",
        output=model_to_dict(answer),
        provenance={"claim_count": len(answer.claims), "limitation_count": len(answer.limitations)},
    )


def _finalize_with_workspace_evidence(
    question: str,
    decision: LoopDecision,
    context: ToolContext,
    trace: AssistantTrace,
    model_decisions: list[dict[str, Any]],
    *,
    debug: bool,
) -> AssistantResult:
    fallback_answer = _safe_final_fallback(decision.answer or "")
    if not context.workspace.tables:
        answer = "I need grounded evidence from a governed retrieval before giving a final answer."
        trace.tool_calls.append(
            ToolCallTrace(
                tool_call_id=new_id("tc"),
                tool_name="answer_composer.compose",
                status="failed",
                input={"workspace_table_count": 0},
                output={"fallback_reason": "missing_workspace_evidence"},
                provenance=ToolProvenance(composer_fallback_reason="missing_workspace_evidence"),
            )
        )
        debug_payload = {
            "trace": model_to_dict(trace),
            "model_decisions": model_decisions,
            "composer_fallback_reason": "missing_workspace_evidence",
        } if debug else None
        return AssistantResult(answer=answer, artifacts=list(context.workspace.artifacts.values()), debug=debug_payload)
    composed = compose_grounded_answer(
        question=question,
        evidence_tables=[model_to_dict(table) for table in context.workspace.tables.values()],
        findings=[model_to_dict(finding) for finding in context.workspace.findings.values()],
        artifacts=list(context.workspace.artifacts.values()),
        fallback_answer=fallback_answer,
    )
    fallback_reason = "no_valid_claims" if composed.answer == fallback_answer and not composed.claims else None
    trace.tool_calls.append(
        ToolCallTrace(
            tool_call_id=new_id("tc"),
            tool_name="answer_composer.compose",
            status="ok",
            input={"workspace_table_count": len(context.workspace.tables)},
            output={"claim_count": len(composed.claims), "limitation_count": len(composed.limitations)},
            provenance=ToolProvenance(composer_fallback_reason=fallback_reason),
        )
    )
    trace.claims = [model_to_dict(claim) for claim in composed.claims]
    debug_payload = {
        "trace": model_to_dict(trace),
        "model_decisions": model_decisions,
        "claims": [model_to_dict(claim) for claim in composed.claims],
        "limitations": composed.limitations,
        "composer_fallback_reason": fallback_reason,
    } if debug else None
    return AssistantResult(answer=composed.answer, artifacts=list(context.workspace.artifacts.values()), debug=debug_payload)


def _parse_decision(raw_text: str) -> LoopDecision:
    payload = _load_interpreter_json(_strip_json_fences(raw_text))
    return LoopDecision.model_validate(payload) if hasattr(LoopDecision, "model_validate") else LoopDecision.parse_obj(payload)


def _loop_prompt(question: str, specs: list[ToolSpec], tool_outputs: list[dict[str, Any]]) -> str:
    payload = {
        "question": question,
        "allowed_tools": [model_to_dict(spec) for spec in specs if spec.model_visible],
        "previous_tool_outputs": tool_outputs,
    }
    return f"""
You are an NBA analytics orchestrator. Choose the next governed tool call or produce a final answer.

Return JSON only in one of these shapes:
{{"action":"tool_call","tool_name":"semantic_query.plan_execute","purpose":"...","arguments":{{...}}}}
{{"action":"final","answer":"..."}}

Rules:
- Use only allowed_tools.
- Haskell is the only SQL author forever; express retrieval only as semantic tool requests.
- Never write SQL, repair SQL, transform SQL, include SQL snippets, inspect warehouse tables, or ask for DuckDB/database access.
- Never write Python code.
- Never request raw_sql, raw_python, arbitrary_python, sql.execute, python_code, or duckdb.execute.
- Keep tool arguments small and grounded in the question or prior tool outputs.

Payload:
{json.dumps(payload, sort_keys=True)}
""".strip()


def _tool_call_trace(result: ToolResult, decision: LoopDecision) -> ToolCallTrace:
    return ToolCallTrace(
        tool_call_id=result.tool_call_id,
        tool_name=result.tool_name,
        status="ok" if result.ok else "failed",
        input={"purpose": decision.purpose, "arguments_hash": _stable_hash(decision.arguments)},
        output=_summarize_for_model(result.output),
        provenance=ToolProvenance(**_tool_provenance_fields(result.provenance)),
    )


def _tool_provenance_fields(provenance: dict[str, Any]) -> dict[str, Any]:
    allowed = set(ToolProvenance.model_fields) if hasattr(ToolProvenance, "model_fields") else set(ToolProvenance.__fields__)
    return {key: value for key, value in provenance.items() if key in allowed}


def _summarize_semantic_result(result: Any) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "query_id": result.query_id,
        "status": result.status,
        "result_shape": result.result_shape,
        "answer_text": result.answer_text,
        "tables": [_semantic_table_handle(table) for table in result.tables],
        "artifact_count": len(result.artifacts),
        "assumptions": result.assumptions,
        "error": model_to_dict(result.error) if result.error is not None else None,
    }


def _analysis_table_from_semantic_table(table: Any) -> AnalysisTable:
    return AnalysisTable(
        id=str(table.id),
        title=str(table.title or ""),
        columns=[
            AnalysisTableColumn(
                id=str(column.get("id")),
                label=str(column.get("label") or column.get("id")),
                type=column.get("type") or "text",
            )
            for column in table.columns
            if isinstance(column, dict)
        ],
        rows=[row for row in table.rows if isinstance(row, dict)],
        row_count=int(table.row_count or len(table.rows)),
        metadata={"source_table_id": str(table.id), **(table.provenance if isinstance(table.provenance, dict) else {})},
    )


def _analysis_table_from_payload(payload: dict[str, Any]) -> AnalysisTable:
    return AnalysisTable(
        id=str(payload["id"]),
        title=str(payload.get("title") or ""),
        columns=[
            AnalysisTableColumn(
                id=str(column["id"]),
                label=str(column.get("label") or column["id"]),
                type=column.get("type") or "text",
            )
            for column in payload.get("columns", [])
            if isinstance(column, dict)
        ],
        rows=[row for row in payload.get("rows", []) if isinstance(row, dict)],
        row_count=int(payload.get("row_count") or len(payload.get("rows", []))),
        metadata=payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {},
    )


def _semantic_table_handle(table: Any) -> dict[str, Any]:
    analysis_table = _analysis_table_from_semantic_table(table)
    return _table_handle(analysis_table)


def _table_handle(table: AnalysisTable) -> dict[str, Any]:
    return {
        "table_id": table.id,
        "title": table.title,
        "columns": [model_to_dict(column) for column in table.columns],
        "row_count": int(table.row_count if table.row_count is not None else len(table.rows)),
        "sample_rows": table.rows[: min(len(table.rows), 5)],
    }


def _analysis_request_from_workspace(payload: dict[str, Any], context: ToolContext) -> AnalysisRequest:
    if "analysis_request" in payload:
        request_payload = dict(payload["analysis_request"])
        table_ids = request_payload.pop("table_ids", None) or payload.get("table_ids")
        if table_ids is not None:
            request_payload["tables"] = [model_to_dict(table) for table in context.workspace.resolve_tables(table_ids)]
        return AnalysisRequest(**request_payload)
    table_ids = payload.get("table_ids")
    if not table_ids:
        raise ValueError("python_analysis.run requires analysis_request or table_ids.")
    return AnalysisRequest(
        runtime=payload.get("runtime", "local_trusted"),
        tables=context.workspace.resolve_tables(table_ids),
        operation=payload.get("operation"),
        metadata=payload.get("metadata", {}),
    )


def _resolve_payload_tables(payload: dict[str, Any], context: ToolContext) -> list[AnalysisTable]:
    table_ids = payload.get("table_ids")
    if table_ids:
        return context.workspace.resolve_tables(table_ids)
    return [AnalysisTable(**table) if isinstance(table, dict) else table for table in payload.get("tables", [])]


def _safe_final_fallback(answer_hint: str) -> str:
    numeric_tokens = re.findall(r"(?<![A-Za-z0-9])[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?(?![A-Za-z0-9])", answer_hint)
    if numeric_tokens:
        return "I could not validate the final numeric answer against the gathered evidence."
    return answer_hint or "I could not validate a grounded final answer from the gathered evidence."


def _summarize_for_model(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _summarize_for_model(child)
            for key, child in value.items()
            if key not in {"debug", "private_debug", "execution_plan", "sql", "code"}
        }
    if isinstance(value, list):
        return [_summarize_for_model(child) for child in value[:MAX_MODEL_VISIBLE_ROWS]]
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {}


def _limit_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    limited = []
    for table in tables:
        rows = table.get("rows", [])
        limited.append(
            {
                **table,
                "rows": rows[:MAX_MODEL_VISIBLE_ROWS] if isinstance(rows, list) else rows,
                "displayed_row_count": min(len(rows), MAX_MODEL_VISIBLE_ROWS) if isinstance(rows, list) else table.get("displayed_row_count"),
            }
        )
    return limited


def _artifact_summaries(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"kind": artifact.get("kind"), "title": artifact.get("title"), "role": artifact.get("role")}
        for artifact in artifacts
        if isinstance(artifact, dict)
    ]


def _payload_mentions_forbidden_capability(payload: Any) -> bool:
    text = json.dumps(payload, sort_keys=True).lower()
    return any(token in text for token in FORBIDDEN_TOOL_NAMES) or any(
        pattern.search(text) for pattern in FORBIDDEN_SQL_AUTHORING_PATTERNS
    )


def _payload_mentions_python_code(payload: Any) -> bool:
    return "python_code" in json.dumps(payload, sort_keys=True).lower()


def _stable_hash(value: object) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode('utf-8')).hexdigest()}"
