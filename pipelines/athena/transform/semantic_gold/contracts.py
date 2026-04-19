"""Purpose: Define the semantic_gold v1 public table contract and S3 destinations.
Inputs: Schema decisions for semantic object tables.
Outputs: PyArrow schemas and Athena table specs for semantic_gold deployment.
Next file: deploy_semantic_gold_tables.py registers these tables in Athena.
"""

from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa

from pipelines.athena.transform.gold.gold_transform_helpers import S3_BUCKET


@dataclass(frozen=True)
class SemanticGoldTableSpec:
    table_name: str
    data_key: str
    table_location: str
    schema: pa.Schema


PLAYER_SCHEMA = pa.schema(
    [
        pa.field("person_id", pa.int64()),
        pa.field("full_name", pa.string()),
        pa.field("first_name", pa.string()),
        pa.field("last_name", pa.string()),
        pa.field("primary_position", pa.string()),
        pa.field("position_group", pa.string()),
        pa.field("latest_team_id", pa.int64()),
        pa.field("latest_jersey_number", pa.string()),
        pa.field("birth_date", pa.date32()),
        pa.field("school", pa.string()),
        pa.field("country", pa.string()),
        pa.field("height_inches", pa.int64()),
        pa.field("weight_lbs", pa.int64()),
        pa.field("draft_year", pa.int64()),
        pa.field("draft_round", pa.int64()),
        pa.field("draft_number", pa.int64()),
    ]
)

TEAM_SCHEMA = pa.schema(
    [
        pa.field("team_id", pa.int64()),
        pa.field("team_name", pa.string()),
        pa.field("team_city", pa.string()),
        pa.field("team_abbreviation", pa.string()),
        pa.field("team_slug", pa.string()),
        pa.field("conference", pa.string()),
        pa.field("division", pa.string()),
        pa.field("first_seen_game_date", pa.date32()),
        pa.field("last_seen_game_date", pa.date32()),
    ]
)

ARENA_SCHEMA = pa.schema(
    [
        pa.field("arena_id", pa.int64()),
        pa.field("arena_name", pa.string()),
        pa.field("arena_city", pa.string()),
        pa.field("arena_state", pa.string()),
        pa.field("arena_country", pa.string()),
        pa.field("arena_timezone", pa.string()),
    ]
)

GAME_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("season_year", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("game_date", pa.date32()),
        pa.field("game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("arena_id", pa.int64()),
        pa.field("home_team_id", pa.int64()),
        pa.field("away_team_id", pa.int64()),
    ]
)

PLAYER_GAME_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("person_id", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("team_side", pa.string()),
        pa.field("game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("game_date", pa.date32()),
        pa.field("season_year", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("is_starter", pa.int64()),
        pa.field("did_play", pa.int64()),
        pa.field("minutes_played_decimal", pa.float64()),
        pa.field("plus_minus", pa.int64()),
        pa.field("assists", pa.int64()),
        pa.field("shots_blocked", pa.int64()),
        pa.field("shots_blocked_against", pa.int64()),
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
    ]
)

TEAM_GAME_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("team_id", pa.int64()),
        pa.field("opponent_team_id", pa.int64()),
        pa.field("game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("game_date", pa.date32()),
        pa.field("season_year", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("team_side", pa.string()),
        pa.field("score", pa.int64()),
        pa.field("opponent_score", pa.int64()),
        pa.field("point_differential", pa.int64()),
        pa.field("seconds_played_total", pa.float64()),
        pa.field("minutes_played_decimal", pa.float64()),
        pa.field("assists", pa.int64()),
        pa.field("shots_blocked", pa.int64()),
        pa.field("shots_blocked_against", pa.int64()),
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
        pa.field("game_result", pa.string()),
    ]
)

PLAYER_SEASON_SCHEMA = pa.schema(
    [
        pa.field("person_id", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("team_count", pa.int64()),
        pa.field("is_multi_team_season", pa.int64()),
        pa.field("games_played", pa.int64()),
        pa.field("total_points", pa.int64()),
        pa.field("average_points", pa.float64()),
    ]
)

PLAYER_SEASON_TEAM_SCHEMA = pa.schema(
    [
        pa.field("person_id", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("games_played", pa.int64()),
        pa.field("total_points", pa.int64()),
        pa.field("average_points", pa.float64()),
    ]
)

TEAM_SEASON_SCHEMA = pa.schema(
    [
        pa.field("team_id", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("games_played", pa.int64()),
        pa.field("wins", pa.int64()),
        pa.field("losses", pa.int64()),
        pa.field("win_percentage", pa.float64()),
    ]
)


SEMANTIC_GOLD_TABLE_SPECS = [
    SemanticGoldTableSpec(
        table_name="player",
        data_key="semantic_gold/player/player.parquet",
        table_location=f"s3://{S3_BUCKET}/semantic_gold/player/",
        schema=PLAYER_SCHEMA,
    ),
    SemanticGoldTableSpec(
        table_name="team",
        data_key="semantic_gold/team/team.parquet",
        table_location=f"s3://{S3_BUCKET}/semantic_gold/team/",
        schema=TEAM_SCHEMA,
    ),
    SemanticGoldTableSpec(
        table_name="arena",
        data_key="semantic_gold/arena/arena.parquet",
        table_location=f"s3://{S3_BUCKET}/semantic_gold/arena/",
        schema=ARENA_SCHEMA,
    ),
    SemanticGoldTableSpec(
        table_name="game",
        data_key="semantic_gold/game/game.parquet",
        table_location=f"s3://{S3_BUCKET}/semantic_gold/game/",
        schema=GAME_SCHEMA,
    ),
    SemanticGoldTableSpec(
        table_name="player_game",
        data_key="semantic_gold/player_game/player_game.parquet",
        table_location=f"s3://{S3_BUCKET}/semantic_gold/player_game/",
        schema=PLAYER_GAME_SCHEMA,
    ),
    SemanticGoldTableSpec(
        table_name="team_game",
        data_key="semantic_gold/team_game/team_game.parquet",
        table_location=f"s3://{S3_BUCKET}/semantic_gold/team_game/",
        schema=TEAM_GAME_SCHEMA,
    ),
    SemanticGoldTableSpec(
        table_name="player_season",
        data_key="semantic_gold/player_season/player_season.parquet",
        table_location=f"s3://{S3_BUCKET}/semantic_gold/player_season/",
        schema=PLAYER_SEASON_SCHEMA,
    ),
    SemanticGoldTableSpec(
        table_name="player_season_team",
        data_key="semantic_gold/player_season_team/player_season_team.parquet",
        table_location=f"s3://{S3_BUCKET}/semantic_gold/player_season_team/",
        schema=PLAYER_SEASON_TEAM_SCHEMA,
    ),
    SemanticGoldTableSpec(
        table_name="team_season",
        data_key="semantic_gold/team_season/team_season.parquet",
        table_location=f"s3://{S3_BUCKET}/semantic_gold/team_season/",
        schema=TEAM_SEASON_SCHEMA,
    ),
]
