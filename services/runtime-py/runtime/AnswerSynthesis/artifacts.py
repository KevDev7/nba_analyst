# Purpose:
# Convert typed final answers into renderer-friendly structured artifacts.
#
# Uses:
# - FinalAnswer objects from response_models.py
# - the same answer-language/table ordering helpers as format_response.py
#
# Produces:
# - JSON-ready artifacts for web, CLI, or future renderers
#
# Next:
# - apps/assistant/pipeline.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .answer_language import field_label, metric_header, time_header
from .format_response import (
    DISPLAY_METADATA_TYPE_ORDER,
    DISPLAY_ROW_LIMIT,
    _context_header,
    _display_metadata_value,
    _grouping_header,
    _grouping_value,
    _metadata_duplicates_display_metric,
)
from .response_models import FinalAnswer


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class TableColumnBuilder:
    id: str
    label: str
    value_type: str
    getter: Callable[[Any], object]


def build_artifacts(answer: FinalAnswer) -> list[JsonDict]:
    artifacts: list[JsonDict] = [
        {
            "kind": "text",
            "role": "interpretation",
            "text": f"Interpreted as: {answer.interpretation}",
        },
        {
            "kind": "text",
            "role": "summary",
            "text": answer.summary,
        },
    ]
    if answer.assumptions:
        artifacts.append(
            {
                "kind": "text",
                "role": "assumptions",
                "text": "\n".join(answer.assumptions),
                "items": list(answer.assumptions),
            }
        )

    table = _build_primary_table(answer)
    if table is not None:
        artifacts.append(table)
    return artifacts


def _build_primary_table(answer: FinalAnswer) -> JsonDict | None:
    if answer.comparison is not None:
        if answer.comparison.breakdown_rows:
            return _build_table_artifact(
                title="Comparison",
                columns=_comparison_breakdown_columns(answer, answer.comparison.breakdown_rows),
                rows=answer.comparison.breakdown_rows,
            )
        compared_entities = answer.comparison.entities or [
            answer.comparison.entity_a,
            answer.comparison.entity_b,
        ]
        return _build_table_artifact(
            title="Comparison",
            columns=_comparison_entity_columns(answer, compared_entities),
            rows=compared_entities,
        )
    if answer.find_rows:
        return _build_table_artifact(
            title=f"Matching {answer.entity_label_plural}",
            columns=_find_columns(answer.find_rows),
            rows=answer.find_rows,
        )
    if answer.aggregate_rows:
        return _build_table_artifact(
            title=answer.summary,
            columns=_row_table_columns(answer, answer.aggregate_rows, include_rank=False),
            rows=answer.aggregate_rows,
        )
    if answer.object_rows:
        return _build_table_artifact(
            title=answer.summary,
            columns=_row_table_columns(answer, answer.object_rows, include_rank=False),
            rows=answer.object_rows,
        )
    if answer.time_series_rows:
        return _build_table_artifact(
            title=answer.summary,
            columns=_time_series_columns(answer, answer.time_series_rows),
            rows=answer.time_series_rows,
        )
    if answer.rows:
        return _build_table_artifact(
            title=answer.summary,
            columns=_row_table_columns(answer, answer.rows, include_rank=True),
            rows=answer.rows,
        )
    return None


def _build_table_artifact(
    *,
    title: str,
    columns: Sequence[TableColumnBuilder],
    rows: Sequence[Any],
) -> JsonDict:
    display_rows = list(rows[:DISPLAY_ROW_LIMIT])
    return {
        "kind": "table",
        "title": title,
        "columns": [
            {
                "id": column.id,
                "label": column.label,
                "type": column.value_type,
            }
            for column in columns
        ],
        "rows": [
            {column.id: _json_value(column.getter(row)) for column in columns}
            for row in display_rows
        ],
        "row_count": len(rows),
        "displayed_row_count": len(display_rows),
        "display_limit": DISPLAY_ROW_LIMIT,
    }


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _value_type(column_id: str, label: str, values: Sequence[object]) -> str:
    if column_id in {"rank", "games", "games_played"}:
        return "integer"
    if "date" in column_id or "date" in label.lower() or column_id in {"day", "week", "month", "time_bucket"}:
        return "date"
    if any(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values if value is not None):
        return "number"
    return "text"


def _make_column(
    column_id: str,
    label: str,
    rows: Sequence[Any],
    getter: Callable[[Any], object],
    *,
    value_type: str | None = None,
) -> TableColumnBuilder:
    values = [getter(row) for row in rows]
    return TableColumnBuilder(
        id=column_id,
        label=label,
        value_type=value_type or _value_type(column_id, label, values),
        getter=getter,
    )


