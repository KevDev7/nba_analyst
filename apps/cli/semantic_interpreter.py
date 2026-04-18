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
import time
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, model_validator


ROOT = Path(__file__).resolve().parents[2]
CAPABILITY_PATH = ROOT / "fixtures" / "interpreter" / "semantic-capabilities.json"

load_dotenv(ROOT / ".env", override=False)


class SemanticInterpreterError(RuntimeError):
    """Raised when the Gemini semantic interpreter cannot produce a valid query."""


class SemanticFilter(BaseModel):
    kind: str
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
    metric: str


class SemanticComparison(BaseModel):
    kind: Literal["compare_entities"]
    target_object: str
    entities: list[str]


class ResolvedComparisonEntityRef(BaseModel):
    entityId: int
    entityName: str


class SemanticLinkedFilter(BaseModel):
    target_object: str
    attribute: str
    value: str

    @model_validator(mode="after")
    def validate_linked_filter_shape(self) -> "SemanticLinkedFilter":
        if not self.target_object:
            raise ValueError("linked filters require a target_object.")
        if not self.attribute:
            raise ValueError("linked filters require an attribute.")
        if not self.value:
            raise ValueError("linked filters require a non-empty string value.")
        return self


class SemanticQueryTemplate(BaseModel):
    query_kind: Literal["metric_query", "object_query"]
    core_fact_object: str
    row_object: Optional[str] = None
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    time_grain: Optional[str] = None
    filters: list[SemanticFilter] = Field(default_factory=list)
    linked_filters: list[SemanticLinkedFilter] = Field(default_factory=list)
    orders: list[SemanticOrder] = Field(default_factory=list)
    limit: Optional[int] = None
    entity_filters: list[str] = Field(default_factory=list)
    comparison: Optional[SemanticComparison] = None
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_supported_live_contract(self) -> "SemanticQueryTemplate":
        if len(self.metrics) != 1:
            raise ValueError("The live contract requires exactly one selected metric.")
        if len(self.dimensions) > 1:
            raise ValueError("The live contract allows at most one selected dimension.")
        if self.query_kind == "metric_query" and self.row_object is not None:
            raise ValueError("Metric queries must not set row_object.")
        if self.comparison is not None and self.entity_filters:
            raise ValueError("Comparison queries must keep entity_filters empty in the live contract.")

        matched_family = _match_family(self)
        if matched_family is None:
            raise ValueError(
                "The query template does not match any supported interpreter capability family."
            )

        return self


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
def _capability_artifact() -> dict[str, Any]:
    return json.loads(CAPABILITY_PATH.read_text(encoding="utf-8"))


def _filter_kinds(filters: list[SemanticFilter]) -> list[str]:
    return [filter_value.kind for filter_value in filters]


