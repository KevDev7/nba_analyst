"""
Build paired gold player-game shot profile tables.

Reads:
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_player_game/fct_player_game.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_team_game/fct_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/playbyplay/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/pbpstats_event_projection_v1/game_id=<GAME_ID>.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_player_game_shot_profile_standard/fct_player_game_shot_profile_standard.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_player_game_shot_profile_source/fct_player_game_shot_profile_source.parquet
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.gold.gold_transform_helpers import (
        S3_BUCKET,
        normalize_game_id,
        parse_date_or_none,
        parse_timestamp_utc,
        to_bool_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        S3_BUCKET,
        normalize_game_id,
        parse_date_or_none,
        parse_timestamp_utc,
        to_bool_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )

load_dotenv(override=True)

PLAYER_FACT_KEY = "legacy_gold/fct_player_game/fct_player_game.parquet"
TEAM_FACT_KEY = "legacy_gold/fct_team_game/fct_team_game.parquet"
PLAYBYPLAY_PREFIX = "silver/playbyplay/"
PBPSTATS_PROJECTION_PREFIX = "silver/pbpstats_event_projection_v1/"
STANDARD_DESTINATION_KEY = (
    "legacy_gold/fct_player_game_shot_profile_standard/fct_player_game_shot_profile_standard.parquet"
)
SOURCE_DESTINATION_KEY = (
    "legacy_gold/fct_player_game_shot_profile_source/fct_player_game_shot_profile_source.parquet"
)

RECORD_SOURCE = (
    "gold.fct_player_game|gold.fct_team_game|silver.playbyplay|silver.pbpstats_event_projection_v1"
)

PLAYER_FACT_REQUIRED_COLUMNS = [
    "fct_player_game_sk",
    "game_sk",
    "date_sk",
    "player_sk",
    "team_sk",
    "game_id",
    "person_id",
    "team_id",
    "game_datetime_utc",
    "game_date",
    "season_year",
    "season_start_year",
    "raw_season_type_code",
    "season_type",
    "did_play",
]

TEAM_FACT_REQUIRED_COLUMNS = [
    "game_id",
    "team_id",
    "opponent_team_id",
    "opponent_team_sk",
]

PBPSTATS_REQUIRED_COLUMNS = [
    "game_id",
    "player1_id",
    "is_field_goal_event",
    "is_made",
    "shot_value",
    "shot_type",
]

PLAYBYPLAY_REQUIRED_COLUMNS = [
    "gameId",
    "personId",
    "isFieldGoal",
    "isMadeShot",
    "shotValue",
    "area",
    "areaDetail",
]

STANDARD_BUCKET_COLUMN_PREFIX_BY_LABEL = {
    "AtRim": "at_rim",
    "ShortMidRange": "short_mid_range",
    "LongMidRange": "long_mid_range",
    "Corner3": "corner_3",
    "Arc3": "arc_3",
    "UnknownDistance2pt": "unknown_distance_2pt",
}

SOURCE_AREA_COLUMN_PREFIX_BY_LABEL = {
    "Restricted Area": "restricted_area",
    "In The Paint (Non-RA)": "paint_non_restricted_area",
    "Mid-Range": "mid_range",
    "Left Corner 3": "left_corner_3",
    "Right Corner 3": "right_corner_3",
    "Above the Break 3": "above_the_break_3",
}

SOURCE_AREA_DETAIL_COLUMN_PREFIX_BY_LABEL = {
    "0-8 Center": "center_0_8",
    "8-16 Left": "left_8_16",
    "8-16 Center": "center_8_16",
    "8-16 Right": "right_8_16",
    "16-24 Left": "left_16_24",
    "16-24 Left Center": "left_center_16_24",
    "16-24 Center": "center_16_24",
    "16-24 Right Center": "right_center_16_24",
    "16-24 Right": "right_16_24",
    "24+ Left": "left_24_plus",
    "24+ Left Center": "left_center_24_plus",
    "24+ Center": "center_24_plus",
    "24+ Right Center": "right_center_24_plus",
    "24+ Right": "right_24_plus",
}

STANDARD_BUCKET_COLUMN_PREFIXES = list(STANDARD_BUCKET_COLUMN_PREFIX_BY_LABEL.values())
SOURCE_BUCKET_COLUMN_PREFIXES = (
    list(SOURCE_AREA_COLUMN_PREFIX_BY_LABEL.values())
    + list(SOURCE_AREA_DETAIL_COLUMN_PREFIX_BY_LABEL.values())
    + ["unmapped_source_area", "unmapped_source_area_detail"]
)

STANDARD_TARGET_SCHEMA = pa.schema(
    [
        pa.field("fct_player_game_shot_profile_standard_sk", pa.int64()),
        pa.field("fct_player_game_sk", pa.int64()),
        pa.field("game_sk", pa.int64()),
        pa.field("date_sk", pa.int64()),
        pa.field("player_sk", pa.int64()),
        pa.field("team_sk", pa.int64()),
        pa.field("opponent_team_sk", pa.int64()),
        pa.field("game_id", pa.string()),
        pa.field("person_id", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("opponent_team_id", pa.int64()),
        pa.field("game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("game_date", pa.date32()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("field_goals_attempted", pa.int64()),
        pa.field("field_goals_made", pa.int64()),
        pa.field("three_pointers_attempted", pa.int64()),
        pa.field("three_pointers_made", pa.int64()),
        pa.field("points_from_field_goals", pa.int64()),
        pa.field("at_rim_field_goals_attempted", pa.int64()),
        pa.field("at_rim_field_goals_made", pa.int64()),
        pa.field("short_mid_range_field_goals_attempted", pa.int64()),
        pa.field("short_mid_range_field_goals_made", pa.int64()),
        pa.field("long_mid_range_field_goals_attempted", pa.int64()),
        pa.field("long_mid_range_field_goals_made", pa.int64()),
        pa.field("corner_3_field_goals_attempted", pa.int64()),
        pa.field("corner_3_field_goals_made", pa.int64()),
        pa.field("arc_3_field_goals_attempted", pa.int64()),
        pa.field("arc_3_field_goals_made", pa.int64()),
        pa.field("unknown_distance_2pt_field_goals_attempted", pa.int64()),
        pa.field("unknown_distance_2pt_field_goals_made", pa.int64()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)

SOURCE_TARGET_SCHEMA = pa.schema(
    [
        pa.field("fct_player_game_shot_profile_source_sk", pa.int64()),
        pa.field("fct_player_game_sk", pa.int64()),
        pa.field("game_sk", pa.int64()),
        pa.field("date_sk", pa.int64()),
        pa.field("player_sk", pa.int64()),
        pa.field("team_sk", pa.int64()),
        pa.field("opponent_team_sk", pa.int64()),
        pa.field("game_id", pa.string()),
        pa.field("person_id", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("opponent_team_id", pa.int64()),
        pa.field("game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("game_date", pa.date32()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("field_goals_attempted", pa.int64()),
        pa.field("field_goals_made", pa.int64()),
        pa.field("three_pointers_attempted", pa.int64()),
        pa.field("three_pointers_made", pa.int64()),
        pa.field("points_from_field_goals", pa.int64()),
        pa.field("restricted_area_field_goals_attempted", pa.int64()),
        pa.field("restricted_area_field_goals_made", pa.int64()),
        pa.field("paint_non_restricted_area_field_goals_attempted", pa.int64()),
        pa.field("paint_non_restricted_area_field_goals_made", pa.int64()),
        pa.field("mid_range_field_goals_attempted", pa.int64()),
        pa.field("mid_range_field_goals_made", pa.int64()),
        pa.field("left_corner_3_field_goals_attempted", pa.int64()),
        pa.field("left_corner_3_field_goals_made", pa.int64()),
        pa.field("right_corner_3_field_goals_attempted", pa.int64()),
        pa.field("right_corner_3_field_goals_made", pa.int64()),
        pa.field("above_the_break_3_field_goals_attempted", pa.int64()),
        pa.field("above_the_break_3_field_goals_made", pa.int64()),
        pa.field("center_0_8_field_goals_attempted", pa.int64()),
        pa.field("center_0_8_field_goals_made", pa.int64()),
        pa.field("left_8_16_field_goals_attempted", pa.int64()),
        pa.field("left_8_16_field_goals_made", pa.int64()),
        pa.field("center_8_16_field_goals_attempted", pa.int64()),
        pa.field("center_8_16_field_goals_made", pa.int64()),
        pa.field("right_8_16_field_goals_attempted", pa.int64()),
        pa.field("right_8_16_field_goals_made", pa.int64()),
        pa.field("left_16_24_field_goals_attempted", pa.int64()),
        pa.field("left_16_24_field_goals_made", pa.int64()),
        pa.field("left_center_16_24_field_goals_attempted", pa.int64()),
        pa.field("left_center_16_24_field_goals_made", pa.int64()),
        pa.field("center_16_24_field_goals_attempted", pa.int64()),
        pa.field("center_16_24_field_goals_made", pa.int64()),
        pa.field("right_center_16_24_field_goals_attempted", pa.int64()),
        pa.field("right_center_16_24_field_goals_made", pa.int64()),
        pa.field("right_16_24_field_goals_attempted", pa.int64()),
        pa.field("right_16_24_field_goals_made", pa.int64()),
        pa.field("left_24_plus_field_goals_attempted", pa.int64()),
        pa.field("left_24_plus_field_goals_made", pa.int64()),
        pa.field("left_center_24_plus_field_goals_attempted", pa.int64()),
        pa.field("left_center_24_plus_field_goals_made", pa.int64()),
        pa.field("center_24_plus_field_goals_attempted", pa.int64()),
        pa.field("center_24_plus_field_goals_made", pa.int64()),
        pa.field("right_center_24_plus_field_goals_attempted", pa.int64()),
        pa.field("right_center_24_plus_field_goals_made", pa.int64()),
        pa.field("right_24_plus_field_goals_attempted", pa.int64()),
        pa.field("right_24_plus_field_goals_made", pa.int64()),
        pa.field("unmapped_source_area_field_goals_attempted", pa.int64()),
        pa.field("unmapped_source_area_field_goals_made", pa.int64()),
        pa.field("unmapped_source_area_detail_field_goals_attempted", pa.int64()),
        pa.field("unmapped_source_area_detail_field_goals_made", pa.int64()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)


def _empty_stats(bucket_prefixes: list[str]) -> dict[str, int]:
    stats = {
        "field_goals_attempted": 0,
        "field_goals_made": 0,
        "three_pointers_attempted": 0,
        "three_pointers_made": 0,
        "points_from_field_goals": 0,
    }
    for bucket_prefix in bucket_prefixes:
        stats[f"{bucket_prefix}_field_goals_attempted"] = 0
        stats[f"{bucket_prefix}_field_goals_made"] = 0
    return stats


def _new_standard_stats() -> dict[str, int]:
    return _empty_stats(STANDARD_BUCKET_COLUMN_PREFIXES)


def _new_source_stats() -> dict[str, int]:
    return _empty_stats(SOURCE_BUCKET_COLUMN_PREFIXES)


def _read_optional_rows_from_s3(key: str, columns: list[str]) -> list[dict[str, Any]]:
    s3_client = boto3.client("s3")
    try:
        payload = s3_client.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read()
    except ClientError as exc:
        error_code = str(exc.response.get("Error", {}).get("Code") or "")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            return []
        raise
    table = pq.read_table(pa.BufferReader(payload), columns=columns)
    return table.to_pylist()


def _standard_key_for_game(game_id: str) -> str:
    return f"{PBPSTATS_PROJECTION_PREFIX}game_id={game_id}.parquet"


def _source_key_for_game(game_id: str) -> str:
    return f"{PLAYBYPLAY_PREFIX}game_id={game_id}.parquet"


def aggregate_standard_rows(rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, int], dict[str, int]], set[str]]:
    stats_by_key: dict[tuple[str, int], dict[str, int]] = {}
    unknown_labels: set[str] = set()

    for row in rows:
        game_id = normalize_game_id(row.get("game_id"))
        person_id = to_int_or_none(row.get("player1_id"))
        if game_id is None or person_id is None or person_id <= 0:
            continue
        if not to_bool_or_none(row.get("is_field_goal_event")):
            continue

        key = (game_id, person_id)
        stats = stats_by_key.setdefault(key, _new_standard_stats())
        stats["field_goals_attempted"] += 1

        shot_value = to_int_or_none(row.get("shot_value")) or 0
        if shot_value == 3:
            stats["three_pointers_attempted"] += 1

        is_made = to_bool_or_none(row.get("is_made")) is True
        if is_made:
            stats["field_goals_made"] += 1
            stats["points_from_field_goals"] += shot_value
            if shot_value == 3:
                stats["three_pointers_made"] += 1

        shot_type = to_str_or_none(row.get("shot_type"))
        bucket_prefix = STANDARD_BUCKET_COLUMN_PREFIX_BY_LABEL.get(shot_type or "")
        if bucket_prefix is None:
            if shot_type:
                unknown_labels.add(shot_type)
            continue
        stats[f"{bucket_prefix}_field_goals_attempted"] += 1
        if is_made:
            stats[f"{bucket_prefix}_field_goals_made"] += 1

    return stats_by_key, unknown_labels


def aggregate_source_rows(rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, int], dict[str, int]], set[str], set[str]]:
    stats_by_key: dict[tuple[str, int], dict[str, int]] = {}
    unknown_area_labels: set[str] = set()
    unknown_area_detail_labels: set[str] = set()

    for row in rows:
        game_id = normalize_game_id(row.get("gameId"))
        person_id = to_int_or_none(row.get("personId"))
        if game_id is None or person_id is None or person_id <= 0:
            continue
        if to_int_or_none(row.get("isFieldGoal")) != 1:
            continue

        key = (game_id, person_id)
        stats = stats_by_key.setdefault(key, _new_source_stats())
        stats["field_goals_attempted"] += 1

        shot_value = to_int_or_none(row.get("shotValue")) or 0
        if shot_value == 3:
            stats["three_pointers_attempted"] += 1

        is_made = to_bool_or_none(row.get("isMadeShot")) is True
        if is_made:
            stats["field_goals_made"] += 1
            stats["points_from_field_goals"] += shot_value
            if shot_value == 3:
                stats["three_pointers_made"] += 1

        area = to_str_or_none(row.get("area"))
        area_prefix = SOURCE_AREA_COLUMN_PREFIX_BY_LABEL.get(area or "")
        if area_prefix is None:
            if area:
                unknown_area_labels.add(area)
            stats["unmapped_source_area_field_goals_attempted"] += 1
            if is_made:
                stats["unmapped_source_area_field_goals_made"] += 1
        else:
            stats[f"{area_prefix}_field_goals_attempted"] += 1
            if is_made:
                stats[f"{area_prefix}_field_goals_made"] += 1

        area_detail = to_str_or_none(row.get("areaDetail"))
        area_detail_prefix = SOURCE_AREA_DETAIL_COLUMN_PREFIX_BY_LABEL.get(area_detail or "")
        if area_detail_prefix is None:
            if area_detail:
                unknown_area_detail_labels.add(area_detail)
            stats["unmapped_source_area_detail_field_goals_attempted"] += 1
            if is_made:
                stats["unmapped_source_area_detail_field_goals_made"] += 1
        else:
            stats[f"{area_detail_prefix}_field_goals_attempted"] += 1
            if is_made:
                stats[f"{area_detail_prefix}_field_goals_made"] += 1

    return stats_by_key, unknown_area_labels, unknown_area_detail_labels


def aggregate_game_shot_profiles(
    game_id: str,
) -> tuple[
    dict[tuple[str, int], dict[str, int]],
    dict[tuple[str, int], dict[str, int]],
    set[str],
    set[str],
    set[str],
]:
    standard_rows = _read_optional_rows_from_s3(_standard_key_for_game(game_id), PBPSTATS_REQUIRED_COLUMNS)
    source_rows = _read_optional_rows_from_s3(_source_key_for_game(game_id), PLAYBYPLAY_REQUIRED_COLUMNS)
    standard_stats, unknown_standard_labels = aggregate_standard_rows(standard_rows)
    source_stats, unknown_area_labels, unknown_area_detail_labels = aggregate_source_rows(source_rows)
    return (
        standard_stats,
        source_stats,
        unknown_standard_labels,
        unknown_area_labels,
        unknown_area_detail_labels,
    )


def build_team_fact_map(team_fact_rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, int | None]]:
    output: dict[tuple[str, int], dict[str, int | None]] = {}
    for row in team_fact_rows:
        game_id = normalize_game_id(row.get("game_id"))
        team_id = to_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        output[(game_id, team_id)] = {
            "opponent_team_id": to_int_or_none(row.get("opponent_team_id")),
            "opponent_team_sk": to_int_or_none(row.get("opponent_team_sk")),
        }
    return output


def build_standard_row(
    base_row: dict[str, Any],
    *,
    team_fact_map: dict[tuple[str, int], dict[str, int | None]],
    stats_by_key: dict[tuple[str, int], dict[str, int]],
    run_ts: datetime,
) -> dict[str, Any]:
    game_id = normalize_game_id(base_row.get("game_id"))
    person_id = to_int_or_none(base_row.get("person_id"))
    team_id = to_int_or_none(base_row.get("team_id"))
    key = (game_id or "", person_id or -1)
    stats = stats_by_key.get(key, _new_standard_stats())
    team_fact_context = team_fact_map.get((game_id or "", team_id or -1), {})
    return {
        "fct_player_game_sk": to_int_or_none(base_row.get("fct_player_game_sk")),
        "game_sk": to_int_or_none(base_row.get("game_sk")),
        "date_sk": to_int_or_none(base_row.get("date_sk")),
        "player_sk": to_int_or_none(base_row.get("player_sk")),
        "team_sk": to_int_or_none(base_row.get("team_sk")),
        "opponent_team_sk": to_int_or_none(team_fact_context.get("opponent_team_sk")),
        "game_id": game_id,
        "person_id": person_id,
        "team_id": team_id,
        "opponent_team_id": to_int_or_none(team_fact_context.get("opponent_team_id")),
        "game_datetime_utc": parse_timestamp_utc(base_row.get("game_datetime_utc")),
        "game_date": parse_date_or_none(base_row.get("game_date")),
        "season_year": to_str_or_none(base_row.get("season_year")),
        "season_start_year": to_int_or_none(base_row.get("season_start_year")),
        "raw_season_type_code": to_str_or_none(base_row.get("raw_season_type_code")),
        "season_type": to_str_or_none(base_row.get("season_type")),
        **stats,
        "record_source": RECORD_SOURCE,
        "created_at_utc": run_ts,
        "updated_at_utc": run_ts,
    }


def build_source_row(
    base_row: dict[str, Any],
    *,
    team_fact_map: dict[tuple[str, int], dict[str, int | None]],
    stats_by_key: dict[tuple[str, int], dict[str, int]],
    run_ts: datetime,
) -> dict[str, Any]:
    game_id = normalize_game_id(base_row.get("game_id"))
    person_id = to_int_or_none(base_row.get("person_id"))
    team_id = to_int_or_none(base_row.get("team_id"))
    key = (game_id or "", person_id or -1)
    stats = stats_by_key.get(key, _new_source_stats())
    team_fact_context = team_fact_map.get((game_id or "", team_id or -1), {})
    return {
        "fct_player_game_sk": to_int_or_none(base_row.get("fct_player_game_sk")),
        "game_sk": to_int_or_none(base_row.get("game_sk")),
        "date_sk": to_int_or_none(base_row.get("date_sk")),
        "player_sk": to_int_or_none(base_row.get("player_sk")),
        "team_sk": to_int_or_none(base_row.get("team_sk")),
        "opponent_team_sk": to_int_or_none(team_fact_context.get("opponent_team_sk")),
        "game_id": game_id,
        "person_id": person_id,
        "team_id": team_id,
        "opponent_team_id": to_int_or_none(team_fact_context.get("opponent_team_id")),
        "game_datetime_utc": parse_timestamp_utc(base_row.get("game_datetime_utc")),
        "game_date": parse_date_or_none(base_row.get("game_date")),
        "season_year": to_str_or_none(base_row.get("season_year")),
        "season_start_year": to_int_or_none(base_row.get("season_start_year")),
        "raw_season_type_code": to_str_or_none(base_row.get("raw_season_type_code")),
        "season_type": to_str_or_none(base_row.get("season_type")),
        **stats,
        "record_source": RECORD_SOURCE,
        "created_at_utc": run_ts,
        "updated_at_utc": run_ts,
    }


def build_shot_profile_rows(
    player_fact_rows: list[dict[str, Any]],
    team_fact_rows: list[dict[str, Any]],
    *,
    max_workers: int = 16,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]]]:
    base_rows = [
        row
        for row in player_fact_rows
        if to_int_or_none(row.get("did_play")) == 1
        and normalize_game_id(row.get("game_id")) is not None
        and to_int_or_none(row.get("person_id")) is not None
    ]
    base_rows.sort(
        key=lambda row: (
            normalize_game_id(row.get("game_id")) or "",
            to_int_or_none(row.get("person_id")) or -1,
        )
    )

    game_ids = sorted({normalize_game_id(row.get("game_id")) for row in base_rows if normalize_game_id(row.get("game_id"))})
    team_fact_map = build_team_fact_map(team_fact_rows)

    standard_stats_by_key: dict[tuple[str, int], dict[str, int]] = {}
    source_stats_by_key: dict[tuple[str, int], dict[str, int]] = {}
    unknown_standard_labels: set[str] = set()
    unknown_area_labels: set[str] = set()
    unknown_area_detail_labels: set[str] = set()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(aggregate_game_shot_profiles, game_id): game_id
            for game_id in game_ids
        }
        total_games = len(futures)
        for index, future in enumerate(as_completed(futures), start=1):
            game_id = futures[future]
            (
                game_standard_stats,
                game_source_stats,
                game_unknown_standard_labels,
                game_unknown_area_labels,
                game_unknown_area_detail_labels,
            ) = future.result()
            standard_stats_by_key.update(game_standard_stats)
            source_stats_by_key.update(game_source_stats)
            unknown_standard_labels.update(game_unknown_standard_labels)
            unknown_area_labels.update(game_unknown_area_labels)
            unknown_area_detail_labels.update(game_unknown_area_detail_labels)
            if index == 1 or index % 250 == 0 or index == total_games:
                print(f"Aggregated shot profiles for {index}/{total_games} games (latest={game_id})")

    run_ts = datetime.now(timezone.utc)
    standard_rows = [
        build_standard_row(
            row,
            team_fact_map=team_fact_map,
            stats_by_key=standard_stats_by_key,
            run_ts=run_ts,
        )
        for row in base_rows
    ]
    source_rows = [
        build_source_row(
            row,
            team_fact_map=team_fact_map,
            stats_by_key=source_stats_by_key,
            run_ts=run_ts,
        )
        for row in base_rows
    ]

    for index, row in enumerate(standard_rows, start=1):
        row["fct_player_game_shot_profile_standard_sk"] = index
    for index, row in enumerate(source_rows, start=1):
        row["fct_player_game_shot_profile_source_sk"] = index

    label_diagnostics = {
        "unknown_standard_shot_types": sorted(unknown_standard_labels),
        "unknown_source_area_labels": sorted(unknown_area_labels),
        "unknown_source_area_detail_labels": sorted(unknown_area_detail_labels),
    }
    return standard_rows, source_rows, label_diagnostics


def _read_single_parquet_rows_from_s3(key: str, columns: list[str]) -> list[dict[str, Any]]:
    s3_client = boto3.client("s3")
    payload = s3_client.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read()
    table = pq.read_table(io.BytesIO(payload), columns=columns)
    return table.to_pylist()


def main() -> None:
    player_fact_rows = _read_single_parquet_rows_from_s3(PLAYER_FACT_KEY, PLAYER_FACT_REQUIRED_COLUMNS)
    team_fact_rows = _read_single_parquet_rows_from_s3(TEAM_FACT_KEY, TEAM_FACT_REQUIRED_COLUMNS)

    standard_rows, source_rows, label_diagnostics = build_shot_profile_rows(player_fact_rows, team_fact_rows)

    s3_client = boto3.client("s3")
    write_parquet_to_s3(standard_rows, STANDARD_TARGET_SCHEMA, STANDARD_DESTINATION_KEY, s3_client)
    write_parquet_to_s3(source_rows, SOURCE_TARGET_SCHEMA, SOURCE_DESTINATION_KEY, s3_client)

    print(
        "Wrote player-game shot profiles:",
        {
            "standard_row_count": len(standard_rows),
            "source_row_count": len(source_rows),
            **label_diagnostics,
        },
    )


if __name__ == "__main__":
    main()
