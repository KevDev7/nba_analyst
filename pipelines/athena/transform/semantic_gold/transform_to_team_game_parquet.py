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
TEAM_GAME_POSSESSION_CONTEXT_SOURCE_KEY = "silver/team_game_possession_context.parquet"
TEAM_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "team_id",
    "offensive_possessions",
    "defensive_possessions",
    "possessions_total",
]
TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY = "silver/team_game_defensive_shot_context.parquet"
TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "team_id",
    "opponent_two_point_attempts",
]


def _rounded_value(value: object, digits: int) -> float | None:
    numeric = to_float_or_none(value)
    return round(numeric, digits) if numeric is not None else None


def build_team_game_possession_map_from_table(
    team_game_possession_context_table: pa.Table | None,
) -> dict[tuple[str, int], dict[str, float]]:
    if team_game_possession_context_table is None:
        return {}

    possession_map: dict[tuple[str, int], dict[str, float]] = {}
    for row in team_game_possession_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        team_id = to_positive_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        offensive_possessions = to_float_or_none(row.get("offensive_possessions")) or 0.0
        defensive_possessions = to_float_or_none(row.get("defensive_possessions")) or 0.0
        possessions = to_float_or_none(row.get("possessions_total"))
        if possessions is None and (offensive_possessions > 0 or defensive_possessions > 0):
            possessions = (offensive_possessions + defensive_possessions) / 2.0
        possession_map[(game_id, team_id)] = {
            "offensive_possessions": offensive_possessions,
            "defensive_possessions": defensive_possessions,
            "possessions": possessions or 0.0,
        }
    return possession_map


def build_team_game_defensive_shot_context_map_from_table(
    team_game_defensive_shot_context_table: pa.Table | None,
) -> dict[tuple[str, int], dict[str, float]]:
    if team_game_defensive_shot_context_table is None:
        return {}

    shot_context_map: dict[tuple[str, int], dict[str, float]] = {}
    for row in team_game_defensive_shot_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        team_id = to_positive_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        shot_context_map[(game_id, team_id)] = {
            "opponent_two_point_attempts": to_float_or_none(row.get("opponent_two_point_attempts"))
            or 0.0,
        }
    return shot_context_map


