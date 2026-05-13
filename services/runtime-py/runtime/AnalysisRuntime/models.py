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

from pydantic import BaseModel, ConfigDict, Field


class StrictContractModel(BaseModel):
    # Boundary/contract models reject stale fields so old transport shapes do
    # not quietly survive beside the nested answer_context contract.
    model_config = ConfigDict(extra="forbid")


class PlanStep(StrictContractModel):
    # One executable runtime step.
    # Example: run one SQL query, or run one Python analysis step.
    kind: Literal["run_sql", "run_python"]
    sql: Optional[str] = None
    analysis_spec: Optional[str] = None


class PlanFindFilter(StrictContractModel):
    # Grounded time/window metadata for find-row answers.
    # Example: exact season, season type, or last-N games.
    filter_kind: str
    filter_value: Optional[object] = None


class PlanFindOrder(StrictContractModel):
    # Grounded user-facing ordering metadata for find-row answers.
    # Example: score descending, opponent ascending.
    order_field: str
    order_direction: str


class PlanDisplayMetadata(StrictContractModel):
    # One display metadata column Haskell intentionally emitted.
    # Example: Games Played or Minutes.
    column_key: str
    label: str
    column_type: str


class PlanDisplayMetric(StrictContractModel):
    # One metric/result column Haskell intentionally emitted.
    # When present, these replace the old single "metric_value" display path.
    column_key: str
    metric: str
    label: str
    aggregation: str = ""


class PlanGroupingColumn(StrictContractModel):
    # One column that defines aggregate result grain.
    # Example: Team, Season Type, Conference.
    column_key: str
    label: str


class PlanExecutionContext(StrictContractModel):
    # Executable runtime instructions. Answer-facing metadata lives in
    # PlanAnswerContext instead of being duplicated beside these fields.
    plan_type: Literal["single_sql", "multi_step"]
    steps: List[PlanStep]


class PlanAnswerSubjectContext(StrictContractModel):
    singular: str
    plural: str
    context_label: str


class PlanAnswerMetricContext(StrictContractModel):
    key: str
    aggregation: str
    order_direction: str


class PlanAnswerTimeContext(StrictContractModel):
    window_games: int
    grain: Optional[str] = None
    filter: Optional[str] = None
    window_days: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    season_label: Optional[str] = None
    season_type: Optional[str] = None


class PlanAnswerRankingContext(StrictContractModel):
    intent_label: Optional[str] = None
    limit: int


class PlanAnswerFindContext(StrictContractModel):
    predicate_tree: Optional[Dict[str, object]] = None
    filters: List[PlanFindFilter] = Field(default_factory=list)
    orders: List[PlanFindOrder] = Field(default_factory=list)


class PlanAnswerPredicateContext(StrictContractModel):
    row: Optional[Dict[str, object]] = None
    result: Optional[Dict[str, object]] = None


class PlanAnswerDisplayContext(StrictContractModel):
    grouping_columns: List[PlanGroupingColumn] = Field(default_factory=list)
    metadata: List[PlanDisplayMetadata] = Field(default_factory=list)
    metrics: List[PlanDisplayMetric] = Field(default_factory=list)


class PlanAnswerContext(StrictContractModel):
    # Answer-facing metadata emitted by Haskell. Runtime preserves this nested
    # contract and exposes compatibility properties instead of duplicating
    # top-level answer fields.
    query_kind: str
    result_shape: str
    subject: PlanAnswerSubjectContext
    metric: PlanAnswerMetricContext
    time: PlanAnswerTimeContext
    ranking: PlanAnswerRankingContext
    find: PlanAnswerFindContext
    predicates: PlanAnswerPredicateContext
    display: PlanAnswerDisplayContext
    assumptions: List[str] = Field(default_factory=list)


