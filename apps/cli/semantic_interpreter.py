# Purpose:
# Ask the LLM for a loose semantic draft of the user's NBA analytics question.
#
# Uses:
# - root .env Gemini config
# - a deliberately non-ontology draft schema
#
# Produces:
# - basic validated semantic draft JSON for Haskell grounding
#
# Next:
# - apps/cli/main.py

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, model_validator


ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env", override=False)


class SemanticInterpreterError(RuntimeError):
    """Raised when the LLM semantic interpreter cannot produce a valid draft."""


class DraftTimeWindow(BaseModel):
    kind: str
    value: int

    @model_validator(mode="after")
    def validate_time_window_shape(self) -> "DraftTimeWindow":
        if self.kind != "last_n_games":
            raise ValueError("Slice 36 only supports last_n_games time windows.")
        if self.value <= 0:
            raise ValueError("last_n_games requires a positive integer value.")
        return self


class SemanticDraft(BaseModel):
    task: str
    subject: str
    measure: str
    time_window: DraftTimeWindow
    limit: Optional[int] = None
    sort: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_basic_draft_shape(self) -> "SemanticDraft":
        if self.limit is not None and self.limit <= 0:
            raise ValueError("limit must be positive when provided.")
        return self


class InterpreterUnsupported(BaseModel):
    status: Literal["unsupported"]
    reason: str


class InterpreterSupported(BaseModel):
    status: Literal["ok"]
    draft: SemanticDraft


def _strip_json_fences(raw_text: str) -> str:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


@lru_cache(maxsize=1)
def _semantic_draft_prompt_preamble() -> str:
    return """
You map NBA analytics questions into a loose semantic draft.

Rules:
- Output JSON only.
- Never write SQL.
- Never write prose outside the JSON.
- Do not output ontology object names, table names, metric keys, dimension keys, SQL, or planner IR.
- Your job is only to preserve the user's semantic intent in the draft schema.
- Slice 36 supports exactly one family: ranking players by points/scoring over the last N games.
- Set limit only when the user explicitly asks for a numeric top-N result or a singular highest/best result.
- If the question cannot be represented by this Slice 36 family, return:
  {"status":"unsupported","reason":"<short reason>"}
- If the question is supported, return:
  {"status":"ok","draft":{...}}

JSON template for supported drafts:
{
  "status": "ok",
  "draft": {
    "task": "rank",
    "subject": "players",
    "measure": "points" | "scoring" | "pts",
    "time_window": {"kind":"last_n_games","value":10},
    "limit": 10 | 5 | 1 | null,
    "sort": "desc",
    "assumptions": []
  }
}

Assumption rules:
- Never invent assumptions the user did not trigger literally.
- If the user uses the canonical phrase "points", assumptions must be [].
- If the user says "pts", include: "Interpreted 'pts' as points."
- If the user says "scoring", include: "Interpreted 'scoring' as points."
- If the user says "scorer" or "scorers", include: "Interpreted 'scorers' as players ranked by points." or the singular equivalent.

Examples:
Q: Show me the top 10 players by points over the last 10 games
A: {"status":"ok","draft":{"task":"rank","subject":"players","measure":"points","time_window":{"kind":"last_n_games","value":10},"limit":10,"sort":"desc","assumptions":[]}}

Q: Who are the top 10 scorers over the last 10 games?
A: {"status":"ok","draft":{"task":"rank","subject":"players","measure":"scoring","time_window":{"kind":"last_n_games","value":10},"limit":10,"sort":"desc","assumptions":["Interpreted 'scorers' as players ranked by points."]}}

Q: Show me the best scorer over the last 5 games
A: {"status":"ok","draft":{"task":"rank","subject":"players","measure":"scoring","time_window":{"kind":"last_n_games","value":5},"limit":1,"sort":"desc","assumptions":["Interpreted 'scorer' as players ranked by points.","Interpreted 'scoring' as points."]}}

Q: Show me teams by points over the last 10 games
A: {"status":"unsupported","reason":"team rankings are outside Slice 36"}
""".strip()


def _call_gemini(prompt: str) -> str:
    provider = os.getenv("LLM_INTERPRETER_PROVIDER", "google")
    if provider != "google":
        raise SemanticInterpreterError(
            f"Unsupported LLM_INTERPRETER_PROVIDER '{provider}'. This CLI supports 'google' only."
        )

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    temperature = float(os.getenv("LLM_INTERPRETER_TEMPERATURE", "0"))
    if not api_key:
        raise SemanticInterpreterError("Missing GEMINI_API_KEY for semantic interpretation.")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    body = ""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 503} and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise SemanticInterpreterError(
                f"Gemini interpreter request failed with HTTP {exc.code}: {body[:500]}"
            ) from exc
        except Exception as exc:  # pragma: no cover - network exceptions are environment-specific
            raise SemanticInterpreterError(f"Gemini interpreter request failed: {exc}") from exc

    try:
        payload_json = json.loads(body)
        return payload_json["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:
        raise SemanticInterpreterError("Gemini response did not contain a text candidate.") from exc


def _parse_interpreter_response(
    raw_text: str,
) -> Union[InterpreterSupported, InterpreterUnsupported]:
    cleaned = _strip_json_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SemanticInterpreterError(f"Gemini returned malformed JSON: {exc}") from exc

    status = parsed.get("status")
    if status == "ok":
        try:
            return InterpreterSupported.model_validate(parsed)
        except ValidationError as exc:
            raise SemanticInterpreterError(f"Gemini returned an invalid semantic draft: {exc}") from exc
    if status == "unsupported":
        try:
            return InterpreterUnsupported.model_validate(parsed)
        except ValidationError as exc:
            raise SemanticInterpreterError(f"Gemini returned an invalid unsupported response: {exc}") from exc
    raise SemanticInterpreterError("Gemini response must include status 'ok' or 'unsupported'.")


@lru_cache(maxsize=256)
def interpret_question_to_semantic_draft(question: str) -> dict[str, Any]:
    prompt = (
        f"{_semantic_draft_prompt_preamble()}\n\n"
        f"User question:\n{question}\n\n"
        "Return the JSON response now."
    )
    raw_text = _call_gemini(prompt)
    interpreted = _parse_interpreter_response(raw_text)
    if isinstance(interpreted, InterpreterUnsupported):
        raise SemanticInterpreterError(interpreted.reason)
    return interpreted.draft.model_dump()
