"""Purpose: Build semantic_gold team_season as a silver-first team season aggregate object.
Inputs: Silver team-game rows plus silver game/schedule context.
Outputs: One semantic team_season row per (team_id, season_year, season_type).
Next file: deploy_semantic_gold_tables.py publishes the expanded semantic object surface.
"""

from __future__ import annotations

import boto3
import pyarrow as pa
from dotenv import load_dotenv

from pipelines.athena.transform.gold.gold_transform_helpers import (
    S3_BUCKET,
    read_parquet_table_from_s3,
    safe_ratio,
    to_float_or_none,
    to_int_or_none,
    to_positive_int_or_none,
    to_str_or_none,
    write_parquet_to_s3,
)
from pipelines.athena.transform.gold.transform_to_dim_game_parquet import (
    BOXSCORE_REQUIRED_COLUMNS,
    BOXSCORE_SOURCE_KEY,
    SCHEDULE_REQUIRED_COLUMNS,
    SCHEDULE_SOURCE_KEY,
)
from pipelines.athena.transform.gold.transform_to_fct_team_game_parquet import (
    TEAM_GAME_REQUIRED_COLUMNS,
    TEAM_GAME_SOURCE_KEY,
)

from .contracts import TEAM_SEASON_SCHEMA
from .transform_to_team_game_parquet import build_team_game_rows_from_tables

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/team_season/team_season.parquet"


def build_team_season_rows_from_team_game_rows(
    team_game_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[int, str, str], dict[str, object]] = {}

    for row in team_game_rows:
        team_id = to_positive_int_or_none(row.get("team_id"))
        season_year = to_str_or_none(row.get("season_year"))
        season_type = to_str_or_none(row.get("season_type"))
        if team_id is None or season_year is None or season_type is None:
            continue

        key = (team_id, season_year, season_type)
        current = grouped.setdefault(
            key,
            {
                "team_id": team_id,
                "season_year": season_year,
                "season_type": season_type,
                "games_played": 0,
                "wins": 0,
                "losses": 0,
            },
        )

        current["games_played"] = to_int_or_none(current.get("games_played")) or 0
        current["games_played"] += 1
        game_result = row.get("game_result")
        current["wins"] = to_int_or_none(current.get("wins")) or 0
        current["wins"] += 1 if game_result == "win" else 0
        current["losses"] = to_int_or_none(current.get("losses")) or 0
        current["losses"] += 1 if game_result == "loss" else 0

    season_rows: list[dict[str, object]] = []
    for key in sorted(grouped):
        aggregate = grouped[key]
        games_played = to_int_or_none(aggregate.get("games_played")) or 0
        wins = to_int_or_none(aggregate.get("wins")) or 0
        losses = to_int_or_none(aggregate.get("losses")) or 0
        season_rows.append(
            {
                **aggregate,
                "games_played": games_played,
                "wins": wins,
                "losses": losses,
                "win_percentage": round(safe_ratio(wins, games_played), 3)
                if games_played > 0
                else None,
            }
        )
    return season_rows


def build_team_season_rows_from_tables(
    team_game_table: pa.Table,
    box_table: pa.Table,
    schedule_table: pa.Table,
) -> list[dict[str, object]]:
    team_game_rows = build_team_game_rows_from_tables(
        team_game_table, box_table, schedule_table
    )
    return build_team_season_rows_from_team_game_rows(team_game_rows)


def main() -> None:
    s3_client = boto3.client("s3")
    team_game_table = read_parquet_table_from_s3(
        s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS
    )
    box_table = read_parquet_table_from_s3(
        s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS
    )
    schedule_table = read_parquet_table_from_s3(
        s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS
    )
    rows = build_team_season_rows_from_tables(team_game_table, box_table, schedule_table)
    write_parquet_to_s3(rows, TEAM_SEASON_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
