from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pyarrow as pa

try:
    from ..gold_transform_helpers import (
        normalize_game_id,
        parse_date_or_none,
        parse_timestamp_utc,
        to_float_or_none,
        to_int_or_none,
        to_positive_int_or_none,
        to_str_or_none,
    )
    from ..scd2_utils import assign_surrogate_keys, build_scd2_versions
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        normalize_game_id,
        parse_date_or_none,
        parse_timestamp_utc,
        to_float_or_none,
        to_int_or_none,
        to_positive_int_or_none,
        to_str_or_none,
    )
    from scd2_utils import assign_surrogate_keys, build_scd2_versions  # type: ignore[no-redef]


DIM_PLAYER_RECORD_SOURCE = (
    "silver/boxscore_player_game.parquet|silver/boxscore_game.parquet|"
    "silver/players.parquet|gold/dim_team/dim_team.parquet"
)
TRACKED_COLS = [
    "player_name",
    "first_name",
    "family_name",
    "display_name",
    "primary_position",
    "latest_team_id",
    "latest_nba_team_id",
]


def build_game_time_map(game_table: pa.Table) -> dict[str, datetime | None]:
    game_time_by_id: dict[str, datetime | None] = {}
    for row in game_table.to_pylist():
        game_id = normalize_game_id(row.get("gameId"))
        if game_id is None:
            continue
        candidate = parse_timestamp_utc(row.get("gameTimeUTC"))
        current = game_time_by_id.get(game_id)
        if current is None or (candidate is not None and current is not None and candidate > current):
            game_time_by_id[game_id] = candidate
        elif current is None:
            game_time_by_id[game_id] = candidate
    return game_time_by_id


def build_current_nba_team_ids(dim_team_table: pa.Table) -> set[int]:
    team_ids: set[int] = set()
    for row in dim_team_table.to_pylist():
        team_id = to_positive_int_or_none(row.get("team_id"))
        if team_id is not None and to_int_or_none(row.get("is_current")) == 1:
            team_ids.add(team_id)
    return team_ids


def build_player_bio_map(player_bio_table: pa.Table) -> dict[int, dict[str, Any]]:
    def quality_score(row: dict[str, Any]) -> int:
        return sum(
            1
            for key in [
                "first_name",
                "family_name",
                "birth_date",
                "school",
                "country",
                "height_inches",
                "weight_lbs",
                "draft_year",
                "draft_round",
                "draft_number",
            ]
            if row.get(key) is not None
        )

    best_by_person: dict[int, dict[str, Any]] = {}
    for row in player_bio_table.to_pylist():
        person_id = to_positive_int_or_none(row.get("personId"))
        if person_id is None:
            continue
        candidate = {
            "first_name": to_str_or_none(row.get("firstName")),
            "family_name": to_str_or_none(row.get("lastName")),
            "birth_date": parse_date_or_none(row.get("birthDate")),
            "school": to_str_or_none(row.get("school")),
            "country": to_str_or_none(row.get("country")),
            "height_inches": to_int_or_none(row.get("heightInches")),
            "weight_lbs": to_int_or_none(row.get("bodyWeightLbs")),
            "draft_year": to_int_or_none(row.get("draftYear")),
            "draft_round": to_int_or_none(row.get("draftRound")),
            "draft_number": to_int_or_none(row.get("draftNumber")),
        }
        current = best_by_person.get(person_id)
        if current is None or quality_score(candidate) > quality_score(current):
            best_by_person[person_id] = candidate
    return best_by_person


def build_bbr_birth_date_map(
    bridge_table: pa.Table | None,
    bbr_profile_table: pa.Table | None,
) -> dict[int, Any]:
    if bridge_table is None or bbr_profile_table is None:
        return {}

    birth_date_by_bbr_id: dict[str, Any] = {}
    for row in bbr_profile_table.to_pylist():
        bbr_id = to_str_or_none(row.get("basketball_reference_player_id"))
        birth_date = parse_date_or_none(row.get("birth_date"))
        if bbr_id is None or birth_date is None:
            continue
        birth_date_by_bbr_id[bbr_id] = birth_date

    best_by_person: dict[int, tuple[float, Any]] = {}
    for row in bridge_table.to_pylist():
        person_id = to_positive_int_or_none(row.get("nba_person_id"))
        bbr_id = to_str_or_none(row.get("basketball_reference_player_id"))
        if person_id is None or bbr_id is None:
            continue
        birth_date = birth_date_by_bbr_id.get(bbr_id)
        if birth_date is None:
            continue
        confidence = to_float_or_none(row.get("match_confidence"))
        current = best_by_person.get(person_id)
        if current is None or (confidence or float("-inf")) > current[0]:
            best_by_person[person_id] = (confidence or float("-inf"), birth_date)

    return {person_id: birth_date for person_id, (_, birth_date) in best_by_person.items()}


def merge_bbr_birth_date_fallbacks(
    player_bio_by_person: dict[int, dict[str, Any]],
    bbr_birth_date_by_person: dict[int, Any],
) -> dict[int, dict[str, Any]]:
    if not bbr_birth_date_by_person:
        return player_bio_by_person

    merged = {person_id: dict(attrs) for person_id, attrs in player_bio_by_person.items()}
    for person_id, birth_date in bbr_birth_date_by_person.items():
        attrs = merged.setdefault(
            person_id,
            {
                "first_name": None,
                "family_name": None,
                "birth_date": None,
                "school": None,
                "country": None,
                "height_inches": None,
                "weight_lbs": None,
                "draft_year": None,
                "draft_round": None,
                "draft_number": None,
            },
        )
        if attrs.get("birth_date") is None:
            attrs["birth_date"] = birth_date
    return merged


