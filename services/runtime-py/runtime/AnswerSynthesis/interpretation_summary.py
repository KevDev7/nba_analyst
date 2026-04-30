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

from typing import Any

from runtime.AnalysisRuntime.models import PlanFindFilter, PlanFindOrder
from runtime.AnswerSynthesis.answer_language import (
    field_phrase,
    grain_phrase,
    grouping_phrase_label,
    join_nonempty,
    join_phrase,
    metric_phrase,
    or_list_phrase,
    season_phrase,
    season_type_label,
    value_phrase,
)
from runtime.AnswerSynthesis.response_models import SynthesisPayload


def _human_metric(metric: str) -> str:
    return metric_phrase(metric)


def _season_phrase(season_label: str | None, season_type: str | None) -> str:
    return season_phrase(season_label, season_type, plural_type_only=True)


def _time_phrase(payload: SynthesisPayload) -> str:
    season_phrase = _season_phrase(payload.season_label, payload.season_type)
    if payload.window_games > 0:
        window_phrase = f"over the last {payload.window_games} games"
        return _join_nonempty([window_phrase, season_phrase])
    if payload.time_window_days:
        return f"over the last {payload.time_window_days} days"
    if payload.time_start_date and payload.time_end_date:
        return f"from {payload.time_start_date} through {payload.time_end_date}"
    if payload.time_start_date:
        return f"since {payload.time_start_date}"
    if payload.time_end_date:
        return f"through {payload.time_end_date}"
    if season_phrase:
        return season_phrase
    if payload.time_filter == "past_year":
        return "over the past year"
    if payload.time_filter == "season_type":
        season_type_text = season_type_label(payload.season_type)
        if season_type_text:
            return f"for {season_type_text}s"
    return ""


def _join_phrase(values: list[str]) -> str:
    return join_phrase(values)


def _join_nonempty(parts: list[str]) -> str:
    return join_nonempty(parts)


def _display_metric_phrase(payload: SynthesisPayload) -> str:
    if not payload.display_metrics:
        return _human_metric(payload.metric)
    return _join_phrase([_human_metric(display_metric.metric) for display_metric in payload.display_metrics])


def _extra_display_metric_phrase(payload: SynthesisPayload) -> str:
    extra_metrics = [
        _human_metric(display_metric.metric)
        for display_metric in payload.display_metrics
        if display_metric.metric != payload.metric
    ]
    return _join_phrase(extra_metrics)


def _plural_lower(payload: SynthesisPayload) -> str:
    return payload.entity_label_plural.lower()


def _singular_lower(payload: SynthesisPayload) -> str:
    return payload.entity_label_singular.lower()


def _grouping_phrase(payload: SynthesisPayload) -> str:
    if not payload.grouping_columns:
        return _singular_lower(payload)
    labels = [grouping_phrase_label(grouping.label, payload.entity_label_singular) for grouping in payload.grouping_columns]
    return _join_phrase(labels)


def _ranked_subject_phrase(payload: SynthesisPayload) -> str:
    if len(payload.grouping_columns) > 1:
        return f"{_grouping_phrase(payload)} combinations"
    return _plural_lower(payload)


def _is_ascending_metric_order(payload: SynthesisPayload) -> bool:
    return str(payload.metric_order_direction).lower() in {"asc", "ascending"}


def _ranking_limit_phrase(payload: SynthesisPayload) -> str:
    if payload.limit > 0:
        direction_label = "Bottom" if _is_ascending_metric_order(payload) else "Top"
        return f"{direction_label} {payload.limit}"
    return "Ranked from lowest to highest" if _is_ascending_metric_order(payload) else "Ranked"


def _grain_phrase(time_grain: Optional[str]) -> str:
    return grain_phrase(time_grain)


def _operator_phrase(operator: str) -> str:
    return {
        "=": "equals",
        "<>": "does not equal",
        "not_equals": "does not equal",
        ">": "is greater than",
        "greater_than": "is greater than",
        ">=": "is at least",
        "greater_than_or_equal": "is at least",
        "<": "is less than",
        "less_than": "is less than",
        "<=": "is at most",
        "less_than_or_equal": "is at most",
        "in": "is in",
        "not_in": "is not in",
        "between": "is between",
        "contains": "contains",
    }.get(operator, operator)


