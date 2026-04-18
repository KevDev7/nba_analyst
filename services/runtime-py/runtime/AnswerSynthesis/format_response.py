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
        "games_played": "Games Played",
        "wins": "Wins",
        "losses": "Losses",
        "win_percentage": "Win Percentage",
    }.get(metric, metric.replace("_", " ").title())


def _metric_value(metric: str, value: float) -> str:
    if metric == "average_points":
        return f"{value:.1f}"
    if metric == "win_percentage":
        return f"{value:.3f}"
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
        for entity in [answer.comparison.entity_a, answer.comparison.entity_b]:
            context_suffix = f" ({entity.context_value})" if entity.context_value else ""
            lines.append(
                f"{entity.entity_name}{context_suffix}: "
                f"{_metric_value(answer.metric, entity.metric_value)} {_metric_header(answer.metric).lower()} "
                f"across {entity.games_count} games"
            )
        lines.append(
            f"Differential: {_metric_value(answer.metric, answer.comparison.metric_differential)} "
            f"{_metric_header(answer.metric).lower()}"
        )
        return "\n".join(lines)

    if answer.object_rows:
        show_context = bool(answer.context_label) and any(
            row.context_value for row in answer.object_rows
        )
        if show_context:
            lines.append(
                f"{answer.entity_label_singular} | {answer.context_label} | {_metric_header(answer.metric)}"
            )
            lines.append("--- | --- | ---")
            for row in answer.object_rows:
                lines.append(
                    f"{row.entity_name} | {(row.context_value or '')} | {_metric_value(answer.metric, row.metric_value)}"
                )
        else:
            lines.append(
                f"{answer.entity_label_singular} | {_metric_header(answer.metric)}"
            )
            lines.append("--- | ---")
            for row in answer.object_rows:
                lines.append(
                    f"{row.entity_name} | {_metric_value(answer.metric, row.metric_value)}"
                )
        return "\n".join(lines)

    if answer.time_series_rows:
        if any(row.series_name for row in answer.time_series_rows):
            lines.append(f"Month | {answer.entity_label_singular} | {_metric_header(answer.metric)}")
            lines.append("--- | --- | ---")
            for row in answer.time_series_rows:
                lines.append(
                    f"{row.time_bucket} | {(row.series_name or '')} | {_metric_value(answer.metric, row.metric_value)}"
                )
        else:
            lines.append(f"Month | {_metric_header(answer.metric)}")
            lines.append("--- | ---")
            for row in answer.time_series_rows:
                lines.append(
                    f"{row.time_bucket} | {_metric_value(answer.metric, row.metric_value)}"
                )
        return "\n".join(lines)

    show_context = bool(answer.context_label) and any(row.context_value for row in answer.rows)
    if show_context:
        lines.append(
            f"Rank | {answer.entity_label_singular} | {answer.context_label} | {_metric_header(answer.metric)}"
        )
        lines.append("--- | --- | --- | ---")
        for row in answer.rows:
            lines.append(
                f"{row.rank} | {row.entity_name} | {(row.context_value or '')} | {_metric_value(answer.metric, row.metric_value)}"
            )
    else:
        lines.append(
            f"Rank | {answer.entity_label_singular} | {_metric_header(answer.metric)}"
        )
        lines.append("--- | --- | ---")
        for row in answer.rows:
            lines.append(
                f"{row.rank} | {row.entity_name} | {_metric_value(answer.metric, row.metric_value)}"
            )
    return "\n".join(lines)
