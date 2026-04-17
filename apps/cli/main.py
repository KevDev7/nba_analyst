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
from apps.cli.semantic_interpreter import SemanticInterpreterError, interpret_question_to_planner_query
from scripts.load_gold_snapshot import load_database


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"


def call_haskell_planner_for_query(query_payload: dict) -> dict:
    command = [
        "cabal",
        "run",
        "-v0",
        "ontology-hs",
        "--",
        "plan-query-json",
        "--ontology",
        str(ONTOLOGY_PATH),
        "--query-json",
        json.dumps(query_payload),
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
        raise RuntimeError("Haskell planner returned no output.")
    payload = json.loads(payload_text)
    if result.returncode != 0:
        raise RuntimeError(payload.get("message", payload_text))
    return payload


def plan_question(question: str) -> tuple[dict, dict]:
    try:
        interpreted_query = interpret_question_to_planner_query(question)
    except SemanticInterpreterError as exc:
        raise RuntimeError(str(exc)) from exc
    planner_output = call_haskell_planner_for_query(interpreted_query)
    return interpreted_query, planner_output


def run_cli(question: str, debug: bool = False) -> str:
    load_database()
    interpreted_query, planner_output = plan_question(question)
    if hasattr(ExecutionPlan, "model_validate"):
        execution_plan = ExecutionPlan.model_validate(planner_output["execution_plan"])
    else:
        execution_plan = ExecutionPlan.parse_obj(planner_output["execution_plan"])
    runtime_result = execute_plan(execution_plan)
    packaged = package_results(runtime_result)
    answer = synthesize_answer(packaged)
    formatted = format_response(answer)

    if not debug:
        return formatted

    debug_lines = [
        f"Query type: {planner_output['query_type']}",
        f"Interpreted query: {json.dumps(interpreted_query, indent=2)}",
        f"Query: {json.dumps(planner_output['query'], indent=2)}",
        f"Resolved query: {json.dumps(planner_output['resolved_query'], indent=2)}",
        f"Execution plan: {json.dumps(planner_output['execution_plan'], indent=2)}",
        "",
        formatted,
    ]
    return "\n".join(debug_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the gold-first NBA analyst CLI.")
    parser.add_argument("question", help="Natural-language analytics question.")
    parser.add_argument("--debug", action="store_true", help="Print IR and plan details.")
    args = parser.parse_args()
    print(run_cli(args.question, debug=args.debug))


if __name__ == "__main__":
    main()
