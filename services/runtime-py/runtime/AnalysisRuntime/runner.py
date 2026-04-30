# Purpose:
# Execute runtime plan steps in order for the live semantic-layer slices.
#
# Uses:
# - ExecutionPlan models from models.py
# - SQL execution from query_engine.py
# - optional Python analysis from analysis.py
#
# Produces:
# - RuntimeResult objects for answer synthesis
#
# Next:
# - ../AnswerSynthesis/package_results.py

from __future__ import annotations

from typing import List

from .analysis import run_analysis
from .models import (
    AggregateRow,
    ExecutionPlan,
    ObjectRow,
    RankingRow,
    RuntimeResult,
    TimeSeriesRow,
    runtime_context_from_plan,
)
from .query_engine import run_sql
from .state import RuntimeState


def _row_with_display_values(row: dict[str, object], plan: ExecutionPlan) -> dict[str, object]:
    # Preserve display columns in a generic bag so answer formatting is driven
    # by the execution plan instead of one Python field per possible column.
    display_values = {
        metadata.column_key: row.get(metadata.column_key)
        for metadata in plan.display_metadata
        if metadata.column_key in row
    }
    display_values.update(
        {
            metric.column_key: row.get(metric.column_key)
            for metric in plan.display_metrics
            if metric.column_key in row
        }
    )
    return {**row, "display_values": display_values}


def _aggregate_row_values(row: dict[str, object], plan: ExecutionPlan) -> dict[str, object]:
    group_values = {
        grouping.column_key: row.get(grouping.column_key)
        for grouping in plan.grouping_columns
        if grouping.column_key in row
    }
    return {**_row_with_display_values(row, plan), "group_values": group_values}


def _ranking_row_values(row: dict[str, object], plan: ExecutionPlan) -> dict[str, object]:
    group_values = {
        grouping.column_key: row.get(grouping.column_key)
        for grouping in plan.grouping_columns
        if grouping.column_key in row
    }
    return {**_row_with_display_values(row, plan), "group_values": group_values}


def _time_series_row_values(row: dict[str, object], plan: ExecutionPlan) -> dict[str, object]:
    group_values = {
        grouping.column_key: row.get(grouping.column_key)
        for grouping in plan.grouping_columns
        if grouping.column_key in row
    }
    return {**_row_with_display_values(row, plan), "group_values": group_values}


def execute_plan(plan: ExecutionPlan) -> RuntimeResult:
    # Create a scratchpad for multi-step execution and placeholders for outputs.
    runtime_state = RuntimeState()
    raw_rows = []
    comparison_result = None

    # Walk through the steps Haskell compiled and execute them in order.
    for step in plan.steps:
        if step.kind == "run_sql":
            if not step.sql:
                raise ValueError("SQL step missing sql text.")
            # Run the SQL and remember its rows in runtime state for later steps.
            raw_rows = run_sql(step.sql)
            runtime_state.latest_result = raw_rows
        elif step.kind == "run_python":
            if not step.analysis_spec:
                raise ValueError("Python analysis step missing analysis spec.")
            # Let Python analysis inspect the latest SQL result and derive something richer.
            comparison_result = run_analysis(step.analysis_spec, runtime_state, plan)
            runtime_state.latest_result = comparison_result
        else:
            raise ValueError(f"Unsupported plan step kind: {step.kind}")

    # Convert raw runtime rows into the final typed result shape the rest of the app expects.
    rows: List[RankingRow] = []
    aggregate_rows: List[AggregateRow] = []
    object_rows: List[ObjectRow] = []
    time_series_rows: List[TimeSeriesRow] = []
    find_rows = []
    if plan.plan_type == "single_sql" and plan.result_shape == "ranking":
        rows = [RankingRow(**_ranking_row_values(row, plan)) for row in raw_rows]
    elif plan.plan_type == "single_sql" and plan.result_shape == "aggregate":
        aggregate_rows = [AggregateRow(**_aggregate_row_values(row, plan)) for row in raw_rows]
    elif plan.plan_type == "single_sql" and plan.result_shape == "object_rows":
        object_rows = [ObjectRow(**_row_with_display_values(row, plan)) for row in raw_rows]
    elif plan.plan_type == "single_sql" and plan.result_shape == "time_series":
        time_series_rows = [TimeSeriesRow(**_time_series_row_values(row, plan)) for row in raw_rows]
    elif plan.plan_type == "single_sql" and plan.result_shape == "find_rows":
        find_rows = raw_rows
    # Return one unified result object for answer synthesis.
    return RuntimeResult(
        **runtime_context_from_plan(plan),
        rows=rows,
        aggregate_rows=aggregate_rows,
        object_rows=object_rows,
        time_series_rows=time_series_rows,
        find_rows=find_rows,
        raw_rows=raw_rows,
        comparison=comparison_result,
    )
