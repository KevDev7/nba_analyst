# Purpose:
# Add optional chart artifacts after an answer has already been grounded.
#
# Uses:
# - the user's original presentation request
# - typed FinalAnswer result shape
# - table artifacts built from actual runtime rows
# - local trusted Python analysis worker
#
# Produces:
# - chart artifacts appended to the structured response when safe

from __future__ import annotations

import re
from typing import Any

from runtime.AnalysisTools.local_worker import run_analysis_request
from runtime.AnalysisTools.models import AnalysisRequest, AnalysisTable, AnalysisTableColumn
from runtime.AnswerSynthesis.response_models import FinalAnswer


JsonDict = dict[str, Any]

CHART_INTENT_PATTERN = re.compile(
    r"\b(chart|charts|graph|graphs|plot|plots|visualize|visualise|visualization|visualisation)\b",
    re.IGNORECASE,
)
SUPPORTED_COLUMN_TYPES = {"text", "number", "integer", "date", "boolean"}


def append_requested_chart_artifacts(
    question: str,
    answer: FinalAnswer,
    artifacts: list[JsonDict],
) -> list[JsonDict]:
    if not _requests_chart(question):
        return artifacts
    if answer.result_shape != "time_series":
        return artifacts

    table_artifact = _primary_table_artifact(artifacts)
    if table_artifact is None:
        return artifacts

    operation = _chart_operation(answer, table_artifact)
    if operation is None:
        return artifacts

    request = AnalysisRequest(
        tables=[_analysis_table_from_table_artifact(table_artifact)],
        operation=operation,
    )
    result = run_analysis_request(request)
    if not result.ok:
        return artifacts

    chart_artifacts = [_model_dump(artifact) for artifact in result.artifacts]
    return _insert_before_first_table(artifacts, chart_artifacts)


def _requests_chart(question: str) -> bool:
    return bool(CHART_INTENT_PATTERN.search(question))


def _primary_table_artifact(artifacts: list[JsonDict]) -> JsonDict | None:
    for artifact in artifacts:
        if artifact.get("kind") == "table":
            return artifact
    return None


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


def _chart_operation(answer: FinalAnswer, table_artifact: JsonDict) -> dict[str, Any] | None:
    columns = list(table_artifact.get("columns", []))
    if not columns:
        return None

    x_column = _time_axis_column(columns)
    if x_column is None:
        return None
    y_column = _first_metric_column(columns, x_column["id"])
    if y_column is None:
        return None
    series_column = _series_column(columns, x_column["id"], y_column["id"])

    return {
        "kind": "line_chart",
        "input_table_id": "primary_answer_table",
        "x": x_column["id"],
        "y": y_column["id"],
        "series": series_column["id"] if series_column is not None else None,
        "title": _chart_title(answer, table_artifact),
        "renderer": "vega_lite",
        "metadata": {
            "source_result_shape": answer.result_shape,
            "source_time_grain": answer.time_grain,
        },
    }


def _time_axis_column(columns: list[JsonDict]) -> JsonDict | None:
    for column in columns:
        if column.get("id") == "time_bucket":
            return column
    for column in columns:
        if column.get("type") == "date":
            return column
    return None


def _first_metric_column(columns: list[JsonDict], x_column_id: object) -> JsonDict | None:
    for column in columns:
        if column.get("id") == x_column_id:
            continue
        if column.get("type") in {"number", "integer"}:
            return column
    return None


def _series_column(columns: list[JsonDict], x_column_id: object, y_column_id: object) -> JsonDict | None:
    for column in columns:
        if column.get("id") in {x_column_id, y_column_id}:
            continue
        if column.get("type") == "text":
            return column
    return None


def _chart_title(answer: FinalAnswer, table_artifact: JsonDict) -> str:
    if answer.summary:
        return answer.summary
    return str(table_artifact.get("title") or "Chart")


def _insert_before_first_table(artifacts: list[JsonDict], chart_artifacts: list[JsonDict]) -> list[JsonDict]:
    for index, artifact in enumerate(artifacts):
        if artifact.get("kind") == "table":
            return [*artifacts[:index], *chart_artifacts, *artifacts[index:]]
    return [*artifacts, *chart_artifacts]


def _model_dump(model: Any) -> JsonDict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
