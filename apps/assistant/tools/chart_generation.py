# Purpose:
# Create validated Vega-Lite chart artifacts from approved tool-output tables.
#
# Uses:
# - AnalysisTable contracts produced by semantic_query/python_analysis
# - deterministic chart operations first
# - optional gated model/sandbox spec generation
#
# Produces:
# - chart artifacts with renderer="vega_lite" and parent-table provenance

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.local_worker import run_analysis_request
from runtime.AnalysisTools.models import (
    AnalysisRequest,
    AnalysisTable,
    AnalysisTableColumn,
    ChartOperation,
    PythonCodeOperation,
    PythonCodeOutputTableSchema,
)

from apps.assistant.semantic.interpreter import _load_interpreter_json, _strip_json_fences
from apps.assistant.semantic.llm_transport import call_gemini
from apps.assistant.trace import new_id


MODEL_CHART_GENERATION_ENV = "NBA_ENABLE_MODEL_CHART_GENERATION"
SANDBOX_CHART_GENERATION_ENV = "NBA_ENABLE_SANDBOX_CHART_GENERATION"
PYTHON_CODE_SANDBOX_ENV = "NBA_ENABLE_PYTHON_CODE_SANDBOX"
DEFAULT_RENDERER = "vega_lite"
FORBIDDEN_CHART_TEXT_RE = re.compile(
    r"\b(select|insert|update|delete|drop|alter|create|copy|attach|pragma|load|install|duckdb|sqlite|sqlalchemy|read_sql|execute|cursor|connect)\b",
    re.IGNORECASE,
)


ChartGenerationMode = Literal["deterministic", "model", "sandbox"]


class ChartGenerationRequest(BaseModel):
    question: str = ""
    tables: list[AnalysisTable] = Field(default_factory=list)
    table_ids: list[str] = Field(default_factory=list)
    chart_intent: str = ""
    allowed_renderers: list[str] = Field(default_factory=lambda: [DEFAULT_RENDERER])
    max_rows: int = Field(default=100, ge=1, le=5000)
    generation_mode: ChartGenerationMode = "deterministic"
    candidate_spec: Optional[dict[str, Any]] = None
    sandbox_code: Optional[str] = Field(default=None, max_length=20000)
    title: Optional[str] = None

    @model_validator(mode="after")
    def validate_request(self) -> "ChartGenerationRequest":
        if DEFAULT_RENDERER not in self.allowed_renderers:
            raise ValueError("chart_generation.run currently requires vega_lite in allowed_renderers.")
        if not self.tables:
            raise ValueError("chart_generation.run requires at least one approved input table.")
        if self.table_ids:
            known = {table.id for table in self.tables}
            missing = sorted(set(self.table_ids) - known)
            if missing:
                raise ValueError(f"Unknown or unapproved table ids: {', '.join(missing)}")
        if self.sandbox_code and FORBIDDEN_CHART_TEXT_RE.search(self.sandbox_code):
            raise ValueError("Sandbox chart code references forbidden SQL/database capability.")
        return self


class ChartGenerationResult(BaseModel):
    ok: bool
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    artifact_count: int = 0
    provenance: dict[str, Any] = Field(default_factory=dict)
    error: Optional[dict[str, Any]] = None


def run(
    request: ChartGenerationRequest,
    *,
    call_model: Callable[[str], str] = call_gemini,
) -> ChartGenerationResult:
    started = time.perf_counter()
    parent_table_ids = request.table_ids or [table.id for table in request.tables]
    mode = request.generation_mode
    try:
        if mode == "model" and not _enabled(MODEL_CHART_GENERATION_ENV):
            return _deterministic_result(request, started, fallback_reason="model_chart_generation_disabled")
        if mode == "sandbox" and not (_enabled(SANDBOX_CHART_GENERATION_ENV) and _enabled(PYTHON_CODE_SANDBOX_ENV)):
            return _deterministic_result(request, started, fallback_reason="sandbox_chart_generation_disabled")

        if mode == "model":
            artifact = _model_chart_artifact(request, call_model=call_model)
        elif mode == "sandbox":
            artifact = _sandbox_chart_artifact(request)
        else:
            artifact = _deterministic_chart_artifact(request)
        return ChartGenerationResult(
            ok=True,
            artifacts=[artifact],
            artifact_count=1,
            provenance=_provenance(
                request,
                started,
                generation_mode=mode,
                parent_table_ids=parent_table_ids,
                validation_status="validated",
            ),
        )
    except Exception as exc:
        if mode in {"model", "sandbox"}:
            return _deterministic_result(request, started, fallback_reason=str(exc))
        return ChartGenerationResult(
            ok=False,
            provenance=_provenance(
                request,
                started,
                generation_mode=mode,
                parent_table_ids=parent_table_ids,
                validation_status="failed",
            ),
            error={"code": "chart_generation_failed", "message": str(exc)},
        )


