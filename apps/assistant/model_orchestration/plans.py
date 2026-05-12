# Purpose:
# Define validated model-produced orchestration plans.
#
# Uses:
# - Pydantic discriminated unions
# - governed assistant tool names only
#
# Produces:
# - structured plans that contain no SQL or Python code

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.assistant.routes.period_delta import PeriodDeltaPlan


ALLOWED_TOOL_NAMES = {
    "ontology_catalog.inspect",
    "semantic_query.plan_execute",
    "python_analysis.run",
    "artifact_renderer.render",
}
FORBIDDEN_TOOL_NAMES = {"raw_sql", "raw_python", "arbitrary_python", "sql.execute", "python_code", "duckdb.execute"}
UNSUPPORTED_SURFACES = {"play_by_play", "play-by-play", "lineups", "on_off", "on-off", "clutch", "shot_location", "shot-location"}


class StrictPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SimpleSemanticQueryPlan(StrictPlanModel):
    kind: Literal["simple_semantic_query"]
    question: str
    presentation: Optional[dict[str, Any]] = None


class ArtifactRequestPlan(StrictPlanModel):
    kind: Literal["artifact_request"]
    question: str
    artifact_intent: Literal["table", "chart", "table_and_chart"] = "table_and_chart"


class UnsupportedPlan(StrictPlanModel):
    kind: Literal["unsupported"]
    reason: str
    unsupported_surface: Optional[str] = None


AnalysisPlan = Union[SimpleSemanticQueryPlan, PeriodDeltaPlan, ArtifactRequestPlan, UnsupportedPlan]


class ToolPlanStep(StrictPlanModel):
    tool_name: str
    purpose: str

    @model_validator(mode="after")
    def validate_tool_name(self) -> "ToolPlanStep":
        if self.tool_name in FORBIDDEN_TOOL_NAMES or self.tool_name not in ALLOWED_TOOL_NAMES:
            raise ValueError(f"Tool '{self.tool_name}' is not allowed in model orchestration.")
        return self


class ModelAnalysisPlan(StrictPlanModel):
    plan: AnalysisPlan = Field(discriminator="kind")
    tool_sequence: list[ToolPlanStep] = Field(default_factory=list, max_length=8)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plan_safety(self) -> "ModelAnalysisPlan":
        payload = _string_payload(self)
        if any(token in payload for token in FORBIDDEN_TOOL_NAMES):
            raise ValueError("Model plan includes a forbidden raw SQL or Python tool reference.")
        if isinstance(self.plan, UnsupportedPlan):
            return self
        if any(surface in payload for surface in UNSUPPORTED_SURFACES):
            raise ValueError("Model plan references an unsupported data surface.")
        return self


def planned_tool_names(plan: ModelAnalysisPlan) -> list[str]:
    if plan.tool_sequence:
        return [step.tool_name for step in plan.tool_sequence]
    if isinstance(plan.plan, SimpleSemanticQueryPlan):
        return ["semantic_query.plan_execute"]
    if isinstance(plan.plan, PeriodDeltaPlan):
        return [
            "semantic_query.plan_execute",
            "semantic_query.plan_execute",
            "python_analysis.run",
            "artifact_renderer.render",
        ]
    if isinstance(plan.plan, ArtifactRequestPlan):
        return ["semantic_query.plan_execute", "artifact_renderer.render"]
    return []


def _string_payload(model: BaseModel) -> str:
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json().lower()
    return model.json().lower()