def _field_phrase(attribute: str) -> str:
    return field_phrase(attribute)


def _value_phrase(value: object) -> str:
    return value_phrase(value)


def _predicate_tree_phrase(predicate_tree: dict[str, Any]) -> str:
    kind = str(predicate_tree.get("kind", ""))
    if kind == "leaf":
        field = predicate_tree.get("field", {})
        attribute = str(field.get("attribute", "field")) if isinstance(field, dict) else "field"
        operator = str(predicate_tree.get("operator", ""))
        value = predicate_tree.get("value")
        return f"{_field_phrase(attribute)} {_operator_phrase(operator)} {_predicate_value_phrase(value)}"
    if kind == "and":
        children = predicate_tree.get("predicates", [])
        has_nested_logic = any(
            isinstance(child, dict) and child.get("kind") in {"and", "or", "not"}
            for child in children
        )
        return _join_predicate_children(predicate_tree, " and ", parenthesize=has_nested_logic)
    if kind == "or":
        return _join_predicate_children(predicate_tree, " or ", parenthesize=True)
    if kind == "not":
        nested = predicate_tree.get("predicate")
        if isinstance(nested, dict):
            return f"not ({_predicate_tree_phrase(nested)})"
        return "not matching the selected predicate"
    return "matching the selected predicate"


def _join_predicate_children(
    predicate_tree: dict[str, Any],
    separator: str,
    *,
    parenthesize: bool,
) -> str:
    children = [
        _predicate_tree_phrase(child)
        for child in predicate_tree.get("predicates", [])
        if isinstance(child, dict)
    ]
    if not children:
        return "matching the selected predicate"
    if len(children) == 1:
        return children[0]
    joined = separator.join(children)
    return f"({joined})" if parenthesize else joined


def _predicate_value_phrase(value: object) -> str:
    if isinstance(value, dict):
        kind = value.get("kind")
        if kind == "scalar":
            return _value_phrase(value.get("value"))
        if kind == "list":
            values = value.get("values", [])
            if isinstance(values, list):
                return _format_list_phrase([_value_phrase(item) for item in values])
        if kind == "range":
            return f"{_value_phrase(value.get('lower'))} and {_value_phrase(value.get('upper'))}"
    return _value_phrase(value)


def _format_list_phrase(values: list[str]) -> str:
    return or_list_phrase(values)


def _find_filter_phrase(filter_value: PlanFindFilter) -> str:
    if filter_value.filter_kind == "last_n_games" and filter_value.filter_value:
        return f"over the last {filter_value.filter_value} games"
    if filter_value.filter_kind == "last_n_days" and filter_value.filter_value:
        return f"over the last {filter_value.filter_value} days"
    if filter_value.filter_kind == "date_from" and filter_value.filter_value:
        return f"since {_value_phrase(filter_value.filter_value)}"
    if filter_value.filter_kind == "date_to" and filter_value.filter_value:
        return f"through {_value_phrase(filter_value.filter_value)}"
    if filter_value.filter_kind == "exact_season" and filter_value.filter_value:
        return f"in the {_value_phrase(filter_value.filter_value)} season"
    if filter_value.filter_kind == "season_type" and filter_value.filter_value:
        return f"for {_value_phrase(filter_value.filter_value)}s"
    if filter_value.filter_kind == "past_year":
        return "over the past year"
    return ""


