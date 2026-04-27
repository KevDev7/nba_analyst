from __future__ import annotations

import re
from copy import deepcopy
from functools import lru_cache
from typing import Any, Optional

import duckdb

from scripts.load_gold_snapshot import load_database


DEFAULT_SEASON_YEAR = "2025-26"
DEFAULT_SEASON_TYPE = "regular_season"
ALL_AVAILABLE_DATA_KIND = "all"


_FULL_SEASON_RE = re.compile(r"\b(20\d{2})\s*[-–—]\s*(\d{2})\b")
_SHORT_SEASON_RE = re.compile(r"(?<!\d)(\d{2})\s*[-–—]\s*(\d{2})(?!\d)")


def _normalized(value: object) -> str:
    return "".join(character.lower() for character in str(value).strip() if character.isalnum())


@lru_cache(maxsize=1)
def _snapshot_season_range() -> Optional[str]:
    database_path = load_database()
    conn = duckdb.connect(str(database_path), read_only=True)
    try:
        start_season, end_season = conn.execute(
            """
            SELECT MIN(season_year), MAX(season_year)
            FROM game
            """
        ).fetchone()
    finally:
        conn.close()

    if start_season and end_season:
        return f"{start_season} through {end_season}"
    return None


def _explicit_season_year(question: str) -> Optional[str]:
    return _season_year_from_text(question)


def _season_year_from_text(text: object) -> Optional[str]:
    raw_text = str(text)
    full_match = _FULL_SEASON_RE.search(raw_text)
    if full_match:
        return f"{full_match.group(1)}-{full_match.group(2)}"

    short_match = _SHORT_SEASON_RE.search(raw_text)
    if short_match:
        return f"20{short_match.group(1)}-{short_match.group(2)}"

    return None


def _explicit_season_type(question: str) -> Optional[str]:
    question_key = _normalized(question)
    if "regularseason" in question_key:
        return "regular_season"
    if "playoffs" in question_key or "playoff" in question_key or "postseason" in question_key:
        return "playoffs"
    return None


def _is_find_draft(draft: dict[str, Any]) -> bool:
    return _normalized(draft.get("task", "")) == "find"


def _is_rank_draft(draft: dict[str, Any]) -> bool:
    return _normalized(draft.get("task", "")) == "rank"


def _has_entity_row_language(question: str) -> bool:
    question_key = _normalized(question)
    return "andtheir" in question_key or "withtheir" in question_key


def _mentions_scoring_totals(question: str, draft: dict[str, Any]) -> bool:
    question_key = _normalized(question)
    draft_measure_key = _normalized(draft.get("measure", ""))
    return (
        "scoring" in question_key
        and ("total" in question_key or "totals" in question_key)
        and "scoring" in draft_measure_key
    )


def _reconcile_family_shape(question: str, draft: dict[str, Any]) -> dict[str, Any]:
    # Object-row wording owns entity rows even when the user also asks for a
    # limit/order, like "top 5 players and their total points".
    if _is_rank_draft(draft) and _has_entity_row_language(question):
        draft["task"] = "object"
    if _mentions_scoring_totals(question, draft):
        _append_assumption(draft, "Interpreted 'scoring' as total points.")
    return draft


def _mentions_all_available_data(question: str) -> bool:
    question_key = _normalized(question)
    return any(
        phrase in question_key
        for phrase in [
            "allgames",
            "alltime",
            "allavailabledata",
            "availabledata",
            "entiredataset",
            "wholedata",
        ]
    )


def _needs_find_all_window(question: str, draft: dict[str, Any]) -> bool:
    time_window = draft.get("time_window")
    if time_window is None:
        return True
    if _mentions_all_available_data(question):
        return True
    if not isinstance(time_window, dict):
        return False
    window_kind = _normalized(time_window.get("kind", ""))
    if window_kind in {"", "none", "unspecified", "null"}:
        return True
    if window_kind == "season" and time_window.get("value") is None and _mentions_all_available_data(question):
        return True
    return False


def _is_exact_season_scoped(draft: dict[str, Any], question: str) -> bool:
    # Only exact season windows get defaulted to 2025-26. A trend "by season"
    # should remain cross-season rather than being narrowed to one season.
    time_window = draft.get("time_window") or {}
    question_key = _normalized(question)
    if _is_find_draft(draft) and _normalized(time_window.get("kind", "")) == ALL_AVAILABLE_DATA_KIND:
        return False
    if "allseasons" in question_key or "acrossseasons" in question_key or "byseason" in question_key:
        return False

    has_exact_season_reference = (
        _explicit_season_year(question) is not None
        or _explicit_season_type(question) is not None
        or "thisseason" in question_key
        or "currentseason" in question_key
    )
    if _normalized(draft.get("grain", "")) == "season" and not has_exact_season_reference:
        return False

    if _normalized(time_window.get("kind", "")) in {"season", "thisseason", "currentseason"}:
        return True

    has_season_language = "season" in question_key or "playoff" in question_key or "postseason" in question_key
    has_conflicting_window = _normalized(time_window.get("kind", "")) in {
        "lastngames",
        "pastyear",
    }
    return has_season_language and not has_conflicting_window


