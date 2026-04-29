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
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, model_validator

from apps.cli.llm_transport import LlmTransportError, call_gemini
from apps.cli.predicate_draft_normalizer import normalize_flat_filter_predicates


ROOT = Path(__file__).resolve().parents[2]

# Find the project root and load API/model configuration from .env.
load_dotenv(ROOT / ".env", override=False)


class SemanticInterpreterError(RuntimeError):
    """Raised when the LLM semantic interpreter cannot produce a valid draft."""


class DraftTimeWindow(BaseModel):
    # The time part of the user's question.
    # Examples: last 10 games, past year, 2025-26 season.
    kind: str
    value: Optional[Union[int, str]] = None

    @model_validator(mode="after")
    def validate_time_window_shape(self) -> "DraftTimeWindow":
        # Only validate basic shape here. Haskell decides whether the time
        # window is actually supported by the ontology/planner.
        if not self.kind:
            raise ValueError("time_window.kind must be non-empty.")
        if isinstance(self.value, str) and not self.value:
            raise ValueError("time_window.value must be non-empty when provided as text.")
        return self


class SemanticDraft(BaseModel):
    # The loose, user-facing intent schema the LLM fills in.
    # This should preserve meaning without using SQL, table names, or ontology keys.
    task: str
    subject: str
    measure: Optional[str] = None
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    result_filters: list[dict[str, Any]] = Field(default_factory=list)
    predicate: Optional[dict[str, Any]] = None
    result_predicate: Optional[dict[str, Any]] = None
    time_window: Optional[DraftTimeWindow] = None
    grain: Optional[str] = None
    order: list[dict[str, Any]] = Field(default_factory=list)
    limit: Optional[int] = None
    sort: Optional[str] = None
    entities: list[str] = Field(default_factory=list)
    operations: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_basic_draft_shape(self) -> "SemanticDraft":
        # Keep Python validation lightweight. It checks obvious bad shapes,
        # while Haskell remains the source of truth for semantic validity.
        if self.limit is not None and self.limit <= 0:
            raise ValueError("limit must be positive when provided.")
        if self.time_window is None and self.task not in {"find", "compare"}:
            raise ValueError("time_window is required except for find drafts.")
        return self


class InterpreterUnsupported(BaseModel):
    # Gemini can use this only when the request is not NBA analytics or cannot
    # fit the draft schema at all.
    status: Literal["unsupported"]
    reason: str


class InterpreterSupported(BaseModel):
    # Gemini uses this when it can preserve the user's intent as a draft.
    status: Literal["ok"]
    draft: SemanticDraft


def _strip_json_fences(raw_text: str) -> str:
    # If the model wraps JSON in ``` fences, remove them before parsing.
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


