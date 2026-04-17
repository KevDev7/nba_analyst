"""Purpose: Build semantic_gold player as a current-state business object from silver sources.
Inputs: Silver player-game, game, player bio, and accepted BBR enrichment tables.
Outputs: One semantic player row per person_id with core identity and selected enrichment fields.
Next file: transform_to_player_game_parquet.py links player_game rows to this player surface.
"""

from __future__ import annotations

import boto3
import pyarrow as pa
from dotenv import load_dotenv

from pipelines.athena.transform.gold.gold_transform_helpers import S3_BUCKET, TEAM_CONTEXT_BY_ID, normalize_position_group, read_parquet_table_from_s3, to_positive_int_or_none, to_str_or_none, write_parquet_to_s3
from pipelines.athena.transform.gold.player_surface.bbr_projection import build_bbr_by_person_id
from pipelines.athena.transform.gold.player_surface.current_profile import build_profile_flags_map, map_bbr_draft_team_id
from pipelines.athena.transform.gold.player_surface.history import (
    build_bbr_birth_date_map,
    build_game_time_map,
    build_player_bio_map,
    build_player_events,
    merge_bbr_birth_date_fallbacks,
)
from pipelines.athena.transform.gold.player_surface.sources import (
    BBR_BRIDGE_REQUIRED_COLUMNS,
    BBR_BRIDGE_SOURCE_KEY,
    BBR_PROFILE_REQUIRED_COLUMNS,
    BBR_PROFILE_SOURCE_KEY,
    GAME_REQUIRED_COLUMNS,
    GAME_SOURCE_KEY,
    PLAYER_BIO_REQUIRED_COLUMNS,
    PLAYER_BIO_SOURCE_KEY,
    PLAYER_REQUIRED_COLUMNS,
    PLAYER_SOURCE_KEY,
)

from .contracts import PLAYER_SCHEMA

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/player/player.parquet"


