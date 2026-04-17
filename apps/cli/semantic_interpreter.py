# Purpose:
# Map raw user questions into a constrained semantic query template using Gemini.
#
# Uses:
# - root .env Gemini config
# - the generated ontology fixture for prompt grounding
#
# Produces:
# - normalized Haskell Query JSON for plan-query-json
#
# Next:
# - apps/cli/main.py

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional, Union

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, model_validator


ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"

load_dotenv(ROOT / ".env", override=False)


class SemanticInterpreterError(RuntimeError):
    """Raised when the Gemini semantic interpreter cannot produce a valid query."""


class SemanticFilter(BaseModel):
    kind: Literal["last_n_games", "past_year", "exact_season", "season_type"]
    value: Optional[Union[int, str]] = None

    @model_validator(mode="after")
    def validate_filter_shape(self) -> "SemanticFilter":
        if self.kind == "past_year":
            if self.value is not None:
                raise ValueError("past_year filters must not provide a value.")
            return self

        if self.kind == "last_n_games":
            if not isinstance(self.value, int) or self.value <= 0:
                raise ValueError("last_n_games filters require a positive integer value.")
            return self

        if not isinstance(self.value, str) or not self.value:
            raise ValueError(f"{self.kind} filters require a non-empty string value.")
        return self


class SemanticOrder(BaseModel):
    kind: Literal["desc"]
    metric: Literal[
        "total_points",
        "average_points",
        "games_played",
        "points_per_36",
        "wins",
        "losses",
        "win_percentage",
    ]


class SemanticComparison(BaseModel):
    kind: Literal["compare_entities"]
    entities: list[Literal["jalen_brunson", "tyrese_haliburton"]]


class SemanticQueryTemplate(BaseModel):
    query_kind: Literal["metric_query", "object_query"]
    core_fact_object: Literal["PlayerGame", "TeamGame", "PlayerSeason", "TeamSeason"]
    row_object: Optional[Literal["Player", "Team"]] = None
    metrics: list[
        Literal[
            "total_points",
            "average_points",
            "games_played",
            "points_per_36",
            "wins",
            "losses",
            "win_percentage",
        ]
    ] = Field(default_factory=list)
    dimensions: list[Literal["player_name", "team_name"]] = Field(default_factory=list)
    time_grain: Optional[Literal["month"]] = None
    filters: list[SemanticFilter] = Field(default_factory=list)
    orders: list[SemanticOrder] = Field(default_factory=list)
    limit: Optional[int] = None
    entity_filters: list[Literal["jalen_brunson", "tyrese_haliburton"]] = Field(
        default_factory=list
    )
    comparison: Optional[SemanticComparison] = None
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_supported_live_contract(self) -> "SemanticQueryTemplate":
        if len(self.metrics) != 1:
            raise ValueError("The live contract requires exactly one selected metric.")
        if len(self.dimensions) > 1:
            raise ValueError("The live contract allows at most one selected dimension.")

        if self.query_kind == "object_query":
            if self.row_object != "Player":
                raise ValueError("Object queries currently require row_object = Player.")
            if self.core_fact_object not in {"PlayerGame", "PlayerSeason"}:
                raise ValueError("Object queries currently require PlayerGame or PlayerSeason.")
            if self.metrics != ["total_points"]:
                raise ValueError("Object queries currently support total_points only.")
            if self.orders != [SemanticOrder(kind="desc", metric="total_points")]:
                raise ValueError("Object queries currently require descending total_points ordering.")

        if self.time_grain is not None:
            if self.query_kind != "metric_query":
                raise ValueError("Only metric queries may request a time grain.")
            if self.time_grain != "month":
                raise ValueError("The live contract only supports month time grain.")
            if self.core_fact_object != "TeamGame":
                raise ValueError("Trend queries currently use TeamGame only.")
            if self.metrics != ["average_points"]:
                raise ValueError("Trend queries currently support average_points only.")
            if [flt.kind for flt in self.filters] != ["past_year"]:
                raise ValueError("Trend queries currently require a single past_year filter.")
            if self.dimensions not in ([], ["team_name"]):
                raise ValueError("Trend queries currently allow zero or one team_name dimension.")

        if self.comparison is not None:
            if self.query_kind != "metric_query":
                raise ValueError("Comparison is only supported on metric queries.")
            if self.core_fact_object != "PlayerGame":
                raise ValueError("Comparison currently uses PlayerGame only.")
            if self.metrics != ["total_points"]:
                raise ValueError("Comparison currently supports total_points only.")
            if self.dimensions != ["player_name"]:
                raise ValueError("Comparison currently requires player_name dimension.")
            if self.entity_filters != list(self.comparison.entities):
                raise ValueError("entity_filters must match comparison.entities exactly.")
            if len(self.comparison.entities) != 2:
                raise ValueError("Comparison currently requires exactly two entities.")
            if self.orders:
                raise ValueError("Comparison queries must not request ranking order.")

        if self.core_fact_object == "PlayerSeason":
            filter_kinds = {flt.kind for flt in self.filters}
            if filter_kinds:
                required = {"exact_season", "season_type"}
                if filter_kinds != required:
                    raise ValueError(
                        "PlayerSeason queries currently require exact_season and season_type filters."
                    )
            if self.query_kind == "metric_query" and self.dimensions != ["player_name"]:
                raise ValueError("PlayerSeason metric queries currently require player_name.")

        if self.core_fact_object == "TeamSeason":
            filter_kinds = {flt.kind for flt in self.filters}
            required = {"exact_season", "season_type"}
            if filter_kinds != required:
                raise ValueError(
                    "TeamSeason queries currently require exact_season and season_type filters."
                )
            if self.query_kind != "metric_query" or self.dimensions != ["team_name"]:
                raise ValueError("TeamSeason queries currently require metric_query with team_name.")

        return self


