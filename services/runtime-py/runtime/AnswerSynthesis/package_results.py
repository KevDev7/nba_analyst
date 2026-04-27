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

from runtime.AnalysisRuntime.models import RuntimeResult
from runtime.AnswerSynthesis.response_models import SynthesisPayload


def package_results(result: RuntimeResult) -> SynthesisPayload:
    return SynthesisPayload(
        query_kind=result.query_kind,
        result_shape=result.result_shape,
        entity_label_singular=result.entity_label_singular,
        entity_label_plural=result.entity_label_plural,
        context_label=result.context_label,
        metric=result.metric,
        window_games=result.window_games,
        time_grain=result.time_grain,
        time_filter=result.time_filter,
        season_label=result.season_label,
        season_type=result.season_type,
        limit=result.limit,
        assumptions=result.assumptions,
        rows=result.rows,
        aggregate_rows=result.aggregate_rows,
        object_rows=result.object_rows,
        time_series_rows=result.time_series_rows,
        find_rows=result.find_rows,
        comparison=result.comparison,
    )
