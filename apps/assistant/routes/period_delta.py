# Purpose:
# Execute deterministic period-delta plans through governed assistant tools.
#
# Uses:
# - semantic_query.plan_execute for each period
# - python_analysis.run for right-minus-left deltas
# - artifact_renderer.render for derived tables
#
# Produces:
# - AssistantResult values for period-over-period metric increases

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.models import AnalysisRequest, AnalysisTable, AnalysisTableColumn

from apps.assistant.models import AssistantResult
from apps.assistant.tools.artifact_renderer import ArtifactRenderRequest, render as render_artifacts
from apps.assistant.tools.python_analysis import PythonAnalysisToolRequest, run as run_python_analysis
from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute
from apps.assistant.trace import AssistantTrace, ToolCallTrace, ToolProvenance, model_to_dict, new_id


PERIOD_DELTA_RE = re.compile(
    r"(?P<subject>teams|players)\b.*?"
    r"(?:biggest|largest|most)?\s*(?:increase|jump|improvement|improved).*?"
    r"(?:in|by)\s+(?P<measure>.+?)\s+from\s+(?:the\s+)?"
    r"(?P<left_season>\d{4}-\d{2})(?:\s+(?P<left_type>regular season|playoffs|postseason))?\s+to\s+(?:the\s+)?"
    r"(?P<right_season>\d{4}-\d{2})(?:\s+(?P<right_type>regular season|playoffs|postseason))?",
    re.IGNORECASE,
)


class PeriodSpec(BaseModel):
    season: str
    season_type: str = "regular_season"


class PeriodDeltaPlan(BaseModel):
    kind: Literal["period_delta"] = "period_delta"
    subject: Literal["teams", "players"]
    measure: str
    periods: list[PeriodSpec] = Field(min_length=2, max_length=2)
    join_key: str = "entity"
    delta: Literal["right_minus_left"] = "right_minus_left"


def maybe_build_period_delta_plan(question: str) -> Optional[PeriodDeltaPlan]:
    match = PERIOD_DELTA_RE.search(question)
    if match is None:
        return None
    return PeriodDeltaPlan(
        subject=match.group("subject").lower(),
        measure=_clean_measure(match.group("measure")),
        periods=[
            PeriodSpec(
                season=match.group("left_season"),
                season_type=_season_type(match.group("left_type")),
            ),
            PeriodSpec(
                season=match.group("right_season"),
                season_type=_season_type(match.group("right_type")),
            ),
        ],
    )


def execute_period_delta_plan(question: str, plan: PeriodDeltaPlan, *, debug: bool = False) -> AssistantResult:
    left_period, right_period = plan.periods
    left_query = plan_execute(
        SemanticQueryRequest(
            semantic_draft=_semantic_draft(plan, left_period),
            semantic_draft_state="prepared",
            question_context=question,
            include_debug=debug,
            caller="orchestrator",
        )
    )
    right_query = plan_execute(
        SemanticQueryRequest(
            semantic_draft=_semantic_draft(plan, right_period),
            semantic_draft_state="prepared",
            question_context=question,
            include_debug=debug,
            caller="orchestrator",
        )
    )
    _raise_if_failed(left_query)
    _raise_if_failed(right_query)

    left_table = _analysis_table_from_semantic_result(left_query, "period_delta_left", _period_title(plan, left_period))
    right_table = _analysis_table_from_semantic_result(right_query, "period_delta_right", _period_title(plan, right_period))
    analysis_result = run_python_analysis(
        PythonAnalysisToolRequest(
            analysis_request=AnalysisRequest(
                tables=[left_table, right_table],
                operation={
                    "kind": "join_and_delta",
                    "left_table_id": left_table.id,
                    "right_table_id": right_table.id,
                    "join_keys": [plan.join_key],
                    "left_metric": "metric_value",
                    "right_metric": "metric_value",
                    "left_output_column": _period_metric_column(plan, left_period),
                    "right_output_column": _period_metric_column(plan, right_period),
                    "output_metric": "delta",
                    "sort": {"by": "delta", "direction": "desc"},
                    "title": _result_title(plan),
                    "metadata": {
                        "plan_kind": plan.kind,
                        "subject": plan.subject,
                        "measure": plan.measure,
                    },
                },
            )
        )
    )
    if not analysis_result.ok:
        message = analysis_result.error.get("message", "Python analysis failed.") if analysis_result.error else "Python analysis failed."
        raise RuntimeError(message)

    output_table = _analysis_table_from_tool_output(analysis_result.outputs["tables"][0])
    artifact_result = render_artifacts(
        ArtifactRenderRequest(
            question=question,
            tables=[output_table],
            summary=_result_title(plan),
            interpretation=question,
            allowed_artifact_kinds=["text", "table", "chart"],
        )
    )
    if not artifact_result.ok:
        message = artifact_result.error.get("message", "Artifact rendering failed.") if artifact_result.error else "Artifact rendering failed."
        raise RuntimeError(message)

    answer = _answer(plan, output_table)
    debug_payload = None
    if debug:
        debug_payload = {
            "route": "period_delta",
            "period_delta_plan": model_to_dict(plan),
            "left_query": model_to_dict(left_query.trace),
            "right_query": model_to_dict(right_query.trace),
            "analysis": model_to_dict(analysis_result),
            "trace": model_to_dict(_multi_call_trace(question, left_query, right_query, analysis_result, artifact_result, artifact_result.artifacts)),
        }
    return AssistantResult(answer=answer, artifacts=artifact_result.artifacts, debug=debug_payload)


