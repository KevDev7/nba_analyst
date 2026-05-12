# Purpose:
# Wrap table/chart artifact generation as a first-class assistant tool boundary.
#
# Uses:
# - grounded FinalAnswer objects
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

from apps.assistant.chart_artifacts import append_chart_artifacts


ArtifactKind = Literal["text", "table", "chart"]


class ArtifactRenderRequest(BaseModel):
    question: str = ""
    answer: FinalAnswer
    artifacts: Optional[list[dict[str, Any]]] = None
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
        artifacts = list(request.artifacts) if request.artifacts is not None else build_artifacts(request.answer)
        if "chart" in allowed:
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
