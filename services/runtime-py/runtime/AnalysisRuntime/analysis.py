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

from .models import ComparisonBreakdownRow, ComparisonEntityStats, ComparisonResult, ComparisonRow

def _aggregate_metric(metric_aggregation: str, rows: list[dict[str, object]]) -> float:
    # Re-aggregate the per-row metric values the SQL step returned.
    metric_values = [float(row["metric_value"]) for row in rows]
    if metric_aggregation == "sum":
        return float(sum(metric_values))
    if metric_aggregation == "avg":
        return round(sum(metric_values) / len(metric_values), 1) if metric_values else 0.0
    if metric_aggregation == "identity":
        return float(metric_values[0]) if metric_values else 0.0
    raise ValueError(
        f"Comparison analysis does not support metric aggregation '{metric_aggregation}'."
    )


def _games_count(rows: list[dict[str, object]]) -> int:
    # Recent comparisons return one row per game. Season comparisons return
    # one season row and can carry games_played as metadata.
    games_played_values = [
        float(row["games_played"])
        for row in rows
        if row.get("games_played") is not None
    ]
    if games_played_values:
        return int(round(sum(games_played_values)))
    return len(rows)


def _comparison_group_values(row: dict[str, object], plan: object) -> dict[str, object]:
    return {
        grouping.column_key: row.get(grouping.column_key)
        for grouping in plan.grouping_columns
        if grouping.column_key in row
    }


def _comparison_breakdown_key(row: dict[str, object], plan: object) -> tuple[object, ...]:
    group_values = _comparison_group_values(row, plan)
    return (
        int(row["entity_id"]),
        row.get("time_bucket"),
        *[
            group_values.get(grouping.column_key)
            for grouping in plan.grouping_columns
        ],
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
        games_count = _games_count(rows)
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
                time_bucket=(str(row["time_bucket"]) if row.get("time_bucket") is not None else None),
                group_values=_comparison_group_values(row, plan),
                game_date=(str(row["game_date"]) if row.get("game_date") is not None else None),
                metric_value=float(row["metric_value"]),
            )
            for row in rows
        )

    breakdown_rows = []
    if plan.grouping_columns or plan.time_grain:
        grouped_breakdowns = defaultdict(list)
        for row in raw_rows:
            grouped_breakdowns[_comparison_breakdown_key(row, plan)].append(row)
        for _breakdown_key, rows in sorted(
            grouped_breakdowns.items(),
            key=lambda item: (
                str(item[1][0].get("time_bucket") or ""),
                int(item[1][0]["entity_id"]),
                [
                    str(item[1][0].get(grouping.column_key) or "")
                    for grouping in plan.grouping_columns
                ],
            ),
        ):
            first_row = rows[0]
            breakdown_rows.append(
                ComparisonBreakdownRow(
                    entity_id=int(first_row["entity_id"]),
                    entity_name=str(first_row["entity_name"]),
                    context_value=(
                        str(first_row["context_value"])
                        if first_row.get("context_value") is not None
                        else None
                    ),
                    time_bucket=(
                        str(first_row["time_bucket"])
                        if first_row.get("time_bucket") is not None
                        else None
                    ),
                    group_values=_comparison_group_values(first_row, plan),
                    metric_value=_aggregate_metric(str(plan.metric_aggregation), rows),
                    games_count=_games_count(rows),
                )
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
        breakdown_rows=breakdown_rows,
    )
    runtime_state.artifacts["comparison"] = result
    return result
