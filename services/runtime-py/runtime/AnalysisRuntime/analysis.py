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

from .models import ComparisonResult, ComparisonRow, PlayerComparisonStats

def run_analysis(analysis_spec: str, runtime_state: object) -> object:
    if analysis_spec != "ComparePlayers":
        raise NotImplementedError(
            f"Python analysis step '{analysis_spec}' is not implemented."
        )

    raw_rows = runtime_state.latest_result or []
    grouped = defaultdict(list)
    for row in raw_rows:
        grouped[int(row["player_id"])].append(row)

    if len(grouped) != 2:
        raise ValueError("ComparePlayers expects exactly two players in runtime state.")

    stats = []
    comparison_rows = []
    for player_id, rows in sorted(grouped.items()):
        player_name = str(rows[0]["player_name"]) if rows else ""
        total_points = sum(int(row["points"]) for row in rows)
        games_count = len(rows)
        average_points = total_points / games_count if games_count else 0.0
        team = str(rows[0]["team"]) if rows else ""
        stats.append(
            PlayerComparisonStats(
                player_id=player_id,
                player_name=player_name,
                team=team,
                total_points=total_points,
                average_points=round(average_points, 1),
                games_count=games_count,
            )
        )
        comparison_rows.extend(
            ComparisonRow(
                player_id=int(row["player_id"]),
                player_name=str(row["player_name"]),
                team=str(row["team"]),
                game_date=str(row["game_date"]),
                points=int(row["points"]),
            )
            for row in rows
        )

    player_a, player_b = stats
    if player_a.total_points >= player_b.total_points:
      leader = player_a.player_name
      differential = player_a.total_points - player_b.total_points
    else:
      leader = player_b.player_name
      differential = player_b.total_points - player_a.total_points

    result = ComparisonResult(
        leader=leader,
        point_differential=differential,
        player_a=player_a,
        player_b=player_b,
        per_game_rows=comparison_rows,
    )
    runtime_state.artifacts["comparison"] = result
    return result
