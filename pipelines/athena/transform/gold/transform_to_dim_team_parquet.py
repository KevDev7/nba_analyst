"""
Build gold dim_team as an SCD2 dimension from silver team/game history.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_player_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/scheduleLeagueV2_1.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_game.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/gold/dim_team/dim_team.parquet
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
from dotenv import load_dotenv

try:
    from .gold_transform_helpers import (
        S3_BUCKET,
        TEAM_CONTEXT_BY_ID,
        best_row,
        normalize_game_id,
        parse_date_or_none,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        team_context_for_id,
        to_int_or_none,
        to_positive_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
    from .scd2_utils import assign_surrogate_keys, build_scd2_versions
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        S3_BUCKET,
        TEAM_CONTEXT_BY_ID,
        best_row,
        normalize_game_id,
        parse_date_or_none,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        team_context_for_id,
        to_int_or_none,
        to_positive_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
    from scd2_utils import assign_surrogate_keys, build_scd2_versions  # type: ignore[no-redef]

load_dotenv(override=True)

TEAM_GAME_SOURCE_KEY = "silver/boxscore_team_game.parquet"
PLAYER_GAME_SOURCE_KEY = "silver/boxscore_player_game.parquet"
SCHEDULE_SOURCE_KEY = "silver/scheduleLeagueV2_1.parquet"
GAME_SOURCE_KEY = "silver/boxscore_game.parquet"
DESTINATION_KEY = "gold/dim_team/dim_team.parquet"

RECORD_SOURCE = f"{TEAM_GAME_SOURCE_KEY}|{PLAYER_GAME_SOURCE_KEY}|{SCHEDULE_SOURCE_KEY}|{GAME_SOURCE_KEY}"
TRACKED_COLS = ["team_name", "team_city", "team_abbreviation", "team_slug"]

TEAM_GAME_REQUIRED_COLUMNS = ["gameId", "teamId", "teamName", "teamCity", "teamTricode"]
PLAYER_GAME_REQUIRED_COLUMNS = ["gameId", "teamId"]
SCHEDULE_REQUIRED_COLUMNS = [
    "gameId",
    "gameDate",
    "gameDateTimeUTC",
    "homeTeamId",
    "homeTeamName",
    "homeTeamCity",
    "homeTeamTricode",
    "homeTeamSlug",
    "awayTeamId",
    "awayTeamName",
    "awayTeamCity",
    "awayTeamTricode",
    "awayTeamSlug",
]
GAME_REQUIRED_COLUMNS = ["gameId", "gameTimeUTC"]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("team_sk", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("team_name", pa.string()),
        pa.field("team_city", pa.string()),
        pa.field("team_abbreviation", pa.string()),
        pa.field("team_slug", pa.string()),
        pa.field("first_seen_game_date", pa.date32()),
        pa.field("last_seen_game_date", pa.date32()),
        pa.field("record_source", pa.string()),
        pa.field("valid_from_utc", pa.timestamp("us", tz="UTC")),
        pa.field("valid_to_utc", pa.timestamp("us", tz="UTC")),
        pa.field("is_current", pa.int64()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("conference", pa.string()),
        pa.field("division", pa.string()),
    ]
)


def build_schedule_events(schedule_table: pa.Table) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in schedule_table.to_pylist():
        game_id = normalize_game_id(row.get("gameId"))
        if game_id is None:
            continue
        game_time_utc = parse_timestamp_utc(row.get("gameDateTimeUTC"))
        game_date = parse_date_or_none(row.get("gameDate")) or (game_time_utc.date() if game_time_utc else None)
        for side in ("home", "away"):
            team_id = to_positive_int_or_none(row.get(f"{side}TeamId"))
            if team_id is None:
                continue
            events.append(
                {
                    "game_id": game_id,
                    "game_time_utc": game_time_utc,
                    "game_date": game_date,
                    "team_id": team_id,
                    "team_name": to_str_or_none(row.get(f"{side}TeamName")),
                    "team_city": to_str_or_none(row.get(f"{side}TeamCity")),
                    "team_abbreviation": to_str_or_none(row.get(f"{side}TeamTricode")),
                    "team_slug": to_str_or_none(row.get(f"{side}TeamSlug")),
                    "_source_priority": 2,
                }
            )
    return events


def build_boxscore_time_map(game_table: pa.Table) -> dict[str, datetime | None]:
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


def build_team_game_events(team_game_table: pa.Table, game_time_by_id: dict[str, datetime | None]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in team_game_table.to_pylist():
        team_id = to_positive_int_or_none(row.get("teamId"))
        game_id = normalize_game_id(row.get("gameId"))
        if team_id is None or game_id is None:
            continue
        game_time_utc = game_time_by_id.get(game_id)
        events.append(
            {
                "game_id": game_id,
                "game_time_utc": game_time_utc,
                "game_date": game_time_utc.date() if game_time_utc is not None else None,
                "team_id": team_id,
                "team_name": to_str_or_none(row.get("teamName")),
                "team_city": to_str_or_none(row.get("teamCity")),
                "team_abbreviation": to_str_or_none(row.get("teamTricode")),
                "team_slug": None,
                "_source_priority": 1,
            }
        )
    return events


def build_player_game_team_fallback_events(
    player_game_table: pa.Table,
    game_time_by_id: dict[str, datetime | None],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen_keys: set[tuple[int, str]] = set()
    for row in player_game_table.to_pylist():
        team_id = to_positive_int_or_none(row.get("teamId"))
        game_id = normalize_game_id(row.get("gameId"))
        if team_id is None or game_id is None:
            continue
        key = (team_id, game_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        game_time_utc = game_time_by_id.get(game_id)
        events.append(
            {
                "game_id": game_id,
                "game_time_utc": game_time_utc,
                "game_date": game_time_utc.date() if game_time_utc is not None else None,
                "team_id": team_id,
                "team_name": None,
                "team_city": None,
                "team_abbreviation": None,
                "team_slug": None,
                "_source_priority": 0,
            }
        )
    return events


def dedupe_team_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[int, str], dict[str, Any]] = {}
    for event in events:
        key = (event["team_id"], event["game_id"])
        quality_keys = ["team_name", "team_city", "team_abbreviation", "team_slug"]
        current = deduped.get(key)
        candidate = best_row(
            current,
            event,
            quality_keys=quality_keys,
            preferred_timestamp_keys=["game_time_utc"],
        )
        if current is not None and candidate is current:
            current_priority = current.get("_source_priority") or 0
            candidate_priority = event.get("_source_priority") or 0
            if candidate_priority > current_priority:
                candidate = event
        deduped[key] = candidate
    return [dict(event, _source_priority=None) for event in deduped.values()]


def finalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    output: list[dict[str, Any]] = []
    for row in rows:
        context = team_context_for_id(row.get("team_id")) or {}
        output.append(
            {
                "team_sk": row.get("team_sk"),
                "team_id": row.get("team_id"),
                "team_name": row.get("team_name"),
                "team_city": row.get("team_city"),
                "team_abbreviation": row.get("team_abbreviation"),
                "team_slug": row.get("team_slug"),
                "first_seen_game_date": row.get("first_seen_game_date"),
                "last_seen_game_date": row.get("last_seen_game_date"),
                "record_source": row.get("record_source"),
                "valid_from_utc": row.get("valid_from_utc"),
                "valid_to_utc": row.get("valid_to_utc"),
                "is_current": to_int_or_none(row.get("is_current")) or 0,
                "created_at_utc": run_ts,
                "updated_at_utc": run_ts,
                "conference": context.get("conference"),
                "division": context.get("division"),
            }
        )
    return output


def main() -> None:
    s3_client = boto3.client("s3")
    team_game_table = read_parquet_table_from_s3(s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS)
    player_game_table = read_parquet_table_from_s3(s3_client, PLAYER_GAME_SOURCE_KEY, PLAYER_GAME_REQUIRED_COLUMNS)
    schedule_table = read_parquet_table_from_s3(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    game_table = read_parquet_table_from_s3(s3_client, GAME_SOURCE_KEY, GAME_REQUIRED_COLUMNS)
    game_time_by_id = build_boxscore_time_map(game_table)

    events = dedupe_team_events(
        build_schedule_events(schedule_table)
        + build_team_game_events(team_game_table, game_time_by_id)
        + build_player_game_team_fallback_events(player_game_table, game_time_by_id)
    )
    versions = build_scd2_versions(
        events=events,
        entity_id_col="team_id",
        tracked_cols=TRACKED_COLS,
        carry_forward_cols=TRACKED_COLS,
        event_time_col="game_time_utc",
        event_date_col="game_date",
        event_order_cols=["game_time_utc", "game_id"],
        record_source=RECORD_SOURCE,
    )
    keyed_rows = assign_surrogate_keys(
        versions,
        sk_col="team_sk",
        sort_keys=["team_id", "valid_from_utc", "team_name"],
    )
    write_parquet_to_s3(finalize_rows(keyed_rows), TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