def build_display_name(first_name: str | None, family_name: str | None, player_name: str | None) -> str | None:
    full_name = " ".join(part for part in [first_name, family_name] if part)
    return full_name or player_name


def build_player_events(
    player_table: pa.Table,
    game_time_by_id: dict[str, datetime | None],
    player_bio_by_person: dict[int, dict[str, Any]],
    nba_team_ids: set[int],
) -> list[dict[str, Any]]:
    events_by_person_game: dict[tuple[int, str], dict[str, Any]] = {}

    def quality_score(row: dict[str, Any]) -> int:
        return sum(
            1
            for key in [
                "player_name",
                "first_name",
                "family_name",
                "display_name",
                "primary_position",
                "latest_team_id",
                "latest_nba_team_id",
                "game_time_utc",
            ]
            if row.get(key) is not None
        )

    for row in player_table.to_pylist():
        person_id = to_positive_int_or_none(row.get("personId"))
        game_id = normalize_game_id(row.get("gameId"))
        if person_id is None or game_id is None:
            continue
        bio = player_bio_by_person.get(person_id, {})
        team_id = to_positive_int_or_none(row.get("teamId"))
        first_name = to_str_or_none(row.get("firstName")) or bio.get("first_name")
        family_name = to_str_or_none(row.get("familyName")) or bio.get("family_name")
        candidate = {
            "person_id": person_id,
            "game_id": game_id,
            "game_time_utc": game_time_by_id.get(game_id),
            "game_date": game_time_by_id.get(game_id).date() if game_time_by_id.get(game_id) is not None else None,
            "player_name": to_str_or_none(row.get("name")),
            "first_name": first_name,
            "family_name": family_name,
            "display_name": build_display_name(first_name, family_name, to_str_or_none(row.get("name"))),
            "primary_position": to_str_or_none(row.get("position")),
            "latest_team_id": team_id,
            "latest_nba_team_id": team_id if team_id in nba_team_ids else None,
        }
        key = (person_id, game_id)
        current = events_by_person_game.get(key)
        if current is None or quality_score(candidate) > quality_score(current):
            events_by_person_game[key] = candidate

    return list(events_by_person_game.values())


def finalize_rows(rows: list[dict[str, Any]], player_bio_by_person: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    output: list[dict[str, Any]] = []
    for row in rows:
        bio = player_bio_by_person.get(to_int_or_none(row.get("person_id")) or -1, {})
        output.append(
            {
                "player_sk": row.get("player_sk"),
                "person_id": row.get("person_id"),
                "player_name": row.get("player_name"),
                "first_name": row.get("first_name"),
                "family_name": row.get("family_name"),
                "display_name": row.get("display_name"),
                "primary_position": row.get("primary_position"),
                "latest_team_id": row.get("latest_team_id"),
                "latest_nba_team_id": row.get("latest_nba_team_id"),
                "record_source": row.get("record_source"),
                "valid_from_utc": row.get("valid_from_utc"),
                "valid_to_utc": row.get("valid_to_utc"),
                "is_current": to_int_or_none(row.get("is_current")) or 0,
                "created_at_utc": run_ts,
                "updated_at_utc": run_ts,
                "birth_date": bio.get("birth_date"),
                "school": bio.get("school"),
                "country": bio.get("country"),
                "height_inches": bio.get("height_inches"),
                "weight_lbs": bio.get("weight_lbs"),
                "draft_year": bio.get("draft_year"),
                "draft_round": bio.get("draft_round"),
                "draft_number": bio.get("draft_number"),
            }
        )
    return output


def build_dim_player_rows(
    player_table: pa.Table,
    game_table: pa.Table,
    player_bio_table: pa.Table,
    dim_team_table: pa.Table,
    bridge_table: pa.Table | None = None,
    bbr_profile_table: pa.Table | None = None,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    game_time_by_id = build_game_time_map(game_table)
    player_bio_by_person = merge_bbr_birth_date_fallbacks(
        build_player_bio_map(player_bio_table),
        build_bbr_birth_date_map(bridge_table, bbr_profile_table),
    )
    nba_team_ids = build_current_nba_team_ids(dim_team_table)
    events = build_player_events(player_table, game_time_by_id, player_bio_by_person, nba_team_ids)
    versions = build_scd2_versions(
        events=events,
        entity_id_col="person_id",
        tracked_cols=TRACKED_COLS,
        carry_forward_cols=TRACKED_COLS,
        event_time_col="game_time_utc",
        event_date_col="game_date",
        event_order_cols=["game_time_utc", "game_id"],
        record_source=DIM_PLAYER_RECORD_SOURCE,
    )
    keyed_rows = assign_surrogate_keys(
        versions,
        sk_col="player_sk",
        sort_keys=["person_id", "valid_from_utc", "player_name"],
    )
    return finalize_rows(keyed_rows, player_bio_by_person), player_bio_by_person
