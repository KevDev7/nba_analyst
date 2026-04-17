from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from .identity import null_if_empty, to_date_or_none, to_int_or_none
from .types import BbrGoldProfile


def to_float_or_none(value: Any) -> float | None:
    value = null_if_empty(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_str_or_none(value: Any) -> str | None:
    value = null_if_empty(value)
    return None if value is None else str(value)


def build_bbr_profile_map(bbr_profile_rows: list[dict[str, Any]]) -> dict[str, BbrGoldProfile]:
    best_by_bbr_id: dict[str, BbrGoldProfile] = {}
    for row in bbr_profile_rows:
        bbr_id = to_str_or_none(row.get("basketball_reference_player_id"))
        if bbr_id is None:
            continue
        best_by_bbr_id[bbr_id] = BbrGoldProfile(
            bbr_profile_url=to_str_or_none(row.get("player_profile_url")),
            bbr_formal_name=to_str_or_none(row.get("formal_name")),
            bbr_pronunciation=to_str_or_none(row.get("pronunciation")),
            bbr_former_name_note=to_str_or_none(row.get("former_name_note")),
            bbr_nicknames_raw=to_str_or_none(row.get("nicknames_raw")),
            bbr_instagram_handle=to_str_or_none(row.get("instagram_handle")),
            bbr_position_raw=to_str_or_none(row.get("position_raw")),
            bbr_shoots=to_str_or_none(row.get("shoots")),
            bbr_height_raw=to_str_or_none(row.get("height_raw")),
            bbr_height_cm=to_int_or_none(row.get("height_cm")),
            bbr_weight_kg=to_int_or_none(row.get("weight_kg")),
            bbr_current_team_raw=to_str_or_none(row.get("current_team_raw")),
            bbr_birth_place_raw=to_str_or_none(row.get("birth_place_raw")),
            bbr_birth_country_code=to_str_or_none(row.get("birth_country_code")),
            bbr_death_date=to_date_or_none(row.get("death_date")),
            bbr_college_raw=to_str_or_none(row.get("college_raw")),
            bbr_colleges_raw=to_str_or_none(row.get("colleges_raw")),
            bbr_high_school_raw=to_str_or_none(row.get("high_school_raw")),
            bbr_high_schools_raw=to_str_or_none(row.get("high_schools_raw")),
            bbr_recruiting_rank_raw=to_str_or_none(row.get("recruiting_rank_raw")),
            bbr_recruiting_rank_year=to_int_or_none(row.get("recruiting_rank_year")),
            bbr_recruiting_rank_ordinal=to_int_or_none(row.get("recruiting_rank_ordinal")),
            bbr_relatives_raw=to_str_or_none(row.get("relatives_raw")),
            bbr_draft_raw=to_str_or_none(row.get("draft_raw")),
            bbr_draft_team_raw=to_str_or_none(row.get("draft_team_raw")),
            bbr_draft_pick_in_round=to_int_or_none(row.get("draft_pick_in_round")),
            bbr_draft_league=to_str_or_none(row.get("draft_league")),
            bbr_draft_selection_note=to_str_or_none(row.get("draft_selection_note")),
            bbr_nba_debut_date=to_date_or_none(row.get("nba_debut_date")),
            bbr_aba_debut_date=to_date_or_none(row.get("aba_debut_date")),
            bbr_experience_years=to_int_or_none(row.get("experience_years")),
            bbr_career_length_years=to_int_or_none(row.get("career_length_years")),
            bbr_hall_of_fame_flag=to_int_or_none(row.get("hall_of_fame_flag")),
            bbr_hall_of_fame_role=to_str_or_none(row.get("hall_of_fame_role")),
            bbr_hall_of_fame_year=to_int_or_none(row.get("hall_of_fame_year")),
            bbr_hall_of_fame_raw=to_str_or_none(row.get("hall_of_fame_raw")),
            bbr_headshot_url=to_str_or_none(row.get("headshot_url")),
        )
    return best_by_bbr_id


def build_current_gold_profiles(
    current_person_ids: set[int],
    accepted_bridge_rows: list[dict[str, Any]],
    profile_rows: list[dict[str, Any]],
) -> dict[int, BbrGoldProfile]:
    profile_by_bbr_id = build_bbr_profile_map(profile_rows)
    best_by_person: dict[int, BbrGoldProfile] = {}
    for row in accepted_bridge_rows:
        person_id = to_int_or_none(row.get("nba_person_id"))
        bbr_id = to_str_or_none(row.get("basketball_reference_player_id"))
        if person_id is None or person_id not in current_person_ids or bbr_id is None:
            continue
        profile_payload = asdict(profile_by_bbr_id.get(bbr_id, BbrGoldProfile()))
        profile_payload.pop("basketball_reference_player_id", None)
        profile_payload.pop("bbr_match_method", None)
        profile_payload.pop("bbr_match_confidence", None)
        candidate = BbrGoldProfile(
            basketball_reference_player_id=bbr_id,
            bbr_match_method=to_str_or_none(row.get("match_method")),
            bbr_match_confidence=to_float_or_none(row.get("match_confidence")),
            **profile_payload,
        )
        current = best_by_person.get(person_id)
        current_confidence = current.bbr_match_confidence if current else None
        if current is None or ((candidate.bbr_match_confidence or float("-inf")) > (current_confidence or float("-inf"))):
            best_by_person[person_id] = candidate
    return best_by_person
