"""
Build gold fct_player_game from silver boxscore player-game rows.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_player_game.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_game/dim_game.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_date/dim_date.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_player/dim_player.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_team/dim_team.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_player_game/fct_player_game.parquet
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.gold.gold_transform_helpers import (
        S3_BUCKET,
        normalize_game_id,
        parse_date_or_none,
        parse_iso_duration_seconds,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        to_float_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
    from pipelines.athena.transform.gold.scd2_utils import resolve_scd2_sk
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        S3_BUCKET,
        normalize_game_id,
        parse_date_or_none,
        parse_iso_duration_seconds,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        to_float_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
    from scd2_utils import resolve_scd2_sk  # type: ignore[no-redef]

load_dotenv(override=True)

PLAYER_SOURCE_KEY = "silver/boxscore_player_game.parquet"
DIM_GAME_KEY = "legacy_gold/dim_game/dim_game.parquet"
DIM_DATE_KEY = "legacy_gold/dim_date/dim_date.parquet"
DIM_PLAYER_KEY = "legacy_gold/dim_player/dim_player.parquet"
DIM_TEAM_KEY = "legacy_gold/dim_team/dim_team.parquet"
DESTINATION_KEY = "legacy_gold/fct_player_game/fct_player_game.parquet"

RECORD_SOURCE = "silver.boxscore_player_game|gold.dim_game|gold.dim_date|gold.dim_player|gold.dim_team"

PLAYER_REQUIRED_COLUMNS = [
    "gameId",
    "teamId",
    "team_side",
    "personId",
    "position",
    "status",
    "order",
    "starter",
    "oncourt",
    "played",
    "minutes",
    "minutesCalculated",
    "plus",
    "minus",
    "plusMinusPoints",
    "assists",
    "blocks",
    "blocksReceived",
    "fieldGoalsAttempted",
    "fieldGoalsMade",
    "fieldGoalsPercentage",
    "foulsOffensive",
    "foulsDrawn",
    "foulsPersonal",
    "foulsTechnical",
    "freeThrowsAttempted",
    "freeThrowsMade",
    "freeThrowsPercentage",
    "reboundsDefensive",
    "reboundsOffensive",
    "reboundsTotal",
    "steals",
    "turnovers",
    "points",
    "threePointersAttempted",
    "threePointersMade",
    "threePointersPercentage",
    "twoPointersAttempted",
    "twoPointersMade",
    "twoPointersPercentage",
    "pointsFastBreak",
    "pointsInThePaint",
    "pointsSecondChance",
]

DIM_GAME_REQUIRED_COLUMNS = [
    "game_id",
    "game_sk",
    "game_date",
    "game_datetime_utc",
    "season_year",
    "season_start_year",
    "raw_season_type_code",
    "season_type",
]

DIM_DATE_REQUIRED_COLUMNS = [
    "calendar_date",
    "date_sk",
]

DIM_PLAYER_REQUIRED_COLUMNS = [
    "player_sk",
    "person_id",
    "valid_from_utc",
    "valid_to_utc",
    "is_current",
]

DIM_TEAM_REQUIRED_COLUMNS = [
    "team_sk",
    "team_id",
    "team_name",
    "team_abbreviation",
    "valid_from_utc",
    "valid_to_utc",
    "is_current",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("fct_player_game_sk", pa.int64()),
        pa.field("game_sk", pa.int64()),
        pa.field("date_sk", pa.int64()),
        pa.field("player_sk", pa.int64()),
        pa.field("team_sk", pa.int64()),
        pa.field("game_id", pa.string()),
        pa.field("person_id", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("team", pa.string()),
        pa.field("game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("game_date", pa.date32()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("team_side", pa.string()),
        pa.field("player_position", pa.string()),
        pa.field("player_status", pa.string()),
        pa.field("player_order", pa.int64()),
        pa.field("is_starter", pa.int64()),
        pa.field("is_on_court", pa.int64()),
        pa.field("did_play", pa.int64()),
        pa.field("minutes_raw", pa.string()),
        pa.field("minutes_calculated_raw", pa.string()),
        pa.field("raw_plus_value", pa.int64()),
        pa.field("raw_minus_value", pa.int64()),
        pa.field("plus_minus_points", pa.int64()),
        pa.field("assists", pa.int64()),
        pa.field("blocks", pa.int64()),
        pa.field("blocks_received", pa.int64()),
        pa.field("field_goals_attempted", pa.int64()),
        pa.field("field_goals_made", pa.int64()),
        pa.field("field_goals_percentage", pa.float64()),
        pa.field("fouls_offensive", pa.int64()),
        pa.field("fouls_drawn", pa.int64()),
        pa.field("fouls_personal", pa.int64()),
        pa.field("fouls_technical", pa.int64()),
        pa.field("free_throws_attempted", pa.int64()),
        pa.field("free_throws_made", pa.int64()),
        pa.field("free_throws_percentage", pa.float64()),
        pa.field("rebounds_defensive", pa.int64()),
        pa.field("rebounds_offensive", pa.int64()),
        pa.field("rebounds_total", pa.int64()),
        pa.field("steals", pa.int64()),
        pa.field("turnovers", pa.int64()),
        pa.field("points", pa.int64()),
        pa.field("three_pointers_attempted", pa.int64()),
        pa.field("three_pointers_made", pa.int64()),
        pa.field("three_pointers_percentage", pa.float64()),
        pa.field("two_pointers_attempted", pa.int64()),
        pa.field("two_pointers_made", pa.int64()),
        pa.field("two_pointers_percentage", pa.float64()),
        pa.field("points_fast_break", pa.int64()),
        pa.field("points_in_the_paint", pa.int64()),
        pa.field("points_second_chance", pa.int64()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("seconds_played_total", pa.float64()),
        pa.field("minutes_played_decimal", pa.float64()),
    ]
)


def build_dim_game_map(dim_game_table: pa.Table) -> dict[str, dict[str, Any]]:
    game_map: dict[str, dict[str, Any]] = {}
    for row in dim_game_table.to_pylist():
        game_id = normalize_game_id(row.get("game_id"))
        if game_id is None:
            continue

        candidate = {
            "game_sk": to_int_or_none(row.get("game_sk")),
            "game_date": parse_date_or_none(row.get("game_date")),
            "game_datetime_utc": parse_timestamp_utc(row.get("game_datetime_utc")),
            "season_year": to_str_or_none(row.get("season_year")),
            "season_start_year": to_int_or_none(row.get("season_start_year")),
            "raw_season_type_code": to_str_or_none(row.get("raw_season_type_code")),
            "season_type": to_str_or_none(row.get("season_type")),
        }

        current = game_map.get(game_id)
        if current is None:
            game_map[game_id] = candidate
            continue

        current_dt = current.get("game_datetime_utc")
        candidate_dt = candidate.get("game_datetime_utc")
        if current_dt is None and candidate_dt is not None:
            game_map[game_id] = candidate

    return game_map


def build_date_sk_map(dim_date_table: pa.Table) -> dict[date, int]:
    output: dict[date, int] = {}
    for row in dim_date_table.to_pylist():
        calendar_date = parse_date_or_none(row.get("calendar_date"))
        date_sk = to_int_or_none(row.get("date_sk"))
        if calendar_date is None or date_sk is None:
            continue
        output[calendar_date] = date_sk
    return output


def build_team_label_by_sk(dim_team_rows: list[dict[str, Any]]) -> dict[int, str]:
    labels: dict[int, str] = {}
    for row in dim_team_rows:
        team_sk = to_int_or_none(row.get("team_sk"))
        if team_sk is None:
            continue
        label = to_str_or_none(row.get("team_abbreviation")) or to_str_or_none(row.get("team_name"))
        if label is None:
            continue
        labels[team_sk] = label
    return labels


def row_quality_score(row: dict[str, Any]) -> int:
    return sum(
        1
        for key in (
            "team_id",
            "team_side",
            "player_position",
            "player_status",
            "minutes",
            "points",
            "assists",
            "rebounds_total",
        )
        if row.get(key) is not None
    )


def _raise_if_unresolved(rows: list[dict[str, Any]], column_name: str, natural_key_cols: list[str]) -> None:
    unresolved = [row for row in rows if row.get(column_name) is None]
    if not unresolved:
        return
    sample_rows = [{key: row.get(key) for key in natural_key_cols} for row in unresolved[:10]]
    raise ValueError(
        f"Unable to resolve {column_name} for {len(unresolved)} fact rows. Sample keys: {sample_rows}"
    )


def build_base_fact_rows(
    player_table: pa.Table,
    game_map: dict[str, dict[str, Any]],
    date_sk_map: dict[date, int],
) -> list[dict[str, Any]]:
    cols = {column: player_table[column].to_pylist() for column in PLAYER_REQUIRED_COLUMNS}
    dedup_by_key: dict[tuple[str, int], dict[str, Any]] = {}

    for idx in range(player_table.num_rows):
        game_id = normalize_game_id(cols["gameId"][idx])
        person_id = to_int_or_none(cols["personId"][idx])
        if game_id is None or person_id is None:
            continue

        game_attrs = game_map.get(game_id)
        if game_attrs is None:
            continue

        game_date = game_attrs.get("game_date")
        row = {
            "game_id": game_id,
            "person_id": person_id,
            "team_id": to_int_or_none(cols["teamId"][idx]),
            "game_sk": game_attrs.get("game_sk"),
            "date_sk": date_sk_map.get(game_date) if game_date is not None else None,
            "game_datetime_utc": game_attrs.get("game_datetime_utc"),
            "game_date": game_date,
            "team_side": to_str_or_none(cols["team_side"][idx]),
            "player_position": to_str_or_none(cols["position"][idx]),
            "player_status": to_str_or_none(cols["status"][idx]),
            "player_order": to_int_or_none(cols["order"][idx]),
            "is_starter": to_int_or_none(cols["starter"][idx]),
            "is_on_court": to_int_or_none(cols["oncourt"][idx]),
            "did_play": to_int_or_none(cols["played"][idx]),
            "minutes_raw": to_str_or_none(cols["minutes"][idx]),
            "minutes_calculated_raw": to_str_or_none(cols["minutesCalculated"][idx]),
            "raw_plus_value": to_int_or_none(cols["plus"][idx]),
            "raw_minus_value": to_int_or_none(cols["minus"][idx]),
            "plus_minus_points": to_int_or_none(cols["plusMinusPoints"][idx]),
            "assists": to_int_or_none(cols["assists"][idx]),
            "blocks": to_int_or_none(cols["blocks"][idx]),
            "blocks_received": to_int_or_none(cols["blocksReceived"][idx]),
            "field_goals_attempted": to_int_or_none(cols["fieldGoalsAttempted"][idx]),
            "field_goals_made": to_int_or_none(cols["fieldGoalsMade"][idx]),
            "field_goals_percentage": to_float_or_none(cols["fieldGoalsPercentage"][idx]),
            "fouls_offensive": to_int_or_none(cols["foulsOffensive"][idx]),
            "fouls_drawn": to_int_or_none(cols["foulsDrawn"][idx]),
            "fouls_personal": to_int_or_none(cols["foulsPersonal"][idx]),
            "fouls_technical": to_int_or_none(cols["foulsTechnical"][idx]),
            "free_throws_attempted": to_int_or_none(cols["freeThrowsAttempted"][idx]),
            "free_throws_made": to_int_or_none(cols["freeThrowsMade"][idx]),
            "free_throws_percentage": to_float_or_none(cols["freeThrowsPercentage"][idx]),
            "rebounds_defensive": to_int_or_none(cols["reboundsDefensive"][idx]),
            "rebounds_offensive": to_int_or_none(cols["reboundsOffensive"][idx]),
            "rebounds_total": to_int_or_none(cols["reboundsTotal"][idx]),
            "steals": to_int_or_none(cols["steals"][idx]),
            "turnovers": to_int_or_none(cols["turnovers"][idx]),
            "points": to_int_or_none(cols["points"][idx]),
            "three_pointers_attempted": to_int_or_none(cols["threePointersAttempted"][idx]),
            "three_pointers_made": to_int_or_none(cols["threePointersMade"][idx]),
            "three_pointers_percentage": to_float_or_none(cols["threePointersPercentage"][idx]),
            "two_pointers_attempted": to_int_or_none(cols["twoPointersAttempted"][idx]),
            "two_pointers_made": to_int_or_none(cols["twoPointersMade"][idx]),
            "two_pointers_percentage": to_float_or_none(cols["twoPointersPercentage"][idx]),
            "points_fast_break": to_int_or_none(cols["pointsFastBreak"][idx]),
            "points_in_the_paint": to_int_or_none(cols["pointsInThePaint"][idx]),
            "points_second_chance": to_int_or_none(cols["pointsSecondChance"][idx]),
            "season_year": game_attrs.get("season_year"),
            "season_start_year": game_attrs.get("season_start_year"),
            "raw_season_type_code": game_attrs.get("raw_season_type_code"),
            "season_type": game_attrs.get("season_type"),
        }

        seconds_played_total = parse_iso_duration_seconds(row["minutes_calculated_raw"])
        if seconds_played_total is None:
            seconds_played_total = parse_iso_duration_seconds(row["minutes_raw"])
        row["seconds_played_total"] = seconds_played_total
        row["minutes_played_decimal"] = (
            round(seconds_played_total / 60.0, 2) if seconds_played_total is not None else None
        )

        key = (game_id, person_id)
        current = dedup_by_key.get(key)
        if current is None or row_quality_score(row) > row_quality_score(current):
            dedup_by_key[key] = row

    return sorted(
        dedup_by_key.values(),
        key=lambda row: (row.get("game_id") or "", row.get("person_id") if row.get("person_id") is not None else -1),
    )


def finalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    for index, row in enumerate(rows, start=1):
        row["fct_player_game_sk"] = index
        row["record_source"] = RECORD_SOURCE
        row["created_at_utc"] = run_ts
        row["updated_at_utc"] = run_ts
    return rows


def main() -> None:
    s3_client = boto3.client("s3")

    player_table = read_parquet_table_from_s3(s3_client, PLAYER_SOURCE_KEY, PLAYER_REQUIRED_COLUMNS)
    dim_game_table = read_parquet_table_from_s3(s3_client, DIM_GAME_KEY, DIM_GAME_REQUIRED_COLUMNS)
    dim_date_table = read_parquet_table_from_s3(s3_client, DIM_DATE_KEY, DIM_DATE_REQUIRED_COLUMNS)
    dim_player_table = read_parquet_table_from_s3(s3_client, DIM_PLAYER_KEY, DIM_PLAYER_REQUIRED_COLUMNS)
    dim_team_table = read_parquet_table_from_s3(s3_client, DIM_TEAM_KEY, DIM_TEAM_REQUIRED_COLUMNS)

    game_map = build_dim_game_map(dim_game_table)
    date_sk_map = build_date_sk_map(dim_date_table)

    rows = build_base_fact_rows(player_table, game_map, date_sk_map)
    rows = resolve_scd2_sk(
        fact_rows=rows,
        dim_rows=dim_player_table.to_pylist(),
        natural_id_col="person_id",
        fact_event_time_col="game_datetime_utc",
        sk_col="player_sk",
        output_sk_col="player_sk",
    )
    rows = resolve_scd2_sk(
        fact_rows=rows,
        dim_rows=dim_team_table.to_pylist(),
        natural_id_col="team_id",
        fact_event_time_col="game_datetime_utc",
        sk_col="team_sk",
        output_sk_col="team_sk",
    )

    team_label_by_sk = build_team_label_by_sk(dim_team_table.to_pylist())
    for row in rows:
        row["team"] = team_label_by_sk.get(row.get("team_sk"))

    _raise_if_unresolved(rows, "date_sk", ["game_id"])
    _raise_if_unresolved(rows, "player_sk", ["game_id", "person_id"])
    _raise_if_unresolved(rows, "team_sk", ["game_id", "person_id", "team_id"])
    _raise_if_unresolved(rows, "team", ["game_id", "person_id", "team_id", "team_sk"])

    write_parquet_to_s3(finalize_rows(rows), TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
