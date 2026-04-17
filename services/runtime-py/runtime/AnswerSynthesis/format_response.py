# Purpose:
# Format the final answer payload into a CLI-friendly response.
#
# Uses:
# - FinalAnswer models from response_models.py
#
# Produces:
# - a human-readable answer string
#
# Next:
# - apps/cli/main.py

from __future__ import annotations

from .response_models import FinalAnswer


def _metric_header(metric: str) -> str:
    return {
        "total_points": "Total Points",
        "average_points": "Average Points",
    }.get(metric, metric.replace("_", " ").title())


def _metric_value(metric: str, value: float) -> str:
    if metric == "average_points":
        return f"{value:.1f}"
    return str(int(round(value)))


def format_response(answer: FinalAnswer) -> str:
    lines = [answer.summary, ""]
    if answer.assumptions:
        lines.append("Assumptions:")
        lines.extend(f"- {assumption}" for assumption in answer.assumptions)
        lines.append("")

    if answer.comparison is not None:
        lines.append("Comparison")
        lines.append("---")
        lines.append(
            f"{answer.comparison.player_a.player_name}: "
            f"{answer.comparison.player_a.total_points} total points, "
            f"{answer.comparison.player_a.average_points:.1f} per game"
        )
        lines.append(
            f"{answer.comparison.player_b.player_name}: "
            f"{answer.comparison.player_b.total_points} total points, "
            f"{answer.comparison.player_b.average_points:.1f} per game"
        )
        lines.append(
            f"Differential: {answer.comparison.point_differential} points"
        )
        return "\n".join(lines)

    if answer.object_rows:
        lines.append(f"Player | Team | {_metric_header(answer.metric)}")
        lines.append("--- | --- | ---")
        for row in answer.object_rows:
            lines.append(
                f"{row.player_name} | {row.team} | {_metric_value(answer.metric, row.metric_value)}"
            )
        return "\n".join(lines)

    lines.append(f"Rank | Player | Team | {_metric_header(answer.metric)}")
    lines.append("--- | --- | --- | ---")
    for row in answer.rows:
        lines.append(
            f"{row.rank} | {row.player_name} | {row.team} | {_metric_value(answer.metric, row.metric_value)}"
        )
    return "\n".join(lines)