def _deterministic_result(
    request: ChartGenerationRequest,
    started: float,
    *,
    fallback_reason: str,
) -> ChartGenerationResult:
    try:
        artifact = _deterministic_chart_artifact(request)
        return ChartGenerationResult(
            ok=True,
            artifacts=[artifact],
            artifact_count=1,
            provenance=_provenance(
                request,
                started,
                generation_mode="deterministic",
                parent_table_ids=request.table_ids or [table.id for table in request.tables],
                validation_status="fallback_validated",
                fallback_reason=fallback_reason,
            ),
        )
    except Exception as exc:
        return ChartGenerationResult(
            ok=False,
            provenance=_provenance(
                request,
                started,
                generation_mode="deterministic",
                parent_table_ids=request.table_ids or [table.id for table in request.tables],
                validation_status="fallback_failed",
                fallback_reason=fallback_reason,
            ),
            error={"code": "chart_generation_failed", "message": str(exc)},
        )


def _deterministic_chart_artifact(request: ChartGenerationRequest) -> dict[str, Any]:
    table = _selected_table(request)
    table = _limited_table(table, request.max_rows)
    operation = _plan_operation(table, request)
    result = run_analysis_request(AnalysisRequest(tables=[table], operation=operation))
    if not result.ok or not result.artifacts:
        message = result.error.message if result.error is not None else "Chart operation did not return an artifact."
        raise ValueError(message)
    artifact = result.artifacts[0].model_dump()
    return _validated_artifact(artifact, table)


def _model_chart_artifact(
    request: ChartGenerationRequest,
    *,
    call_model: Callable[[str], str],
) -> dict[str, Any]:
    table = _limited_table(_selected_table(request), request.max_rows)
    spec = request.candidate_spec
    if spec is None:
        raw_text = call_model(_model_prompt(request, table))
        spec = _load_interpreter_json(_strip_json_fences(raw_text))
    artifact = {
        "kind": "chart",
        "renderer": DEFAULT_RENDERER,
        "title": request.title or table.title or request.chart_intent or "Chart",
        "spec": spec,
        "data": {"row_count": len(table.rows)},
        "metadata": {
            "source_table_id": table.id,
            "generation_mode": "model",
            "chart_intent": request.chart_intent,
        },
    }
    return _validated_artifact(artifact, table)


def _sandbox_chart_artifact(request: ChartGenerationRequest) -> dict[str, Any]:
    if request.candidate_spec is not None:
        return _validated_artifact(
            {
                "kind": "chart",
                "renderer": DEFAULT_RENDERER,
                "title": request.title or request.chart_intent or "Chart",
                "spec": request.candidate_spec,
                "data": {"row_count": len(_selected_table(request).rows)},
                "metadata": {"source_table_id": _selected_table(request).id, "generation_mode": "sandbox"},
            },
            _selected_table(request),
        )
    if not request.sandbox_code:
        raise ValueError("sandbox chart generation requires sandbox_code or candidate_spec.")

    table = _limited_table(_selected_table(request), request.max_rows)
    operation = PythonCodeOperation(
        kind="python_code",
        code=request.sandbox_code,
        input_table_ids=[table.id],
        output_tables=[
            PythonCodeOutputTableSchema(
                id="chart_spec_output",
                columns=[
                    AnalysisTableColumn(id="title", label="Title", type="text"),
                    AnalysisTableColumn(id="spec_json", label="Spec JSON", type="text"),
                ],
            )
        ],
        metadata={"purpose": "chart_generation_spec_builder"},
    )
    result = run_analysis_request(AnalysisRequest(runtime="local_sandbox", tables=[table], operation=operation))
    if not result.ok or not result.tables or not result.tables[0].rows:
        message = result.error.message if result.error is not None else "Sandbox chart generation returned no spec."
        raise ValueError(message)
    row = result.tables[0].rows[0]
    spec = json.loads(str(row.get("spec_json") or "{}"))
    artifact = {
        "kind": "chart",
        "renderer": DEFAULT_RENDERER,
        "title": str(row.get("title") or request.title or request.chart_intent or "Chart"),
        "spec": spec,
        "data": {"row_count": len(table.rows)},
        "metadata": {
            "source_table_id": table.id,
            "generation_mode": "sandbox",
            "sandbox_backend": result.metadata.get("backend_id"),
        },
    }
    return _validated_artifact(artifact, table)


def _selected_table(request: ChartGenerationRequest) -> AnalysisTable:
    if request.table_ids:
        wanted = request.table_ids[0]
        for table in request.tables:
            if table.id == wanted:
                return table
    return request.tables[0]


def _limited_table(table: AnalysisTable, max_rows: int) -> AnalysisTable:
    if len(table.rows) <= max_rows:
        return table
    return table.model_copy(
        update={
            "rows": table.rows[:max_rows],
            "metadata": {**table.metadata, "truncated_for_chart_generation": True, "max_rows": max_rows},
        }
    )


