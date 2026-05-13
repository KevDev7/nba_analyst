from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import unittest


ALLOWED_SQL_TRACE_KEYS = {"sql_hash", "sql_redacted"}
RAW_EXECUTION_KEYS = {"sql", "raw_sql", "execution_plan"}


def load_eval_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise AssertionError(f"Eval bank must be a list: {path}")
    return payload


def tool_names_from_trace(trace: dict[str, Any]) -> list[str]:
    return [
        str(tool_call.get("tool_name"))
        for tool_call in trace.get("tool_calls", [])
        if isinstance(tool_call, dict)
    ]


def assert_expected_tool_sequence(
    test_case: unittest.TestCase,
    trace: dict[str, Any],
    expected_tools: list[str],
) -> None:
    test_case.assertEqual(tool_names_from_trace(trace), expected_tools)


def assert_forbidden_tools_absent(
    test_case: unittest.TestCase,
    trace: dict[str, Any],
    forbidden_tools: list[str],
) -> None:
    test_case.assertTrue(set(tool_names_from_trace(trace)).isdisjoint(forbidden_tools))


def assert_artifact_kinds(
    test_case: unittest.TestCase,
    artifacts: list[dict[str, Any]],
    expected_artifacts: list[str],
) -> None:
    artifact_kinds = {str(artifact.get("kind")) for artifact in artifacts if isinstance(artifact, dict)}
    for expected_artifact in expected_artifacts:
        test_case.assertIn(expected_artifact, artifact_kinds)


def assert_no_raw_sql_or_private_debug(test_case: unittest.TestCase, payload: Any) -> None:
    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                if key_text in RAW_EXECUTION_KEYS and child not in (None, ""):
                    test_case.fail(f"Raw execution detail leaked at {child_path}.")
                if key_text == "private_debug" and child not in (None, {}, []):
                    test_case.fail(f"Private debug leaked at {child_path}.")
                if key_text == "sql" and key_text not in ALLOWED_SQL_TRACE_KEYS:
                    test_case.fail(f"Raw SQL leaked at {child_path}.")
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(payload, "")


def assert_claims_have_evidence(test_case: unittest.TestCase, trace: dict[str, Any]) -> None:
    for claim in trace.get("claims", []):
        test_case.assertIsInstance(claim, dict)
        refs = claim.get("evidence_refs")
        test_case.assertIsInstance(refs, list)
        test_case.assertGreater(len(refs), 0)
        for ref in refs:
            test_case.assertIn("table_id", ref)
            test_case.assertIn("row_index", ref)
            test_case.assertIn("columns", ref)
