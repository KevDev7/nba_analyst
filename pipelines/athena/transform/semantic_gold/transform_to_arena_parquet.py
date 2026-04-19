"""Purpose: Build semantic_gold arena as a reusable venue object from silver game sources.
Inputs: Silver boxscore game, silver schedule, and silver team-game rows through semantic game context.
Outputs: One semantic arena row per arena_id with no warehouse-only fields.
Next file: transform_to_game_parquet.py keeps the arena link on Game.
"""

from __future__ import annotations

import boto3
import pyarrow as pa
from dotenv import load_dotenv

from pipelines.athena.transform.gold.gold_transform_helpers import (
    S3_BUCKET,
    read_parquet_table_from_s3,
    to_positive_int_or_none,
    write_parquet_to_s3,
)
from pipelines.athena.transform.gold.transform_to_dim_game_parquet import (
    BOXSCORE_REQUIRED_COLUMNS,
    BOXSCORE_SOURCE_KEY,
    SCHEDULE_REQUIRED_COLUMNS,
    SCHEDULE_SOURCE_KEY,
    TEAM_GAME_REQUIRED_COLUMNS,
    TEAM_GAME_SOURCE_KEY,
)

from .contracts import ARENA_SCHEMA
from .transform_to_game_parquet import build_semantic_game_source_rows_from_tables

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/arena/arena.parquet"


def finalize_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    public_columns = ARENA_SCHEMA.names
    return [{column: row.get(column) for column in public_columns} for row in rows]


def build_arena_rows_from_tables(
    box_table: pa.Table,
    schedule_table: pa.Table,
    team_game_table: pa.Table,
) -> list[dict[str, object]]:
    game_rows = build_semantic_game_source_rows_from_tables(
        box_table, schedule_table, team_game_table
    )
    deduped: dict[int, dict[str, object]] = {}

    def quality_score(row: dict[str, object]) -> int:
        return sum(
            1
            for key in (
                "arena_name",
                "arena_city",
                "arena_state",
                "arena_country",
                "arena_timezone",
            )
            if row.get(key) is not None
        )

    for row in game_rows:
        arena_id = to_positive_int_or_none(row.get("arena_id"))
        if arena_id is None:
            continue
        candidate = {
            "arena_id": arena_id,
            "arena_name": row.get("arena_name"),
            "arena_city": row.get("arena_city"),
            "arena_state": row.get("arena_state"),
            "arena_country": row.get("arena_country"),
            "arena_timezone": row.get("arena_timezone"),
        }
        current = deduped.get(arena_id)
        if current is None or quality_score(candidate) > quality_score(current):
            deduped[arena_id] = candidate

    return finalize_rows([deduped[key] for key in sorted(deduped)])


def main() -> None:
    s3_client = boto3.client("s3")
    box_table = read_parquet_table_from_s3(s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS)
    schedule_table = read_parquet_table_from_s3(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    team_game_table = read_parquet_table_from_s3(s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS)
    rows = build_arena_rows_from_tables(box_table, schedule_table, team_game_table)
    write_parquet_to_s3(rows, ARENA_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
