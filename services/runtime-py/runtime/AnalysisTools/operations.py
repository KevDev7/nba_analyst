# Purpose:
# Build controlled analysis artifacts from typed operation specs.
#
# Uses:
# - AnalysisTool request models
# - pandas for table normalization
# - Altair for Vega-Lite chart specs
#
# Produces:
# - ChartArtifact objects ready for a renderer
#
# Next:
# - local_worker.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import warnings

import altair as alt
import pandas as pd

from .models import AnalysisTable, AnalysisTableColumn, ChartArtifact, ChartOperation


@dataclass(frozen=True)
class AnalysisOperationError(Exception):
    code: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


def run_controlled_operation(table: AnalysisTable, operation: ChartOperation) -> ChartArtifact:
    if operation.renderer != "vega_lite":
        raise AnalysisOperationError(
            code="unsupported_renderer",
            message=f"Renderer '{operation.renderer}' is not supported by the local trusted worker.",
            metadata={"renderer": operation.renderer},
        )
    if operation.kind == "line_chart":
        return _build_chart_artifact(table, operation, mark="line")
    if operation.kind == "bar_chart":
        return _build_chart_artifact(table, operation, mark="bar")
    if operation.kind == "point_chart":
        return _build_chart_artifact(table, operation, mark="point")
    raise AnalysisOperationError(
        code="unsupported_operation",
        message=f"Operation '{operation.kind}' is not supported by the local trusted worker.",
        metadata={"operation_kind": operation.kind},
    )


def _build_chart_artifact(table: AnalysisTable, operation: ChartOperation, mark: str) -> ChartArtifact:
    columns_by_id = {column.id: column for column in table.columns}
    x_column = columns_by_id[operation.x]
    y_column = columns_by_id[operation.y]
    series_column = columns_by_id.get(operation.series or "")
    value_column = _value_axis_column(operation, x_column, y_column, mark)

    if value_column.type not in {"number", "integer"}:
        raise AnalysisOperationError(
            code="invalid_chart_operation",
            message=f"Chart value-axis column '{value_column.id}' must be numeric.",
            metadata={"column": value_column.id, "column_type": value_column.type},
        )

    structural_column_ids = _structural_column_ids(operation)
    frame = _dataframe_from_table(table, structural_column_ids)
    _coerce_numeric_column(frame, value_column)
    chart_family = _chart_family(mark)
    series_count = _series_count(frame, operation.series)
    category_count = _category_count(frame, operation, x_column, y_column, mark)

    chart = alt.Chart(frame)
    if mark == "line":
        chart = chart.mark_line(point=True)
    elif mark == "point":
        chart = chart.mark_point(filled=True, size=70)
    else:
        chart = chart.mark_bar()

    encodings: dict[str, Any] = {
        "x": alt.X(
            field=operation.x,
            type=_vega_lite_type(x_column),
            title=x_column.label,
            sort=_channel_sort(operation, "x"),
        ),
        "y": alt.Y(
            field=operation.y,
            type=_vega_lite_type(y_column),
            title=y_column.label,
            sort=_channel_sort(operation, "y"),
        ),
        "tooltip": _tooltip_columns(table.columns, structural_column_ids),
    }
    if series_column is not None and operation.series is not None:
        encodings["color"] = alt.Color(
            field=operation.series,
            type=_vega_lite_type(series_column),
            title=series_column.label,
        )

    spec = _configure_chart(chart.encode(**encodings)).to_dict()
    return ChartArtifact(
        renderer="vega_lite",
        title=_chart_title(table, operation, x_column, y_column),
        spec=spec,
        data={"row_count": len(table.rows)},
        metadata={
            **operation.metadata,
            "source_table_id": table.id,
            "operation_kind": operation.kind,
            "chart_family": chart_family,
            "x": operation.x,
            "y": operation.y,
            "x_type": x_column.type,
            "y_type": y_column.type,
            "series": operation.series,
            "orientation": operation.orientation,
            "series_count": series_count,
            "category_count": category_count,
            "row_count": len(table.rows),
        },
    )


def _value_axis_column(
    operation: ChartOperation,
    x_column: AnalysisTableColumn,
    y_column: AnalysisTableColumn,
    mark: str,
) -> AnalysisTableColumn:
    if mark == "bar" and operation.orientation == "horizontal":
        return x_column
    return y_column


def _chart_family(mark: str) -> str:
    if mark == "line":
        return "line"
    if mark == "point":
        return "point"
    return "bar"


def _channel_sort(operation: ChartOperation, channel: str) -> object:
    if operation.sort is None or operation.sort.channel != channel:
        return alt.Undefined
    if operation.sort.field is None and operation.sort.order is None:
        return None
    if operation.sort.field is None:
        return operation.sort.order
    return alt.SortField(
        field=operation.sort.field,
        order=operation.sort.order or "ascending",
    )


def _structural_column_ids(operation: ChartOperation) -> set[str]:
    column_ids = {operation.x, operation.y}
    if operation.series is not None:
        column_ids.add(operation.series)
    if operation.sort is not None and operation.sort.field is not None:
        column_ids.add(operation.sort.field)
    return column_ids