@lru_cache(maxsize=1)
def _semantic_draft_prompt_preamble() -> str:
    # These are Gemini's instructions. The key rule: preserve user intent,
    # but do not invent SQL, ontology object names, metric keys, or planner IR.
    return """
You map NBA analytics questions into a loose semantic draft.

Rules:
- Output JSON only.
- Never write SQL.
- Never write prose outside the JSON.
- Do not output ontology object names, table names, metric keys, dimension keys, SQL, or planner IR.
- Your job is only to preserve the user's semantic intent in the draft schema.
- Set limit only when the user explicitly asks for a numeric top-N result or a singular highest/best result.
- Return an ok draft for NBA analytics questions whenever you can preserve the user's intent in this schema.
- Do not decide whether the ontology can answer the question; Haskell does ontology grounding and planning after you return the draft.
- Return unsupported only when the question is not an NBA analytics request or cannot be represented in this draft schema at all:
  {"status":"unsupported","reason":"<short reason>"}
- If the question is supported, return:
  {"status":"ok","draft":{...}}

Question family rules:
- Use "rank" when the user wants entities ordered by a measure. This includes wording like top, highest, best, leaders, leaderboard, or "<entities> by <measure>".
- Use "object" when the user wants entity rows with their attributes or measures, such as "players and their total points" or "teams with their wins".
- If wording uses "and their" or "with their", prefer "object" even when it also includes a limit like "top 5"; preserve the limit/order inside the object draft.
- Use "rank" for "top N <entities> by <measure>" because "by" makes the metric the organizing idea.
- Use "aggregate" when the user asks for a grouped calculation or summary without ranking/order intent, such as "average points by team".
- Use "trend" when the user asks for a metric over time or uses a time grain like by day, by week, monthly, or by season.
- Use "find" when the user asks to find/list matching games, players, teams, or rows that satisfy filters.
- Use "compare" when the user asks to compare named entities.
- For compare questions, preserve requested breakdowns in dimensions, such as "by season type", "by team", or "by conference".
- For compare questions with calendar/time buckets like "by month" or "monthly", keep task "compare" and set grain to the requested bucket.
- If a compare question has no explicit time scope, keep time_window null; the policy layer will apply the product default.
- If a rank question does not explicitly ask for a limit, keep limit null but still include a descending order for positive performance metrics unless the user asks for ascending/lowest.
- When the user asks for multiple measures, put every requested measure phrase in "measures" in user-facing order.
- Keep "measure" as the primary measure used for ranking, ordering, and summary. For object/aggregate questions without an explicit primary measure, use the first requested measure.
- Do not invent multi-sort. Extra measures are display measures unless the user clearly names one as the ranking/order measure.
- For find questions, put requested display fields after words like "show" in dimensions, and put requested sort fields in order using user-facing phrases. Example: "show date and score, sorted newest first" should use dimensions ["date","score"] and order [{"by":"date","direction":"desc"}].

Filter rules:
- Put row-level constraints in filters using the user's field phrase, operator, and value.
- Preserve numeric filter values as numbers when possible, including decimals such as 0.6.
- Examples of row-level filters: "minutes over 30" -> {"field":"minutes","op":">","value":30}; "win percentage above .600" -> {"field":"win percentage","op":">","value":0.6}.
- For any question family with OR, NOT, IN, BETWEEN, or CONTAINS row-level logic, put the richer condition in predicate instead of flattening it into filters.
- Predicate leaves still use user-facing field phrases, not ontology/table/column names.
- Predicate examples:
  "team is Lakers or Warriors" -> {"kind":"leaf","field":"team","op":"in","value":["Lakers","Warriors"]}
  "not in the West" -> {"kind":"not","predicate":{"kind":"leaf","field":"conference","op":"=","value":"West"}}
  "name contains Smith" -> {"kind":"leaf","field":"name","op":"contains","value":"Smith"}
  "score between 110 and 120" -> {"kind":"leaf","field":"score","op":"between","value":{"lower":110,"upper":120}}
- For AND/OR predicate trees, always use "predicates": [...]. Do not use "left" and "right".
- Put aggregate/result constraints in result_filters or result_predicate, not filters. These are conditions that must be applied after grouping/calculation.
- Examples of result filters: "averaging over 30 minutes" -> {"field":"average minutes","op":">","value":30}; "total points above 200" -> {"field":"total points","op":">","value":200}.
- For aggregate/result constraints with OR, NOT, IN, or BETWEEN logic, put the richer condition in result_predicate instead of flattening it into result_filters.
- Result predicate leaves still use user-facing result field phrases, not ontology/table/column names.
- If the condition references an average, total, sum, or per-game value, treat it as result-level unless the user is clearly filtering individual rows.

JSON template for supported drafts:
{
  "status": "ok",
  "draft": {
    "task": "rank" | "trend" | "aggregate" | "find" | "compare" | "object",
    "subject": "players" | "teams" | "<business subject from the user>",
    "measure": "<primary user-facing measure phrase or null>",
    "measures": ["<user-facing measure phrase>"],
    "dimensions": ["<user-facing grouping/display phrase>"],
    "filters": [
      {"field":"<user-facing filter field phrase>","op":"<operator or filter kind>","value":"<number, text, date, or object>"}
    ],
    "predicate": {"kind":"leaf" | "and" | "or" | "not", "...":"richer row predicate, or null"},
    "result_filters": [
      {"field":"<user-facing aggregate/result field phrase>","op":"<operator>","value":"<number>"}
    ],
    "result_predicate": {"kind":"leaf" | "and" | "or" | "not", "...":"richer grouped-result predicate, or null"},
    "time_window": {"kind":"last_n_games" | "last_n_days" | "season" | "past_year" | "since_date" | "until_date" | "between_dates" | "all","value":10},
    "grain": "day" | "week" | "month" | "season" | null,
    "order": [{"by":"<user-facing measure/dimension phrase>","direction":"asc" | "desc"}],
    "limit": "<positive integer explicitly requested by the user, or null>",
    "sort": "asc" | "desc" | null,
    "entities": ["<raw entity names from user>"],
    "operations": [
      {
        "kind": "aggregate" | "rank" | "trend" | "compare" | "filter" | "object",
        "measure": "<user-facing measure phrase or null>",
        "dimensions": ["<user-facing dimension phrase>"],
        "order_by": "<user-facing measure/dimension phrase or null>",
        "limit": 5
      }
    ],
    "assumptions": []
  }
}

Assumption rules:
- Keep assumptions empty when the draft preserves the user's wording directly.
- Add an assumption only when you normalize shorthand, ambiguous wording, or a user-facing synonym into clearer draft wording.
- Do not add assumptions about whether the ontology can answer the question.
- Keep each assumption short and grounded in words the user actually used.

Examples:
Q: Show me the top 10 players by points over the last 10 games
A: {"status":"ok","draft":{"task":"rank","subject":"players","measure":"points","measures":["points"],"dimensions":[],"filters":[],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[{"by":"points","direction":"desc"}],"limit":10,"sort":"desc","entities":[],"operations":[],"assumptions":[]}}

Q: Who are the top 10 scorers over the last 10 games?
A: {"status":"ok","draft":{"task":"rank","subject":"players","measure":"scoring","measures":["scoring"],"dimensions":[],"filters":[],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[{"by":"scoring","direction":"desc"}],"limit":10,"sort":"desc","entities":[],"operations":[],"assumptions":["Interpreted 'scorers' as players ranked by points."]}}

Q: What are monthly team average points over the past year?
A: {"status":"ok","draft":{"task":"trend","subject":"teams","measure":"average points","measures":["average points"],"dimensions":["team"],"filters":[],"time_window":{"kind":"past_year","value":null},"grain":"month","order":[],"limit":null,"sort":null,"entities":[],"operations":[],"assumptions":[]}}

Q: Rank players by average points over the last 30 days
A: {"status":"ok","draft":{"task":"rank","subject":"players","measure":"average points","measures":["average points"],"dimensions":[],"filters":[],"time_window":{"kind":"last_n_days","value":30},"grain":null,"order":[{"by":"average points","direction":"desc"}],"limit":null,"sort":"desc","entities":[],"operations":[],"assumptions":[]}}

Q: Show me monthly team wins since 2023-01-01
A: {"status":"ok","draft":{"task":"trend","subject":"teams","measure":"wins","measures":["wins"],"dimensions":["team"],"filters":[],"time_window":{"kind":"since_date","value":"2023-01-01"},"grain":"month","order":[],"limit":null,"sort":null,"entities":[],"operations":[],"assumptions":[]}}

Q: Find Lakers games between 2025-01-01 and 2025-02-01
A: {"status":"ok","draft":{"task":"find","subject":"games","measure":null,"measures":[],"dimensions":[],"filters":[{"field":"team","op":"=","value":"Lakers"}],"time_window":{"kind":"between_dates","value":"2025-01-01 to 2025-02-01"},"grain":null,"order":[],"limit":null,"sort":null,"entities":["Lakers"],"operations":[],"assumptions":[]}}

Q: Calculate average points by team over the last 10 games
A: {"status":"ok","draft":{"task":"aggregate","subject":"teams","measure":"average points","measures":["average points"],"dimensions":["team"],"filters":[],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[],"limit":null,"sort":null,"entities":[],"operations":[],"assumptions":[]}}

Q: Show me players by average points this season
A: {"status":"ok","draft":{"task":"rank","subject":"players","measure":"average points","measures":["average points"],"dimensions":[],"filters":[],"time_window":{"kind":"season","value":null},"grain":null,"order":[{"by":"average points","direction":"desc"}],"limit":null,"sort":"desc","entities":[],"operations":[],"assumptions":[]}}

Q: Show me players and their total points over the last 10 games
A: {"status":"ok","draft":{"task":"object","subject":"players","measure":"total points","measures":["total points"],"dimensions":[],"filters":[],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[],"limit":null,"sort":"desc","entities":[],"operations":[],"assumptions":[]}}

Q: Show me players with points, rebounds, and assists over the last 10 games
A: {"status":"ok","draft":{"task":"object","subject":"players","measure":"points","measures":["points","rebounds","assists"],"dimensions":[],"filters":[],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[],"limit":null,"sort":"desc","entities":[],"operations":[],"assumptions":[]}}

Q: Rank players by points over the last 10 games and show assists and rebounds
A: {"status":"ok","draft":{"task":"rank","subject":"players","measure":"points","measures":["points","assists","rebounds"],"dimensions":[],"filters":[],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[{"by":"points","direction":"desc"}],"limit":null,"sort":"desc","entities":[],"operations":[],"assumptions":[]}}

Q: Show me players with their scoring totals over the last 10 games
A: {"status":"ok","draft":{"task":"object","subject":"players","measure":"scoring totals","measures":["scoring totals"],"dimensions":[],"filters":[],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[],"limit":null,"sort":"desc","entities":[],"operations":[],"assumptions":["Interpreted 'scoring' as total points."]}}

Q: Show me the top 5 players and their total points for the Knicks over the last 10 games
A: {"status":"ok","draft":{"task":"object","subject":"players","measure":"total points","measures":["total points"],"dimensions":[],"filters":[{"field":"team","op":"=","value":"Knicks"}],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[{"by":"total points","direction":"desc"}],"limit":5,"sort":"desc","entities":["Knicks"],"operations":[],"assumptions":[]}}

Q: Show me players by average points with minutes over 30 over the last 10 games
A: {"status":"ok","draft":{"task":"rank","subject":"players","measure":"average points","measures":["average points"],"dimensions":[],"filters":[{"field":"minutes","op":">","value":30}],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[{"by":"average points","direction":"desc"}],"limit":null,"sort":"desc","entities":[],"operations":[],"assumptions":[]}}

Q: Show me teams by wins with win percentage above .600 in the 2025-26 regular season
A: {"status":"ok","draft":{"task":"rank","subject":"teams","measure":"wins","measures":["wins"],"dimensions":[],"filters":[{"field":"win percentage","op":">","value":0.6},{"field":"season type","op":"=","value":"regular season"}],"time_window":{"kind":"season","value":"2025-26"},"grain":null,"order":[{"by":"wins","direction":"desc"}],"limit":null,"sort":"desc","entities":[],"operations":[],"assumptions":[]}}

Q: Find Lakers games over the last 10 games
A: {"status":"ok","draft":{"task":"find","subject":"games","measure":null,"measures":[],"dimensions":[],"filters":[{"field":"team","op":"=","value":"Lakers"}],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[],"limit":null,"sort":null,"entities":["Lakers"],"operations":[],"assumptions":[]}}

Q: Find Lakers games over 120 points and show date, opponent, score, sorted newest first
A: {"status":"ok","draft":{"task":"find","subject":"games","measure":null,"measures":[],"dimensions":["date","opponent","score"],"filters":[{"field":"team","op":"=","value":"Lakers"},{"field":"points","op":">","value":120}],"time_window":{"kind":"all","value":null},"grain":null,"order":[{"by":"date","direction":"desc"}],"limit":null,"sort":null,"entities":["Lakers"],"operations":[],"assumptions":[]}}

Q: Compare Brunson and Tatum scoring over the last 10 games
A: {"status":"ok","draft":{"task":"compare","subject":"players","measure":"scoring","measures":["scoring"],"dimensions":[],"filters":[],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[],"limit":null,"sort":null,"entities":["Brunson","Tatum"],"operations":[],"assumptions":["Interpreted 'scoring' as points."]}}

Q: Compare Brunson and Tatum average points by season type over the last 10 games
A: {"status":"ok","draft":{"task":"compare","subject":"players","measure":"average points","measures":["average points"],"dimensions":["season type"],"filters":[],"time_window":{"kind":"last_n_games","value":10},"grain":null,"order":[],"limit":null,"sort":null,"entities":["Brunson","Tatum"],"operations":[],"assumptions":[]}}

Q: Compare Lakers and Warriors average points by month over the past year
A: {"status":"ok","draft":{"task":"compare","subject":"teams","measure":"average points","measures":["average points"],"dimensions":[],"filters":[],"time_window":{"kind":"past_year","value":null},"grain":"month","order":[],"limit":null,"sort":null,"entities":["Lakers","Warriors"],"operations":[],"assumptions":[]}}
""".strip()


