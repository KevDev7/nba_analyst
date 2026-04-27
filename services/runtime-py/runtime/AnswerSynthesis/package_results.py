# Purpose:
# Package runtime results into a clean payload for final answer synthesis.
#
# Uses:
# - RuntimeResult objects from the analysis runtime
#
# Produces:
# - a narrow synthesis payload that stays grounded in actual results
#
# Next:
# - synthesize.py

from __future__ import annotations

from typing import Dict, List

from runtime.AnalysisRuntime.models import RuntimeResult


def package_results(result: RuntimeResult) -> Dict[str, object]:
    payload = {
        "query_kind": result.query_kind,
        "result_shape": result.result_shape,
        "entity_label_singular": result.entity_label_singular,
        "entity_label_plural": result.entity_label_plural,
        "context_label": result.context_label,
        "metric": result.metric,
        "window_games": result.window_games,
        "time_grain": result.time_grain,
        "time_filter": result.time_filter,
        "season_label": result.season_label,
        "season_type": result.season_type,
        "limit": result.limit,
        "assumptions": result.assumptions,
        "rows": [row.model_dump() if hasattr(row, "model_dump") else row.dict() for row in result.rows],
        "aggregate_rows": [
            row.model_dump() if hasattr(row, "model_dump") else row.dict()
            for row in result.aggregate_rows
        ],
        "object_rows": [
            row.model_dump() if hasattr(row, "model_dump") else row.dict()
            for row in result.object_rows
        ],
        "time_series_rows": [
            row.model_dump() if hasattr(row, "model_dump") else row.dict()
            for row in result.time_series_rows
        ],
        "find_rows": result.find_rows,
    }
    if result.comparison is not None:
        payload["comparison"] = (
            result.comparison.model_dump()
            if hasattr(result.comparison, "model_dump")
            else result.comparison.dict()
        )
    return payload
