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

from .answer_language import (
    format_metric_value,
    grain_adjective,
    grouping_phrase_label,
    join_nonempty,
    join_phrase,
    metric_phrase,
    season_phrase,
)
from .interpretation_summary import build_interpretation
from .response_models import FinalAnswer, SynthesisPayload, final_answer_from_payload


def _human_metric(metric: str) -> str:
    return metric_phrase(metric)


def _format_metric_value(metric: str, value: float) -> str:
    return format_metric_value(metric, value)


def _grain_adjective(time_grain: object) -> str:
    return grain_adjective(time_grain)


def _time_filter_phrase(
    time_filter: object,
    season_label: object = None,
    season_type: object = None,
    time_window_days: object = None,
    time_start_date: object = None,
    time_end_date: object = None,
) -> str:
    season_scope = _season_scope_phrase(season_label, season_type)
    if season_scope:
        return f" {season_scope}"
    if time_window_days:
        return f" over the last {time_window_days} days"
    if time_start_date and time_end_date:
        return f" from {time_start_date} through {time_end_date}"
    if time_start_date:
        return f" since {time_start_date}"
    if time_end_date:
        return f" through {time_end_date}"
    if time_filter == "season_type" and season_type:
        return f" for {str(season_type).replace('_', ' ')}"
    return {
        "past_year": " over the past year",
        "all": "",
        None: "",
    }.get(time_filter, f" with {str(time_filter).replace('_', ' ')}")


def _join_nonempty(parts: list[str]) -> str:
    return join_nonempty(parts)


def _join_phrase(values: list[str]) -> str:
    return join_phrase(values)


def _display_metric_phrase(payload: SynthesisPayload) -> str:
    if not payload.display_metrics:
        return _human_metric(payload.metric)
    return _join_phrase([_human_metric(display_metric.metric) for display_metric in payload.display_metrics])


def _grouping_phrase(payload: SynthesisPayload) -> str:
    if not payload.grouping_columns:
        return payload.entity_label_singular.lower()
    labels = [grouping_phrase_label(grouping.label, payload.entity_label_singular) for grouping in payload.grouping_columns]
    return _join_phrase(labels)


def _ranked_subject_phrase(payload: SynthesisPayload) -> str:
    if len(payload.grouping_columns) > 1:
        return f"{_grouping_phrase(payload)} combinations"
    return payload.entity_label_plural.lower()


def _is_ascending_metric_order(payload: SynthesisPayload) -> bool:
    return str(payload.metric_order_direction).lower() in {"asc", "ascending"}


def _ranking_limit_phrase(payload: SynthesisPayload) -> str:
    if payload.limit > 0:
        direction_label = "Bottom" if _is_ascending_metric_order(payload) else "Top"
        return f"{direction_label} {payload.limit}"
    return "ranked from lowest to highest" if _is_ascending_metric_order(payload) else "ranked"


def _ranking_leader_phrase(payload: SynthesisPayload, entity_name: str, metric: str, value: float) -> str:
    metric_value = _format_metric_value(metric, value)
    metric_label = _human_metric(metric)
    if _is_ascending_metric_order(payload):
        return f"{entity_name} is lowest with {metric_value} {metric_label}."
    return f"{entity_name} leads with {metric_value} {metric_label}."


def _season_scope_phrase(season_label: object, season_type: object) -> str:
    return season_phrase(
        str(season_label) if season_label else None,
        str(season_type) if season_type else None,
        plural_type_only=False,
    )


def _result_time_phrase(
    window_games: int,
    season_label: object,
    season_type: object,
    time_window_days: object = None,
    time_start_date: object = None,
    time_end_date: object = None,
) -> str:
    window_phrase = f"over the last {window_games} games" if window_games > 0 else ""
    days_phrase = f"over the last {time_window_days} days" if time_window_days else ""
    if time_start_date and time_end_date:
        date_phrase = f"from {time_start_date} through {time_end_date}"
    elif time_start_date:
        date_phrase = f"since {time_start_date}"
    elif time_end_date:
        date_phrase = f"through {time_end_date}"
    else:
        date_phrase = ""
    return _join_nonempty([window_phrase, days_phrase, date_phrase, _season_scope_phrase(season_label, season_type)])


