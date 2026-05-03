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
    to_bool_or_none,
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
)

from .contracts import PLAYER_GAME_SCHEMA
from .transform_to_game_parquet import build_game_rows_from_tables
from .transform_to_team_game_parquet import (
    TEAM_GAME_REQUIRED_COLUMNS,
    TEAM_GAME_SOURCE_KEY,
    build_team_game_rows_from_tables,
)

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/player_game/player_game.parquet"
PLAYER_GAME_POSSESSION_CONTEXT_SOURCE_KEY = "silver/player_game_possession_context.parquet"
PLAYER_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "person_id",
    "offensive_possessions",
    "defensive_possessions",
    "used_offensive_possessions",
    "team_points_for_while_on_court",
    "team_points_against_while_on_court",
]
PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY = "silver/player_game_defensive_shot_context.parquet"
PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "person_id",
    "opponent_two_point_attempts_while_on_court",
]
PLAYER_GAME_OPPORTUNITY_CONTEXT_SOURCE_KEY = "silver/player_game_opportunity_context.parquet"
PLAYER_GAME_OPPORTUNITY_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "person_id",
    "teammate_field_goals_made_while_on_court",
    "offensive_rebound_opportunities_while_on_court",
    "defensive_rebound_opportunities_while_on_court",
    "rebound_opportunities_while_on_court",
]
TEAM_GAME_USAGE_SOURCE_KEY = "silver/boxscore_team_game.parquet"
TEAM_GAME_USAGE_REQUIRED_COLUMNS = [
    "gameId",
    "teamId",
    "minutesCalculated",
    "minutes",
    "fieldGoalsAttempted",
    "freeThrowsAttempted",
    "turnovers",
    "turnoversTotal",
]

def build_player_game_possession_context_map_from_table(
    player_game_possession_context_table: pa.Table | None,
) -> dict[tuple[str, int], dict[str, object]]:
    if player_game_possession_context_table is None:
        return {}

    possession_context_by_key: dict[tuple[str, int], dict[str, object]] = {}
    for row in player_game_possession_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        person_id = to_positive_int_or_none(row.get("person_id"))
        if game_id is None or person_id is None:
            continue
        possession_context_by_key[(game_id, person_id)] = {
            "offensive_possessions": to_float_or_none(row.get("offensive_possessions")),
            "defensive_possessions": to_float_or_none(row.get("defensive_possessions")),
            "used_offensive_possessions": to_float_or_none(row.get("used_offensive_possessions")),
            "team_points_for_while_on_court": to_float_or_none(
                row.get("team_points_for_while_on_court")
            ),
            "team_points_against_while_on_court": to_float_or_none(
                row.get("team_points_against_while_on_court")
            ),
        }

    return possession_context_by_key


def build_player_game_defensive_shot_context_map_from_table(
    player_game_defensive_shot_context_table: pa.Table | None,
) -> dict[tuple[str, int], dict[str, object]]:
    if player_game_defensive_shot_context_table is None:
        return {}

    defensive_shot_context_by_key: dict[tuple[str, int], dict[str, object]] = {}
    for row in player_game_defensive_shot_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        person_id = to_positive_int_or_none(row.get("person_id"))
        if game_id is None or person_id is None:
            continue
        defensive_shot_context_by_key[(game_id, person_id)] = {
            "opponent_two_point_attempts_while_on_court": to_float_or_none(
                row.get("opponent_two_point_attempts_while_on_court")
            ),
        }

    return defensive_shot_context_by_key


def build_player_game_opportunity_context_map_from_table(
    player_game_opportunity_context_table: pa.Table | None,
) -> dict[tuple[str, int], dict[str, object]]:
    if player_game_opportunity_context_table is None:
        return {}

    opportunity_context_by_key: dict[tuple[str, int], dict[str, object]] = {}
    for row in player_game_opportunity_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        person_id = to_positive_int_or_none(row.get("person_id"))
        if game_id is None or person_id is None:
            continue
        opportunity_context_by_key[(game_id, person_id)] = {
            "teammate_field_goals_made_while_on_court": to_float_or_none(
                row.get("teammate_field_goals_made_while_on_court")
            ),
            "offensive_rebound_opportunities_while_on_court": to_float_or_none(
                row.get("offensive_rebound_opportunities_while_on_court")
            ),
            "defensive_rebound_opportunities_while_on_court": to_float_or_none(
                row.get("defensive_rebound_opportunities_while_on_court")
            ),
            "rebound_opportunities_while_on_court": to_float_or_none(
                row.get("rebound_opportunities_while_on_court")
            ),
        }

    return opportunity_context_by_key


