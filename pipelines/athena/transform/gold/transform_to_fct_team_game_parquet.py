"""
Build gold fct_team_game from silver team-game boxscore rows.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game.parquet
  s3://nba-analytics-lakehouse-dev/gold/fct_player_game/fct_player_game.parquet
  s3://nba-analytics-lakehouse-dev/gold/dim_game/dim_game.parquet
  s3://nba-analytics-lakehouse-dev/gold/dim_date/dim_date.parquet
  s3://nba-analytics-lakehouse-dev/gold/dim_team/dim_team.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/gold/fct_team_game/fct_team_game.parquet
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
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        safe_ratio,
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
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        safe_ratio,
        to_float_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
    from scd2_utils import resolve_scd2_sk  # type: ignore[no-redef]

load_dotenv(override=True)

TEAM_GAME_SOURCE_KEY = "silver/boxscore_team_game.parquet"
PLAYER_FACT_KEY = "gold/fct_player_game/fct_player_game.parquet"
DIM_GAME_KEY = "gold/dim_game/dim_game.parquet"
DIM_DATE_KEY = "gold/dim_date/dim_date.parquet"
DIM_TEAM_KEY = "gold/dim_team/dim_team.parquet"
DESTINATION_KEY = "gold/fct_team_game/fct_team_game.parquet"

RECORD_SOURCE = "silver.boxscore_team_game|gold.fct_player_game|gold.dim_game|gold.dim_date|gold.dim_team"

TEAM_GAME_REQUIRED_COLUMNS = [
    "gameId",
    "team_side",
    "teamId",
    "teamName",
    "teamCity",
    "teamTricode",
    "score",
    "inBonus",
    "timeoutsRemaining",
]

PLAYER_FACT_REQUIRED_COLUMNS = [
    "game_id",
    "team_id",
    "seconds_played_total",
    "assists",
    "blocks",
    "blocks_received",
    "field_goals_attempted",
    "field_goals_made",
    "fouls_offensive",
    "fouls_drawn",
    "fouls_personal",
    "fouls_technical",
    "free_throws_attempted",
    "free_throws_made",
    "rebounds_defensive",
    "rebounds_offensive",
    "rebounds_total",
    "steals",
    "turnovers",
    "three_pointers_attempted",
    "three_pointers_made",
    "two_pointers_attempted",
    "two_pointers_made",
    "points_fast_break",
    "points_in_the_paint",
    "points_second_chance",
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

DIM_TEAM_REQUIRED_COLUMNS = [
    "team_sk",
    "team_id",
    "valid_from_utc",
    "valid_to_utc",
    "is_current",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("fct_team_game_sk", pa.int64()),
        pa.field("game_sk", pa.int64()),
        pa.field("date_sk", pa.int64()),
        pa.field("team_sk", pa.int64()),
        pa.field("opponent_team_sk", pa.int64()),
        pa.field("game_id", pa.string()),
        pa.field("team_id", pa.int64()),
        pa.field("opponent_team_id", pa.int64()),
        pa.field("game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("game_date", pa.date32()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("team_side", pa.string()),
        pa.field("is_home_team", pa.int64()),
        pa.field("team_name", pa.string()),
        pa.field("team_city", pa.string()),
        pa.field("team_abbreviation", pa.string()),
        pa.field("opponent_team_name", pa.string()),
        pa.field("opponent_team_city", pa.string()),
        pa.field("opponent_team_abbreviation", pa.string()),
        pa.field("score", pa.int64()),
        pa.field("opponent_score", pa.int64()),
        pa.field("point_diff", pa.int64()),
        pa.field("is_in_bonus", pa.int64()),
        pa.field("timeouts_remaining", pa.int64()),
        pa.field("seconds_played_total", pa.float64()),
        pa.field("minutes_played_decimal", pa.float64()),
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
        pa.field("three_pointers_attempted", pa.int64()),
        pa.field("three_pointers_made", pa.int64()),
        pa.field("three_pointers_percentage", pa.float64()),
        pa.field("two_pointers_attempted", pa.int64()),
        pa.field("two_pointers_made", pa.int64()),
        pa.field("two_pointers_percentage", pa.float64()),
        pa.field("points_fast_break", pa.int64()),
        pa.field("points_in_the_paint", pa.int64()),
        pa.field("points_second_chance", pa.int64()),
        pa.field("is_win", pa.int64()),
        pa.field("is_loss", pa.int64()),
        pa.field("is_tie", pa.int64()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)

PLAYER_AGG_SUM_COLS = [
    "assists",
    "blocks",
    "blocks_received",
    "field_goals_attempted",
    "field_goals_made",
    "fouls_offensive",
    "fouls_drawn",
    "fouls_personal",
    "fouls_technical",
    "free_throws_attempted",
    "free_throws_made",
    "rebounds_defensive",
    "rebounds_offensive",
    "rebounds_total",
    "steals",
    "turnovers",
    "three_pointers_attempted",
    "three_pointers_made",
    "two_pointers_attempted",
    "two_pointers_made",
    "points_fast_break",
    "points_in_the_paint",
    "points_second_chance",
]


def build_dim_game_map(dim_game_table: pa.Table) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in dim_game_table.to_pylist():
        game_id = normalize_game_id(row.get("game_id"))
        if game_id is None:
            continue
        output[game_id] = {
            "game_sk": to_int_or_none(row.get("game_sk")),
            "game_date": parse_date_or_none(row.get("game_date")),
            "game_datetime_utc": parse_timestamp_utc(row.get("game_datetime_utc")),
            "season_year": to_str_or_none(row.get("season_year")),
            "season_start_year": to_int_or_none(row.get("season_start_year")),
            "raw_season_type_code": to_str_or_none(row.get("raw_season_type_code")),
            "season_type": to_str_or_none(row.get("season_type")),
        }
    return output


def build_date_sk_map(dim_date_table: pa.Table) -> dict[date, int]:
    output: dict[date, int] = {}
    for row in dim_date_table.to_pylist():
        calendar_date = parse_date_or_none(row.get("calendar_date"))
        date_sk = to_int_or_none(row.get("date_sk"))
        if calendar_date is None or date_sk is None:
            continue
        output[calendar_date] = date_sk
    return output


def row_quality_score(row: dict[str, Any]) -> int:
    return sum(
        1
        for key in ("team_name", "team_city", "team_abbreviation", "score", "is_in_bonus", "timeouts_remaining")
        if row.get(key) is not None
    ) + (1 if row.get("team_side") is not None else 0)


def pick_opponent(base_row: dict[str, Any], game_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [row for row in game_rows if row.get("team_id") != base_row.get("team_id")]
    if not candidates:
        return None

    base_side = to_str_or_none(base_row.get("team_side"))
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for candidate in candidates:
        pref = 0
        candidate_side = to_str_or_none(candidate.get("team_side"))
        if base_side == "home" and candidate_side == "away":
            pref = 2
        elif base_side == "away" and candidate_side == "home":
            pref = 2
        elif candidate.get("team_id") is not None:
            pref = 1
        ranked.append((pref, candidate.get("team_id") or 0, candidate))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][2]


def _raise_if_unresolved(rows: list[dict[str, Any]], column_name: str, natural_key_cols: list[str]) -> None:
    unresolved = [row for row in rows if row.get(column_name) is None]
    if not unresolved:
        return
    sample_rows = [{key: row.get(key) for key in natural_key_cols} for row in unresolved[:10]]
    raise ValueError(
        f"Unable to resolve {column_name} for {len(unresolved)} fact rows. Sample keys: {sample_rows}"
    )


def build_team_rows(team_game_table: pa.Table) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    dedup: dict[tuple[str, int], dict[str, Any]] = {}
    cols = {column: team_game_table[column].to_pylist() for column in TEAM_GAME_REQUIRED_COLUMNS}

    for idx in range(team_game_table.num_rows):
        game_id = normalize_game_id(cols["gameId"][idx])
        team_id = to_int_or_none(cols["teamId"][idx])
        if game_id is None or team_id is None or team_id <= 0:
            continue

        candidate = {
            "game_id": game_id,
            "team_id": team_id,
            "team_side": to_str_or_none(cols["team_side"][idx]),
            "team_name": to_str_or_none(cols["teamName"][idx]),
            "team_city": to_str_or_none(cols["teamCity"][idx]),
            "team_abbreviation": to_str_or_none(cols["teamTricode"][idx]),
            "score": to_int_or_none(cols["score"][idx]),
            "is_in_bonus": to_int_or_none(cols["inBonus"][idx]),
            "timeouts_remaining": to_int_or_none(cols["timeoutsRemaining"][idx]),
        }

        key = (game_id, team_id)
        current = dedup.get(key)
        if current is None or row_quality_score(candidate) > row_quality_score(current):
            dedup[key] = candidate

    dedup_rows = list(dedup.values())
    game_buckets: dict[str, list[dict[str, Any]]] = {}
    for row in dedup_rows:
        game_buckets.setdefault(row["game_id"], []).append(row)
    return dedup_rows, game_buckets


def build_player_team_boxscore_map(player_fact_table: pa.Table) -> dict[tuple[str, int], dict[str, Any]]:
    aggregations: dict[tuple[str, int], dict[str, Any]] = {}
    for row in player_fact_table.to_pylist():
        game_id = normalize_game_id(row.get("game_id"))
        team_id = to_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None or team_id <= 0:
            continue

        key = (game_id, team_id)
        if key not in aggregations:
            aggregations[key] = {"seconds_played_total": 0.0, **{column: 0 for column in PLAYER_AGG_SUM_COLS}}

        agg = aggregations[key]
        agg["seconds_played_total"] += to_float_or_none(row.get("seconds_played_total")) or 0.0
        for column in PLAYER_AGG_SUM_COLS:
            agg[column] += to_int_or_none(row.get(column)) or 0

    for agg in aggregations.values():
        agg["minutes_played_decimal"] = round(agg["seconds_played_total"] / 60.0, 2)
        agg["field_goals_percentage"] = safe_ratio(agg["field_goals_made"], agg["field_goals_attempted"])
        agg["free_throws_percentage"] = safe_ratio(agg["free_throws_made"], agg["free_throws_attempted"])
        agg["three_pointers_percentage"] = safe_ratio(
            agg["three_pointers_made"], agg["three_pointers_attempted"]
        )
        agg["two_pointers_percentage"] = safe_ratio(agg["two_pointers_made"], agg["two_pointers_attempted"])

    return aggregations


def build_base_fact_rows(
    dedup_rows: list[dict[str, Any]],
    game_buckets: dict[str, list[dict[str, Any]]],
    player_team_boxscore_map: dict[tuple[str, int], dict[str, Any]],
    dim_game_map: dict[str, dict[str, Any]],
    date_sk_map: dict[date, int],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in dedup_rows:
        game_id = row.get("game_id")
        team_id = row.get("team_id")
        if game_id is None or team_id is None:
            continue

        game_attrs = dim_game_map.get(game_id)
        if game_attrs is None:
            continue

        opponent = pick_opponent(row, game_buckets.get(game_id, []))
        opponent_team_id = opponent.get("team_id") if opponent is not None else None
        game_date = game_attrs.get("game_date")
        score = row.get("score")
        opponent_score = opponent.get("score") if opponent is not None else None
        point_diff = None
        is_win = 0
        is_loss = 0
        is_tie = 0
        if score is not None and opponent_score is not None:
            point_diff = score - opponent_score
            if score > opponent_score:
                is_win = 1
            elif score < opponent_score:
                is_loss = 1
            else:
                is_tie = 1

        team_side = to_str_or_none(row.get("team_side"))
        is_home_team = 1 if team_side == "home" else 0 if team_side == "away" else None
        player_boxscore = player_team_boxscore_map.get((game_id, team_id), {})

        output.append(
            {
                "game_id": game_id,
                "team_id": team_id,
                "opponent_team_id": opponent_team_id,
                "game_sk": game_attrs.get("game_sk"),
                "date_sk": date_sk_map.get(game_date) if game_date is not None else None,
                "game_datetime_utc": game_attrs.get("game_datetime_utc"),
                "game_date": game_date,
                "season_year": game_attrs.get("season_year"),
                "season_start_year": game_attrs.get("season_start_year"),
                "team_side": team_side,
                "is_home_team": is_home_team,
                "team_name": row.get("team_name"),
                "team_city": row.get("team_city"),
                "team_abbreviation": row.get("team_abbreviation"),
                "opponent_team_name": opponent.get("team_name") if opponent is not None else None,
                "opponent_team_city": opponent.get("team_city") if opponent is not None else None,
                "opponent_team_abbreviation": opponent.get("team_abbreviation") if opponent is not None else None,
                "score": score,
                "opponent_score": opponent_score,
                "point_diff": point_diff,
                "is_in_bonus": row.get("is_in_bonus"),
                "timeouts_remaining": row.get("timeouts_remaining"),
                "seconds_played_total": player_boxscore.get("seconds_played_total"),
                "minutes_played_decimal": player_boxscore.get("minutes_played_decimal"),
                "assists": player_boxscore.get("assists"),
                "blocks": player_boxscore.get("blocks"),
                "blocks_received": player_boxscore.get("blocks_received"),
                "field_goals_attempted": player_boxscore.get("field_goals_attempted"),
                "field_goals_made": player_boxscore.get("field_goals_made"),
                "field_goals_percentage": player_boxscore.get("field_goals_percentage"),
                "fouls_offensive": player_boxscore.get("fouls_offensive"),
                "fouls_drawn": player_boxscore.get("fouls_drawn"),
                "fouls_personal": player_boxscore.get("fouls_personal"),
                "fouls_technical": player_boxscore.get("fouls_technical"),
                "free_throws_attempted": player_boxscore.get("free_throws_attempted"),
                "free_throws_made": player_boxscore.get("free_throws_made"),
                "free_throws_percentage": player_boxscore.get("free_throws_percentage"),
                "rebounds_defensive": player_boxscore.get("rebounds_defensive"),
                "rebounds_offensive": player_boxscore.get("rebounds_offensive"),
                "rebounds_total": player_boxscore.get("rebounds_total"),
                "steals": player_boxscore.get("steals"),
                "turnovers": player_boxscore.get("turnovers"),
                "three_pointers_attempted": player_boxscore.get("three_pointers_attempted"),
                "three_pointers_made": player_boxscore.get("three_pointers_made"),
                "three_pointers_percentage": player_boxscore.get("three_pointers_percentage"),
                "two_pointers_attempted": player_boxscore.get("two_pointers_attempted"),
                "two_pointers_made": player_boxscore.get("two_pointers_made"),
                "two_pointers_percentage": player_boxscore.get("two_pointers_percentage"),
                "points_fast_break": player_boxscore.get("points_fast_break"),
                "points_in_the_paint": player_boxscore.get("points_in_the_paint"),
                "points_second_chance": player_boxscore.get("points_second_chance"),
                "is_win": is_win,
                "is_loss": is_loss,
                "is_tie": is_tie,
                "raw_season_type_code": game_attrs.get("raw_season_type_code"),
                "season_type": game_attrs.get("season_type"),
            }
        )

    return sorted(
        output,
        key=lambda row: (row.get("game_id") or "", row.get("team_id") if row.get("team_id") is not None else -1),
    )


def finalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    for index, row in enumerate(rows, start=1):
        row["fct_team_game_sk"] = index
        row["record_source"] = RECORD_SOURCE
        row["created_at_utc"] = run_ts
        row["updated_at_utc"] = run_ts
    return rows


def main() -> None:
    s3_client = boto3.client("s3")

    team_game_table = read_parquet_table_from_s3(s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS)
    player_fact_table = read_parquet_table_from_s3(s3_client, PLAYER_FACT_KEY, PLAYER_FACT_REQUIRED_COLUMNS)
    dim_game_table = read_parquet_table_from_s3(s3_client, DIM_GAME_KEY, DIM_GAME_REQUIRED_COLUMNS)
    dim_date_table = read_parquet_table_from_s3(s3_client, DIM_DATE_KEY, DIM_DATE_REQUIRED_COLUMNS)
    dim_team_table = read_parquet_table_from_s3(s3_client, DIM_TEAM_KEY, DIM_TEAM_REQUIRED_COLUMNS)

    dim_game_map = build_dim_game_map(dim_game_table)
    date_sk_map = build_date_sk_map(dim_date_table)
    player_team_boxscore_map = build_player_team_boxscore_map(player_fact_table)
    dedup_rows, game_buckets = build_team_rows(team_game_table)
    rows = build_base_fact_rows(
        dedup_rows,
        game_buckets,
        player_team_boxscore_map,
        dim_game_map,
        date_sk_map,
    )

    rows = resolve_scd2_sk(
        fact_rows=rows,
        dim_rows=dim_team_table.to_pylist(),
        natural_id_col="team_id",
        fact_event_time_col="game_datetime_utc",
        sk_col="team_sk",
        output_sk_col="team_sk",
    )
    rows = resolve_scd2_sk(
        fact_rows=rows,
        dim_rows=dim_team_table.to_pylist(),
        natural_id_col="team_id",
        fact_natural_id_col="opponent_team_id",
        fact_event_time_col="game_datetime_utc",
        sk_col="team_sk",
        output_sk_col="opponent_team_sk",
    )

    _raise_if_unresolved(rows, "date_sk", ["game_id"])
    _raise_if_unresolved(rows, "team_sk", ["game_id", "team_id"])
    _raise_if_unresolved(rows, "opponent_team_sk", ["game_id", "team_id", "opponent_team_id"])

    write_parquet_to_s3(finalize_rows(rows), TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