def synthesize_answer(payload: SynthesisPayload) -> FinalAnswer:
    result_shape = payload.result_shape
    rows = list(payload.rows)
    aggregate_rows = list(payload.aggregate_rows)
    object_rows = list(payload.object_rows)
    find_rows = list(payload.find_rows)
    entity_label_singular = payload.entity_label_singular
    entity_label_plural = payload.entity_label_plural
    metric = payload.metric
    window_games = payload.window_games
    time_grain = payload.time_grain
    time_filter = payload.time_filter
    time_window_days = payload.time_window_days
    time_start_date = payload.time_start_date
    time_end_date = payload.time_end_date
    season_label = payload.season_label
    season_type = payload.season_type
    limit = payload.limit
    comparison = payload.comparison
    time_series_rows = list(payload.time_series_rows)
    grouping_columns = list(payload.grouping_columns)
    display_metrics = list(payload.display_metrics)
    interpretation = build_interpretation(payload)

    if comparison is not None:
        metric_phrase = _display_metric_phrase(payload)
        differential_text = _format_metric_value(metric, comparison.metric_differential)
        compared_count = len(comparison.entities) if comparison.entities else 2
        time_scope = _result_time_phrase(window_games, season_label, season_type, time_window_days, time_start_date, time_end_date)
        if not time_scope and time_filter == "past_year":
            time_scope = "over the past year"
        breakdown_scope = (
            f" by {_grouping_phrase(payload)}" if grouping_columns else ""
        )
        grain_scope = (
            f" by {time_grain}" if time_grain else ""
        )
        comparison_scope = (
            _join_nonempty([f"among {compared_count} {entity_label_plural.lower()}", time_scope])
            if compared_count > 2
            else time_scope
        )
        if display_metrics:
            summary = _join_nonempty(
                [
                    f"{metric_phrase.capitalize()} comparison{breakdown_scope}{grain_scope}",
                    comparison_scope,
                    "is shown below.",
                ]
            )
        elif comparison.breakdown_rows:
            summary = (
                f"{_human_metric(metric).capitalize()} comparison{breakdown_scope}{grain_scope} "
                f"{comparison_scope} is shown below. Overall, {comparison.leader} led by "
                f"{differential_text} {_human_metric(metric)}."
            )
        else:
            summary = (
                f"{comparison.leader} led in {_human_metric(metric)} {comparison_scope} "
                f"by {differential_text} {_human_metric(metric)}."
            )
        return final_answer_from_payload(
            payload,
            summary=summary,
            interpretation=interpretation,
            rows=[],
            aggregate_rows=[],
            object_rows=[],
            time_series_rows=[],
            find_rows=[],
            comparison=comparison,
        )

    if result_shape == "find_rows":
        summary = (
            f"Matching {entity_label_plural.lower()} are shown below."
            if find_rows
            else f"No matching {entity_label_plural.lower()} were returned."
        )
        return final_answer_from_payload(
            payload,
            summary=summary,
            interpretation=interpretation,
            rows=[],
            aggregate_rows=[],
            object_rows=[],
            time_series_rows=[],
            find_rows=find_rows,
            comparison=None,
        )

    if aggregate_rows:
        time_scope = _result_time_phrase(window_games, season_label, season_type, time_window_days, time_start_date, time_end_date)
        summary = (
            f"{_human_metric(metric).capitalize()} by {_grouping_phrase(payload)} "
            f"{time_scope} are shown below."
        )
        return final_answer_from_payload(
            payload,
            summary=summary,
            interpretation=interpretation,
            rows=[],
            aggregate_rows=aggregate_rows,
            object_rows=[],
            time_series_rows=[],
            find_rows=[],
            comparison=None,
        )

    if object_rows:
        leader = object_rows[0]
        time_scope = _result_time_phrase(window_games, season_label, season_type, time_window_days, time_start_date, time_end_date)
        summary = (
            f"{entity_label_plural} ordered by {_human_metric(metric)} {time_scope}: "
            f"{leader.entity_name} leads with "
            f"{_format_metric_value(metric, leader.metric_value)} {_human_metric(metric)}."
        )
        return final_answer_from_payload(
            payload,
            summary=summary,
            interpretation=interpretation,
            rows=[],
            aggregate_rows=[],
            object_rows=object_rows,
            time_series_rows=[],
            find_rows=[],
            comparison=None,
        )

    if time_series_rows:
        grain_label = _grain_adjective(time_grain)
        metric_phrase = _display_metric_phrase(payload)
        filter_phrase = _time_filter_phrase(
            time_filter,
            season_label,
            season_type,
            time_window_days,
            time_start_date,
            time_end_date,
        )
        if grouping_columns:
            summary = (
                f"{grain_label} {metric_phrase} by {_grouping_phrase(payload)}{filter_phrase} "
                f"are shown below."
            )
        elif any(row.series_name for row in time_series_rows):
            summary = (
                f"{grain_label} {metric_phrase} by {entity_label_singular.lower()}{filter_phrase} "
                f"are shown below."
            )
        else:
            summary = (
                f"{grain_label} {metric_phrase}{filter_phrase} are shown below."
            )
        return final_answer_from_payload(
            payload,
            summary=summary,
            interpretation=interpretation,
            rows=[],
            aggregate_rows=[],
            object_rows=[],
            time_series_rows=time_series_rows,
            find_rows=[],
            comparison=None,
        )

    if rows:
        leader = rows[0]
        time_scope = _result_time_phrase(window_games, season_label, season_type, time_window_days, time_start_date, time_end_date)
        if limit > 0:
            summary = (
                f"{_ranking_limit_phrase(payload)} {_ranked_subject_phrase(payload)} by {_human_metric(metric)} {time_scope}: "
                f"{_ranking_leader_phrase(payload, leader.entity_name, metric, leader.metric_value)}"
            )
        else:
            summary = (
                f"{_ranked_subject_phrase(payload).capitalize()} {_ranking_limit_phrase(payload)} by {_human_metric(metric)} {time_scope}: "
                f"{_ranking_leader_phrase(payload, leader.entity_name, metric, leader.metric_value)}"
            )
    else:
        summary = (
            f"No {entity_label_plural.lower()} were returned for the requested {_human_metric(metric)} ranking."
        )

    return final_answer_from_payload(
        payload,
        summary=summary,
        interpretation=interpretation,
        rows=rows,
        aggregate_rows=[],
        object_rows=[],
        time_series_rows=[],
        find_rows=[],
        comparison=None,
    )