def _dataframe_from_table(table: AnalysisTable, structural_column_ids: set[str]) -> pd.DataFrame:
    frame = pd.DataFrame(table.rows, columns=[column.id for column in table.columns])
    for column in table.columns:
        if column.id not in structural_column_ids:
            continue
        if column.type in {"number", "integer"} and column.id in frame:
            _coerce_numeric_column(frame, column)
        if column.type == "date" and column.id in frame:
            _coerce_temporal_column(frame, column)
    return frame


def _coerce_numeric_column(frame: pd.DataFrame, column: AnalysisTableColumn) -> None:
    try:
        frame[column.id] = pd.to_numeric(frame[column.id])
    except Exception as exc:
        raise AnalysisOperationError(
            code="invalid_numeric_column",
            message=f"Column '{column.id}' could not be converted to numeric values.",
            metadata={"column": column.id},
        ) from exc


def _coerce_temporal_column(frame: pd.DataFrame, column: AnalysisTableColumn) -> None:
    try:
        converted = _parse_datetime_series(frame[column.id])
    except Exception as exc:
        raise AnalysisOperationError(
            code="invalid_temporal_column",
            message=f"Column '{column.id}' could not be converted to temporal values.",
            metadata={"column": column.id},
        ) from exc
    invalid_values = frame[column.id][converted.isna() & frame[column.id].notna()].tolist()
    if invalid_values:
        raise AnalysisOperationError(
            code="invalid_temporal_column",
            message=f"Column '{column.id}' contains values that cannot be converted to temporal values.",
            metadata={"column": column.id, "invalid_values": invalid_values[:5]},
        )
    frame[column.id] = converted


def _parse_datetime_series(values: pd.Series) -> pd.Series:
    try:
        converted = pd.to_datetime(values, format="ISO8601", errors="coerce")
    except (TypeError, ValueError):
        converted = None
    if converted is not None and not _has_unparsed_values(values, converted):
        return converted

    try:
        return pd.to_datetime(values, format="mixed", errors="coerce")
    except (TypeError, ValueError):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Could not infer format")
            return pd.to_datetime(values, errors="coerce")


def _has_unparsed_values(values: pd.Series, converted: pd.Series) -> bool:
    return bool((converted.isna() & values.notna()).any())


def _chart_title(
    table: AnalysisTable,
    operation: ChartOperation,
    x_column: AnalysisTableColumn,
    y_column: AnalysisTableColumn,
) -> str:
    if operation.title:
        return operation.title
    if table.title:
        return table.title
    return f"{y_column.label} by {x_column.label}"


def _vega_lite_type(column: AnalysisTableColumn) -> str:
    if column.type == "date":
        return "temporal"
    if column.type in {"number", "integer"}:
        return "quantitative"
    if column.type == "boolean":
        return "nominal"
    return "nominal"


def _series_count(frame: pd.DataFrame, series_column_id: str | None) -> int:
    if series_column_id is None or series_column_id not in frame:
        return 0
    return int(frame[series_column_id].dropna().nunique())


def _category_count(
    frame: pd.DataFrame,
    operation: ChartOperation,
    x_column: AnalysisTableColumn,
    y_column: AnalysisTableColumn,
    mark: str,
) -> int:
    category_column = _category_axis_column(operation, x_column, y_column, mark)
    if category_column is None or category_column.id not in frame:
        return 0
    return int(frame[category_column.id].dropna().nunique())


def _category_axis_column(
    operation: ChartOperation,
    x_column: AnalysisTableColumn,
    y_column: AnalysisTableColumn,
    mark: str,
) -> AnalysisTableColumn | None:
    if mark != "bar":
        return None
    if operation.orientation == "horizontal" and _is_categorical_column(y_column):
        return y_column
    if operation.orientation == "vertical" and _is_categorical_column(x_column):
        return x_column
    return None


def _is_categorical_column(column: AnalysisTableColumn) -> bool:
    return column.type in {"text", "boolean"}


def _configure_chart(chart: alt.Chart) -> alt.Chart:
    return (
        chart.properties(
            width="container",
            height=360,
            autosize=alt.AutoSizeParams(type="fit-x", contains="padding", resize=True),
        )
        .configure_axis(
            labelColor="#3d3d3a",
            labelFont="Inter",
            labelFontSize=12,
            titleColor="#252523",
            titleFont="Inter",
            titleFontSize=12,
            titleFontWeight=500,
            gridColor="#ebe6df",
            domainColor="#e6dfd8",
            tickColor="#e6dfd8",
        )
        .configure_legend(
            labelColor="#3d3d3a",
            labelFont="Inter",
            labelFontSize=12,
            titleColor="#252523",
            titleFont="Inter",
            titleFontSize=12,
            titleFontWeight=500,
            symbolSize=80,
        )
        .configure_view(stroke=None)
    )


def _tooltip_columns(columns: list[AnalysisTableColumn], structural_column_ids: set[str]) -> list[alt.Tooltip]:
    return [
        alt.Tooltip(
            field=column.id,
            type=_vega_lite_type(column) if column.id in structural_column_ids else "nominal",
            title=column.label,
        )
        for column in columns
    ]
