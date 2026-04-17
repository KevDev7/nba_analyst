"""Purpose: Build semantic_gold team as a current-state NBA team object from silver sources.
Inputs: Silver schedule, silver team-game, silver team histories, and silver boxscore game rows.
Outputs: One semantic team row per current NBA team_id with clean business-facing fields.
Next file: transform_to_team_game_parquet.py links team_game rows back to this team surface.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import boto3
import pyarrow as pa
from dotenv import load_dotenv

from pipelines.athena.transform.gold.gold_transform_helpers import (
    S3_BUCKET,
    TEAM_CONTEXT_BY_ID,
    best_row,
    parse_date_or_none,
    parse_timestamp_utc,
    read_parquet_table_from_s3,
    team_context_for_id,
    to_positive_int_or_none,
    to_str_or_none,
    write_parquet_to_s3,
)

from .contracts import TEAM_SCHEMA

load_dotenv(override=True)

SCHEDULE_SOURCE_KEY = "silver/scheduleLeagueV2_1.parquet"
TEAM_GAME_SOURCE_KEY = "silver/boxscore_team_game.parquet"
TEAM_HISTORIES_SOURCE_KEY = "silver/team_histories.parquet"
GAME_SOURCE_KEY = "silver/boxscore_game.parquet"
DESTINATION_KEY = "semantic_gold/team/team.parquet"

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
TEAM_GAME_REQUIRED_COLUMNS = ["gameId", "teamId", "teamName", "teamCity", "teamTricode"]
TEAM_HISTORIES_REQUIRED_COLUMNS = ["teamId", "teamCity", "teamName", "teamAbbrev"]
GAME_REQUIRED_COLUMNS = ["gameId", "gameTimeUTC"]


def build_game_time_map(game_table: pa.Table) -> dict[str, object]:
    output: dict[str, object] = {}
    for row in game_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId"))
        if game_id is None:
            continue
        candidate = parse_timestamp_utc(row.get("gameTimeUTC"))
        current = output.get(game_id)
        if current is None or (candidate is not None and current is not None and candidate > current):
            output[game_id] = candidate
    return output


def build_schedule_events(schedule_table: pa.Table) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in schedule_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId"))
        game_date = parse_date_or_none(row.get("gameDate"))
        game_time_utc = parse_timestamp_utc(row.get("gameDateTimeUTC"))
        if game_id is None:
            continue
        for side in ("home", "away"):
            team_id = to_positive_int_or_none(row.get(f"{side}TeamId"))
            if team_id is None:
                continue
            events.append(
                {
                    "team_id": team_id,
                    "game_id": game_id,
                    "game_date": game_date or (game_time_utc.date() if game_time_utc is not None else None),
                    "game_time_utc": game_time_utc,
                    "team_name": to_str_or_none(row.get(f"{side}TeamName")),
                    "team_city": to_str_or_none(row.get(f"{side}TeamCity")),
                    "team_abbreviation": to_str_or_none(row.get(f"{side}TeamTricode")),
                    "team_slug": to_str_or_none(row.get(f"{side}TeamSlug")),
                }
            )
    return events


def build_team_game_events(team_game_table: pa.Table, game_time_by_id: dict[str, object]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in team_game_table.to_pylist():
        team_id = to_positive_int_or_none(row.get("teamId"))
        game_id = to_str_or_none(row.get("gameId"))
        if team_id is None or game_id is None:
            continue
        game_time_utc = game_time_by_id.get(game_id)
        events.append(
            {
                "team_id": team_id,
                "game_id": game_id,
                "game_date": game_time_utc.date() if game_time_utc is not None else None,
                "game_time_utc": game_time_utc,
                "team_name": to_str_or_none(row.get("teamName")),
                "team_city": to_str_or_none(row.get("teamCity")),
                "team_abbreviation": to_str_or_none(row.get("teamTricode")),
                "team_slug": None,
            }
        )
    return events


def build_history_fallbacks(team_histories_table: pa.Table) -> dict[int, dict[str, Any]]:
    fallbacks: dict[int, dict[str, Any]] = {}
    for row in team_histories_table.to_pylist():
        team_id = to_positive_int_or_none(row.get("teamId"))
        if team_id is None:
            continue
        candidate = {
            "team_name": to_str_or_none(row.get("teamName")),
            "team_city": to_str_or_none(row.get("teamCity")),
            "team_abbreviation": to_str_or_none(row.get("teamAbbrev")),
        }
        fallbacks[team_id] = best_row(
            fallbacks.get(team_id),
            candidate,
            quality_keys=["team_name", "team_city", "team_abbreviation"],
        )
    return fallbacks


def build_team_rows_from_tables(
    schedule_table: pa.Table,
    team_game_table: pa.Table,
    team_histories_table: pa.Table,
    game_table: pa.Table,
) -> list[dict[str, object]]:
    game_time_by_id = build_game_time_map(game_table)
    current_team_ids = sorted(TEAM_CONTEXT_BY_ID.keys())
    fallbacks = build_history_fallbacks(team_histories_table)

    events_by_team: dict[int, list[dict[str, Any]]] = {team_id: [] for team_id in current_team_ids}
    for event in build_schedule_events(schedule_table) + build_team_game_events(team_game_table, game_time_by_id):
        team_id = event["team_id"]
        if team_id in events_by_team:
            events_by_team[team_id].append(event)

    rows: list[dict[str, object]] = []
    for team_id in current_team_ids:
        latest: dict[str, Any] = {}
        first_seen: date | None = None
        last_seen: date | None = None
        for event in sorted(
            events_by_team.get(team_id, []),
            key=lambda row: (row.get("game_time_utc") is not None, row.get("game_time_utc"), row.get("game_id") or ""),
        ):
            latest = best_row(
                latest or None,
                event,
                quality_keys=["team_name", "team_city", "team_abbreviation", "team_slug"],
                preferred_timestamp_keys=["game_time_utc"],
            )
            event_date = event.get("game_date")
            if event_date is not None:
                first_seen = event_date if first_seen is None or event_date < first_seen else first_seen
                last_seen = event_date if last_seen is None or event_date > last_seen else last_seen

        fallback = fallbacks.get(team_id, {})
        context = team_context_for_id(team_id) or {}
        rows.append(
            {
                "team_id": team_id,
                "team_name": latest.get("team_name") or fallback.get("team_name"),
                "team_city": latest.get("team_city") or fallback.get("team_city"),
                "team_abbreviation": latest.get("team_abbreviation") or fallback.get("team_abbreviation"),
                "team_slug": latest.get("team_slug"),
                "conference": context.get("conference"),
                "division": context.get("division"),
                "first_seen_game_date": first_seen,
                "last_seen_game_date": last_seen,
            }
        )
    return rows


def main() -> None:
    s3_client = boto3.client("s3")
    schedule_table = read_parquet_table_from_s3(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    team_game_table = read_parquet_table_from_s3(s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS)
    team_histories_table = read_parquet_table_from_s3(s3_client, TEAM_HISTORIES_SOURCE_KEY, TEAM_HISTORIES_REQUIRED_COLUMNS)
    game_table = read_parquet_table_from_s3(s3_client, GAME_SOURCE_KEY, GAME_REQUIRED_COLUMNS)
    rows = build_team_rows_from_tables(schedule_table, team_game_table, team_histories_table, game_table)
    write_parquet_to_s3(rows, TEAM_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
