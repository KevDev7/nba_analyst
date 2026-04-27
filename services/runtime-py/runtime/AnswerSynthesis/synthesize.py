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
from runtime.AnalysisRuntime.models import AggregateRow, ComparisonResult, ObjectRow, RankingRow, TimeSeriesRow


def _human_metric(metric: str) -> str:
    return {
        "total_points": "total points",
        "points_total": "total points",
        "average_points": "average points",
        "points_per_game": "average points",
        "games_played": "games played",
        "points_per_36": "points per 36",
        "wins": "wins",
        "losses": "losses",
        "win_percentage": "win percentage",
    }.get(metric, metric)


def _format_metric_value(metric: str, value: float) -> str:
    if metric in {"average_points", "points_per_game"}:
        return f"{value:.1f}"
    return str(int(round(value)))


def _grain_adjective(time_grain: object) -> str:
    return {
        "day": "Daily",
        "week": "Weekly",
        "month": "Monthly",
        "season": "Season-by-season",
    }.get(str(time_grain), "Time-series")


def _time_filter_phrase(time_filter: object, season_type: object = None) -> str:
    if time_filter == "season_type" and season_type:
        return f" for {str(season_type).replace('_', ' ')}"
    return {
        "past_year": " over the past year",
        "all": "",
        None: "",
    }.get(time_filter, f" with {str(time_filter).replace('_', ' ')}")


def synthesize_answer(payload: Dict[str, object]) -> FinalAnswer:
    query_kind = str(payload["query_kind"])
    result_shape = str(payload["result_shape"])
    rows = [RankingRow(**row) for row in payload["rows"]]
    aggregate_rows = [AggregateRow(**row) for row in payload.get("aggregate_rows", [])]
    object_rows = [ObjectRow(**row) for row in payload.get("object_rows", [])]
    find_rows = list(payload.get("find_rows", []))
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
        compared_count = len(comparison.entities) if comparison.entities else 2
        comparison_scope = (
            f"among {compared_count} {entity_label_plural.lower()}"
            if compared_count > 2
            else f"over the last {window_games} games"
        )
        summary = (
            f"{comparison.leader} led in {_human_metric(metric)} {comparison_scope} "
            f"by {differential_text} {_human_metric(metric)}."
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
            aggregate_rows=[],
            object_rows=[],
            time_series_rows=[],
            find_rows=[],
            comparison=comparison,
        )

    if find_rows:
        summary = f"Matching {entity_label_plural.lower()} are shown below."
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
            aggregate_rows=[],
            object_rows=[],
            time_series_rows=[],
            find_rows=find_rows,
            comparison=None,
        )

    if aggregate_rows:
        if season_label and season_type:
            summary = (
                f"{_human_metric(metric).capitalize()} by {entity_label_singular.lower()} in the "
                f"{season_label} {season_type.replace('_', ' ')} are shown below."
            )
        else:
            summary = (
                f"{_human_metric(metric).capitalize()} by {entity_label_singular.lower()} over the last "
                f"{window_games} games are shown below."
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
            aggregate_rows=aggregate_rows,
            object_rows=[],
            time_series_rows=[],
            find_rows=[],
            comparison=None,
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
            aggregate_rows=[],
            object_rows=object_rows,
            time_series_rows=[],
            find_rows=[],
            comparison=None,
        )

    if time_series_rows:
        grain_label = _grain_adjective(time_grain)
        filter_phrase = _time_filter_phrase(time_filter, season_type)
        if any(row.series_name for row in time_series_rows):
            summary = (
                f"{grain_label} {_human_metric(metric)} by {entity_label_singular.lower()}{filter_phrase} "
                f"are shown below."
            )
        else:
            summary = (
                f"{grain_label} {_human_metric(metric)}{filter_phrase} are shown below."
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
            aggregate_rows=[],
            object_rows=[],
            time_series_rows=time_series_rows,
            find_rows=[],
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
        aggregate_rows=[],
        object_rows=[],
        time_series_rows=[],
        find_rows=[],
        comparison=None,
    )
