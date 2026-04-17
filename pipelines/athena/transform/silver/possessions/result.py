from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class PossessionArtifactRows:
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class ReferenceFailure:
    failure_type: str
    failed_period: int | None
    message: str


@dataclass(frozen=True)
class FallbackDecision:
    source_method: str
    opening_subcluster_applied: bool
    warning_details: str | None = None


@dataclass(frozen=True)
class PossessionBuildResult:
    status: Literal[
        "exact_written_candidate",
        "fallback_written_candidate",
        "unresolved",
        "skipped",
    ]
    rows: PossessionArtifactRows = field(default_factory=lambda: PossessionArtifactRows(rows=[]))
    reference_failure_type: str | None = None
    reference_failure_period: int | None = None
    possession_source_method: str | None = None
    opening_subcluster_applied: bool = False
    warning_details: str | None = None
