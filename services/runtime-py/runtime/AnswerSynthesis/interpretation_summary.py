# Purpose:
# Build the user-facing "Interpreted as" sentence from structured results.
#
# Uses:
# - SynthesisPayload metadata from the grounded runtime result
#
# Produces:
# - a concise semantic summary of what the system actually executed
#
# Next:
# - synthesize.py

from __future__ import annotations

from typing import Iterable, Optional

from runtime.AnalysisRuntime.models import PlanFindFilter, PlanFindPredicate, PlanLinkedFilter
from runtime.AnswerSynthesis.response_models import SynthesisPayload


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
    }.get(metric, metric.replace("_", " "))


def _season_type_label(season_type: Optional[str]) -> Optional[str]:
    if not season_type:
        return None
    return season_type.replace("_", " ")


def _season_phrase(season_label: Optional[str], season_type: Optional[str]) -> str:
    season_type_label = _season_type_label(season_type)
    if season_label and season_type_label:
        return f"in the {season_label} {season_type_label}"
    if season_label:
        return f"in the {season_label} season"
    if season_type_label:
        return f"for {season_type_label}s"
    return ""


def _time_phrase(payload: SynthesisPayload) -> str:
    season_phrase = _season_phrase(payload.season_label, payload.season_type)
    if payload.window_games > 0:
        window_phrase = f"over the last {payload.window_games} games"
        return _join_nonempty([window_phrase, season_phrase])
    if season_phrase:
        return season_phrase
    if payload.time_filter == "past_year":
        return "over the past year"
    if payload.time_filter == "season_type":
        season_type_label = _season_type_label(payload.season_type)
        if season_type_label:
            return f"for {season_type_label}s"
    return ""


def _join_nonempty(parts: Iterable[str]) -> str:
    return " ".join(part for part in parts if part)


def _plural_lower(payload: SynthesisPayload) -> str:
    return payload.entity_label_plural.lower()


def _singular_lower(payload: SynthesisPayload) -> str:
    return payload.entity_label_singular.lower()


def _grain_phrase(time_grain: Optional[str]) -> str:
    return {
        "day": "by day",
        "week": "by week",
        "month": "by month",
        "season": "by season",
    }.get(time_grain or "", "over time")


def _operator_phrase(operator: str) -> str:
    return {
        "=": "equals",
        ">": "is greater than",
        ">=": "is at least",
        "<": "is less than",
        "<=": "is at most",
    }.get(operator, operator)


def _field_phrase(attribute: str) -> str:
    return attribute.replace("_", " ")


def _value_phrase(value: object) -> str:
    if isinstance(value, str):
        return value.replace("_", " ")
    return str(value)


def _find_predicate_phrase(predicate: PlanFindPredicate) -> str:
    return (
        f"{_field_phrase(predicate.attribute)} "
        f"{_operator_phrase(predicate.operator)} "
        f"{_value_phrase(predicate.value)}"
    )


def _find_filter_phrase(filter_value: PlanFindFilter) -> str:
    if filter_value.filter_kind == "last_n_games" and filter_value.filter_value:
        return f"over the last {filter_value.filter_value} games"
    if filter_value.filter_kind == "exact_season" and filter_value.filter_value:
        return f"in the {_value_phrase(filter_value.filter_value)} season"
    if filter_value.filter_kind == "season_type" and filter_value.filter_value:
        return f"for {_value_phrase(filter_value.filter_value)}s"
    if filter_value.filter_kind == "past_year":
        return "over the past year"
    return ""


def _linked_filter_phrase(filter_value: PlanLinkedFilter) -> str:
    value = _value_phrase(filter_value.value)
    attribute = filter_value.attribute
    if filter_value.target_object == "Team" and attribute == "team_name":
        return f"for the {value}"
    if filter_value.target_object == "Team" and attribute == "team_abbreviation":
        return f"for {value}"
    if attribute == "full_name":
        return f"for {value}"

    target_label = filter_value.target_object.replace("_", " ").lower()
    attribute_label = _field_phrase(attribute)
    if target_label and target_label not in attribute_label:
        attribute_label = f"{target_label} {attribute_label}"
    return f"where {attribute_label} equals {value}"


def _linked_filters_phrase(filters: Iterable[PlanLinkedFilter]) -> str:
    phrases = [_linked_filter_phrase(filter_value) for filter_value in filters]
    return " and ".join(phrase for phrase in phrases if phrase)


def _find_time_phrase(payload: SynthesisPayload) -> str:
    exact_season = None
    season_type = None
    remaining_filters = []
    for filter_value in payload.find_filters:
        if filter_value.filter_kind == "exact_season":
            exact_season = str(filter_value.filter_value) if filter_value.filter_value else None
        elif filter_value.filter_kind == "season_type":
            season_type = str(filter_value.filter_value) if filter_value.filter_value else None
        else:
            remaining_filters.append(filter_value)
    season_phrase = _season_phrase(exact_season, season_type)
    phrases = [
        _find_filter_phrase(filter_value) for filter_value in remaining_filters
    ] + [season_phrase]
    return _join_nonempty(phrases) or "across all available data"


def _comparison_entities(payload: SynthesisPayload) -> str:
    if payload.comparison is None:
        return _plural_lower(payload)
    entities = payload.comparison.entities or [
        payload.comparison.entity_a,
        payload.comparison.entity_b,
    ]
    names = [entity.entity_name for entity in entities]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def build_interpretation(payload: SynthesisPayload) -> str:
    metric = _human_metric(payload.metric)
    time_phrase = _time_phrase(payload)
    linked_filters_phrase = _linked_filters_phrase(payload.linked_filters)

    if payload.result_shape == "comparison":
        return _join_nonempty(
            [
                f"{_comparison_entities(payload)} compared by {metric}",
                linked_filters_phrase,
                time_phrase,
            ]
        ) + "."

    if payload.result_shape == "find_rows":
        predicate_phrase = " and ".join(
            _find_predicate_phrase(predicate)
            for predicate in payload.find_predicates
        )
        where_phrase = f"where {predicate_phrase}" if predicate_phrase else "matching the selected filters"
        return _join_nonempty(
            [
                f"{payload.entity_label_plural} {where_phrase}",
                linked_filters_phrase,
                _find_time_phrase(payload),
            ]
        ) + "."

    if payload.result_shape == "time_series":
        series_phrase = (
            f"by {_singular_lower(payload)}"
            if payload.entity_label_singular != "Series"
            else ""
        )
        return _join_nonempty(
            [
                metric.capitalize(),
                series_phrase,
                linked_filters_phrase,
                _grain_phrase(payload.time_grain),
                time_phrase,
            ]
        ) + "."

    if payload.result_shape == "aggregate":
        return _join_nonempty(
            [
                f"{metric.capitalize()} by {_singular_lower(payload)}",
                linked_filters_phrase,
                time_phrase,
            ]
        ) + "."

    if payload.result_shape == "object_rows":
        return _join_nonempty(
            [
                f"{payload.entity_label_plural} and their {metric}",
                linked_filters_phrase,
                time_phrase,
            ]
        ) + "."

    limit_phrase = f"Top {payload.limit}" if payload.limit > 0 else "Ranked"
    return _join_nonempty(
        [
            f"{limit_phrase} {_plural_lower(payload)} by {metric}",
            linked_filters_phrase,
            time_phrase,
        ]
    ) + "."