def _call_gemini(prompt: str) -> str:
    try:
        return call_gemini(prompt)
    except LlmTransportError as exc:
        raise SemanticInterpreterError(str(exc)) from exc


def _parse_interpreter_response(
    raw_text: str,
) -> Union[InterpreterSupported, InterpreterUnsupported]:
    # Turn Gemini's JSON text into either a supported draft or an unsupported reason.
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
    # Build the prompt, attach the user's question, call Gemini, and validate
    # the basic draft shape before handing it back to main.py.
    prompt = (
        f"{_semantic_draft_prompt_preamble()}\n\n"
        f"User question:\n{question}\n\n"
        "Return the JSON response now."
    )
    raw_text = _call_gemini(prompt)
    interpreted = _parse_interpreter_response(raw_text)
    if isinstance(interpreted, InterpreterUnsupported):
        raise SemanticInterpreterError(interpreted.reason)
    # Return a plain Python dict so main.py can JSON-encode it for Haskell.
    return _normalize_supported_draft(interpreted.draft.model_dump())


def _normalize_supported_draft(draft: dict[str, Any]) -> dict[str, Any]:
    # Keep this as a schema-shape repair, not ontology reasoning. Haskell still
    # decides whether the normalized predicate can be grounded.
    normalized = dict(draft)
    predicate = _normalize_predicate_shape(normalized.get("predicate"))
    result_predicate = _normalize_predicate_shape(normalized.get("result_predicate"))
    if result_predicate is None and _looks_like_result_predicate(predicate):
        result_predicate = predicate
        predicate = None
    normalized["predicate"] = predicate
    normalized["result_predicate"] = result_predicate
    normalized = normalize_flat_filter_predicates(normalized)
    return normalized


