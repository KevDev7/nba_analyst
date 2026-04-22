"""
Build gold dim_game as a Type-1 game dimension from silver game sources.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/scheduleLeagueV2_1.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_game/dim_game.parquet
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
from dotenv import load_dotenv

try:
    from .gold_transform_helpers import (
        S3_BUCKET,
        best_row,
        canonical_season_start_year_from_date,
        canonical_season_year_from_date,
        localized_date_from_timestamp,
        parse_iso_duration_minutes,
        parse_date_or_none,
        parse_game_code_date,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        season_type_label_from_code,
        to_bool_or_none,
        to_int_or_none,
        to_positive_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        S3_BUCKET,
        best_row,
        canonical_season_start_year_from_date,
        canonical_season_year_from_date,
        localized_date_from_timestamp,
        parse_iso_duration_minutes,
        parse_date_or_none,
        parse_game_code_date,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        season_type_label_from_code,
        to_bool_or_none,
        to_int_or_none,
        to_positive_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )

load_dotenv(override=True)

BOXSCORE_SOURCE_KEY = "silver/boxscore_game.parquet"
TEAM_GAME_SOURCE_KEY = "silver/boxscore_team_game.parquet"
SCHEDULE_SOURCE_KEY = "silver/scheduleLeagueV2_1.parquet"
DESTINATION_KEY = "legacy_gold/dim_game/dim_game.parquet"
RECORD_SOURCE = "silver.boxscore_game|silver.boxscore_team_game|silver.schedule"

BOXSCORE_REQUIRED_COLUMNS = [
    "meta_version",
    "meta_code",
    "meta_request",
    "meta_time",
    "gameId",
    "gameCode",
    "gameTimeLocal",
    "gameTimeUTC",
    "gameTimeHome",
    "gameTimeAway",
    "gameEt",
    "duration",
    "gameStatus",
    "gameStatusText",
    "regulationPeriods",
    "period",
    "gameClock",
    "attendance",
    "sellout",
    "arenaId",
    "arenaName",
    "arenaCity",
    "arenaState",
    "arenaCountry",
    "arenaTimezone",
]

SCHEDULE_REQUIRED_COLUMNS = [
    "seasonYear",
    "leagueId",
    "gameId",
    "gameCode",
    "gameSequence",
    "gameDate",
    "gameDateTimeUTC",
    "gameStatus",
    "gameStatusText",
    "postponedStatus",
    "ifNecessary",
    "gameLabel",
    "gameSubLabel",
    "gameSubtype",
    "seriesGameNumber",
    "seriesText",
    "isNeutral",
    "arenaName",
    "arenaCity",
    "arenaState",
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

TEAM_GAME_REQUIRED_COLUMNS = [
    "gameId",
    "team_side",
    "teamId",
    "teamName",
    "teamCity",
    "teamTricode",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("game_sk", pa.int64()),
        pa.field("game_id", pa.string()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("league_id", pa.string()),
        pa.field("game_code", pa.string()),
        pa.field("game_sequence", pa.int64()),
        pa.field("game_date", pa.date32()),
        pa.field("game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("local_market_game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("home_market_game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("away_market_game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("eastern_time_game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("game_status_code", pa.int64()),
        pa.field("game_status_text", pa.string()),
        pa.field("postponed_status", pa.string()),
        pa.field("is_if_necessary", pa.bool_()),
        pa.field("game_label", pa.string()),
        pa.field("game_sublabel", pa.string()),
        pa.field("game_subtype", pa.string()),
        pa.field("series_game_number", pa.string()),
        pa.field("series_text", pa.string()),
        pa.field("is_neutral_site", pa.bool_()),
        pa.field("duration_minutes", pa.int64()),
        pa.field("attendance", pa.int64()),
        pa.field("is_sellout", pa.bool_()),
        pa.field("regulation_periods", pa.int64()),
        pa.field("current_period", pa.int64()),
        pa.field("game_clock", pa.string()),
        pa.field("arena_id", pa.int64()),
        pa.field("arena_name", pa.string()),
        pa.field("arena_city", pa.string()),
        pa.field("arena_state", pa.string()),
        pa.field("arena_country", pa.string()),
        pa.field("arena_timezone", pa.string()),
        pa.field("home_team_id", pa.int64()),
        pa.field("away_team_id", pa.int64()),
        pa.field("home_team_name", pa.string()),
        pa.field("away_team_name", pa.string()),
        pa.field("home_team_city", pa.string()),
        pa.field("away_team_city", pa.string()),
        pa.field("home_team_abbreviation", pa.string()),
        pa.field("away_team_abbreviation", pa.string()),
        pa.field("home_team_slug", pa.string()),
        pa.field("away_team_slug", pa.string()),
        pa.field("source_meta_version", pa.int64()),
        pa.field("source_meta_code", pa.int64()),
        pa.field("source_request", pa.string()),
        pa.field("source_meta_time_utc", pa.timestamp("us", tz="UTC")),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)


def coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def build_boxscore_map(box_table: pa.Table) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for row in box_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId"))
        if game_id is None:
            continue
        candidate = {
            "game_id": game_id,
            "game_code": to_str_or_none(row.get("gameCode")),
            "local_market_game_datetime_utc": parse_timestamp_utc(row.get("gameTimeLocal")),
            "game_time_utc": parse_timestamp_utc(row.get("gameTimeUTC")),
            "home_market_game_datetime_utc": parse_timestamp_utc(row.get("gameTimeHome")),
            "away_market_game_datetime_utc": parse_timestamp_utc(row.get("gameTimeAway")),
            "eastern_time_game_datetime_utc": parse_timestamp_utc(row.get("gameEt")),
            "game_status_code": to_int_or_none(row.get("gameStatus")),
            "game_status_text": to_str_or_none(row.get("gameStatusText")),
            "duration_minutes": coalesce(
                to_int_or_none(row.get("duration")),
                parse_iso_duration_minutes(row.get("duration")),
            ),
            "attendance": to_int_or_none(row.get("attendance")),
            "is_sellout": to_bool_or_none(row.get("sellout")),
            "regulation_periods": to_int_or_none(row.get("regulationPeriods")),
            "current_period": to_int_or_none(row.get("period")),
            "game_clock": to_str_or_none(row.get("gameClock")),
            "arena_id": to_int_or_none(row.get("arenaId")),
            "arena_name": to_str_or_none(row.get("arenaName")),
            "arena_city": to_str_or_none(row.get("arenaCity")),
            "arena_state": to_str_or_none(row.get("arenaState")),
            "arena_country": to_str_or_none(row.get("arenaCountry")),
            "arena_timezone": to_str_or_none(row.get("arenaTimezone")),
            "source_meta_version": to_int_or_none(row.get("meta_version")),
            "source_meta_code": to_int_or_none(row.get("meta_code")),
            "source_request": to_str_or_none(row.get("meta_request")),
            "source_meta_time_utc": parse_timestamp_utc(row.get("meta_time")),
            "raw_game_time_utc_date": parse_date_or_none(row.get("gameTimeUTC")),
        }
        records[game_id] = best_row(
            records.get(game_id),
            candidate,
            quality_keys=[
                "game_code",
                "local_market_game_datetime_utc",
                "game_time_utc",
                "game_status_code",
                "arena_name",
                "source_request",
            ],
            preferred_timestamp_keys=["source_meta_time_utc", "game_time_utc"],
        )
    return records


def build_schedule_map(schedule_table: pa.Table) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for row in schedule_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId"))
        if game_id is None:
            continue
        candidate = {
            "game_id": game_id,
            "raw_schedule_season_year": to_str_or_none(row.get("seasonYear")),
            "league_id": to_str_or_none(row.get("leagueId")),
            "game_code": to_str_or_none(row.get("gameCode")),
            "game_sequence": to_int_or_none(row.get("gameSequence")),
            "schedule_game_date": parse_date_or_none(row.get("gameDate")),
            "schedule_game_datetime_utc": parse_timestamp_utc(row.get("gameDateTimeUTC")),
            "game_status_code": to_int_or_none(row.get("gameStatus")),
            "game_status_text": to_str_or_none(row.get("gameStatusText")),
            "postponed_status": to_str_or_none(row.get("postponedStatus")),
            "is_if_necessary": to_bool_or_none(row.get("ifNecessary")),
            "game_label": to_str_or_none(row.get("gameLabel")),
            "game_sublabel": to_str_or_none(row.get("gameSubLabel")),
            "game_subtype": to_str_or_none(row.get("gameSubtype")),
            "series_game_number": to_str_or_none(row.get("seriesGameNumber")),
            "series_text": to_str_or_none(row.get("seriesText")),
            "is_neutral_site": to_bool_or_none(row.get("isNeutral")),
            "arena_name": to_str_or_none(row.get("arenaName")),
            "arena_city": to_str_or_none(row.get("arenaCity")),
            "arena_state": to_str_or_none(row.get("arenaState")),
            "home_team_id": to_positive_int_or_none(row.get("homeTeamId")),
            "away_team_id": to_positive_int_or_none(row.get("awayTeamId")),
            "home_team_name": to_str_or_none(row.get("homeTeamName")),
            "away_team_name": to_str_or_none(row.get("awayTeamName")),
            "home_team_city": to_str_or_none(row.get("homeTeamCity")),
            "away_team_city": to_str_or_none(row.get("awayTeamCity")),
            "home_team_abbreviation": to_str_or_none(row.get("homeTeamTricode")),
            "away_team_abbreviation": to_str_or_none(row.get("awayTeamTricode")),
            "home_team_slug": to_str_or_none(row.get("homeTeamSlug")),
            "away_team_slug": to_str_or_none(row.get("awayTeamSlug")),
        }
        records[game_id] = best_row(
            records.get(game_id),
            candidate,
            quality_keys=[
                "raw_schedule_season_year",
                "game_code",
                "schedule_game_date",
                "home_team_id",
                "away_team_id",
                "home_team_slug",
                "away_team_slug",
            ],
            preferred_timestamp_keys=["schedule_game_datetime_utc"],
        )
    return records


def build_team_side_map(team_game_table: pa.Table) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for row in team_game_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId"))
        side = to_str_or_none(row.get("team_side"))
        if game_id is None or side not in {"home", "away"}:
            continue
        entry = records.setdefault(
            game_id,
            {
                "home_team_id": None,
                "away_team_id": None,
                "home_team_name": None,
                "away_team_name": None,
                "home_team_city": None,
                "away_team_city": None,
                "home_team_abbreviation": None,
                "away_team_abbreviation": None,
            },
        )
        entry[f"{side}_team_id"] = coalesce(entry.get(f"{side}_team_id"), to_positive_int_or_none(row.get("teamId")))
        entry[f"{side}_team_name"] = coalesce(entry.get(f"{side}_team_name"), to_str_or_none(row.get("teamName")))
        entry[f"{side}_team_city"] = coalesce(entry.get(f"{side}_team_city"), to_str_or_none(row.get("teamCity")))
        entry[f"{side}_team_abbreviation"] = coalesce(entry.get(f"{side}_team_abbreviation"), to_str_or_none(row.get("teamTricode")))
    return records


def _game_date_source(
    schedule_game_date: date | None,
    game_code_date: date | None,
    home_local_game_date: date | None,
    utc_local_game_date: date | None,
) -> tuple[date | None, str | None]:
    if schedule_game_date is not None:
        return schedule_game_date, "schedule_game_date"
    if game_code_date is not None:
        return game_code_date, "game_code_date"
    if home_local_game_date is not None:
        return home_local_game_date, "home_local_game_date"
    if utc_local_game_date is not None:
        return utc_local_game_date, "utc_local_game_date"
    return None, None


def _raw_season_type_code(game_id: str | None) -> str | None:
    if game_id is None or len(game_id) < 3:
        return None
    code = game_id[:3]
    return code if code.isdigit() else None


def build_dim_game_rows(
    box_map: dict[str, dict[str, Any]],
    schedule_map: dict[str, dict[str, Any]],
    team_side_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    all_game_ids = sorted(set(box_map) | set(schedule_map))
    rows: list[dict[str, Any]] = []

    for game_id in all_game_ids:
        box = box_map.get(game_id, {})
        schedule = schedule_map.get(game_id, {})
        team_side = team_side_map.get(game_id, {})

        game_code = coalesce(schedule.get("game_code"), box.get("game_code"))
        game_datetime_utc = coalesce(schedule.get("schedule_game_datetime_utc"), box.get("game_time_utc"))
        game_code_date = parse_game_code_date(game_code)
        home_local_game_date = localized_date_from_timestamp(
            box.get("home_market_game_datetime_utc"), box.get("arena_timezone")
        )
        utc_local_game_date = localized_date_from_timestamp(box.get("game_time_utc"), box.get("arena_timezone"))
        utc_fallback_game_date = box.get("raw_game_time_utc_date")
        game_date, game_date_source = _game_date_source(
            schedule.get("schedule_game_date"),
            game_code_date,
            home_local_game_date,
            utc_local_game_date,
        )
        if game_date is None and utc_fallback_game_date is not None:
            game_date = utc_fallback_game_date
            game_date_source = "utc_fallback"

        raw_season_type_code = _raw_season_type_code(game_id)

        row = {
            "game_id": game_id,
            "season_year": canonical_season_year_from_date(game_date),
            "season_start_year": canonical_season_start_year_from_date(game_date),
            "league_id": schedule.get("league_id"),
            "game_code": game_code,
            "game_sequence": schedule.get("game_sequence"),
            "game_date": game_date,
            "game_datetime_utc": game_datetime_utc,
            "local_market_game_datetime_utc": box.get("local_market_game_datetime_utc"),
            "home_market_game_datetime_utc": box.get("home_market_game_datetime_utc"),
            "away_market_game_datetime_utc": box.get("away_market_game_datetime_utc"),
            "eastern_time_game_datetime_utc": box.get("eastern_time_game_datetime_utc"),
            "game_status_code": coalesce(box.get("game_status_code"), schedule.get("game_status_code")),
            "game_status_text": coalesce(box.get("game_status_text"), schedule.get("game_status_text")),
            "postponed_status": schedule.get("postponed_status"),
            "is_if_necessary": schedule.get("is_if_necessary"),
            "game_label": schedule.get("game_label"),
            "game_sublabel": schedule.get("game_sublabel"),
            "game_subtype": schedule.get("game_subtype"),
            "series_game_number": schedule.get("series_game_number"),
            "series_text": schedule.get("series_text"),
            "is_neutral_site": schedule.get("is_neutral_site"),
            "duration_minutes": box.get("duration_minutes"),
            "attendance": box.get("attendance"),
            "is_sellout": box.get("is_sellout"),
            "regulation_periods": box.get("regulation_periods"),
            "current_period": box.get("current_period"),
            "game_clock": box.get("game_clock"),
            "arena_id": box.get("arena_id"),
            "arena_name": coalesce(box.get("arena_name"), schedule.get("arena_name")),
            "arena_city": coalesce(box.get("arena_city"), schedule.get("arena_city")),
            "arena_state": coalesce(box.get("arena_state"), schedule.get("arena_state")),
            "arena_country": box.get("arena_country"),
            "arena_timezone": box.get("arena_timezone"),
            "home_team_id": coalesce(schedule.get("home_team_id"), team_side.get("home_team_id")),
            "away_team_id": coalesce(schedule.get("away_team_id"), team_side.get("away_team_id")),
            "home_team_name": coalesce(schedule.get("home_team_name"), team_side.get("home_team_name")),
            "away_team_name": coalesce(schedule.get("away_team_name"), team_side.get("away_team_name")),
            "home_team_city": coalesce(schedule.get("home_team_city"), team_side.get("home_team_city")),
            "away_team_city": coalesce(schedule.get("away_team_city"), team_side.get("away_team_city")),
            "home_team_abbreviation": coalesce(schedule.get("home_team_abbreviation"), team_side.get("home_team_abbreviation")),
            "away_team_abbreviation": coalesce(schedule.get("away_team_abbreviation"), team_side.get("away_team_abbreviation")),
            "home_team_slug": schedule.get("home_team_slug"),
            "away_team_slug": schedule.get("away_team_slug"),
            "source_meta_version": box.get("source_meta_version"),
            "source_meta_code": box.get("source_meta_code"),
            "source_request": box.get("source_request"),
            "source_meta_time_utc": box.get("source_meta_time_utc"),
            "record_source": RECORD_SOURCE,
            "created_at_utc": run_ts,
            "updated_at_utc": run_ts,
            "raw_season_type_code": raw_season_type_code,
            "season_type": season_type_label_from_code(raw_season_type_code),
            "raw_schedule_season_year": schedule.get("raw_schedule_season_year"),
            "raw_schedule_season_start_year": (
                int(str(schedule.get("raw_schedule_season_year"))[:4])
                if schedule.get("raw_schedule_season_year") and str(schedule.get("raw_schedule_season_year"))[:4].isdigit()
                else None
            ),
            "schedule_game_date": schedule.get("schedule_game_date"),
            "game_code_date": game_code_date,
            "home_local_game_date": home_local_game_date,
            "utc_local_game_date": utc_local_game_date,
            "utc_fallback_game_date": utc_fallback_game_date,
            "game_date_source": game_date_source,
        }

        rows.append(row)

    for index, row in enumerate(rows, start=1):
        row["game_sk"] = index
    return rows


def raise_if_schedule_season_mismatch(rows: list[dict[str, Any]]) -> None:
    bad_rows = [
        {
            "game_id": row["game_id"],
            "raw_schedule_season_year": row["raw_schedule_season_year"],
            "season_year": row["season_year"],
            "season_start_year": row["season_start_year"],
        }
        for row in rows
        if row.get("raw_schedule_season_start_year") is not None
        and row.get("season_start_year") is not None
        and row["raw_schedule_season_start_year"] != row["season_start_year"]
    ]
    if bad_rows:
        raise ValueError(f"dim_game schedule season mismatch detected: {bad_rows[:10]}")


def raise_if_game_date_audit_mismatch(rows: list[dict[str, Any]]) -> None:
    bad_rows = []
    for row in rows:
        game_date = row.get("game_date")
        if game_date is None:
            continue
        audit_candidates = {
            "schedule_game_date": row.get("schedule_game_date"),
            "game_code_date": row.get("game_code_date"),
            "home_local_game_date": row.get("home_local_game_date"),
            "utc_local_game_date": row.get("utc_local_game_date"),
            "utc_fallback_game_date": row.get("utc_fallback_game_date"),
        }
        if not any(candidate == game_date for candidate in audit_candidates.values() if candidate is not None):
            bad_rows.append(
                {
                    "game_id": row["game_id"],
                    "game_date": game_date,
                    "game_code_date": row.get("game_code_date"),
                    "home_local_game_date": row.get("home_local_game_date"),
                    "utc_local_game_date": row.get("utc_local_game_date"),
                    "utc_fallback_game_date": row.get("utc_fallback_game_date"),
                    "game_date_source": row.get("game_date_source"),
                }
            )
    if bad_rows:
        raise ValueError(f"dim_game game date audit mismatch detected: {bad_rows[:10]}")


def finalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public_columns = TARGET_SCHEMA.names
    return [{column: row.get(column) for column in public_columns} for row in rows]


def main() -> None:
    s3_client = boto3.client("s3")

    box_table = read_parquet_table_from_s3(s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS)
    team_game_table = read_parquet_table_from_s3(s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS)
    schedule_table = read_parquet_table_from_s3(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)

    rows = build_dim_game_rows(
        build_boxscore_map(box_table),
        build_schedule_map(schedule_table),
        build_team_side_map(team_game_table),
    )
    raise_if_schedule_season_mismatch(rows)
    raise_if_game_date_audit_mismatch(rows)

    write_parquet_to_s3(finalize_rows(rows), TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
