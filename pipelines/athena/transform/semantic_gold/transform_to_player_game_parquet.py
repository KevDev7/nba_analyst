"""Purpose: Build semantic_gold player_game as a silver-first player participation object.
Inputs: Silver player-game rows plus silver game/schedule/team-game context.
Outputs: One semantic player_game row per (game_id, person_id).
Next file: transform_to_team_game_parquet.py provides the team-side companion object.
"""

from __future__ import annotations

from typing import Any

import boto3
import pyarrow as pa
from dotenv import load_dotenv

from pipelines.athena.transform.gold.gold_transform_helpers import (
    S3_BUCKET,
    TEAM_CONTEXT_BY_ID,
    parse_iso_duration_seconds,
    read_parquet_table_from_s3,
    to_float_or_none,
    to_int_or_none,
    to_positive_int_or_none,
    to_str_or_none,
    write_parquet_to_s3,
)
from pipelines.athena.transform.gold.transform_to_fct_player_game_parquet import (
    PLAYER_REQUIRED_COLUMNS,
    PLAYER_SOURCE_KEY,
)
from pipelines.athena.transform.gold.transform_to_dim_game_parquet import (
    BOXSCORE_REQUIRED_COLUMNS,
    BOXSCORE_SOURCE_KEY,
    SCHEDULE_REQUIRED_COLUMNS,
    SCHEDULE_SOURCE_KEY,
    TEAM_GAME_REQUIRED_COLUMNS,
    TEAM_GAME_SOURCE_KEY,
)

from .contracts import PLAYER_GAME_SCHEMA
from .transform_to_game_parquet import build_game_rows_from_tables

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/player_game/player_game.parquet"


def build_player_game_rows_from_tables(
    player_table: pa.Table,
    box_table: pa.Table,
    schedule_table: pa.Table,
    team_game_table: pa.Table,
) -> list[dict[str, object]]:
    game_rows = build_game_rows_from_tables(box_table, schedule_table, team_game_table)
    game_by_id = {to_str_or_none(row.get("game_id")): row for row in game_rows}
    semantic_team_ids = set(TEAM_CONTEXT_BY_ID.keys())
    deduped: dict[tuple[str, int], dict[str, object]] = {}

    def quality_score(row: dict[str, object]) -> int:
        keys = [
            "game_datetime_utc",
            "game_date",
            "season_year",
            "team_side",
            "minutes_played_decimal",
            "points",
        ]
        return sum(1 for key in keys if row.get(key) is not None)

    for row in player_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId"))
        person_id = to_positive_int_or_none(row.get("personId"))
        team_id = to_positive_int_or_none(row.get("teamId"))
        if game_id is None or person_id is None or team_id not in semantic_team_ids:
            continue
        game = game_by_id.get(game_id, {})
        seconds_played_total = parse_iso_duration_seconds(row.get("minutesCalculated")) or parse_iso_duration_seconds(row.get("minutes"))
        candidate = {
            "game_id": game_id,
            "person_id": person_id,
            "team_id": team_id,
            "team_side": to_str_or_none(row.get("team_side")),
            "game_datetime_utc": game.get("game_datetime_utc"),
            "game_date": game.get("game_date"),
            "season_year": game.get("season_year"),
            "season_start_year": game.get("season_start_year"),
            "raw_season_type_code": game.get("raw_season_type_code"),
            "season_type": game.get("season_type"),
            "is_starter": to_int_or_none(row.get("starter")),
            "is_on_court": to_int_or_none(row.get("oncourt")),
            "did_play": to_int_or_none(row.get("played")),
            "seconds_played_total": seconds_played_total,
            "minutes_played_decimal": round(seconds_played_total / 60.0, 3) if seconds_played_total is not None else None,
            "plus_minus": to_int_or_none(row.get("plusMinusPoints")),
            "assists": to_int_or_none(row.get("assists")),
            "blocks": to_int_or_none(row.get("blocks")),
            "blocks_received": to_int_or_none(row.get("blocksReceived")),
            "field_goals_attempted": to_int_or_none(row.get("fieldGoalsAttempted")),
            "field_goals_made": to_int_or_none(row.get("fieldGoalsMade")),
            "field_goals_percentage": to_float_or_none(row.get("fieldGoalsPercentage")),
            "fouls_offensive": to_int_or_none(row.get("foulsOffensive")),
            "fouls_drawn": to_int_or_none(row.get("foulsDrawn")),
            "fouls_personal": to_int_or_none(row.get("foulsPersonal")),
            "fouls_technical": to_int_or_none(row.get("foulsTechnical")),
            "free_throws_attempted": to_int_or_none(row.get("freeThrowsAttempted")),
            "free_throws_made": to_int_or_none(row.get("freeThrowsMade")),
            "free_throws_percentage": to_float_or_none(row.get("freeThrowsPercentage")),
            "rebounds_defensive": to_int_or_none(row.get("reboundsDefensive")),
            "rebounds_offensive": to_int_or_none(row.get("reboundsOffensive")),
            "rebounds_total": to_int_or_none(row.get("reboundsTotal")),
            "steals": to_int_or_none(row.get("steals")),
            "turnovers": to_int_or_none(row.get("turnovers")),
            "points": to_int_or_none(row.get("points")),
            "three_pointers_attempted": to_int_or_none(row.get("threePointersAttempted")),
            "three_pointers_made": to_int_or_none(row.get("threePointersMade")),
            "three_pointers_percentage": to_float_or_none(row.get("threePointersPercentage")),
            "two_pointers_attempted": to_int_or_none(row.get("twoPointersAttempted")),
            "two_pointers_made": to_int_or_none(row.get("twoPointersMade")),
            "two_pointers_percentage": to_float_or_none(row.get("twoPointersPercentage")),
            "points_fast_break": to_int_or_none(row.get("pointsFastBreak")),
            "points_in_the_paint": to_int_or_none(row.get("pointsInThePaint")),
            "points_second_chance": to_int_or_none(row.get("pointsSecondChance")),
        }
        key = (game_id, person_id)
        current = deduped.get(key)
        if current is None or quality_score(candidate) > quality_score(current):
            deduped[key] = candidate

    return [deduped[key] for key in sorted(deduped)]


def main() -> None:
    s3_client = boto3.client("s3")
    player_table = read_parquet_table_from_s3(s3_client, PLAYER_SOURCE_KEY, PLAYER_REQUIRED_COLUMNS)
    box_table = read_parquet_table_from_s3(s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS)
    schedule_table = read_parquet_table_from_s3(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    team_game_table = read_parquet_table_from_s3(s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS)
    rows = build_player_game_rows_from_tables(player_table, box_table, schedule_table, team_game_table)
    write_parquet_to_s3(rows, PLAYER_GAME_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