def build_team_usage_context_map_from_table(
    team_usage_context_table: pa.Table | None,
) -> dict[tuple[str, int], dict[str, object]]:
    if team_usage_context_table is None:
        return {}

    context_by_key: dict[tuple[str, int], dict[str, object]] = {}
    for row in team_usage_context_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId")) or to_str_or_none(row.get("game_id"))
        team_id = to_positive_int_or_none(row.get("teamId")) or to_positive_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        minutes_played = parse_iso_duration_seconds(row.get("minutesCalculated")) or parse_iso_duration_seconds(row.get("minutes"))
        context_by_key[(game_id, team_id)] = {
            "minutes_played": round(minutes_played / 60.0, 3) if minutes_played is not None else None,
            "field_goals_attempted": to_int_or_none(row.get("fieldGoalsAttempted"))
            or to_int_or_none(row.get("field_goals_attempted")),
            "free_throws_attempted": to_int_or_none(row.get("freeThrowsAttempted"))
            or to_int_or_none(row.get("free_throws_attempted")),
            "turnovers": to_int_or_none(row.get("turnovers"))
            or to_int_or_none(row.get("turnoversTotal"))
            or to_int_or_none(row.get("turnovers_total")),
        }
    return context_by_key


def _counted_usage_percentage(
    *,
    offensive_possessions: float | None,
    used_offensive_possessions: float | None,
    proxy_player_usage_numerator: float,
) -> float | None:
    if offensive_possessions is None or offensive_possessions <= 0:
        return None
    if used_offensive_possessions is None or used_offensive_possessions < 0:
        return None
    if used_offensive_possessions > offensive_possessions:
        return None
    if used_offensive_possessions == 0 and proxy_player_usage_numerator > 0:
        return None
    if proxy_player_usage_numerator > 0 and used_offensive_possessions < (0.25 * proxy_player_usage_numerator):
        return None
    return round((used_offensive_possessions * 100.0) / offensive_possessions, 1)


def _proxy_usage_percentage(
    *,
    player_field_goals_attempted: int | None,
    player_free_throws_attempted: int | None,
    player_turnovers: int | None,
    player_minutes_played: float | None,
    team_field_goals_attempted: int | None,
    team_free_throws_attempted: int | None,
    team_turnovers: int | None,
    team_minutes_played: float | None,
) -> float | None:
    if player_minutes_played is None or player_minutes_played <= 0:
        return None
    if team_minutes_played is None or team_minutes_played <= 0:
        return None
    player_usage_numerator = (
        float(player_field_goals_attempted or 0)
        + (0.44 * float(player_free_throws_attempted or 0))
        + float(player_turnovers or 0)
    )
    team_usage_denominator = (
        float(team_field_goals_attempted or 0)
        + (0.44 * float(team_free_throws_attempted or 0))
        + float(team_turnovers or 0)
    )
    if team_usage_denominator <= 0:
        return None
    return round(
        100.0
        * player_usage_numerator
        * team_minutes_played
        / (team_usage_denominator * 5.0 * player_minutes_played),
        1,
    )