def _season_type_from_value(value: object) -> Optional[str]:
    value_key = _normalized(value)
    if "regularseason" in value_key or value_key == "regular":
        return "regular_season"
    if "playoffs" in value_key or "playoff" in value_key or "postseason" in value_key:
        return "playoffs"
    return None


def _is_season_type_filter(filter_value: dict[str, Any]) -> bool:
    field_key = _normalized(filter_value.get("field", ""))
    return "seasontype" in field_key or _season_type_from_value(filter_value.get("value")) is not None


def _season_type_filter(season_type: str) -> dict[str, Any]:
    return {
        "field": "season type",
        "op": "=",
        "value": "regular season" if season_type == "regular_season" else season_type,
    }


def _season_year_filter(season_year: str) -> dict[str, Any]:
    return {"field": "season", "op": "=", "value": season_year}


def _season_year_from_filter(filter_value: dict[str, Any]) -> Optional[str]:
    field_key = _normalized(filter_value.get("field", ""))
    if field_key not in {"season", "seasonyear", "seasons", "year"}:
        return None
    return _season_year_from_text(filter_value.get("value", ""))


def _season_year_from_filters(draft: dict[str, Any]) -> Optional[str]:
    for filter_value in draft.get("filters", []):
        if isinstance(filter_value, dict):
            season_year = _season_year_from_filter(filter_value)
            if season_year is not None:
                return season_year
    return None


def _append_assumption(draft: dict[str, Any], assumption: str) -> None:
    assumptions = draft.setdefault("assumptions", [])
    if assumption not in assumptions:
        assumptions.append(assumption)


def _remove_contradictory_all_data_assumptions(draft: dict[str, Any]) -> None:
    draft["assumptions"] = [
        assumption
        for assumption in draft.get("assumptions", [])
        if "current season" not in str(assumption).lower()
    ]


def _all_available_data_assumption() -> str:
    season_range = _snapshot_season_range()
    if season_range:
        return f"Used all available data in the local snapshot: {season_range}."
    return "Used all available data in the local snapshot."


def _apply_find_time_window_assumptions(question: str, draft: dict[str, Any]) -> dict[str, Any]:
    if not _is_find_draft(draft) or not _needs_find_all_window(question, draft):
        return draft

    draft["time_window"] = {"kind": ALL_AVAILABLE_DATA_KIND, "value": None}
    _remove_contradictory_all_data_assumptions(draft)
    _append_assumption(draft, _all_available_data_assumption())
    return draft


def _upsert_season_type_filter(draft: dict[str, Any], season_type: str) -> None:
    filters = draft.setdefault("filters", [])
    replacement = _season_type_filter(season_type)
    for index, filter_value in enumerate(filters):
        if isinstance(filter_value, dict) and _is_season_type_filter(filter_value):
            filters[index] = replacement
            return
    filters.append(replacement)


def _upsert_season_year_filter(draft: dict[str, Any], season_year: str) -> None:
    filters = draft.setdefault("filters", [])
    replacement = _season_year_filter(season_year)
    for index, filter_value in enumerate(filters):
        if isinstance(filter_value, dict) and _season_year_from_filter(filter_value) is not None:
            filters[index] = replacement
            return
    filters.append(replacement)


def _is_recent_window(draft: dict[str, Any]) -> bool:
    time_window = draft.get("time_window") or {}
    return _normalized(time_window.get("kind", "")) == "lastngames"


def _apply_recent_season_constraints(question: str, draft: dict[str, Any]) -> dict[str, Any]:
    if not _is_recent_window(draft):
        return draft

    explicit_year = _explicit_season_year(question) or _season_year_from_filters(draft)
    if explicit_year is None:
        return draft

    explicit_type = _explicit_season_type(question)
    season_type = explicit_type or DEFAULT_SEASON_TYPE
    _upsert_season_year_filter(draft, explicit_year)
    _upsert_season_type_filter(draft, season_type)
    if explicit_type is None:
        _append_assumption(draft, "Assumed season type is regular season.")
    return draft


def apply_semantic_assumptions(question: str, draft: dict[str, Any]) -> dict[str, Any]:
    # This is the intentionally small policy layer between "LLM understood the
    # question" and "Haskell validates against the ontology."
    enriched = deepcopy(draft)
    enriched = _reconcile_family_shape(question, enriched)
    enriched = _apply_find_time_window_assumptions(question, enriched)
    enriched = _apply_recent_season_constraints(question, enriched)
    if not _is_exact_season_scoped(enriched, question):
        return enriched

    explicit_year = _explicit_season_year(question)
    explicit_type = _explicit_season_type(question)

    season_year = explicit_year or DEFAULT_SEASON_YEAR
    season_type = explicit_type or DEFAULT_SEASON_TYPE

    time_window = dict(enriched.get("time_window") or {})
    time_window["kind"] = "season"
    time_window["value"] = season_year
    enriched["time_window"] = time_window
    _upsert_season_type_filter(enriched, season_type)

    if explicit_year is None:
        _append_assumption(enriched, f"Assumed season year is {DEFAULT_SEASON_YEAR}.")
    if explicit_type is None:
        _append_assumption(enriched, "Assumed season type is regular season.")

    return enriched
