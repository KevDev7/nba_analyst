"""Purpose: Build semantic_gold game as a current-state business object from silver sources.
Inputs: Silver boxscore game, silver schedule, and silver team-game rows.
Outputs: One semantic game row per game_id with no warehouse-only fields.
Next file: transform_to_player_game_parquet.py reuses the game context emitted here.
"""

from __future__ import annotations

import boto3
import pyarrow as pa
from dotenv import load_dotenv

from pipelines.athena.transform.gold.gold_transform_helpers import S3_BUCKET, read_parquet_table_from_s3, write_parquet_to_s3
from pipelines.athena.transform.gold.transform_to_dim_game_parquet import (
    BOXSCORE_REQUIRED_COLUMNS,
    BOXSCORE_SOURCE_KEY,
    SCHEDULE_REQUIRED_COLUMNS,
    SCHEDULE_SOURCE_KEY,
    TEAM_GAME_REQUIRED_COLUMNS,
    TEAM_GAME_SOURCE_KEY,
    build_boxscore_map,
    build_dim_game_rows,
    build_schedule_map,
    build_team_side_map,
    season_type_label_from_code,
)

from .contracts import GAME_SCHEMA

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/game/game.parquet"


def is_semantic_game_row(row: dict[str, object]) -> bool:
    return (
        row.get("game_id") is not None
        and row.get("game_date") is not None
        and row.get("season_year") is not None
        and row.get("season_type") is not None
        and row.get("home_team_id") is not None
        and row.get("away_team_id") is not None
    )


def finalize_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    public_columns = GAME_SCHEMA.names
    return [{column: row.get(column) for column in public_columns} for row in rows]


def build_game_rows_from_tables(
    box_table: pa.Table,
    schedule_table: pa.Table,
    team_game_table: pa.Table,
) -> list[dict[str, object]]:
    raw_rows = build_dim_game_rows(
        build_boxscore_map(box_table),
        build_schedule_map(schedule_table),
        build_team_side_map(team_game_table),
    )
    semantic_rows = [
        row
        for row in raw_rows
        if is_semantic_game_row(row)
        and season_type_label_from_code(str(row.get("game_id"))[:3]) is not None
    ]
    return finalize_rows(semantic_rows)


def main() -> None:
    s3_client = boto3.client("s3")
    box_table = read_parquet_table_from_s3(s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS)
    schedule_table = read_parquet_table_from_s3(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    team_game_table = read_parquet_table_from_s3(s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS)
    rows = build_game_rows_from_tables(box_table, schedule_table, team_game_table)
    write_parquet_to_s3(rows, GAME_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
