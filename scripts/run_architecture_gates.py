#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.assistant.eval_gates import FORBIDDEN_TOOL_NAMES, evaluate_trace_gates
from apps.assistant.model_orchestration.plans import ModelAnalysisPlan, planned_tool_names


TRACE_BANK = ROOT / "evals" / "orchestrator_trace_eval_bank.json"
MODEL_BANK = ROOT / "evals" / "model_orchestration_question_bank.json"


def main() -> int:
    failures: list[str] = []
    failures.extend(_check_trace_bank())
    failures.extend(_check_model_bank())
    if failures:
        print("Architecture gates failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Architecture gates passed.")
    return 0


def _check_trace_bank() -> list[str]:
    failures: list[str] = []
    for case in _load_cases(TRACE_BANK):
        result = evaluate_trace_gates(
            case["trace"],
            expected_tools=case.get("expected_tools"),
            forbidden_tools=set(case.get("forbidden_tools") or FORBIDDEN_TOOL_NAMES),
            require_claim_evidence=bool(case.get("require_claim_evidence")),
            max_tool_calls=case.get("max_tool_calls"),
        )
        if not result.ok:
            failures.append(f"{TRACE_BANK.name}:{case.get('name')}: {result.failures}")
    return failures


def _check_model_bank() -> list[str]:
    failures: list[str] = []
    for case in _load_cases(MODEL_BANK):
        try:
            plan = ModelAnalysisPlan.model_validate(case["plan"])
        except Exception as exc:
            failures.append(f"{MODEL_BANK.name}:{case.get('name')}: invalid plan: {exc}")
            continue
        tool_names = planned_tool_names(plan)
        if tool_names != case.get("expected_tools"):
            failures.append(f"{MODEL_BANK.name}:{case.get('name')}: tool mismatch {tool_names} != {case.get('expected_tools')}")
        forbidden = set(case.get("forbidden_tools") or FORBIDDEN_TOOL_NAMES)
        if set(tool_names) & forbidden:
            failures.append(f"{MODEL_BANK.name}:{case.get('name')}: forbidden tools {sorted(set(tool_names) & forbidden)}")
        if len(tool_names) > int(case.get("max_tool_calls", 999)):
            failures.append(f"{MODEL_BANK.name}:{case.get('name')}: too many tool calls")
    return failures


def _load_cases(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Eval bank must be a list: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
