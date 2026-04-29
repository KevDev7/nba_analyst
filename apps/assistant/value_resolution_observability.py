# Purpose:
# Build a shared trace for user-facing values resolved into ontology values.
#
# Uses:
# - Python entity resolution metadata stored on the semantic draft
# - Haskell query/plan predicate values before and after ontology aliasing
#
# Produces:
# - compact debug payload showing raw value -> canonical value decisions

from __future__ import annotations

from typing import Any


def build_value_resolution_trace(
    semantic_draft: dict[str, Any],
    planner_output: dict[str, Any],
) -> dict[str, Any]:
    query = _as_dict(planner_output.get("query"))
    execution_plan = _as_dict(planner_output.get("execution_plan"))
    trace = _as_dict(semantic_draft.get("value_resolution_trace"))
    return {
        "entity_resolutions": trace.get("entity_resolutions", []),
        "predicate_value_resolutions": _predicate_value_resolutions(query, execution_plan),
    }


def _predicate_value_resolutions(query: dict[str, Any], execution_plan: dict[str, Any]) -> list[dict[str, Any]]:
    resolutions: list[dict[str, Any]] = []
    for raw_predicate, canonical_predicate in zip(
        _query_predicate_roots(query),
        _plan_predicate_roots(execution_plan),
    ):
        resolutions.extend(_predicate_tree_value_resolutions(raw_predicate, canonical_predicate))
    return resolutions


def _query_predicate_roots(query: dict[str, Any]) -> list[dict[str, Any]]:
    kind = query.get("kind")
    spec = _as_dict(query.get("spec"))
    if kind in {"metric_query", "object_query"}:
        shared = _as_dict(spec.get("sharedQuery"))
        return [
            predicate
            for predicate in [shared.get("rowPredicate"), shared.get("resultPredicate")]
            if isinstance(predicate, dict)
        ]
    if kind == "find_query":
        predicate = spec.get("findPredicateTree")
        return [predicate] if isinstance(predicate, dict) else []
    return []


def _plan_predicate_roots(execution_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        predicate
        for predicate in [
            execution_plan.get("row_predicate"),
            execution_plan.get("result_predicate"),
            execution_plan.get("find_predicate_tree"),
        ]
        if isinstance(predicate, dict)
    ]


def _predicate_tree_value_resolutions(
    raw_predicate: dict[str, Any],
    canonical_predicate: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_kind = raw_predicate.get("kind")
    canonical_kind = canonical_predicate.get("kind")
    if raw_kind != canonical_kind:
        return []
    if raw_kind == "leaf":
        return _leaf_value_resolutions(raw_predicate, canonical_predicate)
    if raw_kind in {"and", "or"}:
        resolutions: list[dict[str, Any]] = []
        raw_children = [child for child in raw_predicate.get("predicates", []) if isinstance(child, dict)]
        canonical_children = [child for child in canonical_predicate.get("predicates", []) if isinstance(child, dict)]
        for raw_child, canonical_child in zip(raw_children, canonical_children):
            resolutions.extend(_predicate_tree_value_resolutions(raw_child, canonical_child))
        return resolutions
    if raw_kind == "not":
        raw_child = raw_predicate.get("predicate")
        canonical_child = canonical_predicate.get("predicate")
        if isinstance(raw_child, dict) and isinstance(canonical_child, dict):
            return _predicate_tree_value_resolutions(raw_child, canonical_child)
    return []


def _leaf_value_resolutions(
    raw_leaf: dict[str, Any],
    canonical_leaf: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_field = _as_dict(raw_leaf.get("field"))
    canonical_field = _as_dict(canonical_leaf.get("field"))
    if raw_field != canonical_field or raw_leaf.get("operator") != canonical_leaf.get("operator"):
        return []
    raw_values = _flatten_predicate_value(_as_dict(raw_leaf.get("value")))
    canonical_values = _flatten_predicate_value(_as_dict(canonical_leaf.get("value")))
    resolutions: list[dict[str, Any]] = []
    for raw_value, canonical_value in zip(raw_values, canonical_values):
        if raw_value == canonical_value:
            continue
        resolutions.append(
            {
                "raw_value": raw_value,
                "canonical_value": canonical_value,
                "target_object": canonical_field.get("targetObject"),
                "attribute": canonical_field.get("attribute"),
                "source": "ontology_value_aliases",
            }
        )
    return resolutions


def _flatten_predicate_value(value: dict[str, Any]) -> list[Any]:
    kind = value.get("kind")
    if kind == "scalar":
        return [value.get("value")]
    if kind == "list":
        return list(value.get("values", []))
    if kind == "range":
        return [value.get("lower"), value.get("upper")]
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
