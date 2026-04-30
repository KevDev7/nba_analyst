# Purpose:
# Format the final answer payload into a CLI-friendly response.
#
# Uses:
# - FinalAnswer models from response_models.py
#
# Produces:
# - a human-readable answer string
#
# Next:
# - apps/cli/main.py

from __future__ import annotations

from typing import Any, Callable, Sequence, TypeVar

from .answer_language import cell_value, field_label, format_metric_value, metric_header, time_header
from .response_models import FinalAnswer


DISPLAY_ROW_LIMIT = 50
DISPLAY_METADATA_TYPE_ORDER = (
    "identity_metadata",
    "filter_context",
    "analytical_metadata",
    "evidence",
    "filter_metadata",
)

RowT = TypeVar("RowT")


def _display_rows(rows: Sequence[RowT]) -> tuple[Sequence[RowT], int]:
    return rows[:DISPLAY_ROW_LIMIT], len(rows)


def _append_display_notice(lines: list[str], total_rows: int) -> None:
    if total_rows > DISPLAY_ROW_LIMIT:
        lines.append(f"Showing first {DISPLAY_ROW_LIMIT} of {total_rows} rows.")
        lines.append("")


def _metric_header(metric: str) -> str:
    return metric_header(metric)


def _metric_value(metric: str, value: float) -> str:
    return format_metric_value(metric, value, table=True)


def _time_header(time_grain: str | None) -> str:
    return time_header(time_grain)


def _field_header(field_name: str) -> str:
    return field_label(field_name)


def _cell_value(value: object) -> str:
    return cell_value(value)


def _metadata_value(metric: str, key: str, value: object, label: str = "") -> str:
    if value is None:
        return ""
    if key == "games_played":
        return str(int(round(float(value))))
    if key == "minutes":
        return f"{float(value):.1f}"
    if "percentage" in label.lower() or "percentage" in key.lower():
        return f"{float(value):.3f}"
    return _metric_value(metric, float(value)) if isinstance(value, (float, int)) else _cell_value(value)


def _display_metadata_value(row: Any, key: str) -> object:
    display_values = getattr(row, "display_values", {})
    if isinstance(display_values, dict) and key in display_values:
        return display_values[key]
    return getattr(row, key, None)


def _display_metric_value(row: Any, key: str, metric: str) -> str:
    value = _display_metadata_value(row, key)
    if value is None:
        return ""
    return _metric_value(metric, float(value))


def _grouping_header(answer: FinalAnswer, label: str) -> str:
    if label in {"team_name", "full_name"}:
        return answer.entity_label_singular
    return _field_header(label)


def _grouping_value(row: Any, key: str) -> object:
    group_values = getattr(row, "group_values", {})
    if isinstance(group_values, dict) and key in group_values:
        return group_values[key]
    return getattr(row, key, None)


def _metadata_duplicates_display_metric(answer: FinalAnswer, metadata_key: str) -> bool:
    display_metric_names = {display_metric.metric for display_metric in answer.display_metrics}
    if metadata_key == "minutes" and display_metric_names & {"average_minutes", "minutes_per_game"}:
        return True
    if metadata_key == "games_played" and "games_played" in display_metric_names:
        return True
    return False


def _row_table_columns(answer: FinalAnswer, rows: Sequence[Any], include_rank: bool) -> list[tuple[str, Callable[[Any], str]]]:
    columns: list[tuple[str, Callable[[Any], str]]] = []
    if include_rank:
        columns.append(("Rank", lambda row: str(row.rank)))

    grouping_labels = {grouping.label for grouping in answer.grouping_columns}
    if answer.result_shape in {"aggregate", "ranking"} and answer.grouping_columns:
        for grouping in answer.grouping_columns:
            columns.append(
                (
                    _grouping_header(answer, grouping.label),
                    lambda row, key=grouping.column_key: _cell_value(_grouping_value(row, key)),
                )
            )
    else:
        columns.append((answer.entity_label_singular, lambda row: _cell_value(row.entity_name)))

    if answer.result_shape != "aggregate" and answer.context_label and any(row.context_value for row in rows):
        columns.append((answer.context_label, lambda row: _cell_value(row.context_value)))

    if answer.season_label and "season_year" not in grouping_labels:
        columns.append(("Season", lambda _row: _cell_value(answer.season_label)))
    if answer.season_type and "season_type" not in grouping_labels:
        columns.append(("Season Type", lambda _row: _cell_value(answer.season_type)))

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
                (
                    _field_header(metadata.label),
                    lambda row, key=metadata.column_key, label=metadata.label: _metadata_value(
                        answer.metric, key, _display_metadata_value(row, key), label
                    ),
                )
            )

    if answer.display_metrics:
        for display_metric in answer.display_metrics:
            columns.append(
                (
                    _metric_header(display_metric.metric),
                    lambda row, key=display_metric.column_key, metric=display_metric.metric: _display_metric_value(row, key, metric),
                )
            )
    else:
        columns.append((_metric_header(answer.metric), lambda row: _metric_value(answer.metric, row.metric_value)))
    return columns