ALLOWED_ASSUMPTIONS = {
    "Interpreted 'pts' as total points.",
    "Interpreted 'scoring' as total points.",
    "Interpreted 'scorers' as players ranked by total points.",
    "Interpreted 'scorer' as players ranked by total points.",
    "Interpreted 'avg points' as average points.",
    "Interpreted 'average scoring' as average points.",
}


class InterpreterUnsupported(BaseModel):
    status: Literal["unsupported"]
    reason: str


class InterpreterSupported(BaseModel):
    status: Literal["ok"]
    query: SemanticQueryTemplate


def _strip_json_fences(raw_text: str) -> str:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


@lru_cache(maxsize=1)
def _ontology_contract_summary() -> str:
    ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    objects = {obj["name"]: obj for obj in ontology["objects"]}
    executable_metrics = {
        object_name: [metric["name"] for metric in objects[object_name].get("metrics", []) if metric.get("executable")]
        for object_name in ["PlayerGame", "TeamGame", "PlayerSeason", "PlayerSeasonTeam", "TeamSeason"]
        if object_name in objects
    }
    return "\n".join(
        [
            "Live ontology-backed objects:",
            "- PlayerGame",
            "- TeamGame",
            "- PlayerSeason",
            "- PlayerSeasonTeam",
            "- TeamSeason",
            "",
            "Executable metrics by fact object:",
            *[
                f"- {object_name}: {', '.join(metrics)}"
                for object_name, metrics in executable_metrics.items()
                if metrics
            ],
            "",
            "Allowed dimensions in the current live query model:",
            "- player_name",
            "- team_name",
            "",
            "Allowed filters:",
            "- last_n_games",
            "- past_year",
            "- exact_season",
            "- season_type",
            "",
            "Allowed time_grain:",
            "- month",
            "",
            "Allowed top-level query kinds:",
            "- metric_query",
            "- object_query",
            "",
            "Current live supported semantic shapes:",
            "- PlayerGame metric rankings over last_n_games by player_name using total_points or average_points",
            "- PlayerGame comparison over last_n_games for exactly jalen_brunson and tyrese_haliburton using total_points",
            "- TeamGame metric rankings over last_n_games by team_name using average_points",
            "- TeamGame monthly trends over past_year using average_points, optionally grouped by team_name",
            "- PlayerGame object queries for Player rows with total_points over last_n_games",
            "- PlayerSeason metric rankings for player_name with exact_season + season_type using average_points",
            "- PlayerSeason object queries for Player rows with exact_season + season_type using total_points",
            "- TeamSeason metric rankings for team_name with exact_season + season_type using wins",
            "",
            "Unsupported requests must return:",
            '{"status":"unsupported","reason":"<short reason>"}',
            "",
            "Supported requests must return:",
            '{"status":"ok","query":{...}}',
        ]
    )


