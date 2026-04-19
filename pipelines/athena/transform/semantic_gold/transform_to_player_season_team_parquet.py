"""Purpose: Build semantic_gold player_season_team as a silver-first player team-stint season object.
Inputs: Silver player-game rows plus silver game/schedule/team-game context.
Outputs: One semantic player_season_team row per (person_id, team_id, season_year, season_type).
Next file: transform_to_team_season_parquet.py provides the team-side season aggregate object.
"""

from __future__ import annotations

import boto3
import pyarrow as pa
from dotenv import load_dotenv

from pipelines.athena.transform.gold.gold_transform_helpers import (
    S3_BUCKET,
    games_played_from_values,
    read_parquet_table_from_s3,
    safe_ratio,
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
    TEAM_GAME_REQUIRED_COLUMNS,
    TEAM_GAME_SOURCE_KEY,
)
from pipelines.athena.transform.gold.transform_to_fct_player_game_parquet import (
    PLAYER_REQUIRED_COLUMNS,
    PLAYER_SOURCE_KEY,
)

from .contracts import PLAYER_SEASON_TEAM_SCHEMA
from .transform_to_player_game_parquet import build_player_game_rows_from_tables

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/player_season_team/player_season_team.parquet"


def build_player_season_team_rows_from_player_game_rows(
    player_game_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[int, int, str, str], dict[str, object]] = {}

    for row in player_game_rows:
        person_id = to_positive_int_or_none(row.get("person_id"))
        team_id = to_positive_int_or_none(row.get("team_id"))
        season_year = to_str_or_none(row.get("season_year"))
        season_type = to_str_or_none(row.get("season_type"))
        if None in {person_id, team_id, season_year, season_type}:
            continue

        key = (person_id, team_id, season_year, season_type)
        current = grouped.setdefault(
            key,
            {
                "person_id": person_id,
                "team_id": team_id,
                "season_year": season_year,
                "season_type": season_type,
                "games_played": 0,
                "total_points": 0,
            },
        )

        current["games_played"] = to_int_or_none(current.get("games_played")) or 0
        current["games_played"] += games_played_from_values(
            row.get("did_play"), row.get("minutes_played")
        )
        current["total_points"] = to_int_or_none(current.get("total_points")) or 0
        current["total_points"] += to_int_or_none(row.get("points")) or 0

    season_team_rows: list[dict[str, object]] = []
    for key in sorted(grouped):
        aggregate = grouped[key]
        games_played = to_int_or_none(aggregate.get("games_played")) or 0
        total_points = to_int_or_none(aggregate.get("total_points")) or 0
        season_team_rows.append(
            {
                **aggregate,
                "games_played": games_played,
                "total_points": total_points,
                "average_points": round(safe_ratio(total_points, games_played), 1)
                if games_played > 0
                else None,
            }
        )
    return season_team_rows


def build_player_season_team_rows_from_tables(
    player_table: pa.Table,
    box_table: pa.Table,
    schedule_table: pa.Table,
    team_game_table: pa.Table,
) -> list[dict[str, object]]:
    player_game_rows = build_player_game_rows_from_tables(
        player_table, box_table, schedule_table, team_game_table
    )
    return build_player_season_team_rows_from_player_game_rows(player_game_rows)


def main() -> None:
    s3_client = boto3.client("s3")
    player_table = read_parquet_table_from_s3(
        s3_client, PLAYER_SOURCE_KEY, PLAYER_REQUIRED_COLUMNS
    )
    box_table = read_parquet_table_from_s3(
        s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS
    )
    schedule_table = read_parquet_table_from_s3(
        s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS
    )
    team_game_table = read_parquet_table_from_s3(
        s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS
    )
    rows = build_player_season_team_rows_from_tables(
        player_table, box_table, schedule_table, team_game_table
    )
    write_parquet_to_s3(rows, PLAYER_SEASON_TEAM_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
