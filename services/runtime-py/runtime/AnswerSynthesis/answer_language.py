# Purpose:
# Centralize shared answer-language helpers so summaries, interpretations,
# and table formatting do not drift from each other.
#
# Uses:
# - metric keys, field keys, time metadata from final answer payloads
#
# Produces:
# - human-facing labels, value formatting, and small phrase fragments
#
# Next:
# - interpretation_summary.py, synthesize.py, format_response.py

from __future__ import annotations

from typing import Iterable, Optional


METRIC_LABELS = {
    "total_points": "total points",
    "points_total": "total points",
    "average_points": "average points",
    "points_per_game": "average points",
    "average_minutes": "average minutes",
    "minutes_per_game": "average minutes",
    "total_assists": "assists",
    "assists_total": "assists",
    "average_assists": "average assists",
    "assists_per_game": "average assists",
    "total_rebounds": "rebounds",
    "rebounds_total": "rebounds",
    "average_rebounds": "average rebounds",
    "rebounds_per_game": "average rebounds",
    "games_played": "games played",
    "points_per_36": "points per 36",
    "wins": "wins",
    "losses": "losses",
    "win_percentage": "win percentage",
}

AVERAGE_METRICS = {
    "average_points",
    "points_per_game",
    "average_minutes",
    "minutes_per_game",
    "average_assists",
    "assists_per_game",
    "average_rebounds",
    "rebounds_per_game",
}


def metric_phrase(metric: str, *, prettify_unknown: bool = True) -> str:
    fallback = metric.replace("_", " ") if prettify_unknown else metric
    return METRIC_LABELS.get(metric, fallback)


def metric_header(metric: str) -> str:
    return metric_phrase(metric).title()


def format_metric_value(metric: str, value: float, *, table: bool = False) -> str:
    if metric in AVERAGE_METRICS:
        return f"{value:.1f}"
    if table and metric == "win_percentage":
        return f"{value:.3f}"
    return str(int(round(value)))


def field_label(field_name: str) -> str:
    return field_name.replace("_", " ").title()


def field_phrase(field_name: str) -> str:
    return field_name.replace("_", " ")


def cell_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and "_" in value:
        return value.replace("_", " ").title()
    return str(value)


def value_phrase(value: object) -> str:
    if isinstance(value, str):
        return value.replace("_", " ")
    return str(value)


def join_nonempty(parts: Iterable[str]) -> str:
    return " ".join(part for part in parts if part)


def join_phrase(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def or_list_phrase(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} or {values[1]}"
    return f"{', '.join(values[:-1])}, or {values[-1]}"


def season_type_label(season_type: Optional[str]) -> Optional[str]:
    if not season_type:
        return None
    return season_type.replace("_", " ")


def season_phrase(
    season_label: Optional[str],
    season_type: Optional[str],
    *,
    plural_type_only: bool,
) -> str:
    season_type_text = season_type_label(season_type)
    if season_label and season_type_text:
        return f"in the {season_label} {season_type_text}"
    if season_label:
        return f"in the {season_label} season"
    if season_type_text:
        suffix = "s" if plural_type_only else ""
        return f"for {season_type_text}{suffix}"
    return ""


def time_header(time_grain: str | None) -> str:
    return {
        "day": "Day",
        "week": "Week",
        "month": "Month",
        "season": "Season",
    }.get(time_grain or "", "Time")


def grain_adjective(time_grain: object) -> str:
    return {
        "day": "Daily",
        "week": "Weekly",
        "month": "Monthly",
        "season": "Season-by-season",
    }.get(str(time_grain), "Time-series")


def grain_phrase(time_grain: Optional[str]) -> str:
    return {
        "day": "by day",
        "week": "by week",
        "month": "by month",
        "season": "by season",
    }.get(time_grain or "", "over time")
