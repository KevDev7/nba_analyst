# Purpose:
# Execute runtime plan steps in order for the live semantic-layer slices.
#
# Uses:
# - ExecutionPlan models from models.py
# - SQL execution from query_engine.py
# - optional future Python analysis from analysis.py
#
# Produces:
# - RuntimeResult objects for answer synthesis
#
# Next:
# - ../AnswerSynthesis/package_results.py

from __future__ import annotations

from typing import List

from .analysis import run_analysis
from .models import ExecutionPlan, ObjectRow, RankingRow, RuntimeResult, TimeSeriesRow
from .query_engine import run_sql
from .state import RuntimeState


def execute_plan(plan: ExecutionPlan) -> RuntimeResult:
    runtime_state = RuntimeState()
    raw_rows = []
    comparison_result = None

    for step in plan.steps:
        if step.kind == "run_sql":
            if not step.sql:
                raise ValueError("SQL step missing sql text.")
            raw_rows = run_sql(step.sql)
            runtime_state.latest_result = raw_rows
        elif step.kind == "run_python":
            if not step.analysis_spec:
                raise ValueError("Python analysis step missing analysis spec.")
            comparison_result = run_analysis(step.analysis_spec, runtime_state)
            runtime_state.latest_result = comparison_result
        else:
            raise ValueError(f"Unsupported plan step kind: {step.kind}")

    rows: List[RankingRow] = []
    object_rows: List[ObjectRow] = []
    time_series_rows: List[TimeSeriesRow] = []
    if plan.plan_type == "single_sql" and plan.result_shape == "ranking":
        rows = [RankingRow(**row) for row in raw_rows]
    elif plan.plan_type == "single_sql" and plan.result_shape == "object_rows":
        object_rows = [ObjectRow(**row) for row in raw_rows]
    elif plan.plan_type == "single_sql" and plan.result_shape == "time_series":
        time_series_rows = [TimeSeriesRow(**row) for row in raw_rows]
    return RuntimeResult(
        query_kind=plan.query_kind,
        result_shape=plan.result_shape,
        entity_label_singular=plan.entity_label_singular,
        entity_label_plural=plan.entity_label_plural,
        context_label=plan.context_label,
        metric=plan.metric,
        window_games=plan.window_games,
        time_grain=plan.time_grain,
        time_filter=plan.time_filter,
        limit=plan.limit,
        assumptions=plan.assumptions,
        rows=rows,
        object_rows=object_rows,
        time_series_rows=time_series_rows,
        raw_rows=raw_rows,
        comparison=comparison_result,
    )