def _plan_operation(table: AnalysisTable, request: ChartGenerationRequest) -> ChartOperation:
    numeric = [column for column in table.columns if column.type in {"number", "integer"}]
    temporal = [column for column in table.columns if column.type == "date"]
    categorical = [column for column in table.columns if column.type in {"text", "boolean"}]
    intent = request.chart_intent.lower()
    title = request.title or table.title or request.chart_intent or None

    if ("scatter" in intent or "relationship" in intent or "correlation" in intent) and len(numeric) >= 2:
        return ChartOperation(kind="point_chart", input_table_id=table.id, x=numeric[0].id, y=numeric[1].id, title=title)
    if temporal and numeric:
        series = categorical[0].id if categorical else None
        return ChartOperation(kind="line_chart", input_table_id=table.id, x=temporal[0].id, y=numeric[0].id, series=series, title=title)
    if categorical and numeric:
        return ChartOperation(
            kind="bar_chart",
            input_table_id=table.id,
            x=numeric[0].id,
            y=categorical[0].id,
            orientation="horizontal",
            title=title,
        )
    if len(numeric) >= 2:
        return ChartOperation(kind="point_chart", input_table_id=table.id, x=numeric[0].id, y=numeric[1].id, title=title)
    raise ValueError("No chartable column pairing found.")


def _validated_artifact(artifact: dict[str, Any], table: AnalysisTable) -> dict[str, Any]:
    if artifact.get("kind") != "chart":
        raise ValueError("Chart generation must produce chart artifacts.")
    if artifact.get("renderer") != DEFAULT_RENDERER:
        raise ValueError("Only vega_lite chart artifacts are supported.")
    spec = artifact.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("Chart artifact spec must be a JSON object.")
    _reject_external_refs(spec)
    _reject_forbidden_text(spec)
    _validate_field_refs(spec, {column.id for column in table.columns})
    metadata = dict(artifact.get("metadata") or {})
    metadata.setdefault("source_table_id", table.id)
    metadata["validated_by"] = "chart_generation.run"
    return {**artifact, "metadata": metadata}


def _reject_external_refs(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) == "$schema":
                continue
            if str(key).lower() in {"url", "href"}:
                raise ValueError("Vega-Lite specs may not include external URLs.")
            _reject_external_refs(child)
    elif isinstance(value, list):
        for child in value:
            _reject_external_refs(child)
    elif isinstance(value, str) and re.search(r"https?://|file://", value, re.IGNORECASE):
        raise ValueError("Vega-Lite specs may not include external URLs.")


def _reject_forbidden_text(value: Any) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _reject_forbidden_text(child)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_text(child)
    elif isinstance(value, str) and FORBIDDEN_CHART_TEXT_RE.search(value):
        raise ValueError("Chart spec references forbidden SQL/database capability.")


def _validate_field_refs(value: Any, allowed_columns: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "field" and child not in allowed_columns:
                raise ValueError(f"Vega-Lite spec references unknown column: {child}")
            _validate_field_refs(child, allowed_columns)
    elif isinstance(value, list):
        for child in value:
            _validate_field_refs(child, allowed_columns)


def _model_prompt(request: ChartGenerationRequest, table: AnalysisTable) -> str:
    payload = {
        "question": request.question,
        "chart_intent": request.chart_intent,
        "table": {
            "id": table.id,
            "columns": [column.model_dump() for column in table.columns],
            "rows": table.rows[: request.max_rows],
        },
    }
    return f"""
Create a Vega-Lite JSON spec for the supplied approved table.

Return JSON for the Vega-Lite spec only. Do not include markdown.

Rules:
- Use only fields listed in table.columns.
- Do not include external URLs.
- Do not mention SQL, DuckDB, database internals, files, or network access.
- Do not invent columns or data.

Payload:
{json.dumps(payload, sort_keys=True)}
""".strip()


def _provenance(
    request: ChartGenerationRequest,
    started: float,
    *,
    generation_mode: str,
    parent_table_ids: list[str],
    validation_status: str,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    provenance = {
        "tool_name": "chart_generation.run",
        "tool_call_id": new_id("tc"),
        "parent_table_ids": parent_table_ids,
        "renderer": DEFAULT_RENDERER,
        "generation_mode": generation_mode,
        "validation_status": validation_status,
        "execution_ms": int((time.perf_counter() - started) * 1000),
        "model_enabled": _enabled(MODEL_CHART_GENERATION_ENV),
        "sandbox_enabled": _enabled(SANDBOX_CHART_GENERATION_ENV),
    }
    if fallback_reason:
        provenance["fallback_reason"] = fallback_reason
    return provenance


def _enabled(env_name: str) -> bool:
    return os.getenv(env_name, "").strip().lower() in {"1", "true", "yes", "on"}
