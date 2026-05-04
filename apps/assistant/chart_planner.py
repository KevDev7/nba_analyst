# Purpose:
# Decide whether a grounded answer table has a supported chart plan.
#
# Uses:
# - typed FinalAnswer context
# - full table artifacts built from runtime rows
#
# Produces:
# - controlled chart operation payloads for AnalysisTools

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from runtime.AnswerSynthesis.response_models import FinalAnswer


JsonDict = dict[str, Any]
PRIMARY_ANALYSIS_TABLE_ID = "primary_answer_table"


@dataclass(frozen=True)
class ChartPlan:
    operation: JsonDict


@dataclass(frozen=True)
class _ChartProfile:
    columns: tuple[Mapping[str, Any], ...]
    x_column: Mapping[str, Any] | None
    y_column: Mapping[str, Any] | None
    series_column: Mapping[str, Any] | None


def plan_chart_operation(
    answer: FinalAnswer,
    table_artifact: Mapping[str, Any],
    *,
    input_table_id: str = PRIMARY_ANALYSIS_TABLE_ID,
) -> ChartPlan | None:
    profile = _chart_profile(table_artifact)
    if answer.result_shape == "time_series":
        return _time_series_chart_plan(answer, table_artifact, profile, input_table_id)
    if answer.result_shape == "ranking":
        return _entity_bar_chart_plan(answer, table_artifact, profile, input_table_id)
    if answer.result_shape == "object_rows":
        return (
            _metric_relationship_chart_plan(answer, table_artifact, profile, input_table_id)
            or _entity_bar_chart_plan(answer, table_artifact, profile, input_table_id)
        )
    if answer.result_shape == "aggregate":
        return _aggregate_chart_plan(answer, table_artifact, profile, input_table_id)
    if answer.result_shape == "comparison":
        return _comparison_chart_plan(answer, table_artifact, profile, input_table_id)
    if answer.result_shape == "find_rows":
        return _find_rows_chart_plan(answer, table_artifact, profile, input_table_id)
    return None


def _time_series_chart_plan(
    answer: FinalAnswer,
    table_artifact: Mapping[str, Any],
    profile: _ChartProfile,
    input_table_id: str,
) -> ChartPlan | None:
    if profile.x_column is None or profile.y_column is None:
        return None

    return ChartPlan(
        operation={
            "kind": "line_chart",
            "input_table_id": input_table_id,
            "x": profile.x_column["id"],
            "y": profile.y_column["id"],
            "series": profile.series_column["id"] if profile.series_column is not None else None,
            "title": _chart_title(answer, table_artifact),
            "renderer": "vega_lite",
            "metadata": {
                "source_result_shape": answer.result_shape,
                "source_time_grain": answer.time_grain,
            },
        }
    )


def _entity_bar_chart_plan(
    answer: FinalAnswer,
    table_artifact: Mapping[str, Any],
    profile: _ChartProfile,
    input_table_id: str,
) -> ChartPlan | None:
    category_column = _category_column(answer, profile.columns)
    metric_column = _primary_metric_column(answer, profile.columns, category_column)
    if category_column is None or metric_column is None:
        return None

    return ChartPlan(
        operation={
            "kind": "bar_chart",
            "input_table_id": input_table_id,
            "x": metric_column["id"],
            "y": category_column["id"],
            "series": None,
            "orientation": "horizontal",
            "sort": _entity_bar_sort(answer, profile.columns, metric_column),
            "title": _chart_title(answer, table_artifact),
            "renderer": "vega_lite",
            "metadata": {
                "source_result_shape": answer.result_shape,
                "source_time_grain": answer.time_grain,
                "source_metric_order_direction": answer.metric_order_direction,
            },
        }
    )


def _metric_relationship_chart_plan(
    answer: FinalAnswer,
    table_artifact: Mapping[str, Any],
    profile: _ChartProfile,
    input_table_id: str,
) -> ChartPlan | None:
    metric_columns = _relationship_metric_columns(answer, profile.columns)
    if len(metric_columns) < 2:
        return None

    return ChartPlan(
        operation={
            "kind": "point_chart",
            "input_table_id": input_table_id,
            "x": metric_columns[0]["id"],
            "y": metric_columns[1]["id"],
            "series": None,
            "title": _chart_title(answer, table_artifact),
            "renderer": "vega_lite",
            "metadata": {
                "source_result_shape": answer.result_shape,
                "source_time_grain": answer.time_grain,
                "source_visual_task": "metric_relationship",
                "source_metric_count": len(metric_columns),
            },
        }
    )


