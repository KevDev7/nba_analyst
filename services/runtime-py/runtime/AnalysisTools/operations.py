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

    if y_column.type not in {"number", "integer"}:
        raise AnalysisOperationError(
            code="invalid_chart_operation",
            message=f"Chart y-axis column '{operation.y}' must be numeric.",
            metadata={"column": operation.y, "column_type": y_column.type},
        )

    frame = _dataframe_from_table(table)
    _coerce_numeric_column(frame, y_column)

    chart = alt.Chart(frame)
    if mark == "line":
        chart = chart.mark_line(point=True)
    else:
        chart = chart.mark_bar()

    encodings: dict[str, Any] = {
        "x": alt.X(field=operation.x, type=_vega_lite_type(x_column), title=x_column.label),
        "y": alt.Y(field=operation.y, type=_vega_lite_type(y_column), title=y_column.label),
        "tooltip": _tooltip_columns(table.columns),
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
            "source_table_id": table.id,
            "operation_kind": operation.kind,
            "x": operation.x,
            "y": operation.y,
            "series": operation.series,
            "row_count": len(table.rows),
        },
    )


def _dataframe_from_table(table: AnalysisTable) -> pd.DataFrame:
    frame = pd.DataFrame(table.rows, columns=[column.id for column in table.columns])
    for column in table.columns:
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
        converted = pd.to_datetime(frame[column.id])
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


def _configure_chart(chart: alt.Chart) -> alt.Chart:
    return (
        chart.configure_axis(
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


def _tooltip_columns(columns: list[AnalysisTableColumn]) -> list[alt.Tooltip]:
    return [
        alt.Tooltip(field=column.id, type=_vega_lite_type(column), title=column.label)
        for column in columns
    ]
