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

from .models import (
    AnalysisFinding,
    AnalysisOperation,
    AnalysisTable,
    AnalysisTableColumn,
    ChartArtifact,
    ChartOperation,
    CorrelationOperation,
    JoinAndDeltaOperation,
    PercentChangeOperation,
    RankExtremesOperation,
    ZScoreOutliersOperation,
)


@dataclass(frozen=True)
class AnalysisOperationError(Exception):
    code: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlledOperationResult:
    tables: list[AnalysisTable] = field(default_factory=list)
    artifacts: list[ChartArtifact] = field(default_factory=list)
    findings: list[AnalysisFinding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def run_controlled_operation(tables: list[AnalysisTable], operation: AnalysisOperation) -> ControlledOperationResult:
    if isinstance(operation, ChartOperation):
        return ControlledOperationResult(
            artifacts=[_run_chart_operation(_table_by_id(tables, operation.input_table_id), operation)],
            metadata={"operation_kind": operation.kind},
        )
    if isinstance(operation, JoinAndDeltaOperation):
        return _run_join_and_delta_operation(tables, operation)
    if isinstance(operation, RankExtremesOperation):
        return _run_rank_extremes_operation(tables, operation)
    if isinstance(operation, CorrelationOperation):
        return _run_correlation_operation(tables, operation)
    if isinstance(operation, PercentChangeOperation):
        return _run_percent_change_operation(tables, operation)
    if isinstance(operation, ZScoreOutliersOperation):
        return _run_zscore_outliers_operation(tables, operation)
    raise AnalysisOperationError(
        code="unsupported_operation",
        message=f"Operation '{operation.kind}' is not supported by the local trusted worker.",
        metadata={"operation_kind": operation.kind},
    )


def _run_chart_operation(table: AnalysisTable, operation: ChartOperation) -> ChartArtifact:
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


def _run_join_and_delta_operation(
    tables: list[AnalysisTable],
    operation: JoinAndDeltaOperation,
) -> ControlledOperationResult:
    left = _table_by_id(tables, operation.left_table_id)
    right = _table_by_id(tables, operation.right_table_id)
    left_output = operation.left_output_column or f"left_{operation.left_metric}"
    right_output = operation.right_output_column or f"right_{operation.right_metric}"

    left_frame = _selected_frame(left, [*operation.join_keys, operation.left_metric])
    right_frame = _selected_frame(right, [*operation.join_keys, operation.right_metric])
    left_frame = left_frame.rename(columns={operation.left_metric: left_output})
    right_frame = right_frame.rename(columns={operation.right_metric: right_output})
    _coerce_numeric_series(left_frame, left_output)
    _coerce_numeric_series(right_frame, right_output)

    merged = left_frame.merge(
        right_frame,
        how=operation.join_type,
        on=operation.join_keys,
    )
    merged[operation.output_metric] = merged[right_output] - merged[left_output]

    sort_by = operation.sort.by if operation.sort else operation.output_metric
    ascending = bool(operation.sort and operation.sort.direction == "asc")
    merged = merged.sort_values(by=sort_by, ascending=ascending, kind="mergesort", na_position="last")
    if operation.limit is not None:
        merged = merged.head(operation.limit)

    columns = [
        *_join_key_columns(left, operation.join_keys),
        AnalysisTableColumn(id=left_output, label=_column_label(left, operation.left_metric, left_output), type="number"),
        AnalysisTableColumn(id=right_output, label=_column_label(right, operation.right_metric, right_output), type="number"),
        AnalysisTableColumn(id=operation.output_metric, label=_label(operation.output_metric), type="number"),
    ]
    output_table = AnalysisTable(
        id=f"{operation.left_table_id}_{operation.right_table_id}_{operation.output_metric}",
        title=operation.title or _label(operation.output_metric),
        columns=columns,
        rows=_rows_from_frame(merged, [column.id for column in columns]),
        row_count=int(len(merged)),
        metadata={
            **operation.metadata,
            "operation_kind": operation.kind,
            "parent_table_ids": [operation.left_table_id, operation.right_table_id],
            "calculation": "right_metric_minus_left_metric",
            "left_metric": operation.left_metric,
            "right_metric": operation.right_metric,
            "output_metric": operation.output_metric,
        },
    )
    return ControlledOperationResult(
        tables=[output_table],
        findings=_ranked_extreme_findings(output_table, operation.output_metric, "largest" if not ascending else "smallest"),
        metadata={"operation_kind": operation.kind, "output_table_id": output_table.id},
    )


def _run_rank_extremes_operation(
    tables: list[AnalysisTable],
    operation: RankExtremesOperation,
) -> ControlledOperationResult:
    table = _table_by_id(tables, operation.input_table_id)
    frame = _selected_frame(table, [column.id for column in table.columns])
    _coerce_numeric_series(frame, operation.metric)
    ascending = operation.direction == "asc"
    frame = frame.sort_values(by=operation.metric, ascending=ascending, kind="mergesort", na_position="last").head(operation.limit)
    frame.insert(0, "rank", range(1, len(frame) + 1))

    columns = [
        AnalysisTableColumn(id="rank", label="Rank", type="integer"),
        *table.columns,
    ]
    output_table = AnalysisTable(
        id=f"{table.id}_{operation.metric}_ranked",
        title=operation.title or table.title or f"Ranked by {_label(operation.metric)}",
        columns=columns,
        rows=_rows_from_frame(frame, [column.id for column in columns]),
        row_count=int(len(frame)),
        metadata={
            **operation.metadata,
            "operation_kind": operation.kind,
            "parent_table_ids": [table.id],
            "metric": operation.metric,
            "direction": operation.direction,
        },
    )
    return ControlledOperationResult(
        tables=[output_table],
        findings=_ranked_extreme_findings(output_table, operation.metric, "largest" if not ascending else "smallest"),
        metadata={"operation_kind": operation.kind, "output_table_id": output_table.id},
    )


def _run_correlation_operation(
    tables: list[AnalysisTable],
    operation: CorrelationOperation,
) -> ControlledOperationResult:
    left = _table_by_id(tables, operation.left_table_id)
    right = _table_by_id(tables, operation.right_table_id)
    left_output = operation.left_output_column or f"left_{operation.left_metric}"
    right_output = operation.right_output_column or f"right_{operation.right_metric}"

    left_frame = _selected_frame(left, [*operation.join_keys, operation.left_metric])
    right_frame = _selected_frame(right, [*operation.join_keys, operation.right_metric])
    left_frame = left_frame.rename(columns={operation.left_metric: left_output})
    right_frame = right_frame.rename(columns={operation.right_metric: right_output})
    _coerce_numeric_series(left_frame, left_output)
    _coerce_numeric_series(right_frame, right_output)

    merged = left_frame.merge(right_frame, how="inner", on=operation.join_keys)
    paired_row_count = int(len(merged))
    correlation = None
    if paired_row_count >= 2:
        correlation = _json_value(merged[left_output].corr(merged[right_output], method=operation.method))

    output_table = AnalysisTable(
        id=f"{operation.left_table_id}_{operation.right_table_id}_correlation",
        title=operation.title or f"Correlation: {_label(left_output)} vs {_label(right_output)}",
        columns=[
            AnalysisTableColumn(id="left_metric", label="Left Metric", type="text"),
            AnalysisTableColumn(id="right_metric", label="Right Metric", type="text"),
            AnalysisTableColumn(id="method", label="Method", type="text"),
            AnalysisTableColumn(id="correlation", label="Correlation", type="number"),
            AnalysisTableColumn(id="paired_row_count", label="Matched Rows", type="integer"),
        ],
        rows=[
            {
                "left_metric": left_output,
                "right_metric": right_output,
                "method": operation.method,
                "correlation": correlation,
                "paired_row_count": paired_row_count,
            }
        ],
        row_count=1,
        metadata={
            **operation.metadata,
            "operation_kind": operation.kind,
            "parent_table_ids": [operation.left_table_id, operation.right_table_id],
            "left_metric": operation.left_metric,
            "right_metric": operation.right_metric,
            "method": operation.method,
        },
    )
    findings: list[AnalysisFinding] = []
    if correlation is not None:
        findings.append(
            AnalysisFinding(
                kind="correlation",
                text=f"Correlation between {left_output} and {right_output} was {correlation}.",
                evidence_table_id=output_table.id,
                row_refs=[0],
                metadata={
                    "left_metric": left_output,
                    "right_metric": right_output,
                    "method": operation.method,
                    "correlation": correlation,
                    "paired_row_count": paired_row_count,
                },
            )
        )
    return ControlledOperationResult(
        tables=[output_table],
        findings=findings,
        metadata={"operation_kind": operation.kind, "output_table_id": output_table.id},
    )


def _run_percent_change_operation(
    tables: list[AnalysisTable],
    operation: PercentChangeOperation,
) -> ControlledOperationResult:
    left = _table_by_id(tables, operation.left_table_id)
    right = _table_by_id(tables, operation.right_table_id)
    left_output = operation.left_output_column or f"left_{operation.left_metric}"
    right_output = operation.right_output_column or f"right_{operation.right_metric}"

    left_frame = _selected_frame(left, [*operation.join_keys, operation.left_metric])
    right_frame = _selected_frame(right, [*operation.join_keys, operation.right_metric])
    left_frame = left_frame.rename(columns={operation.left_metric: left_output})
    right_frame = right_frame.rename(columns={operation.right_metric: right_output})
    _coerce_numeric_series(left_frame, left_output)
    _coerce_numeric_series(right_frame, right_output)

    merged = left_frame.merge(right_frame, how=operation.join_type, on=operation.join_keys)
    denominator = merged[left_output].abs()
    merged[operation.output_metric] = (merged[right_output] - merged[left_output]) / denominator.where(denominator != 0) * 100

    sort_by = operation.sort.by if operation.sort else operation.output_metric
    ascending = bool(operation.sort and operation.sort.direction == "asc")
    merged = merged.sort_values(by=sort_by, ascending=ascending, kind="mergesort", na_position="last")
    if operation.limit is not None:
        merged = merged.head(operation.limit)

    columns = [
        *_join_key_columns(left, operation.join_keys),
        AnalysisTableColumn(id=left_output, label=_column_label(left, operation.left_metric, left_output), type="number"),
        AnalysisTableColumn(id=right_output, label=_column_label(right, operation.right_metric, right_output), type="number"),
        AnalysisTableColumn(id=operation.output_metric, label=_label(operation.output_metric), type="number"),
    ]
    output_table = AnalysisTable(
        id=f"{operation.left_table_id}_{operation.right_table_id}_{operation.output_metric}",
        title=operation.title or _label(operation.output_metric),
        columns=columns,
        rows=_rows_from_frame(merged, [column.id for column in columns]),
        row_count=int(len(merged)),
        metadata={
            **operation.metadata,
            "operation_kind": operation.kind,
            "parent_table_ids": [operation.left_table_id, operation.right_table_id],
            "calculation": "right_minus_left_divided_by_abs_left_times_100",
            "left_metric": operation.left_metric,
            "right_metric": operation.right_metric,
            "output_metric": operation.output_metric,
        },
    )
    return ControlledOperationResult(
        tables=[output_table],
        findings=_ranked_extreme_findings(output_table, operation.output_metric, "largest" if not ascending else "smallest"),
        metadata={"operation_kind": operation.kind, "output_table_id": output_table.id},
    )


def _run_zscore_outliers_operation(
    tables: list[AnalysisTable],
    operation: ZScoreOutliersOperation,
) -> ControlledOperationResult:
    table = _table_by_id(tables, operation.input_table_id)
    frame = _selected_frame(table, [column.id for column in table.columns])
    _coerce_numeric_series(frame, operation.metric)
    mean = frame[operation.metric].mean()
    std = frame[operation.metric].std(ddof=0)
    frame["z_score"] = 0.0 if not std else (frame[operation.metric] - mean) / std
    if operation.direction == "high":
        filtered = frame[frame["z_score"] >= operation.threshold]
        ascending = False
    elif operation.direction == "low":
        filtered = frame[frame["z_score"] <= -operation.threshold]
        ascending = True
    else:
        filtered = frame[frame["z_score"].abs() >= operation.threshold]
        filtered = filtered.assign(__abs_z=filtered["z_score"].abs()).sort_values(by="__abs_z", ascending=False, kind="mergesort")
        ascending = False
    if operation.direction in {"high", "low"}:
        filtered = filtered.sort_values(by="z_score", ascending=ascending, kind="mergesort")
    if operation.limit is not None:
        filtered = filtered.head(operation.limit)
    columns = [
        *table.columns,
        AnalysisTableColumn(id="z_score", label="Z-Score", type="number"),
    ]
    output_table = AnalysisTable(
        id=f"{table.id}_{operation.metric}_zscore_outliers",
        title=operation.title or f"{_label(operation.metric)} Outliers",
        columns=columns,
        rows=_rows_from_frame(filtered, [column.id for column in columns]),
        row_count=int(len(filtered)),
        metadata={
            **operation.metadata,
            "operation_kind": operation.kind,
            "parent_table_ids": [table.id],
            "metric": operation.metric,
            "threshold": operation.threshold,
            "direction": operation.direction,
            "mean": _json_value(mean),
            "stddev": _json_value(std),
        },
    )
    return ControlledOperationResult(
        tables=[output_table],
        findings=_ranked_extreme_findings(output_table, "z_score", "largest absolute"),
        metadata={"operation_kind": operation.kind, "output_table_id": output_table.id},
    )


def _table_by_id(tables: list[AnalysisTable], table_id: str) -> AnalysisTable:
    for table in tables:
        if table.id == table_id:
            return table
    raise AnalysisOperationError(
        code="unknown_table",
        message=f"Operation references unknown table: {table_id}",
        metadata={"table_id": table_id},
    )


def _selected_frame(table: AnalysisTable, column_ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame(table.rows, columns=column_ids)


def _coerce_numeric_series(frame: pd.DataFrame, column_id: str) -> None:
    try:
        frame[column_id] = pd.to_numeric(frame[column_id])
    except Exception as exc:
        raise AnalysisOperationError(
            code="invalid_numeric_column",
            message=f"Column '{column_id}' could not be converted to numeric values.",
            metadata={"column": column_id},
        ) from exc


def _join_key_columns(table: AnalysisTable, join_keys: list[str]) -> list[AnalysisTableColumn]:
    columns_by_id = {column.id: column for column in table.columns}
    return [
        AnalysisTableColumn(
            id=key,
            label=columns_by_id[key].label if key in columns_by_id else _label(key),
            type=columns_by_id[key].type if key in columns_by_id else "text",
        )
        for key in join_keys
    ]


def _column_label(table: AnalysisTable, source_column: str, output_column: str) -> str:
    columns_by_id = {column.id: column for column in table.columns}
    if source_column in columns_by_id:
        return columns_by_id[source_column].label
    return _label(output_column)


def _rows_from_frame(frame: pd.DataFrame, column_ids: list[str]) -> list[dict[str, Any]]:
    rows = []
    for record in frame[column_ids].to_dict(orient="records"):
        rows.append({key: _json_value(value) for key, value in record.items()})
    return rows


def _json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _ranked_extreme_findings(table: AnalysisTable, metric: str, direction_label: str) -> list[AnalysisFinding]:
    if not table.rows:
        return []
    row = table.rows[0]
    entity = _row_identity(row, metric)
    value = row.get(metric)
    return [
        AnalysisFinding(
            kind="ranked_extreme",
            text=f"{entity} had the {direction_label} {metric} at {value}.",
            evidence_table_id=table.id,
            row_refs=[0],
            metadata={"metric": metric, "value": value},
        )
    ]


def _row_identity(row: dict[str, Any], metric: str) -> str:
    for key, value in row.items():
        if key != metric and value is not None:
            return str(value)
    return "The first row"


def _label(value: str) -> str:
    return value.replace("_", " ").strip().title()


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
