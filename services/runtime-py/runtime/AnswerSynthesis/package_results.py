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
        "metric": result.metric,
        "window_games": result.window_games,
        "limit": result.limit,
        "assumptions": result.assumptions,
        "rows": [row.model_dump() if hasattr(row, "model_dump") else row.dict() for row in result.rows],
        "object_rows": [
            row.model_dump() if hasattr(row, "model_dump") else row.dict()
            for row in result.object_rows
        ],
    }
    if result.comparison is not None:
        payload["comparison"] = (
            result.comparison.model_dump()
            if hasattr(result.comparison, "model_dump")
            else result.comparison.dict()
        )
    return payload
