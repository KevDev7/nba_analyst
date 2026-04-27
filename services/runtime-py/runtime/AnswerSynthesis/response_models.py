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

from runtime.AnalysisRuntime.models import AggregateRow, ComparisonResult, ObjectRow, RankingRow, TimeSeriesRow


class FinalAnswer(BaseModel):
    summary: str
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
    comparison: Optional[ComparisonResult] = None
