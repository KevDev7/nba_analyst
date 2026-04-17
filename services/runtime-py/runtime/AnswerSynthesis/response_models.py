# Purpose:
# Define typed final-answer payloads for the live slices.
#
# Uses:
# - packaged runtime results from package_results.py
#
# Produces:
# - a grounded final answer model
#
# Next:
# - format_response.py

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from runtime.AnalysisRuntime.models import ComparisonResult, ObjectRow, RankingRow


class FinalAnswer(BaseModel):
    summary: str
    query_kind: str
    result_shape: str
    metric: str
    window_games: int
    limit: int
    assumptions: List[str] = Field(default_factory=list)
    rows: List[RankingRow]
    object_rows: List[ObjectRow] = Field(default_factory=list)
    comparison: Optional[ComparisonResult] = None
