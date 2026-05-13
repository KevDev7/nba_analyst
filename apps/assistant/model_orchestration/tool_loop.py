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
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.assistant.model_orchestration.answer_composer import compose_grounded_answer
from apps.assistant.model_orchestration.plans import ALLOWED_TOOL_NAMES, FORBIDDEN_TOOL_NAMES
from apps.assistant.models import AssistantResult
from apps.assistant.semantic.interpreter import _load_interpreter_json, _strip_json_fences
from apps.assistant.semantic.llm_transport import call_gemini
from apps.assistant.tools.artifact_renderer import ArtifactRenderRequest, render as render_artifacts
from apps.assistant.tools.chart_generation import ChartGenerationRequest, run as run_chart_generation
from apps.assistant.tools.ontology_catalog import OntologyCatalogRequest, inspect as inspect_catalog
from apps.assistant.tools.python_analysis import PythonAnalysisToolRequest, run as run_python_analysis
from apps.assistant.tools.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec
from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute
from apps.assistant.trace import AssistantTrace, ToolCallTrace, ToolProvenance, model_to_dict


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
            if self.tool_name in FORBIDDEN_TOOL_NAMES or self.tool_name not in ALLOWED_TOOL_NAMES:
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
            debug_payload = {"trace": model_to_dict(trace), "model_decisions": model_decisions} if debug else None
            return AssistantResult(answer=decision.answer or "", artifacts=[], debug=debug_payload)
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
    return ToolResult(
        ok=result.ok,
        tool_name="semantic_query.plan_execute",
        output=_summarize_semantic_result(result),
        provenance=model_to_dict(result.provenance),
        error=model_to_dict(result.error) if result.error is not None else None,
    )


def _execute_python_analysis(payload: dict[str, Any], _context: ToolContext) -> ToolResult:
    if _payload_mentions_python_code(payload):
        return ToolResult(
            ok=False,
            tool_name="python_analysis.run",
            error={"code": "python_code_not_allowed_in_tool_loop", "message": "Model tool loop cannot request code mode."},
        )
    result = run_python_analysis(PythonAnalysisToolRequest(**payload))
    return ToolResult(
        ok=result.ok,
        tool_name="python_analysis.run",
        output=_summarize_for_model(result.outputs),
        provenance=result.provenance,
        error=result.error,
    )


def _execute_chart_generation(payload: dict[str, Any], _context: ToolContext) -> ToolResult:
    result = run_chart_generation(ChartGenerationRequest(**payload))
    return ToolResult(
        ok=result.ok,
        tool_name="chart_generation.run",
        output={"artifact_count": result.artifact_count, "artifacts": _artifact_summaries(result.artifacts)},
        provenance=result.provenance,
        error=result.error,
    )


def _execute_artifact_renderer(payload: dict[str, Any], _context: ToolContext) -> ToolResult:
    result = render_artifacts(ArtifactRenderRequest(**payload))
    return ToolResult(
        ok=result.ok,
        tool_name="artifact_renderer.render",
        output={"artifact_count": result.artifact_count, "artifacts": _artifact_summaries(result.artifacts)},
        provenance=result.provenance,
        error=result.error,
    )


def _execute_answer_composer(payload: dict[str, Any], _context: ToolContext) -> ToolResult:
    answer = compose_grounded_answer(
        question=str(payload.get("question") or ""),
        evidence_tables=list(payload.get("evidence_tables") or []),
        findings=list(payload.get("findings") or []),
        artifacts=list(payload.get("artifacts") or []),
        fallback_answer=str(payload.get("fallback_answer") or ""),
    )
    return ToolResult(
        ok=True,
        tool_name="answer_composer.compose",
        output=model_to_dict(answer),
        provenance={"claim_count": len(answer.claims), "limitation_count": len(answer.limitations)},
    )


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
        "tables": _limit_tables([model_to_dict(table) for table in result.tables]),
        "artifact_count": len(result.artifacts),
        "assumptions": result.assumptions,
        "error": model_to_dict(result.error) if result.error is not None else None,
    }


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
