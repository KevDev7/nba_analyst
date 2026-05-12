# Purpose:
# Own the assistant request lifecycle above governed tools.
#
# Uses:
# - semantic_query.plan_execute fast path
# - deterministic route modules for governed multi-call prototypes
#
# Produces:
# - AssistantResult values for pipeline/web/CLI compatibility

from __future__ import annotations

from apps.assistant.models import AssistantResult
from apps.assistant.routes.period_delta import execute_period_delta_plan, maybe_build_period_delta_plan
from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute


def run_assistant(question: str, debug: bool = False) -> AssistantResult:
    period_delta_plan = maybe_build_period_delta_plan(question)
    if period_delta_plan is not None:
        return execute_period_delta_plan(question, period_delta_plan, debug=debug)
    return _run_fast_path(question, debug=debug)


def _run_fast_path(question: str, *, debug: bool) -> AssistantResult:
    result = plan_execute(
        SemanticQueryRequest(
            question=question,
            include_debug=debug,
            caller="orchestrator",
        )
    )
    if not result.ok and result.error is not None:
        raise RuntimeError(result.error.message)
    return result.to_assistant_result()
