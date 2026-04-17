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
from runtime.AnalysisRuntime.models import ComparisonResult, ObjectRow, RankingRow


def _human_metric(metric: str) -> str:
    return {
        "total_points": "total points",
        "average_points": "average points",
        "games_played": "games played",
        "points_per_36": "points per 36",
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
    limit = int(payload["limit"])
    assumptions = list(payload.get("assumptions", []))
    comparison_payload = payload.get("comparison")

    if comparison_payload is not None:
        comparison = ComparisonResult(**comparison_payload)
        summary = (
            f"{comparison.leader} scored more total points over the last "
            f"{window_games} games, leading by {comparison.point_differential} points."
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
            limit=limit,
            assumptions=assumptions,
            rows=[],
            object_rows=[],
            comparison=comparison,
        )

    if object_rows:
        leader = object_rows[0]
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
            limit=limit,
            assumptions=assumptions,
            rows=[],
            object_rows=object_rows,
            comparison=None,
        )

    if rows:
        leader = rows[0]
        if limit > 0:
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
            f"No {entity_label_plural.lower()} were returned for the requested {_human_metric(metric)} ranking "
            f"over the last {window_games} games."
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
        limit=limit,
        assumptions=assumptions,
        rows=rows,
        object_rows=[],
        comparison=None,
    )