def _append_row_table(lines: list[str], answer: FinalAnswer, rows: Sequence[Any], include_rank: bool) -> None:
    columns = _row_table_columns(answer, rows, include_rank)
    lines.append(" | ".join(header for header, _getter in columns))
    lines.append(" | ".join("---" for _header, _getter in columns))
    for row in rows:
        lines.append(" | ".join(getter(row) for _header, getter in columns))


def _time_series_metric_columns(answer: FinalAnswer) -> list[tuple[str, Callable[[Any], str]]]:
    if answer.display_metrics:
        return [
            (
                _metric_header(display_metric.metric),
                lambda row, key=display_metric.column_key, metric=display_metric.metric: _display_metric_value(row, key, metric),
            )
            for display_metric in answer.display_metrics
        ]
    return [(_metric_header(answer.metric), lambda row: _metric_value(answer.metric, row.metric_value))]


def _append_comparison_breakdown_table(lines: list[str], answer: FinalAnswer) -> None:
    if answer.comparison is None:
        return
    rows_to_display, total_rows = _display_rows(answer.comparison.breakdown_rows)
    _append_display_notice(lines, total_rows)
    columns: list[tuple[str, Callable[[Any], str]]] = []
    if answer.time_grain:
        columns.append((_time_header(answer.time_grain), lambda row: _cell_value(row.time_bucket)))
    columns.append((answer.entity_label_singular, lambda row: _cell_value(row.entity_name)))
    if answer.context_label and any(row.context_value for row in rows_to_display):
        columns.append((answer.context_label, lambda row: _cell_value(row.context_value)))
    for grouping in answer.grouping_columns:
        columns.append(
            (
                _grouping_header(answer, grouping.label),
                lambda row, key=grouping.column_key: _cell_value(_grouping_value(row, key)),
            )
        )
    columns.append(("Games", lambda row: str(row.games_count)))
    if answer.display_metrics:
        for display_metric in answer.display_metrics:
            columns.append(
                (
                    _metric_header(display_metric.metric),
                    lambda row, key=display_metric.column_key, metric=display_metric.metric: _display_metric_value(row, key, metric),
                )
            )
    else:
        columns.append((_metric_header(answer.metric), lambda row: _metric_value(answer.metric, row.metric_value)))
    lines.append(" | ".join(header for header, _getter in columns))
    lines.append(" | ".join("---" for _header, _getter in columns))
    for row in rows_to_display:
        lines.append(" | ".join(getter(row) for _header, getter in columns))


def _append_comparison_entity_table(lines: list[str], answer: FinalAnswer) -> None:
    if answer.comparison is None:
        return
    rows_to_display, total_rows = _display_rows(answer.comparison.entities)
    _append_display_notice(lines, total_rows)
    columns: list[tuple[str, Callable[[Any], str]]] = [
        (answer.entity_label_singular, lambda row: _cell_value(row.entity_name))
    ]
    if answer.context_label and any(row.context_value for row in rows_to_display):
        columns.append((answer.context_label, lambda row: _cell_value(row.context_value)))
    if answer.season_label:
        columns.append(("Season", lambda _row: _cell_value(answer.season_label)))
    if answer.season_type:
        columns.append(("Season Type", lambda _row: _cell_value(answer.season_type)))
    columns.append(("Games", lambda row: str(row.games_count)))
    for display_metric in answer.display_metrics:
        columns.append(
            (
                _metric_header(display_metric.metric),
                lambda row, key=display_metric.column_key, metric=display_metric.metric: _display_metric_value(row, key, metric),
            )
        )
    lines.append(" | ".join(header for header, _getter in columns))
    lines.append(" | ".join("---" for _header, _getter in columns))
    for row in rows_to_display:
        lines.append(" | ".join(getter(row) for _header, getter in columns))