@lru_cache(maxsize=1)
def _interpreter_prompt_preamble() -> str:
    return f"""
You map NBA analytics questions into a constrained semantic query template.

Rules:
- Output JSON only.
- Never write SQL.
- Never write prose outside the JSON.
- Use only the live ontology-backed vocabulary and supported query shapes described below.
- Set limit only when the user explicitly asks for a numeric top-N result or a singular highest/best result.
- When the user does not explicitly request a limit, use null for limit.
- If the question cannot be represented safely by the current live contract, return:
  {{"status":"unsupported","reason":"<short reason>"}}
- If the question is supported, return:
  {{"status":"ok","query":{{...}}}}

JSON template for supported queries:
{{
  "status": "ok",
  "query": {{
    "query_kind": "metric_query" | "object_query",
    "core_fact_object": "PlayerGame" | "TeamGame" | "PlayerSeason" | "TeamSeason",
    "row_object": "Player" | "Team" | null,
    "metrics": ["total_points" | "average_points" | "games_played" | "points_per_36" | "wins" | "losses" | "win_percentage"],
    "dimensions": ["player_name" | "team_name"],
    "time_grain": "month" | null,
    "filters": [
      {{"kind":"last_n_games","value":10}}
      | {{"kind":"past_year"}}
      | {{"kind":"exact_season","value":"2025-26"}}
      | {{"kind":"season_type","value":"regular_season" | "playoffs"}}
    ],
    "orders": [
      {{"kind":"desc","metric":"total_points" | "average_points" | "games_played" | "points_per_36" | "wins" | "losses" | "win_percentage"}}
    ],
    "limit": 10 | 5 | 1 | null,
    "entity_filters": ["jalen_brunson","tyrese_haliburton"],
    "comparison": {{"kind":"compare_entities","entities":["jalen_brunson","tyrese_haliburton"]}} | null,
    "assumptions": ["..."]
  }}
}}

Assumption rules:
- Never invent assumptions the user did not trigger literally.
- If the user uses the canonical phrase "points", "average points", or "wins", assumptions must be [].
- If the user says "pts", include: "Interpreted 'pts' as total points."
- If the user says "scoring" and the metric is total_points, include: "Interpreted 'scoring' as total points."
- If the user says "scorer" or "scorers", include: "Interpreted 'scorers' as players ranked by total points." or the singular equivalent.
- If the user says "avg points", include: "Interpreted 'avg points' as average points."
- If the user says "average scoring", include: "Interpreted 'average scoring' as average points."

Examples:
Q: Show me the top 10 players by points over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerGame","row_object":null,"metrics":["total_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[{{"kind":"desc","metric":"total_points"}}],"limit":10,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Who are the top 10 scorers over the last 10 games?
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerGame","row_object":null,"metrics":["total_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[{{"kind":"desc","metric":"total_points"}}],"limit":10,"entity_filters":[],"comparison":null,"assumptions":["Interpreted 'scorers' as players ranked by total points."]}}}}

Q: Compare Brunson and Haliburton pts over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerGame","row_object":null,"metrics":["total_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[],"limit":null,"entity_filters":["jalen_brunson","tyrese_haliburton"],"comparison":{{"kind":"compare_entities","entities":["jalen_brunson","tyrese_haliburton"]}},"assumptions":["Interpreted 'pts' as total points."]}}}}

Q: Show me players and their total points over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"object_query","core_fact_object":"PlayerGame","row_object":"Player","metrics":["total_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[{{"kind":"desc","metric":"total_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me players by average points over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerGame","row_object":null,"metrics":["average_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me teams by average points over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"TeamGame","row_object":null,"metrics":["average_points"],"dimensions":["team_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: What are the monthly average points by team over the past year?
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"TeamGame","row_object":null,"metrics":["average_points"],"dimensions":["team_name"],"time_grain":"month","filters":[{{"kind":"past_year"}}],"orders":[],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me players by average points in the 2025-26 regular season
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerSeason","row_object":null,"metrics":["average_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"exact_season","value":"2025-26"}},{{"kind":"season_type","value":"regular_season"}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me teams by wins in the 2025-26 regular season
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"TeamSeason","row_object":null,"metrics":["wins"],"dimensions":["team_name"],"time_grain":null,"filters":[{{"kind":"exact_season","value":"2025-26"}},{{"kind":"season_type","value":"regular_season"}}],"orders":[{{"kind":"desc","metric":"wins"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: What is the trend in points over the last month?
A: {{"status":"unsupported","reason":"last month trend is not supported by the current live contract"}}

Q: Show me all information about Brunson
A: {{"status":"unsupported","reason":"object hydration is not supported by the current live contract"}}

Live contract summary:
{_ontology_contract_summary()}
""".strip()


