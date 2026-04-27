# Purpose:
# Hold Python-side analysis hooks for execution-plan steps.
#
# Uses:
# - intermediate results from earlier runtime steps
#
# Produces:
# - derived analytical outputs
#
# Next:
# - runner.py

from __future__ import annotations

from collections import defaultdict

from .models import ComparisonEntityStats, ComparisonResult, ComparisonRow

def _aggregate_metric(metric_aggregation: str, rows: list[dict[str, object]]) -> float:
    # Re-aggregate the per-row metric values the SQL step returned.
    metric_values = [float(row["metric_value"]) for row in rows]
    if metric_aggregation == "sum":
        return float(sum(metric_values))
    if metric_aggregation == "avg":
        return round(sum(metric_values) / len(metric_values), 1) if metric_values else 0.0
    raise ValueError(
        f"Comparison analysis does not support metric aggregation '{metric_aggregation}'."
    )


def run_analysis(analysis_spec: str, runtime_state: object, plan: object) -> object:
    # Dispatch to the matching Python-side analysis routine.
    if analysis_spec != "CompareEntities":
        raise NotImplementedError(
            f"Python analysis step '{analysis_spec}' is not implemented."
        )

    # Read the latest SQL output from runtime state and group rows by compared entity.
    raw_rows = runtime_state.latest_result or []
    grouped = defaultdict(list)
    for row in raw_rows:
        grouped[int(row["entity_id"])].append(row)

    if len(grouped) < 2:
        raise ValueError("CompareEntities expects at least two entities in runtime state.")

    # Build one summary record per entity plus the full per-game comparison rows.
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

    # Decide who led the comparison and the gap to the nearest runner-up.
    sorted_stats = sorted(stats, key=lambda entity: entity.metric_value, reverse=True)
    leader_entity = sorted_stats[0]
    runner_up = sorted_stats[1]
    entity_a, entity_b = stats[0], stats[1]
    leader = leader_entity.entity_name
    differential = leader_entity.metric_value - runner_up.metric_value

    # Save the structured comparison artifact for later answer synthesis.
    result = ComparisonResult(
        leader=leader,
        metric_differential=round(differential, 1),
        entity_a=entity_a,
        entity_b=entity_b,
        entities=stats,
        per_game_rows=comparison_rows,
    )
    runtime_state.artifacts["comparison"] = result
    return result
