# Purpose:
# Run one user question through the shared NBA analyst pipeline.
#
# Uses:
# - semantic interpretation from apps/assistant/semantic
# - Haskell ontology planning
# - Python runtime execution
# - answer synthesis and formatting
#
# Produces:
# - structured assistant results that CLI and web adapters can render
#
# Next:
# - apps/cli/main.py or apps/web/server.py

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisRuntime.models import ExecutionPlan
from runtime.AnalysisRuntime.runner import execute_plan
from runtime.AnswerSynthesis.format_response import format_response
from runtime.AnswerSynthesis.artifacts import build_artifacts
from runtime.AnswerSynthesis.package_results import package_results
from runtime.AnswerSynthesis.synthesize import synthesize_answer
from apps.assistant.chart_artifacts import append_requested_chart_artifacts
from apps.assistant.predicate_observability import build_predicate_trace
from apps.assistant.value_resolution_observability import build_value_resolution_trace
from apps.assistant.semantic.entity_resolver import EntityResolutionError, enrich_semantic_draft_with_resolved_entities
from apps.assistant.semantic.assumptions import apply_semantic_assumptions
from apps.assistant.semantic.interpreter import SemanticInterpreterError, interpret_question_to_semantic_draft
from scripts.load_gold_snapshot import load_database


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"


@dataclass(frozen=True)
class AssistantResult:
    # The product-facing result of one assistant run.
    # Plain English: the answer is what the user sees; debug is optional context
    # for developers who want to inspect each pipeline handoff.
    answer: str
    artifacts: list[dict[str, Any]] | None = None
    debug: dict[str, Any] | None = None


def call_haskell_planner_for_semantic_draft(draft_payload: dict[str, Any]) -> dict[str, Any]:
    # Send the LLM's loose semantic draft to Haskell.
    # Haskell is responsible for turning that draft into a grounded query,
    # validating it against the ontology, and compiling an execution plan.
    command = [
        "cabal",
        "run",
        "-v0",
        "ontology-hs",
        "--",
        "plan-semantic-draft-json",
        "--ontology",
        str(ONTOLOGY_PATH),
        "--draft-json",
        json.dumps(draft_payload),
    ]
    result = subprocess.run(
        command,
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    payload_text = result.stdout.strip() or result.stderr.strip()
    if not payload_text:
        raise RuntimeError("Haskell semantic draft planner returned no output.")
    payload = json.loads(payload_text)
    if result.returncode != 0:
        raise RuntimeError(payload.get("message", payload_text))
    return payload


def plan_question(question: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        # Ask the LLM to turn messy user language into a loose semantic draft.
        semantic_draft = interpret_question_to_semantic_draft(question)
    except SemanticInterpreterError as exc:
        raise RuntimeError(str(exc)) from exc
    # Apply explicit product defaults, like current season and regular season,
    # before Haskell validates the draft against the ontology.
    semantic_draft = apply_semantic_assumptions(question, semantic_draft)
    try:
        # Resolve raw comparison names like "Brunson" against the data snapshot.
        # Haskell should receive grounded entity IDs, not trust the LLM to invent them.
        semantic_draft = enrich_semantic_draft_with_resolved_entities(semantic_draft)
    except EntityResolutionError as exc:
        raise RuntimeError(str(exc)) from exc
    # Ask Haskell to turn the draft into a safe, ontology-grounded plan.
    planner_output = call_haskell_planner_for_semantic_draft(semantic_draft)
    return semantic_draft, planner_output


def run_assistant(question: str, debug: bool = False) -> AssistantResult:
    # Make sure the local DuckDB snapshot exists before anything tries to query it.
    load_database()
    # Turn the user question into a semantic draft, then into a Haskell plan.
    semantic_draft, planner_output = plan_question(question)
    # Validate the Haskell execution plan on the Python side before running it.
    if hasattr(ExecutionPlan, "model_validate"):
        execution_plan = ExecutionPlan.model_validate(planner_output["execution_plan"])
    else:
        execution_plan = ExecutionPlan.parse_obj(planner_output["execution_plan"])
    # Execute the plan, package the result, synthesize an answer, and format it.
    runtime_result = execute_plan(execution_plan)
    packaged = package_results(runtime_result)
    answer = synthesize_answer(packaged)
    formatted = format_response(answer)
    artifacts = append_requested_chart_artifacts(question, answer, build_artifacts(answer))

    if not debug:
        return AssistantResult(answer=formatted, artifacts=artifacts)

    # In debug mode, preserve each major transformation stage for adapters to render.
    return AssistantResult(
        answer=formatted,
        artifacts=artifacts,
        debug={
            "query_type": planner_output.get("query_type"),
            "semantic_draft": semantic_draft,
            "query": planner_output.get("query"),
            "resolved_query": planner_output.get("resolved_query"),
            "execution_plan": planner_output.get("execution_plan"),
            "predicate_trace": build_predicate_trace(semantic_draft, planner_output),
            "value_resolution_trace": build_value_resolution_trace(semantic_draft, planner_output),
            "answer": formatted,
        },
    )