def _normalize_player_alias(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def _comparison_matches(template: SemanticQueryTemplate, family: dict[str, Any]) -> bool:
    comparison_capability = family["comparison"]
    if not comparison_capability["enabled"]:
        return template.comparison is None and not template.entity_filters
    if template.comparison is None:
        return False
    if template.comparison.kind != "compare_entities":
        return False
    entities = template.comparison.entities
    if len(entities) != comparison_capability["max_entities"]:
        return False
    if comparison_capability.get("target_object") != template.comparison.target_object:
        return False
    if template.entity_filters:
        return False
    if template.orders:
        return False
    if template.linked_filters:
        return False
    return True


def _linked_filters_match(template: SemanticQueryTemplate, family: dict[str, Any]) -> bool:
    linked_filter_capabilities = family["linked_filters"]
    if not linked_filter_capabilities:
        return not template.linked_filters
    if len(template.linked_filters) != len(linked_filter_capabilities):
        return False
    for template_filter, capability_filter in zip(
        template.linked_filters, linked_filter_capabilities
    ):
        if template_filter.target_object != capability_filter["target_object"]:
            return False
        if template_filter.attribute != capability_filter["attribute"]:
            return False
        if not template_filter.value:
            return False
    return True


def _orders_match(template: SemanticQueryTemplate, family: dict[str, Any]) -> bool:
    if not template.orders:
        return True
    if len(template.orders) != 1:
        return False
    order = template.orders[0]
    return order.kind == "desc" and order.metric == template.metrics[0]


def _limit_matches(template: SemanticQueryTemplate, family: dict[str, Any]) -> bool:
    if family["allow_limit"]:
        return template.limit is None or template.limit > 0
    return template.limit is None


def _match_family(template: SemanticQueryTemplate) -> Optional[dict[str, Any]]:
    artifact = _capability_artifact()
    for family in artifact["families"]:
        if family["query_kind"] != template.query_kind:
            continue
        if family["core_fact_object"] != template.core_fact_object:
            continue
        if family.get("row_object") != template.row_object:
            continue
        if template.metrics[0] not in family["metrics"]:
            continue
        if template.dimensions != family["dimensions"]:
            continue
        if template.time_grain != family["time_grain"]:
            continue
        if sorted(_filter_kinds(template.filters)) != sorted(
            family["required_filter_kinds"]
        ):
            continue
        if not _linked_filters_match(template, family):
            continue
        if not _orders_match(template, family):
            continue
        if not _limit_matches(template, family):
            continue
        if not _comparison_matches(template, family):
            continue
        return family
    return None


def _resolve_comparison_entity_name(
    target_object: str, dimension: str, name: str
) -> ResolvedComparisonEntityRef:
    alias_key = _normalize_player_alias(name)
    comparison_indexes = _capability_artifact()["comparison_entity_indexes"]
    alias_index = comparison_indexes.get(target_object, {}).get(dimension, {}).get("aliases", {})
    match = alias_index.get(alias_key)
    if match is None:
        raise SemanticInterpreterError(
            f"Could not resolve {target_object} {dimension} value '{name}' for comparison."
        )
    if match["status"] == "ambiguous":
        candidate_names = ", ".join(
            entity["entity_name"] for entity in match["matches"][:5]
        )
        raise SemanticInterpreterError(
            f"{target_object} {dimension} value '{name}' is ambiguous for comparison. Matches: {candidate_names}."
        )
    entity = match["entity"]
    return ResolvedComparisonEntityRef(
        entityId=int(entity["entity_id"]), entityName=entity["entity_name"]
    )


def _resolved_comparison_entities(
    template: SemanticQueryTemplate,
) -> tuple[list[ResolvedComparisonEntityRef], Optional[dict[str, Any]]]:
    if template.comparison is None:
        return [], None

    if len(template.dimensions) != 1:
        raise SemanticInterpreterError(
            "Comparison queries currently require exactly one comparison identity dimension."
        )

    comparison_names = template.comparison.entities
    target_object = template.comparison.target_object
    dimension = template.dimensions[0]
    resolved_entities = [
        _resolve_comparison_entity_name(target_object, dimension, name)
        for name in comparison_names
    ]
    unique_ids = {entity.entityId for entity in resolved_entities}
    if len(unique_ids) != len(resolved_entities):
        raise SemanticInterpreterError("Comparison requires two distinct resolved entities.")

    comparison_payload = {
        "kind": "compare_entities",
        "targetObject": target_object,
        "entities": [entity.model_dump() for entity in resolved_entities],
    }
    return resolved_entities, comparison_payload


@lru_cache(maxsize=1)
def _capability_prompt_summary() -> str:
    artifact = _capability_artifact()
    fact_object_lines = [
        "Live ontology-backed fact objects:",
        *[
            f"- {object_name}: metrics [{', '.join(object_capability['executable_metrics'])}]"
            for object_name, object_capability in artifact["fact_objects"].items()
            if object_capability["executable_metrics"]
        ],
        "",
        f"Allowed top-level query kinds: {', '.join(artifact['top_level_query_kinds'])}",
        f"Allowed filter kinds: {', '.join(artifact['allowed_filter_kinds'])}",
        f"Allowed time grains: {', '.join(artifact['allowed_time_grains']) or 'none'}",
        "",
        artifact["prompt_summary"],
    ]
    return "\n".join(fact_object_lines)


@lru_cache(maxsize=1)
def _interpreter_prompt_preamble() -> str:
    return f"""
You map NBA analytics questions into a constrained semantic query template.

Rules:
- Output JSON only.
- Never write SQL.
- Never write prose outside the JSON.
- Use only the live ontology-backed vocabulary and supported query families described below.
- Set limit only when the user explicitly asks for a numeric top-N result or a singular highest/best result.
- When the user does not explicitly request a limit, use null for limit.
- For comparison queries, keep the compared entities as raw names from the question; the system resolves those names after you return JSON.
- If the question cannot be represented safely by the current live contract, return:
  {{"status":"unsupported","reason":"<short reason>"}}
- If the question is supported, return:
  {{"status":"ok","query":{{...}}}}

JSON template for supported queries:
{{
  "status": "ok",
  "query": {{
    "query_kind": "metric_query" | "object_query",
    "core_fact_object": "<supported fact object from capability summary>",
    "row_object": "<supported row object or null>",
    "metrics": ["<exactly one supported metric>"],
    "dimensions": ["<zero or one supported dimension>"],
    "time_grain": "<supported time grain or null>",
    "filters": [
      {{"kind":"last_n_games","value":10}}
      | {{"kind":"past_year"}}
      | {{"kind":"exact_season","value":"2025-26"}}
      | {{"kind":"season_type","value":"regular_season" | "playoffs"}}
    ],
    "linked_filters": [
      {{"target_object":"Team","attribute":"team_name","value":"Lakers"}}
    ],
    "orders": [
      {{"kind":"desc","metric":"<selected metric>"}}
    ],
    "limit": 10 | 5 | 1 | null,
    "entity_filters": [],
    "comparison": {{"kind":"compare_entities","target_object":"<supported comparison target object>","entities":["<entity names from the question>"]}} | null,
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
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerGame","row_object":null,"metrics":["total_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[],"limit":null,"entity_filters":[],"comparison":{{"kind":"compare_entities","target_object":"Player","entities":["Brunson","Haliburton"]}},"assumptions":["Interpreted 'pts' as total points."]}}}}

Q: Compare Ja and Tatum scoring over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerGame","row_object":null,"metrics":["total_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[],"limit":null,"entity_filters":[],"comparison":{{"kind":"compare_entities","target_object":"Player","entities":["Ja","Tatum"]}},"assumptions":["Interpreted 'scoring' as total points."]}}}}

Q: Show me players and their total points over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"object_query","core_fact_object":"PlayerGame","row_object":"Player","metrics":["total_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[{{"kind":"desc","metric":"total_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me players and their average points over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"object_query","core_fact_object":"PlayerGame","row_object":"Player","metrics":["average_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me the top 5 players and their total points for the Knicks over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"object_query","core_fact_object":"PlayerGame","row_object":"Player","metrics":["total_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"linked_filters":[{{"target_object":"Team","attribute":"team_name","value":"Knicks"}}],"orders":[{{"kind":"desc","metric":"total_points"}}],"limit":5,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me players and their average points for the Lakers over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"object_query","core_fact_object":"PlayerGame","row_object":"Player","metrics":["average_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"linked_filters":[{{"target_object":"Team","attribute":"team_name","value":"Lakers"}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me players by average points over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerGame","row_object":null,"metrics":["average_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me players by average points for the Lakers over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerGame","row_object":null,"metrics":["average_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"linked_filters":[{{"target_object":"Team","attribute":"team_name","value":"Lakers"}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me teams by average points over the last 10 games
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"TeamGame","row_object":null,"metrics":["average_points"],"dimensions":["team_name"],"time_grain":null,"filters":[{{"kind":"last_n_games","value":10}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: What are the monthly average points by team over the past year?
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"TeamGame","row_object":null,"metrics":["average_points"],"dimensions":["team_name"],"time_grain":"month","filters":[{{"kind":"past_year"}}],"orders":[],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me players by average points in the 2025-26 regular season
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerSeason","row_object":null,"metrics":["average_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"exact_season","value":"2025-26"}},{{"kind":"season_type","value":"regular_season"}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me teams by wins in the 2025-26 regular season
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"TeamSeason","row_object":null,"metrics":["wins"],"dimensions":["team_name"],"time_grain":null,"filters":[{{"kind":"exact_season","value":"2025-26"}},{{"kind":"season_type","value":"regular_season"}}],"orders":[{{"kind":"desc","metric":"wins"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: Show me players by average points for the Lakers in the 2025-26 regular season
A: {{"status":"ok","query":{{"query_kind":"metric_query","core_fact_object":"PlayerSeasonTeam","row_object":null,"metrics":["average_points"],"dimensions":["player_name"],"time_grain":null,"filters":[{{"kind":"exact_season","value":"2025-26"}},{{"kind":"season_type","value":"regular_season"}}],"linked_filters":[{{"target_object":"Team","attribute":"team_name","value":"Lakers"}}],"orders":[{{"kind":"desc","metric":"average_points"}}],"limit":null,"entity_filters":[],"comparison":null,"assumptions":[]}}}}

Q: What is the trend in points over the last month?
A: {{"status":"unsupported","reason":"last month trend is not supported by the current live contract"}}

Q: Show me all information about Brunson
A: {{"status":"unsupported","reason":"object hydration is not supported by the current live contract"}}

Capability summary:
{_capability_prompt_summary()}
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
    body = ""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 503} and attempt < 3:
                # Temporary reliability shim. Provider spikes should not change
                # product behavior; we retry a few times before surfacing the
                # upstream failure.
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


def _normalize_to_haskell_query(
    template: SemanticQueryTemplate,
    resolved_entities: list[ResolvedComparisonEntityRef],
    resolved_comparison: Optional[dict[str, Any]],
) -> dict[str, Any]:
    matched_family = _match_family(template)
    normalized_orders = (
        [SemanticOrder(kind="desc", metric=template.metrics[0])]
        if not template.orders
        and matched_family is not None
        and matched_family["require_order_by_metric"]
        else template.orders
    )
    shared_query = {
        "coreFactObject": template.core_fact_object,
        "metrics": template.metrics,
        "dimensions": template.dimensions,
        "timeGrain": template.time_grain,
        "filters": [flt.model_dump(exclude_none=True) for flt in template.filters],
        "linkedFilters": [
            {
                "targetObject": linked_filter.target_object,
                "attribute": linked_filter.attribute,
                "value": linked_filter.value,
            }
            for linked_filter in template.linked_filters
        ],
        "orders": [order.model_dump() for order in normalized_orders],
        "limit": template.limit,
        "assumptions": template.assumptions,
    }
    if template.query_kind == "metric_query":
        return {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": shared_query,
                "entityFilters": [],
                "comparison": resolved_comparison,
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

    # Temporary normalization shim. This keeps harmless Gemini wording drift out
    # of the user-facing/query contract until assumption handling is modeled more
    # semantically instead of as a fixed allow-list.
    # TODO(core-4-first): This shim is lower priority than finishing the four v1
    # families (ranking/top-N, trend, aggregation, filtering/joining). Clean it
    # up after those families feel complete end to end.
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
    interpreted.query.assumptions = _normalize_assumptions(
        question, interpreted.query.assumptions
    )
    unexpected_assumptions = set(interpreted.query.assumptions) - set(
        _capability_artifact()["allowed_assumptions"]
    )
    if unexpected_assumptions:
        raise SemanticInterpreterError(
            "Gemini returned unsupported assumptions: "
            + ", ".join(sorted(unexpected_assumptions))
        )
    resolved_entities, resolved_comparison = _resolved_comparison_entities(
        interpreted.query
    )
    return _normalize_to_haskell_query(
        interpreted.query, resolved_entities, resolved_comparison
    )
