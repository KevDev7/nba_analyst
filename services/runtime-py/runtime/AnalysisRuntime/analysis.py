# Purpose:
# Hold Python-side analysis hooks for future execution-plan steps.
#
# Uses:
# - intermediate results from earlier runtime steps
#
# Produces:
# - derived analytical outputs for future slices
#
# Next:
# - runner.py

from __future__ import annotations

from collections import defaultdict

from .models import ComparisonEntityStats, ComparisonResult, ComparisonRow

def _aggregate_metric(metric_aggregation: str, rows: list[dict[str, object]]) -> float:
    metric_values = [float(row["metric_value"]) for row in rows]
    if metric_aggregation == "sum":
        return float(sum(metric_values))
    if metric_aggregation == "avg":
        return round(sum(metric_values) / len(metric_values), 1) if metric_values else 0.0
    raise ValueError(
        f"Comparison analysis does not support metric aggregation '{metric_aggregation}'."
    )


def run_analysis(analysis_spec: str, runtime_state: object, plan: object) -> object:
    if analysis_spec != "CompareEntities":
        raise NotImplementedError(
            f"Python analysis step '{analysis_spec}' is not implemented."
        )

    raw_rows = runtime_state.latest_result or []
    grouped = defaultdict(list)
    for row in raw_rows:
        grouped[int(row["entity_id"])].append(row)

    if len(grouped) != 2:
        raise ValueError("CompareEntities expects exactly two entities in runtime state.")

    stats = []
    comparison_rows = []
    for entity_id, rows in sorted(grouped.items()):
        entity_name = str(rows[0]["entity_name"]) if rows else ""
        games_count = len(rows)
        context_value = str(rows[0]["context_value"]) if rows and rows[0]["context_value"] is not None else None
        metric_value = _aggregate_metric(str(plan.metric_aggregation), rows)
        stats.append(
            ComparisonEntityStats(
                entity_id=entity_id,
                entity_name=entity_name,
                context_value=context_value,
                metric_value=metric_value,
                games_count=games_count,
            )
        )
        comparison_rows.extend(
            ComparisonRow(
                entity_id=int(row["entity_id"]),
                entity_name=str(row["entity_name"]),
                context_value=(
                    str(row["context_value"]) if row["context_value"] is not None else None
                ),
                game_date=str(row["game_date"]),
                metric_value=float(row["metric_value"]),
            )
            for row in rows
        )

    entity_a, entity_b = stats
    if entity_a.metric_value >= entity_b.metric_value:
      leader = entity_a.entity_name
      differential = entity_a.metric_value - entity_b.metric_value
    else:
      leader = entity_b.entity_name
      differential = entity_b.metric_value - entity_a.metric_value

    result = ComparisonResult(
        leader=leader,
        metric_differential=round(differential, 1),
        entity_a=entity_a,
        entity_b=entity_b,
        per_game_rows=comparison_rows,
    )
    runtime_state.artifacts["comparison"] = result
    return result
