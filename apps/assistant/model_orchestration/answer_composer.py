# Purpose:
# Compose grounded model-assisted answers from structured evidence only.
#
# Uses:
# - evidence tables/findings/artifacts
# - existing Gemini transport behind a feature gate
#
# Produces:
# - answer text plus claim/evidence records, or deterministic fallback

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.assistant.semantic.interpreter import _load_interpreter_json, _strip_json_fences
from apps.assistant.semantic.llm_transport import LlmTransportError, call_gemini


class EvidenceRef(BaseModel):
    table_id: str
    row_index: int = Field(ge=0)
    columns: list[str] = Field(min_length=1)


class GroundedClaim(BaseModel):
    text: str
    evidence_refs: list[EvidenceRef] = Field(min_length=1)


class ComposedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    claims: list[GroundedClaim] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_evidence_for_claims(self) -> "ComposedAnswer":
        for claim in self.claims:
            if not claim.evidence_refs:
                raise ValueError("Every claim requires evidence references.")
        return self


def compose_grounded_answer(
    *,
    question: str,
    evidence_tables: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    fallback_answer: str,
    call_model=call_gemini,
) -> ComposedAnswer:
    try:
        raw_text = call_model(_compose_prompt(question, evidence_tables, findings, artifacts))
        payload = _load_interpreter_json(_strip_json_fences(raw_text))
        answer = ComposedAnswer.model_validate(payload) if hasattr(ComposedAnswer, "model_validate") else ComposedAnswer.parse_obj(payload)
        _validate_evidence_refs(answer, evidence_tables)
        return answer
    except (LlmTransportError, Exception):
        return ComposedAnswer(answer=fallback_answer, claims=[], limitations=[])


def _validate_evidence_refs(answer: ComposedAnswer, evidence_tables: list[dict[str, Any]]) -> None:
    tables_by_id = {str(table.get("id")): table for table in evidence_tables}
    for claim in answer.claims:
        for ref in claim.evidence_refs:
            table = tables_by_id.get(ref.table_id)
            if table is None:
                raise ValueError(f"Unknown evidence table: {ref.table_id}")
            rows = table.get("rows", [])
            if ref.row_index >= len(rows):
                raise ValueError(f"Evidence row {ref.row_index} is outside table {ref.table_id}.")
            row = rows[ref.row_index]
            if not isinstance(row, dict):
                raise ValueError("Evidence row must be an object.")
            missing = [column for column in ref.columns if column not in row]
            if missing:
                raise ValueError(f"Evidence columns missing from table {ref.table_id}: {', '.join(missing)}")


def _compose_prompt(
    question: str,
    evidence_tables: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> str:
    evidence_payload = {
        "question": question,
        "evidence_tables": evidence_tables,
        "findings": findings,
        "artifacts": [
            {"kind": artifact.get("kind"), "title": artifact.get("title"), "role": artifact.get("role")}
            for artifact in artifacts
            if isinstance(artifact, dict)
        ],
    }
    return f"""
Write a concise NBA analytics answer using only the supplied evidence.

Return JSON only:
{{
  "answer": "string",
  "claims": [
    {{"text":"string","evidence_refs":[{{"table_id":"...","row_index":0,"columns":["..."]}}]}}
  ],
  "limitations": []
}}

Rules:
- Do not mention numbers, entities, rankings, or metric values unless they appear in evidence_tables/findings.
- Every numeric or factual claim must have evidence_refs.
- Do not infer causality.
- Do not mention SQL, database internals, or hidden tool output.

Evidence:
{json.dumps(evidence_payload, sort_keys=True)}
""".strip()
