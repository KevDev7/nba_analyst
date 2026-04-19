"""Purpose: Build semantic_gold team_game as a silver-first team participation object.
Inputs: Silver team-game rows plus silver game/schedule context.
Outputs: One semantic team_game row per (game_id, team_id).
Next file: deploy_semantic_gold_tables.py publishes all semantic object tables to Athena.
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
from pipelines.athena.transform.gold.transform_to_fct_team_game_parquet import (
    TEAM_GAME_REQUIRED_COLUMNS,
    TEAM_GAME_SOURCE_KEY,
)
from pipelines.athena.transform.gold.transform_to_dim_game_parquet import (
    BOXSCORE_REQUIRED_COLUMNS,
    BOXSCORE_SOURCE_KEY,
    SCHEDULE_REQUIRED_COLUMNS,
    SCHEDULE_SOURCE_KEY,
)

from .contracts import TEAM_GAME_SCHEMA
from .transform_to_game_parquet import build_game_rows_from_tables

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/team_game/team_game.parquet"


def build_team_game_rows_from_tables(
    team_game_table: pa.Table,
    box_table: pa.Table,
    schedule_table: pa.Table,
) -> list[dict[str, object]]:
    game_rows = build_game_rows_from_tables(box_table, schedule_table, team_game_table)
    game_by_id = {to_str_or_none(row.get("game_id")): row for row in game_rows}
    semantic_team_ids = set(TEAM_CONTEXT_BY_ID.keys())

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in team_game_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId"))
        if game_id is None:
            continue
        grouped.setdefault(game_id, []).append(row)

    deduped: dict[tuple[str, int], dict[str, object]] = {}

    def quality_score(row: dict[str, object]) -> int:
        keys = [
            "game_datetime_utc",
            "game_date",
            "team_side",
            "team_id",
            "opponent_team_id",
            "score",
            "opponent_score",
        ]
        return sum(1 for key in keys if row.get(key) is not None)

    for game_id, rows in grouped.items():
        game = game_by_id.get(game_id, {})
        for row in rows:
            team_id = to_positive_int_or_none(row.get("teamId"))
            if team_id is None:
                continue
            side = to_str_or_none(row.get("team_side"))
            opponent = None
            if side in {"home", "away"}:
                expected = "away" if side == "home" else "home"
                opponent = next((candidate for candidate in rows if to_str_or_none(candidate.get("team_side")) == expected), None)
            if opponent is None:
                opponent = next((candidate for candidate in rows if to_positive_int_or_none(candidate.get("teamId")) != team_id), None)
            opponent_team_id = to_positive_int_or_none(opponent.get("teamId")) if opponent is not None else None
            if team_id not in semantic_team_ids or opponent_team_id not in semantic_team_ids:
                continue
            seconds_played_total = parse_iso_duration_seconds(row.get("minutesCalculated")) or parse_iso_duration_seconds(row.get("minutes"))
            score = to_int_or_none(row.get("score")) or to_int_or_none(row.get("points"))
            opponent_score = (
                to_int_or_none(opponent.get("score")) if opponent is not None else None
            ) or (to_int_or_none(opponent.get("points")) if opponent is not None else None)
            game_result = (
                "win"
                if score is not None and opponent_score is not None and score > opponent_score
                else "loss"
                if score is not None and opponent_score is not None and score < opponent_score
                else None
            )

            candidate = {
                "game_id": game_id,
                "team_id": team_id,
                "opponent_team_id": opponent_team_id,
                "game_datetime_utc": game.get("game_datetime_utc"),
                "game_date": game.get("game_date"),
                "season_year": game.get("season_year"),
                "season_type": game.get("season_type"),
                "team_side": side,
                "score": score,
                "opponent_score": opponent_score,
                "point_differential": (score - opponent_score) if score is not None and opponent_score is not None else None,
                "seconds_played_total": seconds_played_total,
                "minutes_played_decimal": round(seconds_played_total / 60.0, 3) if seconds_played_total is not None else None,
                "assists": to_int_or_none(row.get("assists")),
                "shots_blocked": to_int_or_none(row.get("blocks")),
                "shots_blocked_against": to_int_or_none(row.get("blocksReceived")),
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
                "three_pointers_attempted": to_int_or_none(row.get("threePointersAttempted")),
                "three_pointers_made": to_int_or_none(row.get("threePointersMade")),
                "three_pointers_percentage": to_float_or_none(row.get("threePointersPercentage")),
                "two_pointers_attempted": to_int_or_none(row.get("twoPointersAttempted")),
                "two_pointers_made": to_int_or_none(row.get("twoPointersMade")),
                "two_pointers_percentage": to_float_or_none(row.get("twoPointersPercentage")),
                "points_fast_break": to_int_or_none(row.get("pointsFastBreak")),
                "points_in_the_paint": to_int_or_none(row.get("pointsInThePaint")),
                "points_second_chance": to_int_or_none(row.get("pointsSecondChance")),
                "game_result": game_result,
            }
            key = (game_id, team_id)
            current = deduped.get(key)
            if current is None or quality_score(candidate) > quality_score(current):
                deduped[key] = candidate

    return [deduped[key] for key in sorted(deduped)]


def main() -> None:
    s3_client = boto3.client("s3")
    team_game_table = read_parquet_table_from_s3(s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS)
    box_table = read_parquet_table_from_s3(s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS)
    schedule_table = read_parquet_table_from_s3(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    rows = build_team_game_rows_from_tables(team_game_table, box_table, schedule_table)
    write_parquet_to_s3(rows, TEAM_GAME_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