def build_team_game_rows_from_tables(
    team_game_table: pa.Table,
    box_table: pa.Table,
    schedule_table: pa.Table,
    team_game_possession_context_table: pa.Table | None = None,
    team_game_defensive_shot_context_table: pa.Table | None = None,
) -> list[dict[str, object]]:
    game_rows = build_game_rows_from_tables(box_table, schedule_table, team_game_table)
    game_by_id = {to_str_or_none(row.get("game_id")): row for row in game_rows}
    semantic_team_ids = set(TEAM_CONTEXT_BY_ID.keys())
    team_game_possession_map = build_team_game_possession_map_from_table(
        team_game_possession_context_table
    )
    team_game_defensive_shot_context_map = build_team_game_defensive_shot_context_map_from_table(
        team_game_defensive_shot_context_table
    )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in team_game_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId"))
        if game_id is None:
            continue
        grouped.setdefault(game_id, []).append(row)

    deduped: dict[tuple[str, int], dict[str, object]] = {}

    def quality_score(row: dict[str, object]) -> int:
        keys = [
            "game_start_time_utc",
            "game_date",
            "team_home_or_away",
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
            minutes_played = (
                round(seconds_played_total / 60.0, 1) if seconds_played_total is not None else None
            )
            win_loss_result = (
                "win"
                if score is not None and opponent_score is not None and score > opponent_score
                else "loss"
                if score is not None and opponent_score is not None and score < opponent_score
                else None
            )
            possession_stats = team_game_possession_map.get((game_id, team_id), {})
            possessions = to_float_or_none(possession_stats.get("possessions"))
            offensive_possessions = to_float_or_none(possession_stats.get("offensive_possessions"))
            defensive_possessions = to_float_or_none(possession_stats.get("defensive_possessions"))
            defensive_shot_context = team_game_defensive_shot_context_map.get((game_id, team_id), {})
            opponent_two_point_attempts = to_float_or_none(
                defensive_shot_context.get("opponent_two_point_attempts")
            )
            assists = to_int_or_none(row.get("assists"))
            steals = to_int_or_none(row.get("steals"))
            field_goals_attempted = to_int_or_none(row.get("fieldGoalsAttempted"))
            field_goals_made = to_int_or_none(row.get("fieldGoalsMade"))
            three_pointers_attempted = to_int_or_none(row.get("threePointersAttempted"))
            free_throws_attempted = to_int_or_none(row.get("freeThrowsAttempted"))
            offensive_rebounds = to_int_or_none(row.get("reboundsOffensive"))
            defensive_rebounds = to_int_or_none(row.get("reboundsDefensive"))
            total_rebounds = to_int_or_none(row.get("reboundsTotal"))
            opponent_offensive_rebounds = (
                to_int_or_none(opponent.get("reboundsOffensive")) if opponent is not None else None
            )
            opponent_defensive_rebounds = (
                to_int_or_none(opponent.get("reboundsDefensive")) if opponent is not None else None
            )
            opponent_total_rebounds = (
                to_int_or_none(opponent.get("reboundsTotal")) if opponent is not None else None
            )
            assist_to_turnover_ratio = (
                round((assists or 0) / (to_int_or_none(row.get("turnovers")) or 0), 2)
                if (to_int_or_none(row.get("turnovers")) or 0) > 0
                else None
            )
            assist_percentage = (
                round((assists or 0) * 100.0 / field_goals_made, 1)
                if field_goals_made is not None and field_goals_made > 0
                else None
            )
            effective_field_goal_percentage = (
                round(
                    (
                        (field_goals_made or 0)
                        + (0.5 * (to_int_or_none(row.get("threePointersMade")) or 0))
                    )
                    * 100.0
                    / field_goals_attempted,
                    1,
                )
                if field_goals_attempted is not None and field_goals_attempted > 0
                else None
            )
            three_point_attempt_rate = (
                round(three_pointers_attempted / field_goals_attempted, 3)
                if three_pointers_attempted is not None
                and field_goals_attempted is not None
                and field_goals_attempted > 0
                else None
            )
            free_throw_attempt_rate = (
                round(free_throws_attempted / field_goals_attempted, 3)
                if free_throws_attempted is not None
                and field_goals_attempted is not None
                and field_goals_attempted > 0
                else None
            )
            true_shooting_denominator = 2.0 * (
                (field_goals_attempted or 0) + (0.44 * (free_throws_attempted or 0))
            )
            true_shooting_percentage = (
                round(((score or 0) * 100.0) / true_shooting_denominator, 1)
                if score is not None and true_shooting_denominator > 0
                else None
            )
            offensive_rebound_percentage = (
                round(
                    offensive_rebounds * 100.0
                    / (offensive_rebounds + opponent_defensive_rebounds),
                    1,
                )
                if offensive_rebounds is not None
                and opponent_defensive_rebounds is not None
                and (offensive_rebounds + opponent_defensive_rebounds) > 0
                else None
            )
            defensive_rebound_percentage = (
                round(
                    defensive_rebounds * 100.0
                    / (defensive_rebounds + opponent_offensive_rebounds),
                    1,
                )
                if defensive_rebounds is not None
                and opponent_offensive_rebounds is not None
                and (defensive_rebounds + opponent_offensive_rebounds) > 0
                else None
            )
            rebound_percentage = (
                round(total_rebounds * 100.0 / (total_rebounds + opponent_total_rebounds), 1)
                if total_rebounds is not None
                and opponent_total_rebounds is not None
                and (total_rebounds + opponent_total_rebounds) > 0
                else None
            )
            steal_percentage = (
                round(steals * 100.0 / defensive_possessions, 1)
                if steals is not None
                and defensive_possessions is not None
                and defensive_possessions > 0
                else None
            )
            block_percentage = (
                round((to_int_or_none(row.get("blocks")) or 0) * 100.0 / opponent_two_point_attempts, 1)
                if opponent_two_point_attempts is not None and opponent_two_point_attempts > 0
                else None
            )

            candidate = {
                "game_id": game_id,
                "team_id": team_id,
                "opponent_team_id": opponent_team_id,
                "game_start_time_utc": game.get("game_start_time_utc"),
                "game_date": game.get("game_date"),
                "season_year": game.get("season_year"),
                "season_type": game.get("season_type"),
                "team_home_or_away": side,
                "score": score,
                "opponent_score": opponent_score,
                "point_differential": (score - opponent_score) if score is not None and opponent_score is not None else None,
                "win_loss_result": win_loss_result,
                "minutes_played": minutes_played,
                "possessions": round(possessions, 1) if possessions is not None else None,
                "offensive_possessions": round(offensive_possessions, 1)
                if offensive_possessions is not None
                else None,
                "defensive_possessions": round(defensive_possessions, 1)
                if defensive_possessions is not None
                else None,
                "pace": round(possessions * 240.0 / minutes_played, 1)
                if possessions is not None and minutes_played is not None and minutes_played > 0
                else None,
                "offensive_rating": round(score * 100.0 / possessions, 1)
                if score is not None and possessions is not None and possessions > 0
                else None,
                "defensive_rating": round(opponent_score * 100.0 / possessions, 1)
                if opponent_score is not None and possessions is not None and possessions > 0
                else None,
                "net_rating": round(((score - opponent_score) * 100.0) / possessions, 1)
                if score is not None and opponent_score is not None and possessions is not None and possessions > 0
                else None,
                "assists": assists,
                "assist_percentage": assist_percentage,
                "opponent_assists": (
                    to_int_or_none(opponent.get("assists")) if opponent is not None else None
                ),
                "turnovers": to_int_or_none(row.get("turnovers")),
                "opponent_turnovers": (
                    to_int_or_none(opponent.get("turnovers")) if opponent is not None else None
                ),
                "assist_to_turnover_ratio": assist_to_turnover_ratio,
                "points_off_turnovers": to_int_or_none(row.get("pointsFromTurnovers")),
                "opponent_points_off_turnovers": (
                    to_int_or_none(opponent.get("pointsFromTurnovers")) if opponent is not None else None
                ),
                "steals": steals,
                "steal_percentage": steal_percentage,
                "opponent_steals": (
                    to_int_or_none(opponent.get("steals")) if opponent is not None else None
                ),
                "field_goals_attempted": field_goals_attempted,
                "field_goals_made": field_goals_made,
                "field_goals_percentage": _rounded_value(row.get("fieldGoalsPercentage"), 1),
                "effective_field_goal_percentage": effective_field_goal_percentage,
                "opponent_field_goals_attempted": (
                    to_int_or_none(opponent.get("fieldGoalsAttempted")) if opponent is not None else None
                ),
                "opponent_field_goals_made": (
                    to_int_or_none(opponent.get("fieldGoalsMade")) if opponent is not None else None
                ),
                "opponent_field_goals_percentage": (
                    _rounded_value(opponent.get("fieldGoalsPercentage"), 1) if opponent is not None else None
                ),
                "two_pointers_attempted": to_int_or_none(row.get("twoPointersAttempted")),
                "two_pointers_made": to_int_or_none(row.get("twoPointersMade")),
                "two_pointers_percentage": _rounded_value(row.get("twoPointersPercentage"), 1),
                "opponent_two_pointers_attempted": (
                    to_int_or_none(opponent.get("twoPointersAttempted")) if opponent is not None else None
                ),
                "opponent_two_pointers_made": (
                    to_int_or_none(opponent.get("twoPointersMade")) if opponent is not None else None
                ),
                "opponent_two_pointers_percentage": (
                    _rounded_value(opponent.get("twoPointersPercentage"), 1) if opponent is not None else None
                ),
                "three_pointers_attempted": three_pointers_attempted,
                "three_pointers_made": to_int_or_none(row.get("threePointersMade")),
                "three_pointers_percentage": _rounded_value(row.get("threePointersPercentage"), 1),
                "three_point_attempt_rate": three_point_attempt_rate,
                "opponent_three_pointers_attempted": (
                    to_int_or_none(opponent.get("threePointersAttempted")) if opponent is not None else None
                ),
                "opponent_three_pointers_made": (
                    to_int_or_none(opponent.get("threePointersMade")) if opponent is not None else None
                ),
                "opponent_three_pointers_percentage": (
                    _rounded_value(opponent.get("threePointersPercentage"), 1) if opponent is not None else None
                ),
                "free_throws_attempted": free_throws_attempted,
                "free_throws_made": to_int_or_none(row.get("freeThrowsMade")),
                "free_throws_percentage": _rounded_value(row.get("freeThrowsPercentage"), 1),
                "free_throw_attempt_rate": free_throw_attempt_rate,
                "true_shooting_percentage": true_shooting_percentage,
                "opponent_free_throws_attempted": (
                    to_int_or_none(opponent.get("freeThrowsAttempted")) if opponent is not None else None
                ),
                "opponent_free_throws_made": (
                    to_int_or_none(opponent.get("freeThrowsMade")) if opponent is not None else None
                ),
                "opponent_free_throws_percentage": (
                    _rounded_value(opponent.get("freeThrowsPercentage"), 1) if opponent is not None else None
                ),
                "offensive_rebounds": offensive_rebounds,
                "defensive_rebounds": defensive_rebounds,
                "total_rebounds": total_rebounds,
                "offensive_rebound_percentage": offensive_rebound_percentage,
                "defensive_rebound_percentage": defensive_rebound_percentage,
                "rebound_percentage": rebound_percentage,
                "opponent_offensive_rebounds": opponent_offensive_rebounds,
                "opponent_defensive_rebounds": opponent_defensive_rebounds,
                "opponent_total_rebounds": opponent_total_rebounds,
                "block_percentage": block_percentage,
                "fast_break_points": to_int_or_none(row.get("pointsFastBreak")),
                "opponent_fast_break_points": (
                    to_int_or_none(opponent.get("pointsFastBreak")) if opponent is not None else None
                ),
                "points_in_paint": to_int_or_none(row.get("pointsInThePaint")),
                "opponent_points_in_paint": (
                    to_int_or_none(opponent.get("pointsInThePaint")) if opponent is not None else None
                ),
                "second_chance_points": to_int_or_none(row.get("pointsSecondChance")),
                "opponent_second_chance_points": (
                    to_int_or_none(opponent.get("pointsSecondChance")) if opponent is not None else None
                ),
                "blocks": to_int_or_none(row.get("blocks")),
                "opponent_blocks": to_int_or_none(row.get("blocksReceived")),
                "offensive_fouls_committed": to_int_or_none(row.get("foulsOffensive")),
                "opponent_offensive_fouls_committed": (
                    to_int_or_none(opponent.get("foulsOffensive")) if opponent is not None else None
                ),
                "fouls_drawn": to_int_or_none(row.get("foulsDrawn")),
                "opponent_fouls_drawn": (
                    to_int_or_none(opponent.get("foulsDrawn")) if opponent is not None else None
                ),
                "personal_fouls_committed": to_int_or_none(row.get("foulsPersonal")),
                "opponent_personal_fouls_committed": (
                    to_int_or_none(opponent.get("foulsPersonal")) if opponent is not None else None
                ),
                "technical_fouls_committed": to_int_or_none(row.get("foulsTechnical")),
                "opponent_technical_fouls_committed": (
                    to_int_or_none(opponent.get("foulsTechnical")) if opponent is not None else None
                ),
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
    team_game_possession_context_table = read_parquet_table_from_s3(
        s3_client,
        TEAM_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        TEAM_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS,
    )
    team_game_defensive_shot_context_table = read_parquet_table_from_s3(
        s3_client,
        TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS,
    )
    rows = build_team_game_rows_from_tables(
        team_game_table,
        box_table,
        schedule_table,
        team_game_possession_context_table,
        team_game_defensive_shot_context_table,
    )
    write_parquet_to_s3(rows, TEAM_GAME_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
