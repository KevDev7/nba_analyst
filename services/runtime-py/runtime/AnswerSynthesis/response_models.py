# Purpose:
# Define typed final-answer payloads for the live slices.
#
# Uses:
# - packaged runtime results from package_results.py
#
# Produces:
# - a grounded final answer model
#
# Next:
# - format_response.py

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from runtime.AnalysisRuntime.models import (
    AggregateRow,
    ComparisonResult,
    ObjectRow,
    PlanDisplayMetadata,
    PlanDisplayMetric,
    PlanFindFilter,
    PlanFindOrder,
    PlanGroupingColumn,
    RankingRow,
    RuntimeResult,
    TimeSeriesRow,
)


class SynthesisPayload(BaseModel):
    # Typed handoff from result packaging into answer synthesis.
    # Plain English: preserve the runtime result shape without turning it into
    # a loose dict and then rebuilding the same typed rows one file later.
    query_kind: str
    result_shape: str
    entity_label_singular: str
    entity_label_plural: str
    context_label: str
    metric: str
    metric_order_direction: str = "DESC"
    window_games: int
    time_grain: Optional[str] = None
    time_filter: Optional[str] = None
    time_window_days: Optional[int] = None
    time_start_date: Optional[str] = None
    time_end_date: Optional[str] = None
    season_label: Optional[str] = None
    season_type: Optional[str] = None
    limit: int
    assumptions: List[str] = Field(default_factory=list)
    rows: List[RankingRow] = Field(default_factory=list)
    aggregate_rows: List[AggregateRow] = Field(default_factory=list)
    object_rows: List[ObjectRow] = Field(default_factory=list)
    time_series_rows: List[TimeSeriesRow] = Field(default_factory=list)
    find_rows: List[Dict[str, Any]] = Field(default_factory=list)
    find_predicate_tree: Optional[Dict[str, Any]] = None
    find_filters: List[PlanFindFilter] = Field(default_factory=list)
    find_orders: List[PlanFindOrder] = Field(default_factory=list)
    row_predicate: Optional[Dict[str, Any]] = None
    result_predicate: Optional[Dict[str, Any]] = None
    grouping_columns: List[PlanGroupingColumn] = Field(default_factory=list)
    display_metadata: List[PlanDisplayMetadata] = Field(default_factory=list)
    display_metrics: List[PlanDisplayMetric] = Field(default_factory=list)
    comparison: Optional[ComparisonResult] = None


class FinalAnswer(BaseModel):
    summary: str
    interpretation: str
    query_kind: str
    result_shape: str
    entity_label_singular: str
    entity_label_plural: str
    context_label: str
    metric: str
    metric_order_direction: str = "DESC"
    window_games: int
    time_grain: Optional[str] = None
    time_filter: Optional[str] = None
    time_window_days: Optional[int] = None
    time_start_date: Optional[str] = None
    time_end_date: Optional[str] = None
    season_label: Optional[str] = None
    season_type: Optional[str] = None
    limit: int
    assumptions: List[str] = Field(default_factory=list)
    rows: List[RankingRow]
    aggregate_rows: List[AggregateRow] = Field(default_factory=list)
    object_rows: List[ObjectRow] = Field(default_factory=list)
    time_series_rows: List[TimeSeriesRow] = Field(default_factory=list)
    find_rows: List[Dict[str, Any]] = Field(default_factory=list)
    find_predicate_tree: Optional[Dict[str, Any]] = None
    find_filters: List[PlanFindFilter] = Field(default_factory=list)
    find_orders: List[PlanFindOrder] = Field(default_factory=list)
    row_predicate: Optional[Dict[str, Any]] = None
    result_predicate: Optional[Dict[str, Any]] = None
    grouping_columns: List[PlanGroupingColumn] = Field(default_factory=list)
    display_metadata: List[PlanDisplayMetadata] = Field(default_factory=list)
    display_metrics: List[PlanDisplayMetric] = Field(default_factory=list)
    comparison: Optional[ComparisonResult] = None


def _field_names(model_type: type[BaseModel]) -> tuple[str, ...]:
    if hasattr(model_type, "model_fields"):
        return tuple(model_type.model_fields)
    return tuple(model_type.__fields__)


def _model_values(model: BaseModel, fields: tuple[str, ...]) -> dict[str, Any]:
    include = set(fields)
    if hasattr(model, "model_dump"):
        return model.model_dump(include=include)
    return model.dict(include=include)


SYNTHESIS_PAYLOAD_FIELDS = _field_names(SynthesisPayload)
FINAL_ANSWER_PAYLOAD_FIELDS = tuple(
    field for field in SYNTHESIS_PAYLOAD_FIELDS if field in _field_names(FinalAnswer)
)


def synthesis_payload_from_runtime_result(result: RuntimeResult) -> SynthesisPayload:
    # Preserve the runtime result contract in one place instead of manually
    # copying every shared field in package_results.py.
    return SynthesisPayload(**_model_values(result, SYNTHESIS_PAYLOAD_FIELDS))


def final_answer_from_payload(
    payload: SynthesisPayload,
    *,
    summary: str,
    interpretation: str,
    **overrides: Any,
) -> FinalAnswer:
    # Every final answer should carry the same context payload unless a branch
    # intentionally narrows which row collection it exposes.
    values = _model_values(payload, FINAL_ANSWER_PAYLOAD_FIELDS)
    values.update(overrides)
    return FinalAnswer(summary=summary, interpretation=interpretation, **values)
