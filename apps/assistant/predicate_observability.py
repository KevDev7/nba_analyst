# Purpose:
# Build focused predicate debug traces from the existing assistant pipeline data.
#
# Uses:
# - semantic draft JSON handed to Haskell
# - Haskell planner output
#
# Produces:
# - compact predicate-only observability payloads for CLI/web debug views

from __future__ import annotations

from typing import Any


def build_predicate_trace(
    semantic_draft: dict[str, Any],
    planner_output: dict[str, Any],
) -> dict[str, Any]:
    # Plain English: pull only predicate-related decisions out of the big debug
    # blobs so a developer can follow draft -> IR -> resolved -> plan -> SQL.
    query = _as_dict(planner_output.get("query"))
    resolved_query = _as_dict(planner_output.get("resolved_query"))
    execution_plan = _as_dict(planner_output.get("execution_plan"))
    return {
        "draft_predicates": _draft_predicates(semantic_draft),
        "grounded_ir_predicates": _grounded_ir_predicates(query),
        "resolved_predicates": _resolved_predicates(resolved_query),
        "plan_predicates": _plan_predicates(execution_plan),
        "sql_predicates": _sql_predicates(execution_plan),
    }


def _draft_predicates(semantic_draft: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "filters": semantic_draft.get("filters"),
            "predicate": semantic_draft.get("predicate"),
            "result_filters": semantic_draft.get("result_filters"),
            "result_predicate": semantic_draft.get("result_predicate"),
        }
    )


def _grounded_ir_predicates(query: dict[str, Any]) -> dict[str, Any]:
    kind = query.get("kind")
    spec = _as_dict(query.get("spec"))
    if kind in {"metric_query", "object_query"}:
        shared = _as_dict(spec.get("sharedQuery"))
        return _compact(
            {
                "filters": shared.get("filters"),
                "rowPredicate": shared.get("rowPredicate"),
                "resultPredicate": shared.get("resultPredicate"),
            }
        )
    if kind == "find_query":
        return _compact(
            {
                "findPredicateTree": spec.get("findPredicateTree"),
                "findFilters": spec.get("findFilters"),
            }
        )
    return {}


def _resolved_predicates(resolved_query: dict[str, Any]) -> dict[str, Any]:
    resolved = _as_dict(resolved_query.get("resolved"))
    return _compact(
        {
            "rowPredicateResolved": resolved.get("rowPredicateResolved"),
            "resultPredicateResolved": resolved.get("resultPredicateResolved"),
            "trendRowPredicateResolved": resolved.get("trendRowPredicateResolved"),
            "trendResultPredicateResolved": resolved.get("trendResultPredicateResolved"),
            "objectRowPredicateResolved": resolved.get("objectRowPredicateResolved"),
            "objectResultPredicateResolved": resolved.get("objectResultPredicateResolved"),
            "resolvedFindPredicateTree": resolved.get("resolvedFindPredicateTree"),
            "resolvedFindFilters": resolved.get("resolvedFindFilters"),
        }
    )


def _plan_predicates(execution_plan: dict[str, Any]) -> dict[str, Any]:
    answer_context = _as_dict(execution_plan.get("answer_context"))
    find_context = _as_dict(answer_context.get("find"))
    predicate_context = _as_dict(answer_context.get("predicates"))
    return _compact(
        {
            "find_predicate_tree": find_context.get("predicate_tree"),
            "find_filters": find_context.get("filters"),
            "row_predicate": predicate_context.get("row"),
            "result_predicate": predicate_context.get("result"),
        }
    )


def _sql_predicates(execution_plan: dict[str, Any]) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    execution = _as_dict(execution_plan.get("execution"))
    for index, step in enumerate(execution.get("steps", []), start=1):
        if not isinstance(step, dict) or step.get("kind") != "run_sql":
            continue
        clauses = _sql_predicate_clauses(str(step.get("sql") or ""))
        traces.append(
            {
                "step_index": index,
                "kind": step.get("kind"),
                "clauses": clauses,
            }
        )
    return traces


def _sql_predicate_clauses(sql: str) -> list[str]:
    clauses: list[str] = []
    for raw_line in sql.splitlines():
        line = raw_line.strip()
        if line.startswith(("WHERE ", "AND ", "HAVING ")):
            clauses.append(line)
    return clauses


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if _has_value(value)}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if value == [] or value == {}:
        return False
    return True


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