def build_player_game_rows_from_tables(
    player_table: pa.Table,
    box_table: pa.Table,
    schedule_table: pa.Table,
    team_game_table: pa.Table,
    player_game_possession_context_table: pa.Table | None = None,
    player_game_opportunity_context_table: pa.Table | None = None,
    team_usage_context_table: pa.Table | None = None,
    player_game_defensive_shot_context_table: pa.Table | None = None,
) -> list[dict[str, object]]:
    game_rows = build_game_rows_from_tables(box_table, schedule_table, team_game_table)
    game_by_id = {to_str_or_none(row.get("game_id")): row for row in game_rows}
    team_game_rows = build_team_game_rows_from_tables(team_game_table, box_table, schedule_table)
    team_game_context_by_key = {
        (to_str_or_none(row.get("game_id")), to_positive_int_or_none(row.get("team_id"))): row
        for row in team_game_rows
    }
    player_game_possession_context_by_key = build_player_game_possession_context_map_from_table(
        player_game_possession_context_table
    )
    player_game_opportunity_context_by_key = build_player_game_opportunity_context_map_from_table(
        player_game_opportunity_context_table
    )
    player_game_defensive_shot_context_by_key = (
        build_player_game_defensive_shot_context_map_from_table(
            player_game_defensive_shot_context_table
        )
    )
    team_usage_context_by_key = build_team_usage_context_map_from_table(
        team_usage_context_table if team_usage_context_table is not None else team_game_table
    )
    semantic_team_ids = set(TEAM_CONTEXT_BY_ID.keys())
    deduped: dict[tuple[str, int], dict[str, object]] = {}

    def quality_score(row: dict[str, object]) -> int:
        keys = [
            "game_start_time_utc",
            "game_date",
            "season_year",
            "team_home_or_away",
            "minutes_played",
            "points",
        ]
        return sum(1 for key in keys if row.get(key) is not None)

    for row in player_table.to_pylist():
        game_id = to_str_or_none(row.get("gameId"))
        person_id = to_positive_int_or_none(row.get("personId"))
        team_id = to_positive_int_or_none(row.get("teamId"))
        if game_id is None or person_id is None or team_id not in semantic_team_ids:
            continue
        did_play = to_bool_or_none(row.get("played"))
        if did_play is not True:
            continue
        game = game_by_id.get(game_id, {})
        team_game_context = team_game_context_by_key.get((game_id, team_id), {})
        player_possession_context = player_game_possession_context_by_key.get(
            (game_id, person_id), {}
        )
        team_usage_context = team_usage_context_by_key.get((game_id, team_id), {})
        player_opportunity_context = player_game_opportunity_context_by_key.get(
            (game_id, person_id), {}
        )
        player_defensive_shot_context = player_game_defensive_shot_context_by_key.get(
            (game_id, person_id), {}
        )
        assists = to_int_or_none(row.get("assists"))
        offensive_rebounds = to_int_or_none(row.get("reboundsOffensive"))
        defensive_rebounds = to_int_or_none(row.get("reboundsDefensive"))
        total_rebounds = to_int_or_none(row.get("reboundsTotal"))
        teammate_field_goals_made_while_on_court = to_float_or_none(
            player_opportunity_context.get("teammate_field_goals_made_while_on_court")
        )
        offensive_rebound_opportunities_while_on_court = to_float_or_none(
            player_opportunity_context.get("offensive_rebound_opportunities_while_on_court")
        )
        defensive_rebound_opportunities_while_on_court = to_float_or_none(
            player_opportunity_context.get("defensive_rebound_opportunities_while_on_court")
        )
        rebound_opportunities_while_on_court = to_float_or_none(
            player_opportunity_context.get("rebound_opportunities_while_on_court")
        )
        seconds_played_total = parse_iso_duration_seconds(row.get("minutesCalculated")) or parse_iso_duration_seconds(row.get("minutes"))
        minutes_played = round(seconds_played_total / 60.0, 1) if seconds_played_total is not None else None
        offensive_possessions = to_float_or_none(player_possession_context.get("offensive_possessions"))
        defensive_possessions = to_float_or_none(player_possession_context.get("defensive_possessions"))
        team_points_for_while_on_court = to_float_or_none(
            player_possession_context.get("team_points_for_while_on_court")
        )
        team_points_against_while_on_court = to_float_or_none(
            player_possession_context.get("team_points_against_while_on_court")
        )
        used_offensive_possessions = to_float_or_none(player_possession_context.get("used_offensive_possessions"))
        opponent_two_point_attempts_while_on_court = to_float_or_none(
            player_defensive_shot_context.get("opponent_two_point_attempts_while_on_court")
        )
        field_goals_attempted = to_int_or_none(row.get("fieldGoalsAttempted"))
        free_throws_attempted = to_int_or_none(row.get("freeThrowsAttempted"))
        turnovers = to_int_or_none(row.get("turnovers"))
        offensive_rating = (
            round((team_points_for_while_on_court * 100.0) / offensive_possessions, 1)
            if team_points_for_while_on_court is not None
            and offensive_possessions is not None
            and offensive_possessions > 0
            else None
        )
        defensive_rating = (
            round((team_points_against_while_on_court * 100.0) / defensive_possessions, 1)
            if team_points_against_while_on_court is not None
            and defensive_possessions is not None
            and defensive_possessions > 0
            else None
        )
        block_percentage = (
            round(
                ((to_int_or_none(row.get("blocks")) or 0) * 100.0)
                / opponent_two_point_attempts_while_on_court,
                1,
            )
            if opponent_two_point_attempts_while_on_court is not None
            and opponent_two_point_attempts_while_on_court > 0
            else None
        )
        proxy_player_usage_numerator = (
            float(field_goals_attempted or 0)
            + (0.44 * float(free_throws_attempted or 0))
            + float(turnovers or 0)
        )
        usage_percentage = _counted_usage_percentage(
            offensive_possessions=offensive_possessions,
            used_offensive_possessions=used_offensive_possessions,
            proxy_player_usage_numerator=proxy_player_usage_numerator,
        )
        if usage_percentage is None:
            usage_percentage = _proxy_usage_percentage(
                player_field_goals_attempted=field_goals_attempted,
                player_free_throws_attempted=free_throws_attempted,
                player_turnovers=turnovers,
                player_minutes_played=minutes_played,
                team_field_goals_attempted=to_int_or_none(team_usage_context.get("field_goals_attempted")),
                team_free_throws_attempted=to_int_or_none(team_usage_context.get("free_throws_attempted")),
                team_turnovers=to_int_or_none(team_usage_context.get("turnovers")),
                team_minutes_played=to_float_or_none(team_usage_context.get("minutes_played")),
            )
        candidate = {
            "game_id": game_id,
            "person_id": person_id,
            "team_id": team_id,
            "opponent_team_id": team_game_context.get("opponent_team_id"),
            "team_home_or_away": to_str_or_none(row.get("team_side")),
            "game_start_time_utc": game.get("game_start_time_utc"),
            "game_date": game.get("game_date"),
            "season_year": game.get("season_year"),
            "season_type": game.get("season_type"),
            "is_starter": to_bool_or_none(row.get("starter")),
            "minutes_played": minutes_played,
            "offensive_possessions": round(offensive_possessions, 1)
            if offensive_possessions is not None
            else None,
            "defensive_possessions": round(defensive_possessions, 1)
            if defensive_possessions is not None
            else None,
            "assist_percentage": round((assists or 0) * 100.0 / teammate_field_goals_made_while_on_court, 1)
            if teammate_field_goals_made_while_on_court not in {None, 0}
            else None,
            "usage_percentage": usage_percentage,
            "plus_minus": to_int_or_none(row.get("plusMinusPoints")),
            "assists": assists,
            "blocks": to_int_or_none(row.get("blocks")),
            "opponent_blocks": to_int_or_none(row.get("blocksReceived")),
            "field_goals_attempted": field_goals_attempted,
            "field_goals_made": to_int_or_none(row.get("fieldGoalsMade")),
            "offensive_fouls_committed": to_int_or_none(row.get("foulsOffensive")),
            "fouls_drawn": to_int_or_none(row.get("foulsDrawn")),
            "personal_fouls_committed": to_int_or_none(row.get("foulsPersonal")),
            "technical_fouls_committed": to_int_or_none(row.get("foulsTechnical")),
            "free_throws_attempted": free_throws_attempted,
            "free_throws_made": to_int_or_none(row.get("freeThrowsMade")),
            "offensive_rating": offensive_rating,
            "defensive_rating": defensive_rating,
            "defensive_rebounds": defensive_rebounds,
            "offensive_rebounds": offensive_rebounds,
            "total_rebounds": total_rebounds,
            "offensive_rebound_percentage": round(
                (offensive_rebounds or 0) * 100.0 / offensive_rebound_opportunities_while_on_court,
                1,
            )
            if offensive_rebound_opportunities_while_on_court not in {None, 0}
            else None,
            "defensive_rebound_percentage": round(
                (defensive_rebounds or 0) * 100.0 / defensive_rebound_opportunities_while_on_court,
                1,
            )
            if defensive_rebound_opportunities_while_on_court not in {None, 0}
            else None,
            "rebound_percentage": round((total_rebounds or 0) * 100.0 / rebound_opportunities_while_on_court, 1)
            if rebound_opportunities_while_on_court not in {None, 0}
            else None,
            "steals": to_int_or_none(row.get("steals")),
            "block_percentage": block_percentage,
            "turnovers": turnovers,
            "points": to_int_or_none(row.get("points")),
            "three_pointers_attempted": to_int_or_none(row.get("threePointersAttempted")),
            "three_pointers_made": to_int_or_none(row.get("threePointersMade")),
            "two_pointers_attempted": to_int_or_none(row.get("twoPointersAttempted")),
            "two_pointers_made": to_int_or_none(row.get("twoPointersMade")),
            "fast_break_points": to_int_or_none(row.get("pointsFastBreak")),
            "points_in_paint": to_int_or_none(row.get("pointsInThePaint")),
            "second_chance_points": to_int_or_none(row.get("pointsSecondChance")),
            "win_loss_result": team_game_context.get("win_loss_result"),
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
    player_game_possession_context_table = read_parquet_table_from_s3(
        s3_client,
        PLAYER_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        PLAYER_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS,
    )
    player_game_opportunity_context_table = read_parquet_table_from_s3(
        s3_client,
        PLAYER_GAME_OPPORTUNITY_CONTEXT_SOURCE_KEY,
        PLAYER_GAME_OPPORTUNITY_CONTEXT_REQUIRED_COLUMNS,
    )
    player_game_defensive_shot_context_table = read_parquet_table_from_s3(
        s3_client,
        PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS,
    )
    team_usage_context_table = read_parquet_table_from_s3(
        s3_client,
        TEAM_GAME_USAGE_SOURCE_KEY,
        TEAM_GAME_USAGE_REQUIRED_COLUMNS,
    )
    rows = build_player_game_rows_from_tables(
        player_table,
        box_table,
        schedule_table,
        team_game_table,
        player_game_possession_context_table,
        player_game_opportunity_context_table,
        team_usage_context_table,
        player_game_defensive_shot_context_table,
    )
    write_parquet_to_s3(rows, PLAYER_GAME_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
