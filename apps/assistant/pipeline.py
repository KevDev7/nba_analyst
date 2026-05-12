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

import json
import os
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

from apps.assistant.models import AssistantResult
from apps.assistant.semantic.entity_resolver import EntityResolutionError, enrich_semantic_draft_with_resolved_entities
from apps.assistant.semantic.assumptions import apply_semantic_assumptions
from apps.assistant.semantic.interpreter import SemanticInterpreterError, interpret_question_to_semantic_draft


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
PLANNER_BINARY_ENV = "NBA_ONTOLOGY_PLANNER_BIN"


def _planner_command_for_semantic_draft(draft_json: str) -> tuple[list[str], Path]:
    planner_bin = os.getenv(PLANNER_BINARY_ENV, "").strip()
    planner_args = [
        "plan-semantic-draft-json",
        "--ontology",
        str(ONTOLOGY_PATH),
        "--draft-json",
        draft_json,
    ]
    if planner_bin:
        return [planner_bin, *planner_args], ROOT
    return ["cabal", "run", "-v0", "ontology-hs", "--", *planner_args], HASKELL_SERVICE_DIR


def call_haskell_planner_for_semantic_draft(draft_payload: dict[str, Any]) -> dict[str, Any]:
    # Send the LLM's loose semantic draft to Haskell.
    # Haskell is responsible for turning that draft into a grounded query,
    # validating it against the ontology, and compiling an execution plan.
    command, cwd = _planner_command_for_semantic_draft(json.dumps(draft_payload))
    result = subprocess.run(
        command,
        cwd=cwd,
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
    semantic_draft = prepare_semantic_draft(question, semantic_draft)
    # Ask Haskell to turn the draft into a safe, ontology-grounded plan.
    planner_output = call_haskell_planner_for_semantic_draft(semantic_draft)
    return semantic_draft, planner_output


def prepare_semantic_draft(question: str, semantic_draft: dict[str, Any]) -> dict[str, Any]:
    # Apply explicit product defaults, like current season and regular season,
    # before Haskell validates the draft against the ontology.
    prepared = apply_semantic_assumptions(question, semantic_draft)
    try:
        # Resolve raw comparison names like "Brunson" against the data snapshot.
        # Haskell should receive grounded entity IDs, not trust the LLM to invent them.
        prepared = enrich_semantic_draft_with_resolved_entities(prepared)
    except EntityResolutionError as exc:
        raise RuntimeError(str(exc)) from exc
    return prepared


def run_assistant(question: str, debug: bool = False) -> AssistantResult:
    # Keep pipeline.py as the stable public entrypoint while the deterministic
    # orchestrator owns the request lifecycle above governed tools.
    from apps.assistant.orchestrator import run_assistant as run_orchestrated_assistant

    return run_orchestrated_assistant(question, debug=debug)
