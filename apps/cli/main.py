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
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.assistant.pipeline import (
    AssistantResult,
    call_haskell_planner_for_semantic_draft,
    plan_question,
    run_assistant,
)


def _format_debug_output(result: AssistantResult) -> str:
    debug_payload: dict[str, Any] = result.debug or {}
    debug_lines = [
        f"Query type: {debug_payload.get('query_type')}",
        f"Semantic draft: {json.dumps(debug_payload.get('semantic_draft'), indent=2)}",
        f"Query: {json.dumps(debug_payload.get('query'), indent=2)}",
        f"Resolved query: {json.dumps(debug_payload.get('resolved_query'), indent=2)}",
        f"Execution plan: {json.dumps(debug_payload.get('execution_plan'), indent=2)}",
        "",
        result.answer,
    ]
    return "\n".join(debug_lines)


def run_cli(question: str, debug: bool = False) -> str:
    # Ask the shared assistant pipeline for one answer.
    # The CLI only decides whether to render the compact answer or debug view.
    result = run_assistant(question, debug=debug)
    if not debug:
        return result.answer
    return _format_debug_output(result)


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
