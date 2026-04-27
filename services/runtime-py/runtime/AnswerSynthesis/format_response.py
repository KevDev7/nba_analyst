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

from .response_models import FinalAnswer


DISPLAY_ROW_LIMIT = 50
DISPLAY_METADATA_TYPE_ORDER = (
    "identity_metadata",
    "filter_context",
    "analytical_metadata",
    "evidence",
)

RowT = TypeVar("RowT")


def _display_rows(rows: Sequence[RowT]) -> tuple[Sequence[RowT], int]:
    return rows[:DISPLAY_ROW_LIMIT], len(rows)


def _append_display_notice(lines: list[str], total_rows: int) -> None:
    if total_rows > DISPLAY_ROW_LIMIT:
        lines.append(f"Showing first {DISPLAY_ROW_LIMIT} of {total_rows} rows.")
        lines.append("")


def _metric_header(metric: str) -> str:
    return {
        "total_points": "Total Points",
        "points_total": "Total Points",
        "average_points": "Average Points",
        "points_per_game": "Average Points",
        "games_played": "Games Played",
        "wins": "Wins",
        "losses": "Losses",
        "win_percentage": "Win Percentage",
    }.get(metric, metric.replace("_", " ").title())


def _metric_value(metric: str, value: float) -> str:
    if metric in {"average_points", "points_per_game"}:
        return f"{value:.1f}"
    if metric == "win_percentage":
        return f"{value:.3f}"
    return str(int(round(value)))


def _time_header(time_grain: str | None) -> str:
    return {
        "day": "Day",
        "week": "Week",
        "month": "Month",
        "season": "Season",
    }.get(time_grain or "", "Time")


def _field_header(field_name: str) -> str:
    return field_name.replace("_", " ").title()


def _cell_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and "_" in value:
        return value.replace("_", " ").title()
    return str(value)


def _metadata_value(metric: str, key: str, value: object) -> str:
    if value is None:
        return ""
    if key == "games_played":
        return str(int(round(float(value))))
    if key == "minutes":
        return f"{float(value):.1f}"
    return _metric_value(metric, float(value)) if isinstance(value, (float, int)) else _cell_value(value)


def _display_metadata_value(row: Any, key: str) -> object:
    display_values = getattr(row, "display_values", {})
    if isinstance(display_values, dict) and key in display_values:
        return display_values[key]
    return getattr(row, key, None)


def _row_table_columns(answer: FinalAnswer, rows: Sequence[Any], include_rank: bool) -> list[tuple[str, Callable[[Any], str]]]:
    columns: list[tuple[str, Callable[[Any], str]]] = []
    if include_rank:
        columns.append(("Rank", lambda row: str(row.rank)))

    columns.append((answer.entity_label_singular, lambda row: _cell_value(row.entity_name)))

    if answer.context_label and any(row.context_value for row in rows):
        columns.append((answer.context_label, lambda row: _cell_value(row.context_value)))

    if answer.season_label:
        columns.append(("Season", lambda _row: _cell_value(answer.season_label)))
    if answer.season_type:
        columns.append(("Season Type", lambda _row: _cell_value(answer.season_type)))

    for metadata_type in DISPLAY_METADATA_TYPE_ORDER:
        for metadata in answer.display_metadata:
            if metadata.column_type != metadata_type:
                continue
            if metadata.column_key == answer.metric:
                continue
            if not any(_display_metadata_value(row, metadata.column_key) is not None for row in rows):
                continue
            columns.append(
                (
                    metadata.label,
                    lambda row, key=metadata.column_key: _metadata_value(
                        answer.metric, key, _display_metadata_value(row, key)
                    ),
                )
            )

    columns.append((_metric_header(answer.metric), lambda row: _metric_value(answer.metric, row.metric_value)))
    return columns


def _append_row_table(lines: list[str], answer: FinalAnswer, rows: Sequence[Any], include_rank: bool) -> None:
    columns = _row_table_columns(answer, rows, include_rank)
    lines.append(" | ".join(header for header, _getter in columns))
    lines.append(" | ".join("---" for _header, _getter in columns))
    for row in rows:
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
        if any(row.series_name for row in rows_to_display):
            lines.append(f"{time_header} | {answer.entity_label_singular} | {_metric_header(answer.metric)}")
            lines.append("--- | --- | ---")
            for row in rows_to_display:
                lines.append(
                    f"{row.time_bucket} | {(row.series_name or '')} | {_metric_value(answer.metric, row.metric_value)}"
                )
        else:
            lines.append(f"{time_header} | {_metric_header(answer.metric)}")
            lines.append("--- | ---")
            for row in rows_to_display:
                lines.append(
                    f"{row.time_bucket} | {_metric_value(answer.metric, row.metric_value)}"
                )
        return "\n".join(lines)

    rows_to_display, total_rows = _display_rows(answer.rows)
    _append_display_notice(lines, total_rows)
    _append_row_table(lines, answer, rows_to_display, include_rank=True)
    return "\n".join(lines)
