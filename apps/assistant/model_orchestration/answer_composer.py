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
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.assistant.semantic.interpreter import _load_interpreter_json, _strip_json_fences
from apps.assistant.semantic.llm_transport import LlmTransportError, call_gemini


_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?(?![A-Za-z0-9])")
_UNSUPPORTED_CAUSAL_RE = re.compile(
    r"\b(caused by|because of|due to|drove|driven by|led to|resulted from|responsible for|thanks to)\b",
    re.IGNORECASE,
)


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
    prompt = _compose_prompt(question, evidence_tables, findings, artifacts)
    for _attempt in range(2):
        try:
            raw_text = call_model(prompt)
            payload = _load_interpreter_json(_strip_json_fences(raw_text))
            answer = ComposedAnswer.model_validate(payload) if hasattr(ComposedAnswer, "model_validate") else ComposedAnswer.parse_obj(payload)
            _validate_evidence_refs(answer, evidence_tables)
            return answer
        except (LlmTransportError, Exception):
            continue
    return ComposedAnswer(answer=fallback_answer, claims=[], limitations=[])


def _validate_evidence_refs(answer: ComposedAnswer, evidence_tables: list[dict[str, Any]]) -> None:
    tables_by_id = {str(table.get("id")): table for table in evidence_tables}
    if _contains_unsupported_causal_language(answer.answer):
        raise ValueError("Composed answer used unsupported causal language.")
    if _numeric_tokens(answer.answer) and not answer.claims:
        raise ValueError("Numeric answer text requires claim evidence.")
    all_referenced_values: list[object] = []
    for claim in answer.claims:
        if _contains_unsupported_causal_language(claim.text):
            raise ValueError("Composed claim used unsupported causal language.")
        referenced_values: list[object] = []
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
            referenced_values.extend(row[column] for column in ref.columns)
        _validate_claim_text_matches_evidence(claim.text, referenced_values)
        all_referenced_values.extend(referenced_values)
    _validate_answer_numbers_match_evidence(answer.answer, all_referenced_values)


def _validate_claim_text_matches_evidence(claim_text: str, referenced_values: list[object]) -> None:
    numeric_tokens = _numeric_tokens(claim_text)
    referenced_numbers = [_coerce_number(value) for value in referenced_values]
    referenced_numbers = [number for number in referenced_numbers if number is not None]
    referenced_text_values = [str(value).strip() for value in referenced_values if str(value).strip()]

    if numeric_tokens and not any(
        _number_supported_by_evidence(token, referenced_numbers, referenced_text_values)
        for token in numeric_tokens
    ):
        raise ValueError("Numeric claim text does not match referenced evidence.")

    text_values = [
        value
        for value in referenced_text_values
        if _is_meaningful_text_evidence(value) and _coerce_number(value) is None
    ]
    if text_values and not any(_contains_text_value(claim_text, value) for value in text_values):
        raise ValueError("Entity/text claim does not match referenced evidence.")


def _validate_answer_numbers_match_evidence(answer_text: str, referenced_values: list[object]) -> None:
    numeric_tokens = _numeric_tokens(answer_text)
    if not numeric_tokens:
        return
    referenced_numbers = [_coerce_number(value) for value in referenced_values]
    referenced_numbers = [number for number in referenced_numbers if number is not None]
    referenced_text_values = [str(value).strip() for value in referenced_values if str(value).strip()]
    if not all(
        _number_supported_by_evidence(token, referenced_numbers, referenced_text_values)
        for token in numeric_tokens
    ):
        raise ValueError("Numeric answer text does not match referenced evidence.")


def _numeric_tokens(text: str) -> list[float]:
    tokens: list[float] = []
    for match in _NUMBER_RE.finditer(text):
        value = _coerce_number(match.group(0))
        if value is not None:
            tokens.append(value)
    return tokens


def _coerce_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def _number_supported_by_evidence(
    token: float,
    referenced_numbers: list[float],
    referenced_text_values: list[str],
) -> bool:
    if any(abs(token - number) <= max(0.01, abs(number) * 0.001) for number in referenced_numbers):
        return True
    token_text = _format_number_for_text(token)
    return any(token_text in value for value in referenced_text_values)


def _format_number_for_text(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def _is_meaningful_text_evidence(value: str) -> bool:
    normalized = value.strip()
    return len(normalized) >= 3 and any(character.isalpha() for character in normalized)


def _contains_text_value(claim_text: str, value: str) -> bool:
    return value.lower() in claim_text.lower()


def _contains_unsupported_causal_language(text: str) -> bool:
    return _UNSUPPORTED_CAUSAL_RE.search(text) is not None


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