def _aggregate_chart_plan(
    answer: FinalAnswer,
    table_artifact: Mapping[str, Any],
    profile: _ChartProfile,
    input_table_id: str,
) -> ChartPlan | None:
    if profile.x_column is not None:
        metric_column = _primary_metric_column(answer, profile.columns, profile.x_column)
        if metric_column is not None:
            return ChartPlan(
                operation={
                    "kind": "line_chart",
                    "input_table_id": input_table_id,
                    "x": profile.x_column["id"],
                    "y": metric_column["id"],
                    "series": None,
                    "title": _chart_title(answer, table_artifact),
                    "renderer": "vega_lite",
                    "metadata": {
                        "source_result_shape": answer.result_shape,
                        "source_time_grain": answer.time_grain,
                    },
                }
            )
    relationship_plan = _metric_relationship_chart_plan(answer, table_artifact, profile, input_table_id)
    if relationship_plan is not None:
        return relationship_plan
    return _entity_bar_chart_plan(answer, table_artifact, profile, input_table_id)


def _comparison_chart_plan(
    answer: FinalAnswer,
    table_artifact: Mapping[str, Any],
    profile: _ChartProfile,
    input_table_id: str,
) -> ChartPlan | None:
    if answer.comparison is None:
        return None
    if answer.comparison.breakdown_rows:
        return _comparison_breakdown_chart_plan(answer, table_artifact, profile, input_table_id)
    return _entity_bar_chart_plan(answer, table_artifact, profile, input_table_id)


def _comparison_breakdown_chart_plan(
    answer: FinalAnswer,
    table_artifact: Mapping[str, Any],
    profile: _ChartProfile,
    input_table_id: str,
) -> ChartPlan | None:
    if profile.x_column is None:
        return None
    metric_column = _primary_metric_column(answer, profile.columns, profile.x_column)
    if metric_column is None:
        return None
    series_column = _column_by_id(profile.columns, "entity_name") or _series_column(
        profile.columns,
        profile.x_column["id"],
        metric_column["id"],
    )

    return ChartPlan(
        operation={
            "kind": "line_chart",
            "input_table_id": input_table_id,
            "x": profile.x_column["id"],
            "y": metric_column["id"],
            "series": series_column["id"] if series_column is not None else None,
            "title": _chart_title(answer, table_artifact),
            "renderer": "vega_lite",
            "metadata": {
                "source_result_shape": answer.result_shape,
                "source_time_grain": answer.time_grain,
                "source_comparison_shape": "breakdown",
            },
        }
    )


def _find_rows_chart_plan(
    answer: FinalAnswer,
    table_artifact: Mapping[str, Any],
    profile: _ChartProfile,
    input_table_id: str,
) -> ChartPlan | None:
    relationship_plan = _metric_relationship_chart_plan(answer, table_artifact, profile, input_table_id)
    if relationship_plan is not None:
        return relationship_plan

    if profile.x_column is not None:
        metric_column = _find_row_metric_column(profile.columns, profile.x_column["id"])
        if metric_column is not None:
            return ChartPlan(
                operation={
                    "kind": "line_chart",
                    "input_table_id": input_table_id,
                    "x": profile.x_column["id"],
                    "y": metric_column["id"],
                    "series": None,
                    "title": _chart_title(answer, table_artifact),
                    "renderer": "vega_lite",
                    "metadata": {
                        "source_result_shape": answer.result_shape,
                        "source_time_grain": answer.time_grain,
                    },
                }
            )

    metric_column = _find_row_metric_column(profile.columns, None)
    category_column = _find_row_category_column(profile.columns, metric_column)
    if metric_column is None or category_column is None:
        return None

    return ChartPlan(
        operation={
            "kind": "bar_chart",
            "input_table_id": input_table_id,
            "x": metric_column["id"],
            "y": category_column["id"],
            "series": None,
            "orientation": "horizontal",
            "sort": {"channel": "y", "field": None, "order": None},
            "title": _chart_title(answer, table_artifact),
            "renderer": "vega_lite",
            "metadata": {
                "source_result_shape": answer.result_shape,
                "source_time_grain": answer.time_grain,
            },
        }
    )


def _chart_profile(table_artifact: Mapping[str, Any]) -> _ChartProfile:
    columns = tuple(
        column
        for column in table_artifact.get("columns", [])
        if isinstance(column, Mapping)
    )
    x_column = _time_axis_column(columns)
    y_column = _first_metric_column(columns, x_column["id"]) if x_column is not None else None
    series_column = (
        _series_column(columns, x_column["id"], y_column["id"])
        if x_column is not None and y_column is not None
        else None
    )
    return _ChartProfile(
        columns=columns,
        x_column=x_column,
        y_column=y_column,
        series_column=series_column,
    )


def _time_axis_column(columns: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any] | None:
    for column in columns:
        if column.get("id") == "time_bucket":
            return column
    for column in columns:
        if column.get("type") == "date":
            return column
    return None


