"""
Build gold player-game shot-type source fact from silver play-by-play field-goal events.

Reads:
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_player_game/fct_player_game.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_team_game/fct_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/playbyplay/game_id=<GAME_ID>.parquet

Writes:
  Full mode:
    s3://nba-analytics-lakehouse-dev/legacy_gold/fct_player_game_shot_type_source/fct_player_game_shot_type_source.parquet
  Preview mode:
    s3://nba-analytics-lakehouse-dev/legacy_gold/_preview/fct_player_game_shot_type_source/fct_player_game_shot_type_source_preview.parquet
"""

from __future__ import annotations

import io
import os
import re
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

DESTINATION_KEY = (
    "legacy_gold/fct_player_game_shot_type_source/fct_player_game_shot_type_source.parquet"
)
PREVIEW_DESTINATION_KEY = (
    "legacy_gold/_preview/fct_player_game_shot_type_source/"
    "fct_player_game_shot_type_source_preview.parquet"
)

RECORD_SOURCE = "gold.fct_player_game|gold.fct_team_game|silver.playbyplay"

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

PLAYBYPLAY_REQUIRED_COLUMNS = [
    "gameId",
    "personId",
    "isFieldGoal",
    "isMadeShot",
    "shotValue",
    "actionType",
    "subType",
    "descriptor",
]

TARGET_GAME_IDS = {
    normalized
    for raw_value in os.getenv("PLAYER_GAME_SHOT_TYPE_SOURCE_TARGET_GAME_IDS", "").split(",")
    if (normalized := normalize_game_id(raw_value))
}
PREVIEW_ROW_LIMIT = to_int_or_none(os.getenv("PLAYER_GAME_SHOT_TYPE_SOURCE_PREVIEW_ROW_LIMIT"))
MAX_WORKERS = to_int_or_none(os.getenv("PLAYER_GAME_SHOT_TYPE_SOURCE_MAX_WORKERS")) or 16

