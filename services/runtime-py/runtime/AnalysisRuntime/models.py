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


class PlanFindFilter(BaseModel):
    # Grounded time/window metadata for find-row answers.
    # Example: exact season, season type, or last-N games.
    filter_kind: str
    filter_value: Optional[object] = None


class PlanFindOrder(BaseModel):
    # Grounded user-facing ordering metadata for find-row answers.
    # Example: score descending, opponent ascending.
    order_field: str
    order_direction: str


class PlanDisplayMetadata(BaseModel):
    # One display metadata column Haskell intentionally emitted.
    # Example: Games Played or Minutes.
    column_key: str
    label: str
    column_type: str


class PlanDisplayMetric(BaseModel):
    # One metric/result column Haskell intentionally emitted.
    # When present, these replace the old single "metric_value" display path.
    column_key: str
    metric: str
    label: str
    aggregation: str = ""


class PlanGroupingColumn(BaseModel):
    # One column that defines aggregate result grain.
    # Example: Team, Season Type, Conference.
    column_key: str
    label: str


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
    time_window_days: Optional[int] = None
    time_start_date: Optional[str] = None
    time_end_date: Optional[str] = None
    season_label: Optional[str] = None
    season_type: Optional[str] = None
    limit: int
    assumptions: List[str] = Field(default_factory=list)
    find_predicate_tree: Optional[Dict[str, object]] = None
    find_filters: List[PlanFindFilter] = Field(default_factory=list)
    find_orders: List[PlanFindOrder] = Field(default_factory=list)
    row_predicate: Optional[Dict[str, object]] = None
    result_predicate: Optional[Dict[str, object]] = None
    grouping_columns: List[PlanGroupingColumn] = Field(default_factory=list)
    display_metadata: List[PlanDisplayMetadata] = Field(default_factory=list)
    display_metrics: List[PlanDisplayMetric] = Field(default_factory=list)
    steps: List[PlanStep]


class RankingRow(BaseModel):
    # One final ranked output row, like "1. Jayson Tatum - 31.2".
    rank: int
    entity_name: str
    context_value: Optional[str] = None
    group_values: Dict[str, object] = Field(default_factory=dict)
    games_played: Optional[float] = None
    minutes: Optional[float] = None
    display_values: Dict[str, object] = Field(default_factory=dict)
    metric_value: float


class AggregateRow(BaseModel):
    # One grouped aggregate output row, like "Celtics - 110.6".
    entity_name: str
    context_value: Optional[str] = None
    group_values: Dict[str, object] = Field(default_factory=dict)
    games_played: Optional[float] = None
    minutes: Optional[float] = None
    display_values: Dict[str, object] = Field(default_factory=dict)
    metric_value: float


class ObjectRow(BaseModel):
    # One final object-row output, where each row mainly represents an entity.
    entity_id: int
    entity_name: str
    context_value: Optional[str] = None
    games_played: Optional[float] = None
    minutes: Optional[float] = None
    display_values: Dict[str, object] = Field(default_factory=dict)
    metric_value: float


class ComparisonRow(BaseModel):
    # One raw per-game row used during comparison analysis.
    entity_id: int
    entity_name: str
    context_value: Optional[str] = None
    time_bucket: Optional[str] = None
    group_values: Dict[str, object] = Field(default_factory=dict)
    game_date: Optional[str] = None
    metric_value: float


class ComparisonEntityStats(BaseModel):
    # Aggregated stats for one side of a comparison.
    entity_id: int
    entity_name: str
    context_value: Optional[str] = None
    display_values: Dict[str, object] = Field(default_factory=dict)
    metric_value: float
    games_count: int


class ComparisonBreakdownRow(BaseModel):
    # One grouped comparison row, like "Brunson - Regular Season - 28.4".
    entity_id: int
    entity_name: str
    context_value: Optional[str] = None
    time_bucket: Optional[str] = None
    group_values: Dict[str, object] = Field(default_factory=dict)
    display_values: Dict[str, object] = Field(default_factory=dict)
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
    breakdown_rows: List[ComparisonBreakdownRow] = Field(default_factory=list)


class TimeSeriesRow(BaseModel):
    # One point in a time-series answer.
    time_bucket: str
    series_name: Optional[str] = None
    group_values: Dict[str, object] = Field(default_factory=dict)
    display_values: Dict[str, object] = Field(default_factory=dict)
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
    find_rows: List[Dict[str, object]] = Field(default_factory=list)
    find_predicate_tree: Optional[Dict[str, object]] = None
    find_filters: List[PlanFindFilter] = Field(default_factory=list)
    find_orders: List[PlanFindOrder] = Field(default_factory=list)
    row_predicate: Optional[Dict[str, object]] = None
    result_predicate: Optional[Dict[str, object]] = None
    grouping_columns: List[PlanGroupingColumn] = Field(default_factory=list)
    display_metadata: List[PlanDisplayMetadata] = Field(default_factory=list)
    display_metrics: List[PlanDisplayMetric] = Field(default_factory=list)
    raw_rows: List[Dict[str, object]] = Field(default_factory=list)
    comparison: Optional[ComparisonResult] = None


RUNTIME_RESULT_CONTEXT_FIELDS = (
    "query_kind",
    "result_shape",
    "entity_label_singular",
    "entity_label_plural",
    "context_label",
    "metric",
    "window_games",
    "time_grain",
    "time_filter",
    "time_window_days",
    "time_start_date",
    "time_end_date",
    "season_label",
    "season_type",
    "limit",
    "assumptions",
    "find_predicate_tree",
    "find_filters",
    "find_orders",
    "row_predicate",
    "result_predicate",
    "grouping_columns",
    "display_metadata",
    "display_metrics",
)


def _model_values(model: BaseModel, fields: tuple[str, ...]) -> dict[str, object]:
    include = set(fields)
    if hasattr(model, "model_dump"):
        return model.model_dump(include=include)
    return model.dict(include=include)


def runtime_context_from_plan(plan: ExecutionPlan) -> dict[str, object]:
    # Copy plan-owned answer metadata through one boundary so new context fields
    # do not have to be threaded manually in runner.py.
    return _model_values(plan, RUNTIME_RESULT_CONTEXT_FIELDS)
