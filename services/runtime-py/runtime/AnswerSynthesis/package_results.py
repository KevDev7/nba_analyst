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
from runtime.AnswerSynthesis.response_models import (
    SynthesisPayload,
    synthesis_payload_from_runtime_result,
)


def package_results(result: RuntimeResult) -> SynthesisPayload:
    return synthesis_payload_from_runtime_result(result)
