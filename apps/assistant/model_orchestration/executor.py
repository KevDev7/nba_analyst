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
from typing import Any

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
from apps.assistant.routes.period_delta import PeriodDeltaPlan, execute_period_delta_plan
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
    if debug:
        return AssistantResult(
            answer=assistant_result.answer,
            artifacts=assistant_result.artifacts,
            debug={
                **(assistant_result.debug or {}),
                "model_plan": model_to_dict(plan),
                "trace": model_to_dict(_trace_for_semantic_result(question, plan, result, include_artifact_step=True)),
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


def _trace_for_semantic_result(question: str, plan: ModelAnalysisPlan, result: Any, *, include_artifact_step: bool = False) -> AssistantTrace:
    tool_calls = [
        *result.trace.tool_calls,
    ]
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
