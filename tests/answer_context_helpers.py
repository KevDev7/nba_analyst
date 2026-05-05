from __future__ import annotations

from typing import Any

from runtime.AnswerSynthesis.response_models import FinalAnswer, SynthesisPayload


CONTEXT_KEYS = {
    "query_kind",
    "result_shape",
    "entity_label_singular",
    "entity_label_plural",
    "context_label",
    "metric",
    "metric_aggregation",
    "metric_order_direction",
    "rank_intent_label",
    "window_games",
    "time_grain",
    "time_filter",
    "time_window_days",
    "time_start_date",
    "time_end_date",
    "season_label",
    "season_type",
    "limit",
    "find_predicate_tree",
    "find_filters",
    "find_orders",
    "row_predicate",
    "result_predicate",
    "grouping_columns",
    "display_metadata",
    "display_metrics",
    "assumptions",
}


def answer_context_from_fields(**values: Any) -> dict[str, Any]:
    return {
        "query_kind": values.get("query_kind", "metric_query"),
        "result_shape": values.get("result_shape", "ranking"),
        "subject": {
            "singular": values.get("entity_label_singular", "Player"),
            "plural": values.get("entity_label_plural", "Players"),
            "context_label": values.get("context_label", "Team"),
        },
        "metric": {
            "key": values.get("metric", "average_points"),
            "aggregation": values.get("metric_aggregation", "avg"),
            "order_direction": values.get("metric_order_direction", "DESC"),
        },
        "time": {
            "window_games": values.get("window_games", 0),
            "grain": values.get("time_grain"),
            "filter": values.get("time_filter"),
            "window_days": values.get("time_window_days"),
            "start_date": values.get("time_start_date"),
            "end_date": values.get("time_end_date"),
            "season_label": values.get("season_label"),
            "season_type": values.get("season_type"),
        },
        "ranking": {
            "intent_label": values.get("rank_intent_label"),
            "limit": values.get("limit", 0),
        },
        "find": {
            "predicate_tree": values.get("find_predicate_tree"),
            "filters": values.get("find_filters") or [],
            "orders": values.get("find_orders") or [],
        },
        "predicates": {
            "row": values.get("row_predicate"),
            "result": values.get("result_predicate"),
        },
        "display": {
            "grouping_columns": values.get("grouping_columns") or [],
            "metadata": values.get("display_metadata") or [],
            "metrics": values.get("display_metrics") or [],
        },
        "assumptions": values.get("assumptions") or [],
    }


def _split_answer_context(values: dict[str, Any]) -> dict[str, Any]:
    context_values = {key: values.pop(key) for key in list(values) if key in CONTEXT_KEYS}
    return values.pop("answer_context", None) or answer_context_from_fields(**context_values)


def build_synthesis_payload(**values: Any) -> SynthesisPayload:
    answer_context = _split_answer_context(values)
    return SynthesisPayload(answer_context=answer_context, **values)


def build_final_answer(**values: Any) -> FinalAnswer:
    answer_context = _split_answer_context(values)
    return FinalAnswer(answer_context=answer_context, **values)
