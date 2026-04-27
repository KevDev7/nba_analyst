# Purpose:
# Define the Python-side runtime models for the gold-first execution plans and results.
#
# Uses:
# - JSON execution plans produced by the Haskell semantic core
#
# Produces:
# - typed execution-plan, row, and runtime-result models
#
# Next:
# - runner.py

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    # One executable runtime step.
    # Example: run one SQL query, or run one Python analysis step.
    kind: Literal["run_sql", "run_python"]
    sql: Optional[str] = None
    analysis_spec: Optional[str] = None


class ExecutionPlan(BaseModel):
    # The full runtime instructions handed from Haskell to Python.
    # Plain English: what kind of answer is this, what labels/metadata go with it,
    # and what exact steps should Python execute?
    plan_type: Literal["single_sql", "multi_step"]
    query_kind: Literal["metric_query", "object_query", "find_query"]
    result_shape: Literal["ranking", "aggregate", "comparison", "object_rows", "time_series", "find_rows"]
    entity_label_singular: str
    entity_label_plural: str
    context_label: str
    metric: str
    metric_aggregation: str
    window_games: int
    time_grain: Optional[str] = None
    time_filter: Optional[str] = None
    season_label: Optional[str] = None
    season_type: Optional[str] = None
    limit: int
    assumptions: List[str] = Field(default_factory=list)
    steps: List[PlanStep]


class RankingRow(BaseModel):
    # One final ranked output row, like "1. Jayson Tatum - 31.2".
    rank: int
    entity_name: str
    context_value: Optional[str] = None
    metric_value: float


class AggregateRow(BaseModel):
    # One grouped aggregate output row, like "Celtics - 110.6".
    entity_name: str
    context_value: Optional[str] = None
    metric_value: float


class ObjectRow(BaseModel):
    # One final object-row output, where each row mainly represents an entity.
    entity_id: int
    entity_name: str
    context_value: Optional[str] = None
    metric_value: float


class ComparisonRow(BaseModel):
    # One raw per-game row used during comparison analysis.
    entity_id: int
    entity_name: str
    context_value: Optional[str] = None
    game_date: str
    metric_value: float


class ComparisonEntityStats(BaseModel):
    # Aggregated stats for one side of a comparison.
    entity_id: int
    entity_name: str
    context_value: Optional[str] = None
    metric_value: float
    games_count: int


class ComparisonResult(BaseModel):
    # Final structured comparison result produced by Python analysis.
    leader: str
    metric_differential: float
    entity_a: ComparisonEntityStats
    entity_b: ComparisonEntityStats
    entities: List[ComparisonEntityStats] = Field(default_factory=list)
    per_game_rows: List[ComparisonRow] = Field(default_factory=list)


class TimeSeriesRow(BaseModel):
    # One point in a time-series answer.
    time_bucket: str
    series_name: Optional[str] = None
    metric_value: float


class RuntimeResult(BaseModel):
    # The full result package Python returns after executing the plan.
    # This is the handoff from AnalysisRuntime to AnswerSynthesis.
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
    find_rows: List[Dict[str, object]] = Field(default_factory=list)
    raw_rows: List[Dict[str, object]] = Field(default_factory=list)
    comparison: Optional[ComparisonResult] = None
