# Purpose:
# Add chart artifacts after an answer has already been grounded when the
# typed answer/table shape has a supported chart plan.
#
# Uses:
# - typed FinalAnswer result shape
# - table artifacts built from actual runtime rows
# - local trusted Python analysis worker
#
# Produces:
# - chart artifacts appended to the structured response when safe

from __future__ import annotations

from typing import Any

from runtime.AnalysisTools.local_worker import run_analysis_request
from runtime.AnalysisTools.models import AnalysisRequest, AnalysisTable, AnalysisTableColumn
from runtime.AnswerSynthesis.artifacts import build_primary_table_artifact
from runtime.AnswerSynthesis.response_models import FinalAnswer
from apps.assistant.chart_planner import plan_chart_operation


JsonDict = dict[str, Any]

SUPPORTED_COLUMN_TYPES = {"text", "number", "integer", "date", "boolean"}


def append_chart_artifacts(
    _question: str,
    answer: FinalAnswer,
    artifacts: list[JsonDict],
) -> list[JsonDict]:
    table_artifact = build_primary_table_artifact(answer, row_limit=None)
    if table_artifact is None:
        return artifacts

    plan = plan_chart_operation(answer, table_artifact)
    if plan is None:
        return artifacts

    request = AnalysisRequest(
        tables=[_analysis_table_from_table_artifact(table_artifact)],
        operation=plan.operation,
    )
    result = run_analysis_request(request)
    if not result.ok:
        return artifacts

    chart_artifacts = [_model_dump(artifact) for artifact in result.artifacts]
    return _insert_before_first_table(artifacts, chart_artifacts)


append_requested_chart_artifacts = append_chart_artifacts


def _analysis_table_from_table_artifact(table_artifact: JsonDict) -> AnalysisTable:
    columns = [
        AnalysisTableColumn(
            id=str(column["id"]),
            label=str(column.get("label") or column["id"]),
            type=_column_type(str(column.get("type") or "text")),
        )
        for column in table_artifact.get("columns", [])
    ]
    rows = [
        {
            str(key): value
            for key, value in row.items()
        }
        for row in table_artifact.get("rows", [])
        if isinstance(row, dict)
    ]
    return AnalysisTable(
        id="primary_answer_table",
        title=str(table_artifact.get("title") or ""),
        columns=columns,
        rows=rows,
        row_count=int(table_artifact.get("row_count") or len(rows)),
        metadata={"source_artifact_kind": "table"},
    )


def _column_type(column_type: str):
    if column_type in SUPPORTED_COLUMN_TYPES:
        return column_type
    return "text"


def _insert_before_first_table(artifacts: list[JsonDict], chart_artifacts: list[JsonDict]) -> list[JsonDict]:
    for index, artifact in enumerate(artifacts):
        if artifact.get("kind") == "table":
            return [*artifacts[:index], *chart_artifacts, *artifacts[index:]]
    return [*artifacts, *chart_artifacts]


def _model_dump(model: Any) -> JsonDict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
