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
    PlanFindFilter,
    PlanFindPredicate,
    PlanLinkedFilter,
    RankingRow,
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
    window_games: int
    time_grain: Optional[str] = None
    time_filter: Optional[str] = None
    season_label: Optional[str] = None
    season_type: Optional[str] = None
    limit: int
    assumptions: List[str] = Field(default_factory=list)
    rows: List[RankingRow] = Field(default_factory=list)
    aggregate_rows: List[AggregateRow] = Field(default_factory=list)
    object_rows: List[ObjectRow] = Field(default_factory=list)
    time_series_rows: List[TimeSeriesRow] = Field(default_factory=list)
    find_rows: List[Dict[str, Any]] = Field(default_factory=list)
    find_predicates: List[PlanFindPredicate] = Field(default_factory=list)
    find_filters: List[PlanFindFilter] = Field(default_factory=list)
    linked_filters: List[PlanLinkedFilter] = Field(default_factory=list)
    display_metadata: List[PlanDisplayMetadata] = Field(default_factory=list)
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
    window_games: int
    time_grain: Optional[str] = None
    time_filter: Optional[str] = None
    season_label: Optional[str] = None
    season_type: Optional[str] = None
    limit: int
    assumptions: List[str] = Field(default_factory=list)
    rows: List[RankingRow]
    aggregate_rows: List[AggregateRow] = Field(default_factory=list)
    object_rows: List[ObjectRow] = Field(default_factory=list)
    time_series_rows: List[TimeSeriesRow] = Field(default_factory=list)
    find_rows: List[Dict[str, Any]] = Field(default_factory=list)
    find_predicates: List[PlanFindPredicate] = Field(default_factory=list)
    find_filters: List[PlanFindFilter] = Field(default_factory=list)
    linked_filters: List[PlanLinkedFilter] = Field(default_factory=list)
    display_metadata: List[PlanDisplayMetadata] = Field(default_factory=list)
    comparison: Optional[ComparisonResult] = None
