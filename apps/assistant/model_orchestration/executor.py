# Purpose:
# Execute feature-gated model orchestration plans over governed tools.
#
# Uses:
# - validated ModelAnalysisPlan
# - existing deterministic route/tool boundaries
#
# Produces:
# - AssistantResult plus trace/debug metadata

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.models import AnalysisTable, AnalysisTableColumn

from apps.assistant.model_orchestration.answer_composer import compose_grounded_answer
from apps.assistant.model_orchestration.planner import dry_run_payload
from apps.assistant.model_orchestration.plans import (
    ArtifactRequestPlan,
    ModelAnalysisPlan,
    SimpleSemanticQueryPlan,
    UnsupportedPlan,
    planned_tool_names,
)
from apps.assistant.models import AssistantResult
from apps.assistant.routes.correlation import CorrelationPlan, execute_correlation_plan
from apps.assistant.routes.period_delta import PeriodDeltaPlan, execute_period_delta_plan
from apps.assistant.tools.chart_generation import ChartGenerationRequest, run as run_chart_generation
from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute
from apps.assistant.trace import AssistantTrace, ToolCallTrace, ToolProvenance, model_to_dict, new_id


MAX_MODEL_TOOL_CALLS = 6


def dry_run_result(question: str, plan: ModelAnalysisPlan) -> AssistantResult:
    payload = dry_run_payload(question, plan)
    return AssistantResult(
        answer="Model orchestration dry run produced a validated plan.",
        artifacts=[
            {"kind": "text", "role": "summary", "text": "Model orchestration dry run produced a validated plan."},
            {"kind": "text", "role": "orchestration_plan", "text": json.dumps(payload, sort_keys=True)},
        ],
        debug={"model_orchestration": payload},
    )


def execute_model_plan(question: str, plan: ModelAnalysisPlan, *, debug: bool = False, compose_answer: bool = False) -> AssistantResult:
    tool_names = planned_tool_names(plan)
    if len(tool_names) > MAX_MODEL_TOOL_CALLS:
        return _fallback_error("Model plan requested too many tool calls.", question, plan, debug)
    if isinstance(plan.plan, UnsupportedPlan):
        return AssistantResult(
            answer=plan.plan.reason,
            artifacts=[{"kind": "text", "role": "summary", "text": plan.plan.reason}],
            debug={"model_plan": model_to_dict(plan)} if debug else None,
        )
    if isinstance(plan.plan, SimpleSemanticQueryPlan):
        return _execute_simple_semantic_query(question, plan, debug=debug)
    if isinstance(plan.plan, ArtifactRequestPlan):
        return _execute_artifact_request(question, plan, debug=debug)
    if isinstance(plan.plan, PeriodDeltaPlan):
        result = execute_period_delta_plan(question, plan.plan, debug=debug)
        if compose_answer:
            result = _compose_from_result(question, plan, result)
        return result
    if isinstance(plan.plan, CorrelationPlan):
        result = execute_correlation_plan(question, plan.plan, debug=debug)
        if compose_answer:
            result = _compose_from_result(question, plan, result)
        return result
    return _fallback_error("Model plan kind is not executable.", question, plan, debug)


def _execute_simple_semantic_query(question: str, plan: ModelAnalysisPlan, *, debug: bool) -> AssistantResult:
    assert isinstance(plan.plan, SimpleSemanticQueryPlan)
    result = plan_execute(
        SemanticQueryRequest(
            question=plan.plan.question,
            include_debug=debug,
            caller="model_orchestrator",
        )
    )
    if not result.ok and result.error is not None:
        raise RuntimeError(result.error.message)
    assistant_result = result.to_assistant_result()
    if debug:
        return AssistantResult(
            answer=assistant_result.answer,
            artifacts=assistant_result.artifacts,
            debug={
                **(assistant_result.debug or {}),
                "model_plan": model_to_dict(plan),
                "trace": model_to_dict(_trace_for_semantic_result(question, plan, result)),
            },
        )
    return assistant_result