def _semantic_draft(plan: PeriodDeltaPlan, period: PeriodSpec) -> dict[str, Any]:
    return {
        "task": "rank",
        "subject": plan.subject,
        "measure": plan.measure,
        "measures": [plan.measure],
        "dimensions": [],
        "filters": [{"field": "season type", "op": "=", "value": period.season_type}],
        "time_window": {"kind": "season", "value": period.season},
        "grain": None,
        "order": [{"by": plan.measure, "direction": "desc"}],
        "limit": None,
        "sort": None,
        "rank_intent": "ranked",
        "entities": [],
        "operations": [],
        "assumptions": [],
    }


def _analysis_table_from_semantic_result(result: Any, table_id: str, title: str) -> AnalysisTable:
    if not result.tables:
        raise RuntimeError("Semantic query returned no table for derived analysis.")
    rows = []
    for row in result.tables[0].rows:
        entity = row.get("entity_name") or row.get("group_1")
        value = row.get("metric_value")
        if entity is None or value is None:
            continue
        rows.append({"entity": entity, "metric_value": value})
    return AnalysisTable(
        id=table_id,
        title=title,
        columns=[
            AnalysisTableColumn(id="entity", label="Entity", type="text"),
            AnalysisTableColumn(id="metric_value", label="Metric Value", type="number"),
        ],
        rows=rows,
        row_count=len(rows),
        metadata={"source_query_id": result.query_id},
    )


def _analysis_table_from_tool_output(payload: dict[str, Any]) -> AnalysisTable:
    return AnalysisTable(
        id=str(payload["id"]),
        title=str(payload.get("title") or ""),
        columns=[
            AnalysisTableColumn(
                id=str(column["id"]),
                label=str(column.get("label") or column["id"]),
                type=column.get("type") or "text",
            )
            for column in payload.get("columns", [])
        ],
        rows=[row for row in payload.get("rows", []) if isinstance(row, dict)],
        row_count=int(payload.get("row_count") or len(payload.get("rows", []))),
        metadata=payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {},
    )


def _answer(plan: PeriodDeltaPlan, table: AnalysisTable) -> str:
    if not table.rows:
        left_period, right_period = plan.periods
        return f"I did not find matching {plan.subject} rows for {left_period.season} and {right_period.season}."
    left_period, right_period = plan.periods
    top = table.rows[0]
    entity = top.get(plan.join_key, top.get("entity", "The top result"))
    delta = top.get("delta")
    label = plan.measure
    subject_label = "player" if plan.subject == "players" else "team"
    if isinstance(delta, (int, float)):
        return (
            f"The biggest increase in {label} from the {left_period.season} {left_period.season_type.replace('_', ' ')} "
            f"to the {right_period.season} {right_period.season_type.replace('_', ' ')} was {entity}, "
            f"up {delta:.1f}."
        )
    return f"The {subject_label}s with the biggest increases in {label} are shown below."


def _multi_call_trace(question: str, left_query: Any, right_query: Any, analysis_result: Any, artifact_result: Any, artifacts: list[dict[str, Any]]) -> AssistantTrace:
    return AssistantTrace(
        question=question,
        route="period_delta",
        status="ok",
        tool_calls=[
            *left_query.trace.tool_calls,
            *right_query.trace.tool_calls,
            ToolCallTrace(
                tool_call_id=new_id("tc"),
                tool_name="python_analysis.run",
                status="ok",
                input={
                    "operation_kind": analysis_result.provenance.get("operation_kind"),
                    "parent_table_ids": analysis_result.provenance.get("parent_table_ids", []),
                },
                output={
                    "analysis_id": analysis_result.analysis_id,
                    "table_count": len(analysis_result.outputs.get("tables", [])),
                    "finding_count": len(analysis_result.outputs.get("findings", [])),
                },
                provenance=ToolProvenance(
                    operation_kind=analysis_result.provenance.get("operation_kind"),
                    parent_table_ids=analysis_result.provenance.get("parent_table_ids", []),
                    derived_from_table_ids=analysis_result.provenance.get("derived_from_table_ids", []),
                    output_table_ids=analysis_result.provenance.get("output_table_ids", []),
                ),
            ),
            ToolCallTrace(
                tool_call_id=new_id("tc"),
                tool_name="artifact_renderer.render",
                status="ok",
                input={
                    "source_table_ids": analysis_result.provenance.get("output_table_ids", []),
                    "allowed_artifact_kinds": ["text", "table", "chart"],
                },
                output={
                    "artifact_count": artifact_result.artifact_count,
                },
                provenance=ToolProvenance(),
            ),
        ],
        artifacts=[
            {
                "artifact_id": f"art_{index}",
                "kind": str(artifact.get("kind", "")),
            }
            for index, artifact in enumerate(artifacts)
        ],
    )


def _raise_if_failed(result: Any) -> None:
    if not result.ok and result.error is not None:
        raise RuntimeError(result.error.message)


def _result_title(plan: PeriodDeltaPlan) -> str:
    return f"Biggest increases in {plan.subject} {plan.measure}"


def _period_title(plan: PeriodDeltaPlan, period: PeriodSpec) -> str:
    return f"{period.season} {period.season_type.replace('_', ' ')} {plan.subject} {plan.measure}"


def _period_metric_column(plan: PeriodDeltaPlan, period: PeriodSpec) -> str:
    season_key = period.season.replace("-", "_")
    measure_key = re.sub(r"[^a-z0-9]+", "_", plan.measure.lower()).strip("_")
    return f"{measure_key}_{season_key}"


def _clean_measure(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" ?.,")
    return re.sub(r"\s+per\s+game$", "", cleaned, flags=re.IGNORECASE)


def _season_type(value: Optional[str]) -> str:
    normalized = (value or "regular season").strip().lower()
    if normalized in {"playoffs", "postseason"}:
        return "playoffs"
    return "regular_season"