class AnswerContextProperties:
    answer_context: PlanAnswerContext

    @property
    def query_kind(self) -> str:
        return self.answer_context.query_kind

    @property
    def result_shape(self) -> str:
        return self.answer_context.result_shape

    @property
    def entity_label_singular(self) -> str:
        return self.answer_context.subject.singular

    @property
    def entity_label_plural(self) -> str:
        return self.answer_context.subject.plural

    @property
    def context_label(self) -> str:
        return self.answer_context.subject.context_label

    @property
    def metric(self) -> str:
        return self.answer_context.metric.key

    @property
    def metric_aggregation(self) -> str:
        return self.answer_context.metric.aggregation

    @property
    def metric_order_direction(self) -> str:
        return self.answer_context.metric.order_direction

    @property
    def rank_intent_label(self) -> Optional[str]:
        return self.answer_context.ranking.intent_label

    @property
    def window_games(self) -> int:
        return self.answer_context.time.window_games

    @property
    def time_grain(self) -> Optional[str]:
        return self.answer_context.time.grain

    @property
    def time_filter(self) -> Optional[str]:
        return self.answer_context.time.filter

    @property
    def time_window_days(self) -> Optional[int]:
        return self.answer_context.time.window_days

    @property
    def time_start_date(self) -> Optional[str]:
        return self.answer_context.time.start_date

    @property
    def time_end_date(self) -> Optional[str]:
        return self.answer_context.time.end_date

    @property
    def season_label(self) -> Optional[str]:
        return self.answer_context.time.season_label

    @property
    def season_type(self) -> Optional[str]:
        return self.answer_context.time.season_type

    @property
    def limit(self) -> int:
        return self.answer_context.ranking.limit

    @property
    def assumptions(self) -> List[str]:
        return self.answer_context.assumptions

    @property
    def find_predicate_tree(self) -> Optional[Dict[str, object]]:
        return self.answer_context.find.predicate_tree

    @property
    def find_filters(self) -> List[PlanFindFilter]:
        return self.answer_context.find.filters

    @property
    def find_orders(self) -> List[PlanFindOrder]:
        return self.answer_context.find.orders

    @property
    def row_predicate(self) -> Optional[Dict[str, object]]:
        return self.answer_context.predicates.row

    @property
    def result_predicate(self) -> Optional[Dict[str, object]]:
        return self.answer_context.predicates.result

    @property
    def grouping_columns(self) -> List[PlanGroupingColumn]:
        return self.answer_context.display.grouping_columns

    @property
    def display_metadata(self) -> List[PlanDisplayMetadata]:
        return self.answer_context.display.metadata

    @property
    def display_metrics(self) -> List[PlanDisplayMetric]:
        return self.answer_context.display.metrics


class ExecutionPlan(AnswerContextProperties, StrictContractModel):
    # The full runtime instructions handed from Haskell to Python: executable
    # steps plus nested answer-facing metadata.
    execution: PlanExecutionContext
    answer_context: PlanAnswerContext

    @property
    def plan_type(self) -> str:
        return self.execution.plan_type

    @property
    def steps(self) -> List[PlanStep]:
        return self.execution.steps


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


class RuntimeResult(AnswerContextProperties, StrictContractModel):
    # The full result package Python returns after executing the plan.
    # This is the handoff from AnalysisRuntime to AnswerSynthesis.
    answer_context: PlanAnswerContext
    rows: List[RankingRow]
    aggregate_rows: List[AggregateRow] = Field(default_factory=list)
    object_rows: List[ObjectRow] = Field(default_factory=list)
    time_series_rows: List[TimeSeriesRow] = Field(default_factory=list)
    find_rows: List[Dict[str, object]] = Field(default_factory=list)
    raw_rows: List[Dict[str, object]] = Field(default_factory=list)
    execution_metadata: List[Dict[str, object]] = Field(default_factory=list)
    comparison: Optional[ComparisonResult] = None


RUNTIME_RESULT_CONTEXT_FIELDS = (
    "answer_context",
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
