# Purpose:
# Own the assistant request lifecycle above governed tools.
#
# Uses:
# - semantic_query.plan_execute fast path
# - governed multi-call tools for narrow derived-analysis routes
#
# Produces:
# - AssistantResult values for pipeline/web/CLI compatibility

from __future__ import annotations

import re
from typing import Any, Optional

from apps.assistant.models import AssistantResult
from apps.assistant.tools.python_analysis import PythonAnalysisToolRequest, run as run_python_analysis
from apps.assistant.tools.semantic_query import SemanticQueryRequest, plan_execute
from apps.assistant.trace import (
    AssistantTrace,
    ToolCallTrace,
    ToolProvenance,
    model_to_dict,
    new_id,
)

from runtime.AnalysisTools.models import AnalysisRequest, AnalysisTable, AnalysisTableColumn


TEAM_POINTS_DELTA_RE = re.compile(
    r"teams?.*increase.*average points(?: per game)?.*from\s+"
    r"(?P<left_season>\d{4}-\d{2})\s+regular season\s+to\s+"
    r"(?P<right_season>\d{4}-\d{2})\s+regular season",
    re.IGNORECASE,
)


def run_assistant(question: str, debug: bool = False) -> AssistantResult:
    delta_request = _team_points_delta_request(question)
    if delta_request is not None:
        return _run_team_points_delta(question, delta_request, debug=debug)
    return _run_fast_path(question, debug=debug)


def _run_fast_path(question: str, *, debug: bool) -> AssistantResult:
    result = plan_execute(
        SemanticQueryRequest(
            question=question,
            include_debug=debug,
            caller="orchestrator",
        )
    )
    if not result.ok and result.error is not None:
        raise RuntimeError(result.error.message)
    return result.to_assistant_result()


def _team_points_delta_request(question: str) -> Optional[dict[str, str]]:
    match = TEAM_POINTS_DELTA_RE.search(question)
    if match is None:
        return None
    return {
        "left_season": match.group("left_season"),
        "right_season": match.group("right_season"),
    }


def _run_team_points_delta(question: str, request: dict[str, str], *, debug: bool) -> AssistantResult:
    left_season = request["left_season"]
    right_season = request["right_season"]
    left_query = plan_execute(
        SemanticQueryRequest(
            semantic_draft=_team_average_points_draft(left_season),
            include_debug=debug,
            caller="orchestrator",
        )
    )
    right_query = plan_execute(
        SemanticQueryRequest(
            semantic_draft=_team_average_points_draft(right_season),
            include_debug=debug,
            caller="orchestrator",
        )
    )
    _raise_if_failed(left_query)
    _raise_if_failed(right_query)

    left_table = _analysis_table_from_semantic_result(left_query, "team_points_left", f"{left_season} team average points")
    right_table = _analysis_table_from_semantic_result(right_query, "team_points_right", f"{right_season} team average points")
    analysis_result = run_python_analysis(
        PythonAnalysisToolRequest(
            analysis_request=AnalysisRequest(
                tables=[left_table, right_table],
                operation={
                    "kind": "join_and_delta",
                    "left_table_id": left_table.id,
                    "right_table_id": right_table.id,
                    "join_keys": ["team"],
                    "left_metric": "avg_points",
                    "right_metric": "avg_points",
                    "left_output_column": f"avg_points_{left_season.replace('-', '_')}",
                    "right_output_column": f"avg_points_{right_season.replace('-', '_')}",
                    "output_metric": "increase",
                    "sort": {"by": "increase", "direction": "desc"},
                    "title": "Biggest increases in team average points per game",
                },
            )
        )
    )
    if not analysis_result.ok:
        message = analysis_result.error.get("message", "Python analysis failed.") if analysis_result.error else "Python analysis failed."
        raise RuntimeError(message)

    output_table = analysis_result.outputs["tables"][0]
    artifacts = _artifacts_from_analysis_table(question, output_table)
    answer = _team_points_delta_answer(left_season, right_season, output_table)
    debug_payload = None
    if debug:
        debug_payload = {
            "route": "team_average_points_delta",
            "left_query": model_to_dict(left_query.trace),
            "right_query": model_to_dict(right_query.trace),
            "analysis": model_to_dict(analysis_result),
            "trace": model_to_dict(_multi_call_trace(question, left_query, right_query, analysis_result, artifacts)),
        }
    return AssistantResult(answer=answer, artifacts=artifacts, debug=debug_payload)


def _raise_if_failed(result: Any) -> None:
    if not result.ok and result.error is not None:
        raise RuntimeError(result.error.message)


def _team_average_points_draft(season: str) -> dict[str, Any]:
    return {
        "task": "rank",
        "subject": "teams",
        "measure": "average points",
        "measures": ["average points"],
        "dimensions": [],
        "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
        "time_window": {"kind": "season", "value": season},
        "grain": None,
        "order": [{"by": "average points", "direction": "desc"}],
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
        team = row.get("entity_name") or row.get("group_1")
        value = row.get("metric_value")
        if team is None or value is None:
            continue
        rows.append({"team": team, "avg_points": value})
    return AnalysisTable(
        id=table_id,
        title=title,
        columns=[
            AnalysisTableColumn(id="team", label="Team", type="text"),
            AnalysisTableColumn(id="avg_points", label="Average Points", type="number"),
        ],
        rows=rows,
        row_count=len(rows),
        metadata={"source_query_id": result.query_id},
    )


def _artifacts_from_analysis_table(question: str, table: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "kind": "text",
            "role": "interpretation",
            "text": f"Interpreted as: {question}",
        },
        {
            "kind": "text",
            "role": "summary",
            "text": table.get("title") or "Derived analysis table",
        },
        {
            "kind": "table",
            "title": table.get("title") or "Derived analysis table",
            "columns": table.get("columns", []),
            "rows": table.get("rows", []),
            "row_count": table.get("row_count", len(table.get("rows", []))),
            "displayed_row_count": len(table.get("rows", [])),
            "display_limit": len(table.get("rows", [])),
        },
    ]


def _team_points_delta_answer(left_season: str, right_season: str, table: dict[str, Any]) -> str:
    rows = table.get("rows", [])
    if not rows:
        return f"I did not find matching team rows for {left_season} and {right_season} regular-season average points."
    top = rows[0]
    team = top.get("team", "The top team")
    increase = top.get("increase")
    return (
        f"The biggest increase in average points per game from the {left_season} regular season "
        f"to the {right_season} regular season was {team}"
        f" at {increase:.1f} points per game." if isinstance(increase, (int, float)) else
        f"The teams with the biggest increases in average points per game from {left_season} to {right_season} are shown below."
    )


def _multi_call_trace(question: str, left_query: Any, right_query: Any, analysis_result: Any, artifacts: list[dict[str, Any]]) -> AssistantTrace:
    return AssistantTrace(
        question=question,
        route="team_average_points_delta",
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