def _call_gemini(prompt: str) -> str:
    provider = os.getenv("LLM_INTERPRETER_PROVIDER", "google")
    if provider != "google":
        raise SemanticInterpreterError(
            f"Unsupported LLM_INTERPRETER_PROVIDER '{provider}'. Slice 10 supports 'google' only."
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
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
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


def _parse_interpreter_response(raw_text: str) -> Union[InterpreterSupported, InterpreterUnsupported]:
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
            raise SemanticInterpreterError(f"Gemini returned an invalid supported query template: {exc}") from exc
    if status == "unsupported":
        try:
            return InterpreterUnsupported.model_validate(parsed)
        except ValidationError as exc:
            raise SemanticInterpreterError(f"Gemini returned an invalid unsupported response: {exc}") from exc
    raise SemanticInterpreterError("Gemini response must include status 'ok' or 'unsupported'.")


def _normalize_to_haskell_query(template: SemanticQueryTemplate) -> dict[str, Any]:
    shared_query = {
        "coreFactObject": template.core_fact_object,
        "metrics": template.metrics,
        "dimensions": template.dimensions,
        "timeGrain": template.time_grain,
        "filters": [flt.model_dump(exclude_none=True) for flt in template.filters],
        "orders": [order.model_dump() for order in template.orders],
        "limit": template.limit,
        "assumptions": template.assumptions,
    }
    if template.query_kind == "metric_query":
        return {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": shared_query,
                "entityFilters": template.entity_filters,
                "comparison": template.comparison.model_dump() if template.comparison else None,
            },
        }

    return {
        "kind": "object_query",
        "spec": {
            "sharedQuery": shared_query,
            "rowObject": template.row_object,
        },
    }


def _normalize_assumptions(question: str, assumptions: list[str]) -> list[str]:
    question_text = question.lower()
    normalized: list[str] = []

    if "pts" in question_text and "Interpreted 'pts' as total points." in assumptions:
        normalized.append("Interpreted 'pts' as total points.")
    if "average scoring" in question_text and "Interpreted 'average scoring' as average points." in assumptions:
        normalized.append("Interpreted 'average scoring' as average points.")
    if re.search(r"\bscorers\b", question_text) and "Interpreted 'scorers' as players ranked by total points." in assumptions:
        normalized.append("Interpreted 'scorers' as players ranked by total points.")
    if re.search(r"\bscorer\b", question_text) and "Interpreted 'scorer' as players ranked by total points." in assumptions:
        normalized.append("Interpreted 'scorer' as players ranked by total points.")
    if "avg points" in question_text and "Interpreted 'avg points' as average points." in assumptions:
        normalized.append("Interpreted 'avg points' as average points.")
    if (
        "average scoring" not in question_text
        and re.search(r"\bscoring\b", question_text)
        and "Interpreted 'scoring' as total points." in assumptions
    ):
        normalized.append("Interpreted 'scoring' as total points.")
    return normalized


@lru_cache(maxsize=256)
def interpret_question_to_planner_query(question: str) -> dict[str, Any]:
    prompt = (
        f"{_interpreter_prompt_preamble()}\n\n"
        f"User question:\n{question}\n\n"
        "Return the JSON response now."
    )
    raw_text = _call_gemini(prompt)
    interpreted = _parse_interpreter_response(raw_text)
    if isinstance(interpreted, InterpreterUnsupported):
        raise SemanticInterpreterError(interpreted.reason)
    unexpected_assumptions = set(interpreted.query.assumptions) - ALLOWED_ASSUMPTIONS
    if unexpected_assumptions:
        raise SemanticInterpreterError(
            "Gemini returned unsupported assumptions: "
            + ", ".join(sorted(unexpected_assumptions))
        )
    interpreted.query.assumptions = _normalize_assumptions(
        question, interpreted.query.assumptions
    )
    return _normalize_to_haskell_query(interpreted.query)