def build_player_rows_from_tables(
    player_table: pa.Table,
    game_table: pa.Table,
    player_bio_table: pa.Table,
    bridge_table: pa.Table,
    bbr_profile_table: pa.Table,
) -> list[dict[str, object]]:
    game_time_by_id = build_game_time_map(game_table)
    player_bio_by_person = merge_bbr_birth_date_fallbacks(
        build_player_bio_map(player_bio_table),
        build_bbr_birth_date_map(bridge_table, bbr_profile_table),
    )
    nba_team_ids = set(TEAM_CONTEXT_BY_ID.keys())
    player_events = build_player_events(player_table, game_time_by_id, player_bio_by_person, nba_team_ids)
    flags_by_person = build_profile_flags_map(player_bio_table)
    bbr_by_person = build_bbr_by_person_id(bridge_table, bbr_profile_table)

    latest_event_by_person: dict[int, dict[str, object]] = {}
    first_seen_by_person: dict[int, object] = {}
    last_seen_by_person: dict[int, object] = {}
    latest_detail_by_person: dict[int, dict[str, object]] = {}
    latest_sort_key_by_person: dict[int, tuple[object, str]] = {}

    for row in player_table.to_pylist():
        person_id = to_positive_int_or_none(row.get("personId"))
        game_id = to_str_or_none(row.get("gameId"))
        if person_id is None or game_id is None:
            continue
        sort_key = (game_time_by_id.get(game_id), game_id)
        current_sort_key = latest_sort_key_by_person.get(person_id)
        if current_sort_key is None or sort_key > current_sort_key:
            latest_sort_key_by_person[person_id] = sort_key
            latest_detail_by_person[person_id] = {
                "latest_jersey_number": to_str_or_none(row.get("jerseyNum")),
                "latest_status": to_str_or_none(row.get("status")),
                "primary_position": to_str_or_none(row.get("position")),
            }

    for event in player_events:
        person_id = event["person_id"]
        game_date = event.get("game_date")
        if game_date is not None:
            current_first = first_seen_by_person.get(person_id)
            current_last = last_seen_by_person.get(person_id)
            if current_first is None or game_date < current_first:
                first_seen_by_person[person_id] = game_date
            if current_last is None or game_date > current_last:
                last_seen_by_person[person_id] = game_date
        latest_event_by_person[person_id] = event

    person_ids = sorted(
        {
            person_id
            for table in (player_table.to_pylist(), player_bio_table.to_pylist(), bridge_table.to_pylist())
            for row in table
            if (person_id := to_positive_int_or_none(row.get("personId") if "personId" in row else row.get("nba_person_id"))) is not None
        }
    )
    rows: list[dict[str, object]] = []
    for person_id in person_ids:
        event = latest_event_by_person.get(person_id, {})
        bio = player_bio_by_person.get(person_id, {})
        latest_detail = latest_detail_by_person.get(person_id, {})
        bbr = bbr_by_person.get(person_id, {})
        primary_position = latest_detail.get("primary_position") or event.get("primary_position")
        latest_team_id = event.get("latest_team_id")
        rows.append(
            {
                "person_id": person_id,
                "player_name": event.get("player_name"),
                "first_name": event.get("first_name") or bio.get("first_name"),
                "family_name": event.get("family_name") or bio.get("family_name"),
                "display_name": event.get("display_name") or event.get("player_name"),
                "primary_position": primary_position,
                "position_group": normalize_position_group(primary_position),
                "latest_team_id": latest_team_id if latest_team_id in nba_team_ids else None,
                "latest_jersey_number": latest_detail.get("latest_jersey_number"),
                "latest_status": latest_detail.get("latest_status"),
                "first_seen_game_date": first_seen_by_person.get(person_id),
                "last_seen_game_date": last_seen_by_person.get(person_id),
                "first_season_played": (
                    f"{first_seen_by_person[person_id].year if first_seen_by_person[person_id].month >= 7 else first_seen_by_person[person_id].year - 1}-"
                    f"{((first_seen_by_person[person_id].year if first_seen_by_person[person_id].month >= 7 else first_seen_by_person[person_id].year - 1) + 1) % 100:02d}"
                    if person_id in first_seen_by_person
                    else None
                ),
                "last_season_played": (
                    f"{last_seen_by_person[person_id].year if last_seen_by_person[person_id].month >= 7 else last_seen_by_person[person_id].year - 1}-"
                    f"{((last_seen_by_person[person_id].year if last_seen_by_person[person_id].month >= 7 else last_seen_by_person[person_id].year - 1) + 1) % 100:02d}"
                    if person_id in last_seen_by_person
                    else None
                ),
                "birth_date": bio.get("birth_date"),
                "school": bio.get("school"),
                "country": bio.get("country"),
                "height_inches": bio.get("height_inches"),
                "weight_lbs": bio.get("weight_lbs"),
                "draft_year": bio.get("draft_year"),
                "draft_round": bio.get("draft_round"),
                "draft_number": bio.get("draft_number"),
                "is_guard": flags_by_person.get(person_id, {}).get("is_guard"),
                "is_forward": flags_by_person.get(person_id, {}).get("is_forward"),
                "is_center": flags_by_person.get(person_id, {}).get("is_center"),
                "basketball_reference_player_id": bbr.get("basketball_reference_player_id"),
                "bbr_match_method": bbr.get("bbr_match_method"),
                "bbr_match_confidence": bbr.get("bbr_match_confidence"),
                "bbr_profile_url": bbr.get("bbr_profile_url"),
                "bbr_formal_name": bbr.get("bbr_formal_name"),
                "bbr_position_raw": bbr.get("bbr_position_raw"),
                "bbr_shoots": bbr.get("bbr_shoots"),
                "bbr_height_cm": bbr.get("bbr_height_cm"),
                "bbr_weight_kg": bbr.get("bbr_weight_kg"),
                "bbr_college_raw": bbr.get("bbr_college_raw"),
                "bbr_birth_country_code": bbr.get("bbr_birth_country_code"),
                "bbr_headshot_url": bbr.get("bbr_headshot_url"),
                "bbr_hall_of_fame_flag": bbr.get("bbr_hall_of_fame_flag"),
            }
        )
    return rows


def main() -> None:
    s3_client = boto3.client("s3")
    player_table = read_parquet_table_from_s3(s3_client, PLAYER_SOURCE_KEY, PLAYER_REQUIRED_COLUMNS)
    game_table = read_parquet_table_from_s3(s3_client, GAME_SOURCE_KEY, GAME_REQUIRED_COLUMNS)
    player_bio_table = read_parquet_table_from_s3(s3_client, PLAYER_BIO_SOURCE_KEY, PLAYER_BIO_REQUIRED_COLUMNS)
    bridge_table = read_parquet_table_from_s3(s3_client, BBR_BRIDGE_SOURCE_KEY, BBR_BRIDGE_REQUIRED_COLUMNS)
    bbr_profile_table = read_parquet_table_from_s3(s3_client, BBR_PROFILE_SOURCE_KEY, BBR_PROFILE_REQUIRED_COLUMNS)
    rows = build_player_rows_from_tables(player_table, game_table, player_bio_table, bridge_table, bbr_profile_table)
    write_parquet_to_s3(rows, PLAYER_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
