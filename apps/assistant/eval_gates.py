from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.assistant.trace import safe_trace_summary


FORBIDDEN_TOOL_NAMES = {"raw_sql", "raw_python", "arbitrary_python", "python_code", "duckdb.execute", "sql.execute"}


@dataclass
class GateResult:
    ok: bool
    failures: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def evaluate_trace_gates(
    trace: dict[str, Any],
    *,
    expected_tools: list[str] | None = None,
    forbidden_tools: set[str] | None = None,
    require_claim_evidence: bool = False,
    max_tool_calls: int | None = None,
) -> GateResult:
    summary = safe_trace_summary(trace)
    failures: list[str] = []
    tool_names = [str(name) for name in summary.get("tool_names", [])]
    forbidden = forbidden_tools or FORBIDDEN_TOOL_NAMES
    if expected_tools is not None and tool_names != expected_tools:
        failures.append(f"tool sequence mismatch: expected {expected_tools}, got {tool_names}")
    if set(tool_names) & forbidden:
        failures.append(f"forbidden tools present: {sorted(set(tool_names) & forbidden)}")
    if max_tool_calls is not None and len(tool_names) > max_tool_calls:
        failures.append(f"tool call count exceeded: {len(tool_names)} > {max_tool_calls}")
    if summary.get("has_private_debug"):
        failures.append("private debug present in trace")
    for step in summary.get("sql_steps", []):
        if not step.get("sql_hash") or not step.get("sql_redacted"):
            failures.append("SQL step missing hash/redaction")
    if require_claim_evidence:
        for index, claim in enumerate(trace.get("claims", [])):
            refs = claim.get("evidence_refs") if isinstance(claim, dict) else None
            if not refs:
                failures.append(f"claim {index} missing evidence refs")
    return GateResult(ok=not failures, failures=failures, summary=summary)