def _normalize_predicate_shape(predicate: Any) -> Optional[dict[str, Any]]:
    if not isinstance(predicate, dict):
        return None
    normalized = dict(predicate)
    kind = normalized.get("kind")
    if kind in {"and", "or"}:
        raw_children = normalized.get("predicates")
        if not isinstance(raw_children, list):
            raw_children = [
                child
                for child in [normalized.get("left"), normalized.get("right")]
                if isinstance(child, dict)
            ]
        normalized["predicates"] = [
            child
            for child in (_normalize_predicate_shape(child) for child in raw_children)
            if child is not None
        ]
        normalized.pop("left", None)
        normalized.pop("right", None)
    elif kind == "not":
        normalized["predicate"] = _normalize_predicate_shape(normalized.get("predicate"))
    return normalized


def _looks_like_result_predicate(predicate: Optional[dict[str, Any]]) -> bool:
    leaves = _predicate_leaves(predicate)
    return bool(leaves) and all(_looks_like_result_field(str(leaf.get("field", ""))) for leaf in leaves)


def _predicate_leaves(predicate: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(predicate, dict):
        return []
    kind = predicate.get("kind")
    if kind == "leaf":
        return [predicate]
    if kind in {"and", "or"}:
        leaves: list[dict[str, Any]] = []
        for child in predicate.get("predicates", []):
            leaves.extend(_predicate_leaves(child))
        return leaves
    if kind == "not":
        return _predicate_leaves(predicate.get("predicate"))
    return []


def _looks_like_result_field(field: str) -> bool:
    normalized = field.lower().replace("_", " ")
    result_hints = ("average", "avg", "total", "sum", "per game", "pergame", "ppg", "mpg")
    return any(hint in normalized for hint in result_hints)
