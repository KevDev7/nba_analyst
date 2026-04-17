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
        pa.field("player_name", pa.string()),
        pa.field("first_name", pa.string()),
        pa.field("family_name", pa.string()),
        pa.field("display_name", pa.string()),
        pa.field("primary_position", pa.string()),
        pa.field("position_group", pa.string()),
        pa.field("latest_team_id", pa.int64()),
        pa.field("latest_jersey_number", pa.string()),
        pa.field("latest_status", pa.string()),
        pa.field("first_seen_game_date", pa.date32()),
        pa.field("last_seen_game_date", pa.date32()),
        pa.field("first_season_played", pa.string()),
        pa.field("last_season_played", pa.string()),
        pa.field("birth_date", pa.date32()),
        pa.field("school", pa.string()),
        pa.field("country", pa.string()),
        pa.field("height_inches", pa.int64()),
        pa.field("weight_lbs", pa.int64()),
        pa.field("draft_year", pa.int64()),
        pa.field("draft_round", pa.int64()),
        pa.field("draft_number", pa.int64()),
        pa.field("is_guard", pa.int64()),
        pa.field("is_forward", pa.int64()),
        pa.field("is_center", pa.int64()),
        pa.field("basketball_reference_player_id", pa.string()),
        pa.field("bbr_match_method", pa.string()),
        pa.field("bbr_match_confidence", pa.float64()),
        pa.field("bbr_profile_url", pa.string()),
        pa.field("bbr_formal_name", pa.string()),
        pa.field("bbr_position_raw", pa.string()),
        pa.field("bbr_shoots", pa.string()),
        pa.field("bbr_height_cm", pa.int64()),
        pa.field("bbr_weight_kg", pa.int64()),
        pa.field("bbr_college_raw", pa.string()),
        pa.field("bbr_birth_country_code", pa.string()),
        pa.field("bbr_headshot_url", pa.string()),
        pa.field("bbr_hall_of_fame_flag", pa.int64()),
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

GAME_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("league_id", pa.string()),
        pa.field("game_code", pa.string()),
        pa.field("game_sequence", pa.int64()),
        pa.field("game_date", pa.date32()),
        pa.field("game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("local_market_game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("home_market_game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("away_market_game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("eastern_time_game_datetime_utc", pa.timestamp("us", tz="UTC")),
        pa.field("game_status_code", pa.int64()),
        pa.field("game_status_text", pa.string()),
        pa.field("postponed_status", pa.string()),
        pa.field("is_if_necessary", pa.bool_()),
        pa.field("game_label", pa.string()),
        pa.field("game_sublabel", pa.string()),
        pa.field("game_subtype", pa.string()),
        pa.field("series_game_number", pa.string()),
        pa.field("series_text", pa.string()),
        pa.field("is_neutral_site", pa.bool_()),
        pa.field("duration_minutes", pa.int64()),
        pa.field("attendance", pa.int64()),
        pa.field("is_sellout", pa.bool_()),
        pa.field("regulation_periods", pa.int64()),
        pa.field("current_period", pa.int64()),
        pa.field("game_clock", pa.string()),
        pa.field("arena_id", pa.int64()),
        pa.field("arena_name", pa.string()),
        pa.field("arena_city", pa.string()),
        pa.field("arena_state", pa.string()),
        pa.field("arena_country", pa.string()),
        pa.field("arena_timezone", pa.string()),
        pa.field("home_team_id", pa.int64()),
        pa.field("away_team_id", pa.int64()),
        pa.field("home_team_name", pa.string()),
        pa.field("away_team_name", pa.string()),
        pa.field("home_team_city", pa.string()),
        pa.field("away_team_city", pa.string()),
        pa.field("home_team_abbreviation", pa.string()),
        pa.field("away_team_abbreviation", pa.string()),
        pa.field("home_team_slug", pa.string()),
        pa.field("away_team_slug", pa.string()),
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
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("player_position", pa.string()),
        pa.field("player_status", pa.string()),
        pa.field("player_order", pa.int64()),
        pa.field("is_starter", pa.int64()),
        pa.field("is_on_court", pa.int64()),
        pa.field("did_play", pa.int64()),
        pa.field("seconds_played_total", pa.float64()),
        pa.field("minutes_played_decimal", pa.float64()),
        pa.field("plus_minus_points", pa.int64()),
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
    ]
)

PLAYER_SEASON_SCHEMA = pa.schema(
    [
        pa.field("person_id", pa.int64()),
        pa.field("player_name", pa.string()),
        pa.field("season_year", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
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
        pa.field("player_name", pa.string()),
        pa.field("team_id", pa.int64()),
        pa.field("team_name", pa.string()),
        pa.field("team_abbreviation", pa.string()),
        pa.field("season_year", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("games_played", pa.int64()),
        pa.field("total_points", pa.int64()),
        pa.field("average_points", pa.float64()),
    ]
)

TEAM_SEASON_SCHEMA = pa.schema(
    [
        pa.field("team_id", pa.int64()),
        pa.field("team_name", pa.string()),
        pa.field("team_abbreviation", pa.string()),
        pa.field("season_year", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("games_played", pa.int64()),
        pa.field("wins", pa.int64()),
        pa.field("losses", pa.int64()),
        pa.field("win_percentage", pa.float64()),
        pa.field("average_points", pa.float64()),
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
