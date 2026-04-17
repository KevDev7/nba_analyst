from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any


POSITION_MAP = {
    "Point Guard": "PG",
    "Shooting Guard": "SG",
    "Small Forward": "SF",
    "Power Forward": "PF",
    "Center": "C",
    "Guard": "G",
    "Forward": "F",
    "Guard/Forward": "G-F",
    "Forward/Center": "F-C",
    "Center/Forward": "C-F",
}

EXACT_NAME_MATCH_BLOCKLIST = {
    "dillon jones",
    "dmytro skapintsev",
    "jared harper",
    "jaylin williams",
    "liu yancheng",
    "nate williams",
}

NBA_TO_BBR_OWNER_OVERRIDES = {
    1631119: "willija07",
}

MATCH_METHOD_PRIORITY = {
    "manual_owner_override": 5,
    "exact_full_name_with_suffix_unique": 4,
    "unique_top_score_with_draft_match": 3,
    "unique_top_score_supported_by_multiple_secondary_checks": 2,
    "shared_name_strongest_row_winner": 2,
    "unique_name_key": 1,
    "exact_full_name_unique": 0,
}


def null_if_empty(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def to_int_or_none(value: Any) -> int | None:
    value = null_if_empty(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_date_or_none(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = null_if_empty(value)
    if value is None:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_text(value: str | None) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    ascii_text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = ascii_text.replace("&", " and ")
    ascii_text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", ascii_text)
    ascii_text = ascii_text.replace(".", "")
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    ascii_text = re.sub(r"\s+", " ", ascii_text).strip()
    return ascii_text or None


def normalize_text_preserve_suffix(value: str | None) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    ascii_text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = ascii_text.replace("&", " and ")
    ascii_text = ascii_text.replace(".", "")
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    ascii_text = re.sub(r"\s+", " ", ascii_text).strip()
    return ascii_text or None


def normalize_school(value: str | None) -> str | None:
    value = normalize_text(value)
    if value is None or value == "no college":
        return None
    replacements = {
        "louisiana state": "lsu",
        "unc": "north carolina",
        "st ": "saint ",
        "wisc ": "wisconsin ",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value.strip() or None


def normalize_bbr_position(value: str | None) -> set[str]:
    value = null_if_empty(value)
    if value is None:
        return set()
    tokens: set[str] = set()
    for segment in re.split(r",| and ", value):
        normalized = null_if_empty(segment.strip())
        if normalized is None:
            continue
        mapped = POSITION_MAP.get(normalized)
        if mapped is not None:
            tokens.update(mapped.split("-"))
        else:
            compact = normalize_text(normalized)
            if compact is not None:
                tokens.add(compact.upper())
    return tokens


def normalize_nba_position(row: dict[str, Any]) -> tuple[str | None, set[str]]:
    tokens: set[str] = set()
    if to_int_or_none(row.get("guard")) == 1:
        tokens.add("G")
    if to_int_or_none(row.get("forward")) == 1:
        tokens.add("F")
    if to_int_or_none(row.get("center")) == 1:
        tokens.add("C")
    if not tokens:
        return None, set()
    ordered = [token for token in ["G", "F", "C"] if token in tokens]
    return "-".join(ordered), tokens


def build_nba_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for row in rows:
        name = " ".join(part for part in [null_if_empty(row.get("firstName")), null_if_empty(row.get("lastName"))] if part)
        name_key = normalize_text(name)
        if name_key is None:
            continue
        primary_position, position_tokens = normalize_nba_position(row)
        projected.append(
            {
                "nba_person_id": to_int_or_none(row.get("personId")),
                "nba_player_name": name,
                "name_key": name_key,
                "exact_name_key": normalize_text_preserve_suffix(name),
                "height_inches": to_int_or_none(row.get("heightInches")),
                "weight_lbs": to_int_or_none(row.get("bodyWeightLbs")),
                "draft_year": to_int_or_none(row.get("draftYear")),
                "draft_round": to_int_or_none(row.get("draftRound")),
                "draft_number": to_int_or_none(row.get("draftNumber")),
                "school": null_if_empty(row.get("school")),
                "school_key": normalize_school(row.get("school")),
                "primary_position": primary_position,
                "position_tokens": position_tokens,
            }
        )
    return projected


def build_bbr_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for row in rows:
        name = null_if_empty(row.get("page_player_name"))
        name_key = normalize_text(name)
        if name_key is None:
            continue
        school_value = null_if_empty(row.get("college_raw")) or null_if_empty(row.get("colleges_raw"))
        projected.append(
            {
                "basketball_reference_player_id": null_if_empty(row.get("basketball_reference_player_id")),
                "bbr_player_name": name,
                "name_key": name_key,
                "exact_name_key": normalize_text_preserve_suffix(name),
                "weight_lbs": to_int_or_none(row.get("weight_lbs")),
                "draft_year": to_int_or_none(row.get("draft_year")),
                "draft_round": to_int_or_none(row.get("draft_round")),
                "draft_pick_overall": to_int_or_none(row.get("draft_pick_overall")),
                "school_value": school_value,
                "school_key": normalize_school(school_value),
                "position_raw": null_if_empty(row.get("position_raw")),
                "position_tokens": normalize_bbr_position(row.get("position_raw")),
                "current_team_raw": null_if_empty(row.get("current_team_raw")),
                "nba_debut_date": to_date_or_none(row.get("nba_debut_date")),
                "experience_years": to_int_or_none(row.get("experience_years")) or to_int_or_none(row.get("career_length_years")),
            }
        )
    return projected


def score_candidate(nba_row: dict[str, Any], bbr_row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    evidence = {
        "draft_match_flag": 0,
        "weight_match_flag": 0,
        "school_match_flag": 0,
        "position_match_flag": 0,
        "era_sanity_flag": 1,
    }
    score = 0
    nba_draft = (nba_row.get("draft_year"), nba_row.get("draft_round"), nba_row.get("draft_number"))
    bbr_draft = (bbr_row.get("draft_year"), bbr_row.get("draft_round"), bbr_row.get("draft_pick_overall"))
    if all(value is not None for value in nba_draft) and all(value is not None for value in bbr_draft):
        if nba_draft == bbr_draft:
            evidence["draft_match_flag"] = 1
            score += 100
        else:
            score -= 100
    nba_weight = nba_row.get("weight_lbs")
    bbr_weight = bbr_row.get("weight_lbs")
    if nba_weight is not None and bbr_weight is not None:
        if abs(nba_weight - bbr_weight) <= 1:
            evidence["weight_match_flag"] = 1
            score += 10
        elif abs(nba_weight - bbr_weight) >= 15:
            score -= 10
    nba_school = nba_row.get("school_key")
    bbr_school = bbr_row.get("school_key")
    if nba_school is not None and bbr_school is not None:
        if nba_school == bbr_school:
            evidence["school_match_flag"] = 1
            score += 8
        elif nba_school in bbr_school or bbr_school in nba_school:
            evidence["school_match_flag"] = 1
            score += 5
    nba_positions = nba_row.get("position_tokens") or set()
    bbr_positions = bbr_row.get("position_tokens") or set()
    if nba_positions and bbr_positions and nba_positions.intersection(bbr_positions):
        evidence["position_match_flag"] = 1
        score += 3
    return score, evidence


def choose_candidates(nba_row: dict[str, Any], bbr_candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    accepted: list[dict[str, Any]] = []
    reasons: list[str] = []
    name_key = nba_row.get("name_key")
    exact_name_key = nba_row.get("exact_name_key")
    for candidate in bbr_candidates:
        score, evidence = score_candidate(nba_row, candidate)
        candidate_with_score = dict(candidate)
        candidate_with_score.update(evidence)
        candidate_with_score["match_score"] = score
        accepted.append(candidate_with_score)
    if not accepted:
        return [], reasons
    exact_matches = [
        candidate
        for candidate in accepted
        if candidate.get("exact_name_key") is not None and candidate.get("exact_name_key") == exact_name_key
    ]
    if exact_name_key is not None and exact_name_key != name_key and len(exact_matches) == 1:
        reasons.append("exact_full_name_with_suffix_unique")
        return exact_matches, reasons
    if len(accepted) == 1 and name_key not in EXACT_NAME_MATCH_BLOCKLIST:
        reasons.append("exact_full_name_unique")
        return accepted, reasons
    accepted.sort(
        key=lambda row: (
            row["match_score"],
            row["draft_match_flag"],
            row["school_match_flag"],
            row["weight_match_flag"],
            row["position_match_flag"],
            row["basketball_reference_player_id"],
        ),
        reverse=True,
    )
    top_score = accepted[0]["match_score"]
    top_candidates = [candidate for candidate in accepted if candidate["match_score"] == top_score]
    if len(accepted) == 1 and top_score >= 0 and name_key not in EXACT_NAME_MATCH_BLOCKLIST:
        reasons.append("unique_name_key")
        return top_candidates, reasons
    if len(top_candidates) == 1 and top_score >= 100:
        reasons.append("unique_top_score_with_draft_match")
        return top_candidates, reasons
    if len(top_candidates) == 1 and top_score >= 18:
        reasons.append("unique_top_score_supported_by_multiple_secondary_checks")
        return top_candidates, reasons
    return top_candidates, reasons


def summarize_candidate(candidate: dict[str, Any]) -> str:
    return (
        f"score={candidate['match_score']};"
        f"draft={candidate['draft_match_flag']};"
        f"weight={candidate['weight_match_flag']};"
        f"school={candidate['school_match_flag']};"
        f"position={candidate['position_match_flag']};"
        f"era={candidate['era_sanity_flag']}"
    )


def build_ambiguous_row(nba_row: dict[str, Any], top_candidates: list[dict[str, Any]], *, reason_prefix: str | None = None) -> dict[str, Any]:
    serialized_reasons = "|".join(summarize_candidate(candidate) for candidate in top_candidates)
    candidate_reasons = serialized_reasons if reason_prefix is None else f"{reason_prefix}|{serialized_reasons}"
    return {
        "nba_person_id": nba_row["nba_person_id"],
        "nba_player_name": nba_row["nba_player_name"],
        "name_key": nba_row["name_key"],
        "candidate_count": len(top_candidates),
        "candidate_player_ids": "|".join(candidate["basketball_reference_player_id"] for candidate in top_candidates),
        "candidate_player_names": "|".join(candidate["bbr_player_name"] for candidate in top_candidates),
        "candidate_reasons": candidate_reasons,
    }


def nba_metadata_completeness(nba_row: dict[str, Any]) -> int:
    populated_fields = [
        nba_row.get("height_inches"),
        nba_row.get("weight_lbs"),
        nba_row.get("draft_year"),
        nba_row.get("draft_round"),
        nba_row.get("draft_number"),
        nba_row.get("school_key"),
        nba_row.get("primary_position"),
    ]
    return sum(1 for value in populated_fields if value is not None)


def build_unresolved_entry(nba_row: dict[str, Any], top_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        top_candidates,
        key=lambda row: (
            row["match_score"],
            row["draft_match_flag"],
            row["school_match_flag"],
            row["weight_match_flag"],
            row["position_match_flag"],
            row["basketball_reference_player_id"],
        ),
        reverse=True,
    )
    return {
        "nba_row": nba_row,
        "top_candidates": ordered,
        "top_score": ordered[0]["match_score"] if ordered else None,
        "second_best_score": ordered[1]["match_score"] if len(ordered) > 1 else None,
        "metadata_completeness": nba_metadata_completeness(nba_row),
        "unique_top_candidate": len(ordered) == 1,
    }


def build_accepted_proposal(nba_row: dict[str, Any], candidate: dict[str, Any], accept_reason: str) -> dict[str, Any]:
    return {
        "nba_row": nba_row,
        "candidate": candidate,
        "accept_reason": accept_reason,
        "match_confidence": (
            0.85
            if accept_reason == "exact_full_name_with_suffix_unique"
            else 0.8
            if accept_reason == "exact_full_name_unique"
            else 1.0
            if candidate["draft_match_flag"] == 1
            else 0.85
        ),
    }


def build_manual_override_proposal(nba_row: dict[str, Any], bbr_candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    override_bbr_id = NBA_TO_BBR_OWNER_OVERRIDES.get(nba_row["nba_person_id"])
    if override_bbr_id is None:
        return None
    matching_candidate = next((candidate for candidate in bbr_candidates if candidate["basketball_reference_player_id"] == override_bbr_id), None)
    if matching_candidate is None:
        return None
    score, evidence = score_candidate(nba_row, matching_candidate)
    candidate_with_score = dict(matching_candidate)
    candidate_with_score.update(evidence)
    candidate_with_score["match_score"] = score
    return {
        "nba_row": nba_row,
        "candidate": candidate_with_score,
        "accept_reason": "manual_owner_override",
        "match_confidence": 1.0,
    }