def _row_table_columns(answer: FinalAnswer, rows: Sequence[Any], include_rank: bool) -> list[TableColumnBuilder]:
    columns: list[TableColumnBuilder] = []
    if include_rank:
        columns.append(_make_column("rank", "Rank", rows, lambda row: row.rank, value_type="integer"))

    grouping_labels = {grouping.label for grouping in answer.grouping_columns}
    grouping_headers = {_grouping_header(answer, grouping.label) for grouping in answer.grouping_columns}
    if answer.result_shape in {"aggregate", "ranking"} and answer.grouping_columns:
        for grouping in answer.grouping_columns:
            columns.append(
                _make_column(
                    grouping.column_key,
                    _grouping_header(answer, grouping.label),
                    rows,
                    lambda row, key=grouping.column_key: _grouping_value(row, key),
                )
            )
    else:
        columns.append(_make_column("entity_name", answer.entity_label_singular, rows, lambda row: row.entity_name))

    if answer.result_shape != "aggregate" and answer.context_label and any(row.context_value for row in rows):
        columns.append(
            _make_column(
                "context_value",
                _context_header(answer, grouping_headers),
                rows,
                lambda row: row.context_value,
            )
        )

    if answer.season_label and "season_year" not in grouping_labels:
        columns.append(_make_column("season_label", "Season", rows, lambda _row: answer.season_label))
    if answer.season_type and "season_type" not in grouping_labels:
        columns.append(_make_column("season_type", "Season Type", rows, lambda _row: answer.season_type))

    for metadata_type in DISPLAY_METADATA_TYPE_ORDER:
        for metadata in answer.display_metadata:
            if metadata.column_type != metadata_type:
                continue
            if metadata.column_key == answer.metric:
                continue
            if _metadata_duplicates_display_metric(answer, metadata.column_key):
                continue
            if not any(_display_metadata_value(row, metadata.column_key) is not None for row in rows):
                continue
            columns.append(
                _make_column(
                    metadata.column_key,
                    field_label(metadata.label),
                    rows,
                    lambda row, key=metadata.column_key: _display_metadata_value(row, key),
                )
            )

    if answer.display_metrics:
        for display_metric in answer.display_metrics:
            columns.append(
                _make_column(
                    display_metric.column_key,
                    metric_header(display_metric.metric),
                    rows,
                    lambda row, key=display_metric.column_key: _display_metadata_value(row, key),
                    value_type="number",
                )
            )
    else:
        columns.append(
            _make_column(
                "metric_value",
                metric_header(answer.metric),
                rows,
                lambda row: row.metric_value,
                value_type="number",
            )
        )
    return columns


def _time_series_columns(answer: FinalAnswer, rows: Sequence[Any]) -> list[TableColumnBuilder]:
    columns = [
        _make_column("time_bucket", time_header(answer.time_grain), rows, lambda row: row.time_bucket)
    ]
    if answer.grouping_columns:
        for grouping in answer.grouping_columns:
            columns.append(
                _make_column(
                    grouping.column_key,
                    _grouping_header(answer, grouping.label),
                    rows,
                    lambda row, key=grouping.column_key: _grouping_value(row, key),
                )
            )
    elif any(row.series_name for row in rows):
        columns.append(_make_column("series_name", answer.entity_label_singular, rows, lambda row: row.series_name))

    columns.extend(_display_metric_columns(answer, rows))
    return columns


def _display_metric_columns(answer: FinalAnswer, rows: Sequence[Any]) -> list[TableColumnBuilder]:
    if answer.display_metrics:
        return [
            _make_column(
                display_metric.column_key,
                metric_header(display_metric.metric),
                rows,
                lambda row, key=display_metric.column_key: _display_metadata_value(row, key),
                value_type="number",
            )
            for display_metric in answer.display_metrics
        ]
    return [
        _make_column(
            "metric_value",
            metric_header(answer.metric),
            rows,
            lambda row: row.metric_value,
            value_type="number",
        )
    ]


def _comparison_breakdown_columns(answer: FinalAnswer, rows: Sequence[Any]) -> list[TableColumnBuilder]:
    columns: list[TableColumnBuilder] = []
    if answer.time_grain:
        columns.append(_make_column("time_bucket", time_header(answer.time_grain), rows, lambda row: row.time_bucket))
    columns.append(_make_column("entity_name", answer.entity_label_singular, rows, lambda row: row.entity_name))
    if answer.context_label and any(row.context_value for row in rows):
        columns.append(_make_column("context_value", answer.context_label, rows, lambda row: row.context_value))
    for grouping in answer.grouping_columns:
        columns.append(
            _make_column(
                grouping.column_key,
                _grouping_header(answer, grouping.label),
                rows,
                lambda row, key=grouping.column_key: _grouping_value(row, key),
            )
        )
    columns.append(_make_column("games", "Games", rows, lambda row: row.games_count, value_type="integer"))
    columns.extend(_display_metric_columns(answer, rows))
    return columns


def _comparison_entity_columns(answer: FinalAnswer, rows: Sequence[Any]) -> list[TableColumnBuilder]:
    columns = [_make_column("entity_name", answer.entity_label_singular, rows, lambda row: row.entity_name)]
    if answer.context_label and any(row.context_value for row in rows):
        columns.append(_make_column("context_value", answer.context_label, rows, lambda row: row.context_value))
    if answer.season_label:
        columns.append(_make_column("season_label", "Season", rows, lambda _row: answer.season_label))
    if answer.season_type:
        columns.append(_make_column("season_type", "Season Type", rows, lambda _row: answer.season_type))
    columns.append(_make_column("games", "Games", rows, lambda row: row.games_count, value_type="integer"))
    columns.extend(_display_metric_columns(answer, rows))
    return columns


def _find_columns(rows: Sequence[dict[str, Any]]) -> list[TableColumnBuilder]:
    if not rows:
        return []
    headers = list(rows[0].keys())
    return [
        _make_column(
            header,
            field_label(header),
            rows,
            lambda row, key=header: row.get(key),
        )
        for header in headers
    ]