def _find_time_phrase(payload: SynthesisPayload) -> str:
    exact_season = None
    season_type = None
    date_from = None
    date_to = None
    remaining_filters = []
    for filter_value in payload.find_filters:
        if filter_value.filter_kind == "exact_season":
            exact_season = str(filter_value.filter_value) if filter_value.filter_value else None
        elif filter_value.filter_kind == "season_type":
            season_type = str(filter_value.filter_value) if filter_value.filter_value else None
        elif filter_value.filter_kind == "date_from":
            date_from = str(filter_value.filter_value) if filter_value.filter_value else None
        elif filter_value.filter_kind == "date_to":
            date_to = str(filter_value.filter_value) if filter_value.filter_value else None
        else:
            remaining_filters.append(filter_value)
    season_phrase = _season_phrase(exact_season, season_type)
    if date_from and date_to:
        date_phrase = f"from {date_from} through {date_to}"
    elif date_from:
        date_phrase = f"since {date_from}"
    elif date_to:
        date_phrase = f"through {date_to}"
    else:
        date_phrase = ""
    phrases = [
        _find_filter_phrase(filter_value) for filter_value in remaining_filters
    ] + [date_phrase, season_phrase]
    return _join_nonempty(phrases) or "across all available data"


def _find_order_phrase(find_orders: list[PlanFindOrder]) -> str:
    if not find_orders:
        return ""
    order_phrases = [
        f"{_field_phrase(find_order.order_field)} {find_order.order_direction}"
        for find_order in find_orders
    ]
    return f"sorted by {_join_phrase(order_phrases)}"


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
    display_metric_phrase = _display_metric_phrase(payload)
    extra_display_metric_phrase = _extra_display_metric_phrase(payload)
    time_phrase = _time_phrase(payload)
    row_predicate_phrase = _predicate_tree_phrase(payload.row_predicate) if payload.row_predicate else ""
    row_filters_phrase = f"where {row_predicate_phrase}" if row_predicate_phrase else ""
    result_predicate_phrase = _predicate_tree_phrase(payload.result_predicate) if payload.result_predicate else ""
    result_predicate_clause = f"where {result_predicate_phrase}" if result_predicate_phrase else ""

    if payload.result_shape == "comparison":
        breakdown_phrase = (
            f"by {_grouping_phrase(payload)}"
            if payload.grouping_columns
            else ""
        )
        return _join_nonempty(
            [
                f"{_comparison_entities(payload)} compared by {display_metric_phrase}",
                breakdown_phrase,
                _grain_phrase(payload.time_grain) if payload.time_grain else "",
                row_filters_phrase,
                result_predicate_clause,
                time_phrase,
            ]
        ) + "."

    if payload.result_shape == "find_rows":
        if payload.find_predicate_tree:
            predicate_phrases = [_predicate_tree_phrase(payload.find_predicate_tree)]
        else:
            predicate_phrases = []
        predicate_phrase = " and ".join(predicate_phrases)
        where_phrase = f"where {predicate_phrase}" if predicate_phrase else "matching the selected filters"
        return _join_nonempty(
            [
                f"{payload.entity_label_plural} {where_phrase}",
                _find_time_phrase(payload),
                _find_order_phrase(payload.find_orders),
            ]
        ) + "."

    if payload.result_shape == "time_series":
        series_phrase = (
            f"by {_grouping_phrase(payload)}"
            if payload.grouping_columns
            else f"by {_singular_lower(payload)}"
            if payload.entity_label_singular != "Series"
            else ""
        )
        return _join_nonempty(
            [
                display_metric_phrase.capitalize(),
                series_phrase,
                row_filters_phrase,
                result_predicate_clause,
                _grain_phrase(payload.time_grain),
                time_phrase,
            ]
        ) + "."

    if payload.result_shape == "aggregate":
        return _join_nonempty(
            [
                f"{display_metric_phrase.capitalize()} by {_grouping_phrase(payload)}",
                row_filters_phrase,
                result_predicate_clause,
                time_phrase,
            ]
        ) + "."

    if payload.result_shape == "object_rows":
        return _join_nonempty(
            [
                f"{payload.entity_label_plural} and their {display_metric_phrase}",
                row_filters_phrase,
                result_predicate_clause,
                time_phrase,
            ]
        ) + "."

    limit_phrase = _ranking_limit_phrase(payload)
    return _join_nonempty(
        [
            f"{limit_phrase} {_ranked_subject_phrase(payload)} by {metric}",
            f"showing {extra_display_metric_phrase}" if extra_display_metric_phrase else "",
            row_filters_phrase,
            result_predicate_clause,
            time_phrase,
        ]
    ) + "."