def _execute_artifact_request(question: str, plan: ModelAnalysisPlan, *, debug: bool) -> AssistantResult:
    assert isinstance(plan.plan, ArtifactRequestPlan)
    result = plan_execute(
        SemanticQueryRequest(
            question=plan.plan.question,
            include_debug=debug,
            caller="model_orchestrator",
        )
    )
    if not result.ok and result.error is not None:
        raise RuntimeError(result.error.message)
    assistant_result = result.to_assistant_result()
    chart_artifacts: list[dict[str, Any]] = []
    if plan.plan.artifact_intent in {"chart", "table_and_chart"} and result.tables:
        chart_result = run_chart_generation(
            ChartGenerationRequest(
                question=question,
                tables=[_analysis_table_from_semantic_table(result.tables[0])],
                chart_intent=plan.plan.artifact_intent,
            )
        )
        if chart_result.ok:
            chart_artifacts = chart_result.artifacts
            assistant_result = AssistantResult(
                answer=assistant_result.answer,
                artifacts=[*chart_artifacts, *assistant_result.artifacts],
                debug=assistant_result.debug,
            )
    if debug:
        return AssistantResult(
            answer=assistant_result.answer,
            artifacts=assistant_result.artifacts,
            debug={
                **(assistant_result.debug or {}),
                "model_plan": model_to_dict(plan),
                "trace": model_to_dict(
                    _trace_for_semantic_result(
                        question,
                        plan,
                        result,
                        include_chart_step=bool(chart_artifacts),
                        include_artifact_step=True,
                    )
                ),
            },
        )
    return assistant_result


def _compose_from_result(question: str, plan: ModelAnalysisPlan, result: AssistantResult) -> AssistantResult:
    tables = [_evidence_table(artifact) for artifact in result.artifacts if isinstance(artifact, dict) and artifact.get("kind") == "table"]
    composed = compose_grounded_answer(
        question=question,
        evidence_tables=tables,
        findings=[],
        artifacts=result.artifacts,
        fallback_answer=result.answer,
    )
    return AssistantResult(
        answer=composed.answer,
        artifacts=result.artifacts,
        debug={
            **(result.debug or {}),
            "model_plan": model_to_dict(plan),
            "claims": [model_to_dict(claim) for claim in composed.claims],
            "limitations": composed.limitations,
        },
    )


def _evidence_table(artifact: dict[str, Any]) -> dict[str, Any]:
    if artifact.get("id"):
        return artifact
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
    table_id = metadata.get("source_table_id") or artifact.get("title") or "table"
    return {**artifact, "id": str(table_id)}


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
        ],
        rows=[row for row in table.rows if isinstance(row, dict)],
        row_count=int(table.row_count or len(table.rows)),
        metadata={"source_table_id": str(table.id)},
    )


def _trace_for_semantic_result(
    question: str,
    plan: ModelAnalysisPlan,
    result: Any,
    *,
    include_chart_step: bool = False,
    include_artifact_step: bool = False,
) -> AssistantTrace:
    tool_calls = [
        *result.trace.tool_calls,
    ]
    if include_chart_step:
        tool_calls.append(
            ToolCallTrace(
                tool_call_id=new_id("tc"),
                tool_name="chart_generation.run",
                status="ok",
                input={"source_table_ids": [result.tables[0].id] if result.tables else []},
                output={"artifact_kind": "chart"},
                provenance=ToolProvenance(parent_table_ids=[result.tables[0].id] if result.tables else []),
            )
        )
    if include_artifact_step:
        tool_calls.append(
            ToolCallTrace(
                tool_call_id=new_id("tc"),
                tool_name="artifact_renderer.render",
                status="ok",
                input={"artifact_request": True},
                output={"artifact_count": len(result.artifacts)},
                provenance=ToolProvenance(),
            )
        )
    return AssistantTrace(question=question, route="model_orchestrator", status="ok", tool_calls=tool_calls)


def _fallback_error(message: str, question: str, plan: ModelAnalysisPlan, debug: bool) -> AssistantResult:
    return AssistantResult(
        answer=message,
        artifacts=[{"kind": "text", "role": "summary", "text": message}],
        debug={"question": question, "model_plan": model_to_dict(plan)} if debug else None,
    )
