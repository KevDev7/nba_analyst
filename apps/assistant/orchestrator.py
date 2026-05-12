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

import os

from apps.assistant.model_orchestration.executor import dry_run_result, execute_model_plan
from apps.assistant.model_orchestration.planner import ModelPlanError, plan_question_with_model
from apps.assistant.models import AssistantResult
from apps.assistant.routes.period_delta import execute_period_delta_plan, maybe_build_period_delta_plan
from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute


MODEL_ORCHESTRATOR_ENABLED_ENV = "NBA_ENABLE_MODEL_ORCHESTRATOR"
MODEL_ORCHESTRATOR_DRY_RUN_ENV = "NBA_MODEL_ORCHESTRATOR_DRY_RUN"
MODEL_ANSWER_COMPOSER_ENABLED_ENV = "NBA_ENABLE_MODEL_ANSWER_COMPOSER"


def run_assistant(question: str, debug: bool = False) -> AssistantResult:
    if _model_orchestrator_enabled():
        planned = _run_model_orchestrator(question, debug=debug)
        if planned is not None:
            return planned
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


def _run_model_orchestrator(question: str, *, debug: bool) -> AssistantResult | None:
    try:
        plan = plan_question_with_model(question)
    except ModelPlanError:
        return None
    if _model_orchestrator_dry_run():
        return dry_run_result(question, plan)
    try:
        return execute_model_plan(
            question,
            plan,
            debug=debug,
            compose_answer=_model_answer_composer_enabled(),
        )
    except Exception:
        return None


def _model_orchestrator_enabled() -> bool:
    return os.getenv(MODEL_ORCHESTRATOR_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _model_orchestrator_dry_run() -> bool:
    return os.getenv(MODEL_ORCHESTRATOR_DRY_RUN_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _model_answer_composer_enabled() -> bool:
    return os.getenv(MODEL_ANSWER_COMPOSER_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
