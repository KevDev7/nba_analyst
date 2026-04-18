# Purpose:
# Generate a grounded narrative answer from packaged runtime results.
#
# Uses:
# - packaged runtime results from package_results.py
#
# Produces:
# - summary text and a typed FinalAnswer payload
#
# Next:
# - format_response.py

from __future__ import annotations

from typing import Dict

from .response_models import FinalAnswer
from runtime.AnalysisRuntime.models import ComparisonResult, ObjectRow, RankingRow, TimeSeriesRow


def _human_metric(metric: str) -> str:
    return {
        "total_points": "total points",
        "average_points": "average points",
        "games_played": "games played",
        "points_per_36": "points per 36",
        "wins": "wins",
        "losses": "losses",
        "win_percentage": "win percentage",
    }.get(metric, metric)


def _format_metric_value(metric: str, value: float) -> str:
    if metric == "average_points":
        return f"{value:.1f}"
    return str(int(round(value)))


def synthesize_answer(payload: Dict[str, object]) -> FinalAnswer:
    query_kind = str(payload["query_kind"])
    result_shape = str(payload["result_shape"])
    rows = [RankingRow(**row) for row in payload["rows"]]
    object_rows = [ObjectRow(**row) for row in payload.get("object_rows", [])]
    entity_label_singular = str(payload["entity_label_singular"])
    entity_label_plural = str(payload["entity_label_plural"])
    context_label = str(payload["context_label"])
    metric = str(payload["metric"])
    window_games = int(payload["window_games"])
    time_grain = payload.get("time_grain")
    time_filter = payload.get("time_filter")
    season_label = payload.get("season_label")
    season_type = payload.get("season_type")
    limit = int(payload["limit"])
    assumptions = list(payload.get("assumptions", []))
    comparison_payload = payload.get("comparison")
    time_series_rows = [TimeSeriesRow(**row) for row in payload.get("time_series_rows", [])]

    if comparison_payload is not None:
        comparison = ComparisonResult(**comparison_payload)
        differential_text = _format_metric_value(metric, comparison.metric_differential)
        summary = (
            f"{comparison.leader} led in {_human_metric(metric)} over the last "
            f"{window_games} games by {differential_text} {_human_metric(metric)}."
        )
        return FinalAnswer(
            summary=summary,
            query_kind=query_kind,
            result_shape=result_shape,
            entity_label_singular=entity_label_singular,
            entity_label_plural=entity_label_plural,
            context_label=context_label,
            metric=metric,
            window_games=window_games,
            time_grain=time_grain,
            time_filter=time_filter,
            season_label=season_label,
            season_type=season_type,
            limit=limit,
            assumptions=assumptions,
            rows=[],
            object_rows=[],
            time_series_rows=[],
            comparison=comparison,
        )

    if object_rows:
        leader = object_rows[0]
        if season_label and season_type:
            summary = (
                f"{entity_label_plural} ordered by {_human_metric(metric)} in the "
                f"{season_label} {season_type.replace('_', ' ')}: {leader.entity_name} leads with "
                f"{_format_metric_value(metric, leader.metric_value)} {_human_metric(metric)}."
            )
        else:
            summary = (
                f"{entity_label_plural} ordered by {_human_metric(metric)} over the last "
                f"{window_games} games: {leader.entity_name} leads with "
                f"{_format_metric_value(metric, leader.metric_value)} {_human_metric(metric)}."
            )
        return FinalAnswer(
            summary=summary,
            query_kind=query_kind,
            result_shape=result_shape,
            entity_label_singular=entity_label_singular,
            entity_label_plural=entity_label_plural,
            context_label=context_label,
            metric=metric,
            window_games=window_games,
            time_grain=time_grain,
            time_filter=time_filter,
            season_label=season_label,
            season_type=season_type,
            limit=limit,
            assumptions=assumptions,
            rows=[],
            object_rows=object_rows,
            time_series_rows=[],
            comparison=None,
        )

    if time_series_rows:
        if any(row.series_name for row in time_series_rows):
            summary = (
                f"Monthly {_human_metric(metric)} by {entity_label_singular.lower()} over the past year "
                f"are shown below."
            )
        else:
            summary = (
                f"Monthly {_human_metric(metric)} over the past year are shown below."
            )
        return FinalAnswer(
            summary=summary,
            query_kind=query_kind,
            result_shape=result_shape,
            entity_label_singular=entity_label_singular,
            entity_label_plural=entity_label_plural,
            context_label=context_label,
            metric=metric,
            window_games=window_games,
            time_grain=time_grain,
            time_filter=time_filter,
            season_label=season_label,
            season_type=season_type,
            limit=limit,
            assumptions=assumptions,
            rows=[],
            object_rows=[],
            time_series_rows=time_series_rows,
            comparison=None,
        )

    if rows:
        leader = rows[0]
        if season_label and season_type:
            if limit > 0:
                summary = (
                    f"Top {limit} {entity_label_plural.lower()} by {_human_metric(metric)} in the "
                    f"{season_label} {season_type.replace('_', ' ')}: {leader.entity_name} leads with "
                    f"{_format_metric_value(metric, leader.metric_value)} {_human_metric(metric)}."
                )
            else:
                summary = (
                    f"{entity_label_plural} ranked by {_human_metric(metric)} in the "
                    f"{season_label} {season_type.replace('_', ' ')}: {leader.entity_name} leads with "
                    f"{_format_metric_value(metric, leader.metric_value)} {_human_metric(metric)}."
                )
        elif limit > 0:
            summary = (
                f"Top {limit} {entity_label_plural.lower()} by {_human_metric(metric)} over the last "
                f"{window_games} games: {leader.entity_name} leads with "
                f"{_format_metric_value(metric, leader.metric_value)} {_human_metric(metric)}."
            )
        else:
            summary = (
                f"{entity_label_plural} ranked by {_human_metric(metric)} over the last "
                f"{window_games} games: {leader.entity_name} leads with "
                f"{_format_metric_value(metric, leader.metric_value)} {_human_metric(metric)}."
            )
    else:
        summary = (
            f"No {entity_label_plural.lower()} were returned for the requested {_human_metric(metric)} ranking."
        )

    return FinalAnswer(
        summary=summary,
        query_kind=query_kind,
        result_shape=result_shape,
        entity_label_singular=entity_label_singular,
        entity_label_plural=entity_label_plural,
        context_label=context_label,
        metric=metric,
        window_games=window_games,
        time_grain=time_grain,
        time_filter=time_filter,
        season_label=season_label,
        season_type=season_type,
        limit=limit,
        assumptions=assumptions,
        rows=rows,
        object_rows=[],
        time_series_rows=[],
        comparison=None,
    )
