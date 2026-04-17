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
    kind: Literal["run_sql", "run_python"]
    sql: Optional[str] = None
    analysis_spec: Optional[str] = None


class ExecutionPlan(BaseModel):
    plan_type: Literal["single_sql", "multi_step"]
    query_kind: Literal["metric_query", "object_query"]
    result_shape: Literal["ranking", "comparison", "object_rows", "time_series"]
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
    steps: List[PlanStep]


class RankingRow(BaseModel):
    rank: int
    entity_name: str
    context_value: Optional[str] = None
    metric_value: float


class ObjectRow(BaseModel):
    entity_id: int
    entity_name: str
    context_value: Optional[str] = None
    metric_value: float


class ComparisonRow(BaseModel):
    player_name: str
    team: str
    game_date: str
    points: int


class PlayerComparisonStats(BaseModel):
    player_name: str
    team: str
    total_points: int
    average_points: float
    games_count: int


class ComparisonResult(BaseModel):
    leader: str
    point_differential: int
    player_a: PlayerComparisonStats
    player_b: PlayerComparisonStats
    per_game_rows: List[ComparisonRow] = Field(default_factory=list)


class TimeSeriesRow(BaseModel):
    time_bucket: str
    series_name: Optional[str] = None
    metric_value: float


class RuntimeResult(BaseModel):
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
    object_rows: List[ObjectRow] = Field(default_factory=list)
    time_series_rows: List[TimeSeriesRow] = Field(default_factory=list)
    raw_rows: List[Dict[str, object]] = Field(default_factory=list)
    comparison: Optional[ComparisonResult] = None
