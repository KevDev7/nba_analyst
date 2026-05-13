# Purpose:
# Ask the model for a structured orchestration plan and validate it.
#
# Uses:
# - existing Gemini transport
# - model_orchestration.plans schemas
#
# Produces:
# - validated ModelAnalysisPlan objects

from __future__ import annotations

from apps.assistant.model_orchestration.plans import ModelAnalysisPlan, planned_tool_names
from apps.assistant.semantic.interpreter import _load_interpreter_json, _strip_json_fences
from apps.assistant.semantic.llm_transport import LlmTransportError, call_gemini
from apps.assistant.trace import model_to_dict


class ModelPlanError(RuntimeError):
    """Raised when the model cannot produce a safe orchestration plan."""


def plan_question_with_model(question: str) -> ModelAnalysisPlan:
    try:
        raw_text = call_gemini(_planning_prompt(question))
    except LlmTransportError as exc:
        raise ModelPlanError(str(exc)) from exc
    try:
        payload = _load_interpreter_json(_strip_json_fences(raw_text))
        plan = ModelAnalysisPlan.model_validate(payload) if hasattr(ModelAnalysisPlan, "model_validate") else ModelAnalysisPlan.parse_obj(payload)
    except Exception as exc:
        raise ModelPlanError(f"Model returned an invalid orchestration plan: {exc}") from exc
    return plan


def dry_run_payload(question: str, plan: ModelAnalysisPlan) -> dict[str, object]:
    return {
        "question": question,
        "validated_plan": model_to_dict(plan),
        "planned_tool_sequence": planned_tool_names(plan),
        "auto_executed": False,
    }


def _planning_prompt(question: str) -> str:
    prompt = """
You plan NBA analytics work over governed tools.

Return JSON only. Never write SQL. Never write Python code. Never request raw_sql, raw_python, sql.execute, python_code, or duckdb.execute.

Allowed plan kinds:
1. simple_semantic_query
   {"plan":{"kind":"simple_semantic_query","question":"<original or clarified question>"},"tool_sequence":[{"tool_name":"semantic_query.plan_execute","purpose":"..."}]}

2. period_delta
   {"plan":{"kind":"period_delta","subject":"teams|players","measure":"<user-facing measure>","periods":[{"season":"2023-24","season_type":"regular_season"},{"season":"2024-25","season_type":"regular_season"}],"join_key":"entity","delta":"right_minus_left"},"tool_sequence":[{"tool_name":"semantic_query.plan_execute","purpose":"left period retrieval"},{"tool_name":"semantic_query.plan_execute","purpose":"right period retrieval"},{"tool_name":"python_analysis.run","purpose":"compute delta"},{"tool_name":"artifact_renderer.render","purpose":"render table/chart"}]}

3. correlation
   {"plan":{"kind":"correlation","subject":"teams|players","x_measure":"<user-facing metric>","y_measure":"<user-facing metric>","period":{"season":"2024-25","season_type":"regular_season"},"join_key":"entity","method":"pearson"},"tool_sequence":[{"tool_name":"semantic_query.plan_execute","purpose":"x metric retrieval"},{"tool_name":"semantic_query.plan_execute","purpose":"y metric retrieval"},{"tool_name":"python_analysis.run","purpose":"compute correlation"},{"tool_name":"artifact_renderer.render","purpose":"render table"}]}

4. artifact_request
   {"plan":{"kind":"artifact_request","question":"<question>","artifact_intent":"table|chart|table_and_chart"},"tool_sequence":[{"tool_name":"semantic_query.plan_execute","purpose":"retrieve grounded answer"},{"tool_name":"artifact_renderer.render","purpose":"render requested artifact"}]}

5. unsupported
   Use for unsupported surfaces: play-by-play, lineups, on-off, clutch, shot-location.
   {"plan":{"kind":"unsupported","reason":"<short reason>","unsupported_surface":"<surface>"},"tool_sequence":[]}

Rules:
- Use only these tool names: ontology_catalog.inspect, semantic_query.plan_execute, python_analysis.run, artifact_renderer.render.
- Do not include ontology keys, table names, SQL, Python, file paths, credentials, or database access.
- Prefer period_delta for explicit two-period increase/jump/improvement questions.
- Prefer correlation for explicit relationship/correlation questions between two supported metrics over one explicit season.
- Prefer simple_semantic_query for ordinary one-shot ranking, trend, aggregate, compare, find, or object questions.
""".strip()
    return f"{prompt}\n\nQuestion: {question}"