def _first_metric_column(
    columns: tuple[Mapping[str, Any], ...],
    x_column_id: object,
) -> Mapping[str, Any] | None:
    for column in columns:
        if column.get("id") == x_column_id:
            continue
        if column.get("type") in {"number", "integer"}:
            return column
    return None


def _series_column(
    columns: tuple[Mapping[str, Any], ...],
    x_column_id: object,
    y_column_id: object,
) -> Mapping[str, Any] | None:
    for column in columns:
        if column.get("id") in {x_column_id, y_column_id}:
            continue
        if column.get("type") == "text":
            return column
    return None


def _category_column(
    answer: FinalAnswer,
    columns: tuple[Mapping[str, Any], ...],
) -> Mapping[str, Any] | None:
    entity_column = _column_by_id(columns, "entity_name")
    if entity_column is not None:
        return entity_column
    for grouping in answer.grouping_columns:
        grouping_column = _column_by_id(columns, grouping.column_key)
        if grouping_column is not None:
            return grouping_column
    for column in columns:
        if column.get("type") == "text":
            return column
    return None


def _primary_metric_column(
    answer: FinalAnswer,
    columns: tuple[Mapping[str, Any], ...],
    category_column: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    for display_metric in answer.display_metrics:
        metric_column = _column_by_id(columns, display_metric.column_key)
        if metric_column is not None and metric_column.get("type") in {"number", "integer"}:
            return metric_column

    metric_value_column = _column_by_id(columns, "metric_value")
    if metric_value_column is not None and metric_value_column.get("type") in {"number", "integer"}:
        return metric_value_column

    excluded_ids = {"rank"}
    if category_column is not None:
        excluded_ids.add(category_column.get("id"))
    for column in columns:
        if column.get("id") in excluded_ids:
            continue
        if column.get("type") in {"number", "integer"}:
            return column
    return None


def _relationship_metric_columns(
    answer: FinalAnswer,
    columns: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    display_metric_columns = []
    seen_ids = set()
    for display_metric in answer.display_metrics:
        metric_column = _column_by_id(columns, display_metric.column_key)
        if metric_column is None or not _is_relationship_metric_column(metric_column):
            continue
        display_metric_columns.append(metric_column)
        seen_ids.add(metric_column.get("id"))

    if display_metric_columns or answer.result_shape != "find_rows":
        return tuple(display_metric_columns)

    return tuple(
        column
        for column in columns
        if column.get("id") not in seen_ids and _is_relationship_metric_column(column)
    )


def _is_relationship_metric_column(column: Mapping[str, Any]) -> bool:
    if column.get("type") not in {"number", "integer"}:
        return False
    if _is_identifier_column(column):
        return False
    return str(column.get("id") or "").lower() != "rank"


def _find_row_metric_column(
    columns: tuple[Mapping[str, Any], ...],
    excluded_axis_id: object | None,
) -> Mapping[str, Any] | None:
    for column in columns:
        if column.get("id") == excluded_axis_id:
            continue
        if column.get("type") not in {"number", "integer"}:
            continue
        if _is_identifier_column(column):
            continue
        return column
    return None


def _find_row_category_column(
    columns: tuple[Mapping[str, Any], ...],
    metric_column: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    metric_column_id = metric_column.get("id") if metric_column is not None else None
    for column in columns:
        if column.get("id") == metric_column_id:
            continue
        if column.get("type") == "text":
            return column
    return None


def _is_identifier_column(column: Mapping[str, Any]) -> bool:
    column_id = str(column.get("id") or "").lower()
    label = str(column.get("label") or "").lower()
    return column_id == "id" or column_id.endswith("_id") or label == "id" or label.endswith(" id")


def _entity_bar_sort(
    answer: FinalAnswer,
    columns: tuple[Mapping[str, Any], ...],
    metric_column: Mapping[str, Any],
) -> JsonDict:
    if answer.result_shape == "ranking" and _column_by_id(columns, "rank") is not None:
        return {"channel": "y", "field": "rank", "order": "ascending"}
    if answer.result_shape == "aggregate":
        return {
            "channel": "y",
            "field": metric_column["id"],
            "order": _metric_sort_order(answer.metric_order_direction),
        }
    return {"channel": "y", "field": None, "order": None}


def _metric_sort_order(metric_order_direction: str) -> str:
    if metric_order_direction.lower() in {"asc", "ascending"}:
        return "ascending"
    return "descending"


def _column_by_id(columns: tuple[Mapping[str, Any], ...], column_id: str) -> Mapping[str, Any] | None:
    for column in columns:
        if column.get("id") == column_id:
            return column
    return None


def _chart_title(answer: FinalAnswer, table_artifact: Mapping[str, Any]) -> str:
    if answer.summary:
        return answer.summary
    return str(table_artifact.get("title") or "Chart")
