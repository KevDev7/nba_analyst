from __future__ import annotations

from copy import deepcopy
from typing import Any


def normalize_flat_filter_predicates(draft: dict[str, Any]) -> dict[str, Any]:
    # Repair draft shape before Haskell decoding. This does not decide whether
    # a field exists; it only moves predicate-shaped filters into predicate trees.
    normalized = deepcopy(draft)
    row_filters, row_predicates = _split_filter_lane(normalized.get("filters", []), keep_time_scope=True)
    result_filters, result_predicates = _split_filter_lane(normalized.get("result_filters", []), keep_time_scope=False)

    normalized["filters"] = row_filters
    normalized["result_filters"] = result_filters
    normalized["predicate"] = _merge_predicates(normalized.get("predicate"), _combine_and(row_predicates))
    normalized["result_predicate"] = _merge_predicates(
        normalized.get("result_predicate"),
        _combine_and(result_predicates),
    )
    return normalized


def _split_filter_lane(raw_filters: Any, *, keep_time_scope: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    filters = raw_filters if isinstance(raw_filters, list) else []
    remaining: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    equality_groups = _equality_groups(filters, keep_time_scope=keep_time_scope)
    emitted_equality_groups: set[str] = set()

    for filter_value in filters:
        if not isinstance(filter_value, dict):
            continue
        if keep_time_scope and _is_time_scope_filter(filter_value):
            remaining.append(filter_value)
            continue
        if _is_plain_equality_filter(filter_value):
            group_key = _equality_group_key(filter_value)
            grouped_filters = equality_groups[group_key]
            if len(grouped_filters) <= 1:
                remaining.append(filter_value)
            elif group_key not in emitted_equality_groups:
                promoted.append(_in_predicate_from_equality_group(grouped_filters))
                emitted_equality_groups.add(group_key)
            continue
        predicate = _predicate_from_rich_filter(filter_value)
        if predicate is None:
            remaining.append(filter_value)
        else:
            promoted.append(predicate)

    return remaining, promoted


def _equality_groups(raw_filters: list[Any], *, keep_time_scope: bool) -> dict[str, list[dict[str, Any]]]:
    equality_groups: dict[str, list[dict[str, Any]]] = {}

    for filter_value in raw_filters:
        if not isinstance(filter_value, dict):
            continue
        if keep_time_scope and _is_time_scope_filter(filter_value):
            continue
        if _is_plain_equality_filter(filter_value):
            equality_groups.setdefault(_equality_group_key(filter_value), []).append(filter_value)
    return equality_groups


def _predicate_from_rich_filter(filter_value: dict[str, Any]) -> dict[str, Any] | None:
    field = filter_value.get("field")
    if not isinstance(field, str) or field.strip() == "":
        return None

    op = filter_value.get("op") or filter_value.get("operator")
    op_key = _normalized(op)
    value = filter_value.get("value")

    if isinstance(value, list):
        return {"kind": "leaf", "field": field, "op": _list_operator(op_key), "value": value}
    if isinstance(value, dict) and ("lower" in value or "upper" in value):
        return {"kind": "leaf", "field": field, "op": "between", "value": value}
    if op_key in {"in", "notin"}:
        return None
    if op_key == "between":
        return None
    if op_key in {"contains", "like", "includes"}:
        return {"kind": "leaf", "field": field, "op": "contains", "value": value}
    if op_key in {"!=", "<>", "notequals", "notequal", "neq", "not"}:
        return {"kind": "leaf", "field": field, "op": "!=", "value": value}
    return None


def _list_operator(op_key: str) -> str:
    if op_key in {"notin"}:
        return "not_in"
    return "in"


def _is_plain_equality_filter(filter_value: dict[str, Any]) -> bool:
    field = filter_value.get("field")
    value = filter_value.get("value")
    if not isinstance(field, str) or field.strip() == "":
        return False
    if isinstance(value, (list, dict)):
        return False
    op_key = _normalized(filter_value.get("op") or filter_value.get("operator"))
    return op_key in {"", "=", "eq", "equals", "is"}


def _equality_group_key(filter_value: dict[str, Any]) -> str:
    return _normalized(filter_value.get("field"))


def _in_predicate_from_equality_group(grouped_filters: list[dict[str, Any]]) -> dict[str, Any]:
    first_filter = grouped_filters[0]
    return {
        "kind": "leaf",
        "field": first_filter["field"],
        "op": "in",
        "value": [filter_value.get("value") for filter_value in grouped_filters],
    }


def _merge_predicates(existing: Any, added: dict[str, Any] | None) -> Any:
    if added is None:
        return existing
    if not isinstance(existing, dict):
        return added
    if existing.get("kind") == "and" and isinstance(existing.get("predicates"), list):
        merged = dict(existing)
        merged["predicates"] = [*existing["predicates"], added]
        return merged
    return {"kind": "and", "predicates": [existing, added]}


def _combine_and(predicates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not predicates:
        return None
    if len(predicates) == 1:
        return predicates[0]
    return {"kind": "and", "predicates": predicates}


def _is_time_scope_filter(filter_value: dict[str, Any]) -> bool:
    field_key = _normalized(filter_value.get("field"))
    value_key = _normalized(filter_value.get("value"))
    return (
        field_key in {"season", "seasonyear", "seasons", "year", "seasontype", "gametype"}
        or field_key in {"date", "gamedate", "datefrom", "dateto", "since", "until", "through"}
        or "seasontype" in field_key
        or value_key in {"regularseason", "regular", "playoffs", "playoff", "postseason"}
    )


def _normalized(value: Any) -> str:
    return "".join(character.lower() for character in str(value or "").strip() if character.isalnum() or character in {"!", "=", "<", ">"})
