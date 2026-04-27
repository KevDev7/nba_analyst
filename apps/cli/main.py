# Purpose:
# Run the gold-first semantic-layer slices end to end from a natural-language question.
#
# Uses:
# - the Haskell semantic core to build IR and execution plans
# - the Python analysis runtime to execute plans
# - the answer synthesis layer to format the final response
#
# Produces:
# - a grounded CLI answer for the supported slice families
#
# Next:
# - manual use or the slice regression tests

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisRuntime.models import ExecutionPlan
from runtime.AnalysisRuntime.runner import execute_plan
from runtime.AnswerSynthesis.format_response import format_response
from runtime.AnswerSynthesis.package_results import package_results
from runtime.AnswerSynthesis.synthesize import synthesize_answer
from apps.cli.entity_resolver import EntityResolutionError, enrich_semantic_draft_with_resolved_entities
from apps.cli.semantic_interpreter import SemanticInterpreterError, interpret_question_to_semantic_draft
from scripts.load_gold_snapshot import load_database


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"


def call_haskell_planner_for_semantic_draft(draft_payload: dict) -> dict:
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


def plan_question(question: str) -> tuple[dict, dict]:
    try:
        # Ask the LLM to turn messy user language into a loose semantic draft.
        semantic_draft = interpret_question_to_semantic_draft(question)
    except SemanticInterpreterError as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        # Resolve raw comparison names like "Brunson" against the data snapshot.
        # Haskell should receive grounded entity IDs, not trust the LLM to invent them.
        semantic_draft = enrich_semantic_draft_with_resolved_entities(semantic_draft)
    except EntityResolutionError as exc:
        raise RuntimeError(str(exc)) from exc
    # Ask Haskell to turn the draft into a safe, ontology-grounded plan.
    planner_output = call_haskell_planner_for_semantic_draft(semantic_draft)
    return semantic_draft, planner_output


def run_cli(question: str, debug: bool = False) -> str:
    # Make sure the local DuckDB snapshot exists before anything tries to query it.
    load_database()
    # Turn the user question into a semantic draft, then into a Haskell plan.
    semantic_draft, planner_output = plan_question(question)
    # Validate the Haskell execution plan on the Python side before running it.
    if hasattr(ExecutionPlan, "model_validate"):
        execution_plan = ExecutionPlan.model_validate(planner_output["execution_plan"])
    else:
        execution_plan = ExecutionPlan.parse_obj(planner_output["execution_plan"])
    # Execute the plan, package the result, synthesize an answer, and format it for the terminal.
    runtime_result = execute_plan(execution_plan)
    packaged = package_results(runtime_result)
    answer = synthesize_answer(packaged)
    formatted = format_response(answer)

    if not debug:
        return formatted

    # In debug mode, show each major transformation stage before the final answer.
    debug_lines = [
        f"Query type: {planner_output['query_type']}",
        f"Semantic draft: {json.dumps(semantic_draft, indent=2)}",
        f"Query: {json.dumps(planner_output['query'], indent=2)}",
        f"Resolved query: {json.dumps(planner_output['resolved_query'], indent=2)}",
        f"Execution plan: {json.dumps(planner_output['execution_plan'], indent=2)}",
        "",
        formatted,
    ]
    return "\n".join(debug_lines)


def main() -> None:
    # Take the terminal question.
    parser = argparse.ArgumentParser(description="Run the gold-first NBA analyst CLI.")
    parser.add_argument("question", help="Natural-language analytics question.")
    # Check whether --debug was passed.
    parser.add_argument("--debug", action="store_true", help="Print IR and plan details.")
    args = parser.parse_args()
    # Call run_cli(...) and print whatever it returns.
    print(run_cli(args.question, debug=args.debug))


if __name__ == "__main__":
    main()