def format_response(answer: FinalAnswer) -> str:
    lines = [f"Interpreted as: {answer.interpretation}", "", answer.summary, ""]
    if answer.assumptions:
        lines.append("Assumptions:")
        lines.extend(f"- {assumption}" for assumption in answer.assumptions)
        lines.append("")

    if answer.comparison is not None:
        lines.append("Comparison")
        lines.append("---")
        if answer.comparison.breakdown_rows:
            _append_comparison_breakdown_table(lines, answer)
            return "\n".join(lines)
        if answer.display_metrics:
            _append_comparison_entity_table(lines, answer)
            return "\n".join(lines)
        compared_entities = answer.comparison.entities or [
            answer.comparison.entity_a,
            answer.comparison.entity_b,
        ]
        for entity in compared_entities:
            context_suffix = f" ({entity.context_value})" if entity.context_value else ""
            lines.append(
                f"{entity.entity_name}{context_suffix}: "
                f"{_metric_value(answer.metric, entity.metric_value)} {_metric_header(answer.metric).lower()} "
                f"across {entity.games_count} games"
            )
        lines.append(
            f"Differential: {_metric_value(answer.metric, answer.comparison.metric_differential)} "
            f"{_metric_header(answer.metric).lower()}"
        )
        return "\n".join(lines)

    if answer.find_rows:
        rows_to_display, total_rows = _display_rows(answer.find_rows)
        _append_display_notice(lines, total_rows)
        headers = list(rows_to_display[0].keys())
        lines.append(" | ".join(_field_header(header) for header in headers))
        lines.append(" | ".join("---" for _ in headers))
        for row in rows_to_display:
            lines.append(" | ".join(_cell_value(row.get(header)) for header in headers))
        return "\n".join(lines)

    if answer.aggregate_rows:
        rows_to_display, total_rows = _display_rows(answer.aggregate_rows)
        _append_display_notice(lines, total_rows)
        _append_row_table(lines, answer, rows_to_display, include_rank=False)
        return "\n".join(lines)

    if answer.object_rows:
        rows_to_display, total_rows = _display_rows(answer.object_rows)
        _append_display_notice(lines, total_rows)
        _append_row_table(lines, answer, rows_to_display, include_rank=False)
        return "\n".join(lines)

    if answer.time_series_rows:
        rows_to_display, total_rows = _display_rows(answer.time_series_rows)
        _append_display_notice(lines, total_rows)
        time_header = _time_header(answer.time_grain)
        metric_columns = _time_series_metric_columns(answer)
        if answer.grouping_columns:
            group_columns = [
                (
                    _grouping_header(answer, grouping.label),
                    lambda row, key=grouping.column_key: _cell_value(_grouping_value(row, key)),
                )
                for grouping in answer.grouping_columns
            ]
            headers = [time_header] + [header for header, _getter in group_columns] + [header for header, _getter in metric_columns]
            lines.append(" | ".join(headers))
            lines.append(" | ".join("---" for _header in headers))
            for row in rows_to_display:
                group_values = [getter(row) for _header, getter in group_columns]
                metric_values = [getter(row) for _header, getter in metric_columns]
                lines.append(" | ".join([_cell_value(row.time_bucket)] + group_values + metric_values))
        elif any(row.series_name for row in rows_to_display):
            headers = [time_header, answer.entity_label_singular] + [header for header, _getter in metric_columns]
            lines.append(" | ".join(headers))
            lines.append(" | ".join("---" for _header in headers))
            for row in rows_to_display:
                metric_values = [getter(row) for _header, getter in metric_columns]
                lines.append(" | ".join([_cell_value(row.time_bucket), _cell_value(row.series_name or "")] + metric_values))
        else:
            headers = [time_header] + [header for header, _getter in metric_columns]
            lines.append(" | ".join(headers))
            lines.append(" | ".join("---" for _header in headers))
            for row in rows_to_display:
                metric_values = [getter(row) for _header, getter in metric_columns]
                lines.append(" | ".join([_cell_value(row.time_bucket)] + metric_values))
        return "\n".join(lines)

    rows_to_display, total_rows = _display_rows(answer.rows)
    _append_display_notice(lines, total_rows)
    _append_row_table(lines, answer, rows_to_display, include_rank=True)
    return "\n".join(lines)