FACT_TARGET_SCHEMA = pa.schema(
    [
        pa.field("fct_player_game_shot_type_source_sk", pa.int64()),
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
        pa.field("source_shot_type_key", pa.string()),
        pa.field("source_shot_type_label", pa.string()),
        pa.field("source_shot_type_family", pa.string()),
        pa.field("action_type", pa.string()),
        pa.field("sub_type", pa.string()),
        pa.field("descriptor", pa.string()),
        pa.field("shot_value", pa.int64()),
        pa.field("is_two_point_shot", pa.int64()),
        pa.field("is_three_point_shot", pa.int64()),
        pa.field("field_goals_attempted", pa.int64()),
        pa.field("field_goals_made", pa.int64()),
        pa.field("three_pointers_attempted", pa.int64()),
        pa.field("three_pointers_made", pa.int64()),
        pa.field("points_from_field_goals", pa.int64()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)


def _read_single_parquet_rows_from_s3(key: str, columns: list[str]) -> list[dict[str, Any]]:
    s3_client = boto3.client("s3")
    payload = s3_client.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read()
    table = pq.read_table(io.BytesIO(payload), columns=columns)
    return table.to_pylist()


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


def _source_key_for_game(game_id: str) -> str:
    return f"{PLAYBYPLAY_PREFIX}game_id={game_id}.parquet"


def _normalize_action_token(value: Any) -> str | None:
    text = to_str_or_none(value)
    if text is None:
        return None
    return " ".join(text.split())


def normalize_shot_type_parts(
    *,
    action_type: Any,
    sub_type: Any,
    descriptor: Any,
    shot_value: Any,
) -> tuple[str | None, str | None, str | None, int | None]:
    return (
        _normalize_action_token(action_type),
        _normalize_action_token(sub_type),
        _normalize_action_token(descriptor),
        to_int_or_none(shot_value),
    )


def _title_phrase(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(part.capitalize() for part in value.split())


def _compact_shot_family_token(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower()) or None


def shot_type_family_from_sub_type(sub_type: str | None) -> str | None:
    if sub_type is None:
        return None
    normalized = _compact_shot_family_token(sub_type)
    if normalized == "dunk":
        return "Dunk"
    if normalized == "hook":
        return "Hook"
    if normalized == "layup":
        return "Layup"
    # The source feed mixes `Jump Shot`, `jumpshot`, and the rare bare `shot`
    # for the same coarse shot family, so we canonicalize those together.
    if normalized in {"jumpshot", "shot"}:
        return "Jump Shot"
    return _title_phrase(sub_type)


def build_source_shot_type_label(
    sub_type: str | None,
    descriptor: str | None,
    shot_value: int | None,
) -> str | None:
    family = shot_type_family_from_sub_type(sub_type)
    if family is None:
        return None
    descriptor_prefix = _title_phrase(descriptor)
    base_label = family if family.endswith("Shot") else f"{family} Shot"
    label_core = base_label if descriptor_prefix is None else f"{descriptor_prefix} {base_label}"
    if shot_value == 2:
        return f"2PT {label_core}"
    if shot_value == 3:
        return f"3PT {label_core}"
    return label_core


def build_source_shot_type_key(
    action_type: str | None,
    sub_type: str | None,
    descriptor: str | None,
    shot_value: int | None,
) -> str:
    return "|".join(
        [
            action_type or "",
            sub_type or "",
            descriptor or "",
            "" if shot_value is None else str(shot_value),
        ]
    )


def _new_fact_stats() -> dict[str, int]:
    return {
        "field_goals_attempted": 0,
        "field_goals_made": 0,
        "three_pointers_attempted": 0,
        "three_pointers_made": 0,
        "points_from_field_goals": 0,
    }


def aggregate_source_shot_type_rows(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, int, str, str | None, str | None, int | None], dict[str, int]]:
    stats_by_key: dict[tuple[str, int, str, str | None, str | None, int | None], dict[str, int]] = {}

    for row in rows:
        game_id = normalize_game_id(row.get("gameId"))
        person_id = to_int_or_none(row.get("personId"))
        if game_id is None or person_id is None or person_id <= 0:
            continue
        if to_int_or_none(row.get("isFieldGoal")) != 1:
            continue
        action_type, sub_type, descriptor, shot_value = normalize_shot_type_parts(
            action_type=row.get("actionType"),
            sub_type=row.get("subType"),
            descriptor=row.get("descriptor"),
            shot_value=row.get("shotValue"),
        )
        if action_type is None or sub_type is None or shot_value not in {2, 3}:
            continue

        key = (game_id, person_id, action_type, sub_type, descriptor, shot_value)
        stats = stats_by_key.setdefault(key, _new_fact_stats())
        stats["field_goals_attempted"] += 1
        if shot_value == 3:
            stats["three_pointers_attempted"] += 1

        is_made = to_bool_or_none(row.get("isMadeShot")) is True
        if is_made:
            stats["field_goals_made"] += 1
            stats["points_from_field_goals"] += shot_value
            if shot_value == 3:
                stats["three_pointers_made"] += 1

    return stats_by_key


def aggregate_game_shot_type_rows(
    game_id: str,
) -> dict[tuple[str, int, str, str | None, str | None, int | None], dict[str, int]]:
    source_rows = _read_optional_rows_from_s3(_source_key_for_game(game_id), PLAYBYPLAY_REQUIRED_COLUMNS)
    return aggregate_source_shot_type_rows(source_rows)


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


def build_player_fact_context_map(
    player_fact_rows: list[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    output: dict[tuple[str, int], dict[str, Any]] = {}
    for row in player_fact_rows:
        if to_int_or_none(row.get("did_play")) != 1:
            continue
        game_id = normalize_game_id(row.get("game_id"))
        person_id = to_int_or_none(row.get("person_id"))
        if game_id is None or person_id is None or person_id <= 0:
            continue
        output[(game_id, person_id)] = row
    return output


def build_fact_row(
    *,
    base_row: dict[str, Any],
    team_fact_map: dict[tuple[str, int], dict[str, int | None]],
    action_type: str,
    sub_type: str | None,
    descriptor: str | None,
    shot_value: int | None,
    stats: dict[str, int],
    run_ts: datetime,
) -> dict[str, Any]:
    game_id = normalize_game_id(base_row.get("game_id"))
    person_id = to_int_or_none(base_row.get("person_id"))
    team_id = to_int_or_none(base_row.get("team_id"))
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
        "source_shot_type_key": build_source_shot_type_key(
            action_type,
            sub_type,
            descriptor,
            shot_value,
        ),
        "source_shot_type_label": build_source_shot_type_label(
            sub_type,
            descriptor,
            shot_value,
        ),
        "source_shot_type_family": shot_type_family_from_sub_type(sub_type),
        "action_type": action_type,
        "sub_type": sub_type,
        "descriptor": descriptor,
        "shot_value": shot_value,
        "is_two_point_shot": 1 if shot_value == 2 else 0,
        "is_three_point_shot": 1 if shot_value == 3 else 0,
        **stats,
        "record_source": RECORD_SOURCE,
        "created_at_utc": run_ts,
        "updated_at_utc": run_ts,
    }


def build_shot_type_rows(
    player_fact_rows: list[dict[str, Any]],
    team_fact_rows: list[dict[str, Any]],
    *,
    max_workers: int = 16,
    target_game_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    player_context_map = build_player_fact_context_map(player_fact_rows)
    team_fact_map = build_team_fact_map(team_fact_rows)

    game_ids = sorted({game_id for game_id, _person_id in player_context_map})
    if target_game_ids:
        game_ids = [game_id for game_id in game_ids if game_id in target_game_ids]

    stats_by_key: dict[tuple[str, int, str, str | None, str | None, int | None], dict[str, int]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(aggregate_game_shot_type_rows, game_id): game_id
            for game_id in game_ids
        }
        total_games = len(futures)
        for index, future in enumerate(as_completed(futures), start=1):
            game_id = futures[future]
            game_stats = future.result()
            stats_by_key.update(game_stats)
            if index == 1 or index % 250 == 0 or index == total_games:
                print(f"Aggregated shot-type source rows for {index}/{total_games} games (latest={game_id})")

    run_ts = datetime.now(timezone.utc)
    fact_rows: list[dict[str, Any]] = []
    for key in sorted(
        stats_by_key,
        key=lambda value: (
            value[0],
            value[1],
            value[2] or "",
            value[3] or "",
            value[4] or "",
            -1 if value[5] is None else value[5],
        ),
    ):
        game_id, person_id, action_type, sub_type, descriptor, shot_value = key
        base_row = player_context_map.get((game_id, person_id))
        if base_row is None:
            continue
        fact_rows.append(
            build_fact_row(
                base_row=base_row,
                team_fact_map=team_fact_map,
                action_type=action_type,
                sub_type=sub_type,
                descriptor=descriptor,
                shot_value=shot_value,
                stats=stats_by_key[key],
                run_ts=run_ts,
            )
        )

    fact_rows.sort(
        key=lambda row: (
            row.get("game_id") or "",
            to_int_or_none(row.get("person_id")) or -1,
            row.get("source_shot_type_key") or "",
        )
    )
    for index, row in enumerate(fact_rows, start=1):
        row["fct_player_game_shot_type_source_sk"] = index

    return fact_rows


def select_preview_rows(
    fact_rows: list[dict[str, Any]],
    *,
    row_limit: int,
) -> list[dict[str, Any]]:
    sorted_facts = sorted(
        fact_rows,
        key=lambda row: (
            -(to_int_or_none(row.get("field_goals_attempted")) or 0),
            row.get("game_id") or "",
            to_int_or_none(row.get("person_id")) or -1,
            row.get("source_shot_type_key") or "",
        ),
    )

    selected: list[dict[str, Any]] = []
    seen_shot_types: set[str] = set()
    for row in sorted_facts:
        shot_type_key = to_str_or_none(row.get("source_shot_type_key"))
        if shot_type_key is None or shot_type_key in seen_shot_types:
            continue
        selected.append(dict(row))
        seen_shot_types.add(shot_type_key)
        if len(selected) == row_limit:
            break

    if len(selected) < row_limit:
        used_keys = {
            (
                row.get("game_id"),
                to_int_or_none(row.get("person_id")),
                row.get("source_shot_type_key"),
            )
            for row in selected
        }
        for row in sorted_facts:
            row_key = (
                row.get("game_id"),
                to_int_or_none(row.get("person_id")),
                row.get("source_shot_type_key"),
            )
            if row_key in used_keys:
                continue
            selected.append(dict(row))
            used_keys.add(row_key)
            if len(selected) == row_limit:
                break

    selected.sort(
        key=lambda row: (
            row.get("game_id") or "",
            to_int_or_none(row.get("person_id")) or -1,
            row.get("source_shot_type_key") or "",
        )
    )
    for index, row in enumerate(selected, start=1):
        row["fct_player_game_shot_type_source_sk"] = index
    return selected


def main() -> None:
    player_fact_rows = _read_single_parquet_rows_from_s3(PLAYER_FACT_KEY, PLAYER_FACT_REQUIRED_COLUMNS)
    team_fact_rows = _read_single_parquet_rows_from_s3(TEAM_FACT_KEY, TEAM_FACT_REQUIRED_COLUMNS)

    fact_rows = build_shot_type_rows(
        player_fact_rows,
        team_fact_rows,
        max_workers=MAX_WORKERS,
        target_game_ids=TARGET_GAME_IDS or None,
    )

    destination_key = DESTINATION_KEY
    if PREVIEW_ROW_LIMIT is not None and PREVIEW_ROW_LIMIT > 0:
        fact_rows = select_preview_rows(fact_rows, row_limit=PREVIEW_ROW_LIMIT)
        destination_key = PREVIEW_DESTINATION_KEY

    s3_client = boto3.client("s3")
    write_parquet_to_s3(fact_rows, FACT_TARGET_SCHEMA, destination_key, s3_client)
    print(
        "Wrote player-game shot-type source output:",
        {
            "fact_row_count": len(fact_rows),
            "target_game_ids": sorted(TARGET_GAME_IDS),
            "preview_row_limit": PREVIEW_ROW_LIMIT,
            "destination_key": destination_key,
        },
    )


if __name__ == "__main__":
    main()
