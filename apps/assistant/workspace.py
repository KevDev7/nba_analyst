from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.models import AnalysisFinding, AnalysisTable


class WorkspaceResourceProvenance(BaseModel):
    source_tool_call_id: Optional[str] = None
    source_tool_name: Optional[str] = None
    parent_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunWorkspace(BaseModel):
    """Per-run registry for approved resources produced by governed tools."""

    tables: dict[str, AnalysisTable] = Field(default_factory=dict)
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    findings: dict[str, AnalysisFinding] = Field(default_factory=dict)
    provenance: dict[str, WorkspaceResourceProvenance] = Field(default_factory=dict)

    def add_table(
        self,
        table: AnalysisTable,
        *,
        source_tool_call_id: str | None = None,
        source_tool_name: str | None = None,
        parent_ids: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> AnalysisTable:
        self.tables[table.id] = table
        self.provenance[table.id] = WorkspaceResourceProvenance(
            source_tool_call_id=source_tool_call_id,
            source_tool_name=source_tool_name,
            parent_ids=list(parent_ids),
            metadata=dict(metadata or {}),
        )
        return table

    def add_artifact(
        self,
        artifact: dict[str, Any],
        *,
        artifact_id: str | None = None,
        source_tool_call_id: str | None = None,
        source_tool_name: str | None = None,
        parent_ids: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> str:
        resource_id = artifact_id or str(artifact.get("id") or artifact.get("title") or f"artifact_{len(self.artifacts) + 1}")
        self.artifacts[resource_id] = dict(artifact)
        self.provenance[resource_id] = WorkspaceResourceProvenance(
            source_tool_call_id=source_tool_call_id,
            source_tool_name=source_tool_name,
            parent_ids=list(parent_ids),
            metadata=dict(metadata or {}),
        )
        return resource_id

    def add_finding(
        self,
        finding: AnalysisFinding,
        *,
        finding_id: str | None = None,
        source_tool_call_id: str | None = None,
        source_tool_name: str | None = None,
        parent_ids: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> str:
        resource_id = finding_id or f"finding_{len(self.findings) + 1}"
        self.findings[resource_id] = finding
        self.provenance[resource_id] = WorkspaceResourceProvenance(
            source_tool_call_id=source_tool_call_id,
            source_tool_name=source_tool_name,
            parent_ids=list(parent_ids),
            metadata=dict(metadata or {}),
        )
        return resource_id

    def resolve_table(self, table_id: str) -> AnalysisTable:
        try:
            return self.tables[table_id]
        except KeyError as exc:
            raise ValueError(f"Unknown or unapproved table id: {table_id}") from exc

    def resolve_tables(self, table_ids: Iterable[str]) -> list[AnalysisTable]:
        return [self.resolve_table(table_id) for table_id in table_ids]

    def resolve_artifact(self, artifact_id: str) -> dict[str, Any]:
        try:
            return self.artifacts[artifact_id]
        except KeyError as exc:
            raise ValueError(f"Unknown or unapproved artifact id: {artifact_id}") from exc

    def resolve_artifacts(self, artifact_ids: Iterable[str]) -> list[dict[str, Any]]:
        return [self.resolve_artifact(artifact_id) for artifact_id in artifact_ids]

    def resource_trace_links(self) -> list[dict[str, Any]]:
        return [
            {
                "resource_id": resource_id,
                **provenance.model_dump(),
            }
            for resource_id, provenance in sorted(self.provenance.items())
        ]
