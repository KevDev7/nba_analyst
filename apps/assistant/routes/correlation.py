# Purpose:
# Execute governed correlation plans through assistant tools.
#
# Uses:
# - semantic_query.plan_execute for each metric retrieval
# - python_analysis.run for controlled correlation
# - artifact_renderer.render for derived table artifacts
#
# Produces:
# - AssistantResult values for metric relationship analyses

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.models import AnalysisRequest, AnalysisTable, AnalysisTableColumn

from apps.assistant.models import AssistantResult
from apps.assistant.routes.period_delta import PeriodSpec
from apps.assistant.tools.artifact_renderer import ArtifactRenderRequest, render as render_artifacts
from apps.assistant.tools.python_analysis import PythonAnalysisToolRequest, run as run_python_analysis
from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute
from apps.assistant.trace import AssistantTrace, ToolCallTrace, ToolProvenance, model_to_dict, new_id


class CorrelationPlan(BaseModel):
    kind: Literal["correlation"] = "correlation"
    subject: Literal["teams", "players"]
    x_measure: str
    y_measure: str
    period: PeriodSpec
    join_key: str = "entity"
    method: Literal["pearson"] = "pearson"


def execute_correlation_plan(question: str, plan: CorrelationPlan, *, debug: bool = False) -> AssistantResult:
    x_query = plan_execute(
        SemanticQueryRequest(
            semantic_draft=_semantic_draft(plan, plan.x_measure),
            semantic_draft_state="prepared",
            question_context=question,
            include_debug=debug,
            caller="orchestrator",
        )
    )
    y_query = plan_execute(
        SemanticQueryRequest(
            semantic_draft=_semantic_draft(plan, plan.y_measure),
            semantic_draft_state="prepared",
            question_context=question,
            include_debug=debug,
            caller="orchestrator",
        )
    )
    _raise_if_failed(x_query)
    _raise_if_failed(y_query)

    x_table = _analysis_table_from_semantic_result(x_query, "correlation_x", _metric_column(plan.x_measure))
    y_table = _analysis_table_from_semantic_result(y_query, "correlation_y", _metric_column(plan.y_measure))
    analysis_result = run_python_analysis(
        PythonAnalysisToolRequest(
            analysis_request=AnalysisRequest(
                tables=[x_table, y_table],
                operation={
                    "kind": "correlation",
                    "left_table_id": x_table.id,
                    "right_table_id": y_table.id,
                    "join_keys": [plan.join_key],
                    "left_metric": "metric_value",
                    "right_metric": "metric_value",
                    "left_output_column": _metric_column(plan.x_measure),
                    "right_output_column": _metric_column(plan.y_measure),
                    "method": plan.method,
                    "title": _result_title(plan),
                    "metadata": {
                        "plan_kind": plan.kind,
                        "subject": plan.subject,
                        "x_measure": plan.x_measure,
                        "y_measure": plan.y_measure,
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
            allowed_artifact_kinds=["text", "table"],
        )
    )
    if not artifact_result.ok:
        message = artifact_result.error.get("message", "Artifact rendering failed.") if artifact_result.error else "Artifact rendering failed."
        raise RuntimeError(message)

    debug_payload = None
    if debug:
        debug_payload = {
            "route": "correlation",
            "correlation_plan": model_to_dict(plan),
            "x_query": model_to_dict(x_query.trace),
            "y_query": model_to_dict(y_query.trace),
            "analysis": model_to_dict(analysis_result),
            "trace": model_to_dict(_multi_call_trace(question, x_query, y_query, analysis_result, artifact_result, artifact_result.artifacts)),
        }
    return AssistantResult(answer=_answer(plan, output_table), artifacts=artifact_result.artifacts, debug=debug_payload)


def _semantic_draft(plan: CorrelationPlan, measure: str) -> dict[str, Any]:
    return {
        "task": "rank",
        "subject": plan.subject,
        "measure": measure,
        "measures": [measure],
        "dimensions": [],
        "filters": [{"field": "season type", "op": "=", "value": plan.period.season_type}],
        "time_window": {"kind": "season", "value": plan.period.season},
        "grain": None,
        "order": [{"by": measure, "direction": "desc"}],
        "limit": None,
        "sort": None,
        "rank_intent": "ranked",
        "entities": [],
        "operations": [],
        "assumptions": [],
    }


def _analysis_table_from_semantic_result(result: Any, table_id: str, title: str) -> AnalysisTable:
    if not result.tables:
        raise RuntimeError("Semantic query returned no table for correlation analysis.")
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


def _answer(plan: CorrelationPlan, table: AnalysisTable) -> str:
    if not table.rows:
        return f"I did not find enough matching {plan.subject} rows to compute the correlation."
    row = table.rows[0]
    correlation = row.get("correlation")
    paired_count = row.get("paired_row_count")
    period_label = f"{plan.period.season} {plan.period.season_type.replace('_', ' ')}"
    if isinstance(correlation, (int, float)):
        return (
            f"The {plan.method} correlation between {plan.x_measure} and {plan.y_measure} "
            f"for {plan.subject} in the {period_label} was {correlation:.2f} across {paired_count} matched rows."
        )
    return f"There were not enough matched {plan.subject} rows to compute the correlation."


def _multi_call_trace(question: str, x_query: Any, y_query: Any, analysis_result: Any, artifact_result: Any, artifacts: list[dict[str, Any]]) -> AssistantTrace:
    return AssistantTrace(
        question=question,
        route="correlation",
        status="ok",
        tool_calls=[
            *x_query.trace.tool_calls,
            *y_query.trace.tool_calls,
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
                    "allowed_artifact_kinds": ["text", "table"],
                },
                output={"artifact_count": artifact_result.artifact_count},
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


def _result_title(plan: CorrelationPlan) -> str:
    return f"Correlation between {plan.x_measure} and {plan.y_measure}"


def _metric_column(measure: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", measure.lower()).strip("_") or "metric"
