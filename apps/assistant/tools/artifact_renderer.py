# Purpose:
# Wrap table/chart artifact generation as a first-class assistant tool boundary.
#
# Uses:
# - grounded FinalAnswer objects
# - derived AnalysisTable objects
# - existing answer artifact builder
# - existing chart bridge and trusted AnalysisTools worker
#
# Produces:
# - validated renderer-friendly artifacts without changing current response shape

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnswerSynthesis.artifacts import build_artifacts
from runtime.AnswerSynthesis.response_models import FinalAnswer
from runtime.AnalysisTools.models import AnalysisTable

from apps.assistant.chart_artifacts import append_chart_artifacts


ArtifactKind = Literal["text", "table", "chart"]


class ArtifactRenderRequest(BaseModel):
    question: str = ""
    answer: Optional[FinalAnswer] = None
    tables: list[AnalysisTable] = Field(default_factory=list)
    artifacts: Optional[list[dict[str, Any]]] = None
    summary: Optional[str] = None
    interpretation: Optional[str] = None
    allowed_artifact_kinds: list[ArtifactKind] = Field(default_factory=lambda: ["text", "table", "chart"])


class ArtifactRenderResult(BaseModel):
    ok: bool
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    artifact_count: int = 0
    provenance: dict[str, Any] = Field(default_factory=dict)
    error: Optional[dict[str, Any]] = None


def render(request: ArtifactRenderRequest) -> ArtifactRenderResult:
    try:
        allowed = set(request.allowed_artifact_kinds)
        artifacts = _base_artifacts(request)
        if request.answer is not None and "chart" in allowed:
            artifacts = append_chart_artifacts(request.question, request.answer, artifacts)
        artifacts = [artifact for artifact in artifacts if artifact.get("kind") in allowed]
        return ArtifactRenderResult(
            ok=True,
            artifacts=artifacts,
            artifact_count=len(artifacts),
            provenance={
                "source": "runtime.AnswerSynthesis.artifacts",
                "chart_bridge": "apps.assistant.chart_artifacts.append_chart_artifacts",
            },
        )
    except Exception as exc:
        return ArtifactRenderResult(
            ok=False,
            error={"code": "artifact_render_failed", "message": str(exc)},
        )


def _base_artifacts(request: ArtifactRenderRequest) -> list[dict[str, Any]]:
    if request.artifacts is not None:
        return list(request.artifacts)
    if request.answer is not None:
        return build_artifacts(request.answer)
    if request.tables:
        return _artifacts_from_analysis_tables(request)
    raise ValueError("ArtifactRenderRequest requires answer, tables, or artifacts.")


def _artifacts_from_analysis_tables(request: ArtifactRenderRequest) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    interpretation = request.interpretation or request.question
    if interpretation:
        artifacts.append(
            {
                "kind": "text",
                "role": "interpretation",
                "text": f"Interpreted as: {interpretation}",
            }
        )
    summary = request.summary or (request.tables[0].title if request.tables else "")
    if summary:
        artifacts.append(
            {
                "kind": "text",
                "role": "summary",
                "text": summary,
            }
        )
    for table in request.tables:
        artifacts.append(_table_artifact_from_analysis_table(table))
    return artifacts


def _table_artifact_from_analysis_table(table: AnalysisTable) -> dict[str, Any]:
    return {
        "kind": "table",
        "title": table.title,
        "columns": [
            {
                "id": column.id,
                "label": column.label,
                "type": column.type,
            }
            for column in table.columns
        ],
        "rows": list(table.rows),
        "row_count": int(table.row_count if table.row_count is not None else len(table.rows)),
        "displayed_row_count": len(table.rows),
        "display_limit": len(table.rows),
        "metadata": {
            **table.metadata,
            "source_table_id": table.id,
        },
    }
