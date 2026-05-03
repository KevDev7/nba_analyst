from __future__ import annotations

import json
from pathlib import Path

from pipelines.athena.transform.semantic_gold.contracts import (
    ARENA_SCHEMA,
    GAME_SCHEMA,
    PLAYER_GAME_SCHEMA,
    PLAYER_SCHEMA,
    PLAYER_SEASON_SCHEMA,
    PLAYER_SEASON_TEAM_SCHEMA,
    SEMANTIC_GOLD_TABLE_SPECS,
    TEAM_GAME_SCHEMA,
    TEAM_SCHEMA,
    TEAM_SEASON_SCHEMA,
)
from pipelines.athena.transform.semantic_gold import (
    transform_to_arena_parquet as arena_transform,
    transform_to_game_parquet as game_transform,
    transform_to_player_game_parquet as player_game_transform,
    transform_to_player_parquet as player_transform,
    transform_to_player_season_parquet as player_season_transform,
    transform_to_player_season_team_parquet as player_season_team_transform,
    transform_to_team_season_parquet as team_season_transform,
    transform_to_team_game_parquet as team_game_transform,
    transform_to_team_parquet as team_transform,
)

ROOT = Path(__file__).resolve().parents[4]
ATTRIBUTE_INVENTORY_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_gold_attribute_inventory.json"
)


def test_public_semantic_schemas_exclude_warehouse_only_fields() -> None:
    forbidden_columns = {
        "player_sk",
        "team_sk",
        "game_sk",
        "date_sk",
        "record_source",
        "created_at_utc",
        "updated_at_utc",
        "source_meta_version",
        "source_meta_code",
        "source_request",
        "source_meta_time_utc",
    }
    for spec in SEMANTIC_GOLD_TABLE_SPECS:
        assert forbidden_columns.isdisjoint(set(spec.schema.names)), spec.table_name


def test_player_schema_uses_business_key_and_enrichment_fields() -> None:
    names = set(PLAYER_SCHEMA.names)
    assert "person_id" in names
    assert "full_name" in names
    assert "last_name" in names
    assert "position_group" in names
    assert "first_season_played" not in names
    assert "last_season_played" not in names
    assert "latest_status" not in names
    assert "first_seen_game_date" not in names
    assert "last_seen_game_date" not in names
    assert "basketball_reference_player_id" not in names
    assert "player_sk" not in names


def test_game_schema_keeps_business_context_without_internal_meta() -> None:
    names = set(GAME_SCHEMA.names)
    assert {"game_id", "season_year", "home_team_id", "away_team_id", "arena_id"}.issubset(names)
    assert "arena_name" not in names
    assert "source_meta_version" not in names
    assert "record_source" not in names


def test_arena_schema_keeps_reusable_venue_context() -> None:
    names = set(ARENA_SCHEMA.names)
    assert {"arena_id", "arena_name", "arena_city", "arena_state", "arena_country", "arena_timezone"}.issubset(names)


def test_team_schema_keeps_reusable_team_location_context() -> None:
    names = set(TEAM_SCHEMA.names)
    assert {"team_id", "team_name", "team_city", "team_state", "team_country"}.issubset(names)


def test_fact_like_schemas_keep_link_keys_and_business_grain_fields() -> None:
    player_game_names = set(PLAYER_GAME_SCHEMA.names)
    team_game_names = set(TEAM_GAME_SCHEMA.names)
    player_season_names = set(PLAYER_SEASON_SCHEMA.names)
    player_season_team_names = set(PLAYER_SEASON_TEAM_SCHEMA.names)
    team_season_names = set(TEAM_SEASON_SCHEMA.names)

    assert {
        "game_id",
        "person_id",
        "team_id",
        "opponent_team_id",
        "points",
        "minutes_played",
        "offensive_possessions",
        "defensive_possessions",
        "assist_percentage",
        "usage_percentage",
        "offensive_rating",
        "defensive_rating",
        "offensive_rebound_percentage",
        "defensive_rebound_percentage",
        "rebound_percentage",
        "block_percentage",
        "win_loss_result",
    }.issubset(player_game_names)
    assert {
        "field_goals_percentage",
        "two_pointers_percentage",
        "three_pointers_percentage",
        "free_throws_percentage",
        "assist_to_turnover_ratio",
        "effective_field_goal_percentage",
        "true_shooting_percentage",
        "three_point_attempt_rate",
        "free_throw_attempt_rate",
        "possessions",
        "pace",
        "net_rating",
        "steal_percentage",
    }.isdisjoint(player_game_names)
    assert "is_on_court" not in player_game_names
    assert "seconds_played_total" not in player_game_names
    assert "blocks" in player_game_names
    assert "opponent_blocks" in player_game_names
    assert {
        "game_id",
        "team_id",
        "opponent_team_id",
        "score",
        "opponent_score",
        "minutes_played",
        "offensive_possessions",
        "defensive_possessions",
        "block_percentage",
        "points_off_turnovers",
        "opponent_points_off_turnovers",
        "opponent_field_goals_attempted",
        "opponent_assists",
        "opponent_offensive_fouls_committed",
        "opponent_two_pointers_attempted",
        "opponent_technical_fouls_committed",
    }.issubset(team_game_names)
    assert {
        "point_differential",
        "possessions",
        "pace",
        "offensive_rating",
        "defensive_rating",
        "net_rating",
        "assist_percentage",
        "assist_to_turnover_ratio",
        "three_point_attempt_rate",
        "free_throw_attempt_rate",
        "offensive_rebound_percentage",
        "defensive_rebound_percentage",
        "rebound_percentage",
        "steal_percentage",
        "effective_field_goal_percentage",
        "true_shooting_percentage",
        "field_goals_percentage",
        "opponent_field_goals_percentage",
        "two_pointers_percentage",
        "opponent_two_pointers_percentage",
        "three_pointers_percentage",
        "opponent_three_pointers_percentage",
        "free_throws_percentage",
        "opponent_free_throws_percentage",
    }.isdisjoint(team_game_names)
    assert {
        "person_id",
        "season_year",
        "season_type",
        "age_on_jan_31",
        "games_played",
        "games_started",
        "minutes_total",
        "points_total",
        "assists_total",
        "rebounds_total",
        "offensive_rebounds_total",
        "defensive_rebounds_total",
        "field_goals_made_total",
        "field_goals_attempted_total",
        "three_pointers_made_total",
        "three_pointers_attempted_total",
        "two_pointers_made_total",
        "two_pointers_attempted_total",
        "free_throws_made_total",
        "free_throws_attempted_total",
        "opponent_blocks_total",
        "offensive_fouls_committed_total",
        "fouls_drawn_total",
        "personal_fouls_committed_total",
        "technical_fouls_committed_total",
        "fast_break_points_total",
        "points_in_paint_total",
        "second_chance_points_total",
        "steals_total",
        "blocks_total",
        "turnovers_total",
        "plus_minus_total",
        "offensive_rebound_percentage",
        "defensive_rebound_percentage",
        "rebound_percentage",
        "usage_percentage",
        "offensive_possessions_total",
        "defensive_possessions_total",
        "defensive_rating",
        "net_rating",
        "pace",
        "block_percentage",
    }.issubset(player_season_names)
    assert {
        "person_id",
        "team_id",
        "season_year",
        "season_type",
        "games_played",
        "games_started",
        "minutes_total",
        "points_total",
        "assists_total",
        "rebounds_total",
        "offensive_rebounds_total",
        "defensive_rebounds_total",
        "steals_total",
        "blocks_total",
        "opponent_blocks_total",
        "turnovers_total",
        "plus_minus_total",
        "offensive_fouls_committed_total",
        "personal_fouls_committed_total",
        "technical_fouls_committed_total",
        "fouls_drawn_total",
        "fast_break_points_total",
        "points_in_paint_total",
        "second_chance_points_total",
        "field_goals_made_total",
        "field_goals_attempted_total",
        "two_pointers_made_total",
        "two_pointers_attempted_total",
        "three_pointers_made_total",
        "three_pointers_attempted_total",
        "free_throws_made_total",
        "free_throws_attempted_total",
        "offensive_possessions_total",
        "defensive_possessions_total",
        "pace",
        "defensive_rating",
        "net_rating",
        "usage_percentage",
        "offensive_rebound_percentage",
        "defensive_rebound_percentage",
        "rebound_percentage",
        "block_percentage",
    }.issubset(player_season_team_names)
    assert {
        "team_id",
        "season_year",
        "season_type",
        "wins",
        "losses",
        "minutes",
        "points_total",
        "assists_total",
        "turnovers_total",
        "steals_total",
        "blocks_total",
        "rebounds_total",
        "offensive_rebounds_total",
        "defensive_rebounds_total",
        "field_goals_made_total",
        "field_goals_attempted_total",
        "three_pointers_made_total",
        "three_pointers_attempted_total",
        "two_pointers_made_total",
        "two_pointers_attempted_total",
        "free_throws_made_total",
        "free_throws_attempted_total",
        "offensive_fouls_committed_total",
        "fouls_drawn_total",
        "personal_fouls_committed_total",
        "technical_fouls_committed_total",
        "offensive_possessions",
        "defensive_possessions",
        "pace",
        "defensive_rating",
        "net_rating",
        "block_percentage",
        "offensive_rebound_percentage",
        "defensive_rebound_percentage",
        "rebound_percentage",
    }.issubset(team_season_names)


def test_team_game_schema_exposes_core_trend_fields() -> None:
    team_game_names = set(TEAM_GAME_SCHEMA.names)

    assert {"game_date", "team_id", "opponent_team_id", "score"}.issubset(team_game_names)


def test_semantic_transforms_read_from_silver_only() -> None:
    source_keys = [
        arena_transform.BOXSCORE_SOURCE_KEY,
        arena_transform.SCHEDULE_SOURCE_KEY,
        arena_transform.TEAM_GAME_SOURCE_KEY,
        game_transform.BOXSCORE_SOURCE_KEY,
        game_transform.SCHEDULE_SOURCE_KEY,
        game_transform.TEAM_GAME_SOURCE_KEY,
        player_transform.PLAYER_SOURCE_KEY,
        player_transform.GAME_SOURCE_KEY,
        player_transform.PLAYER_BIO_SOURCE_KEY,
        player_transform.BBR_BRIDGE_SOURCE_KEY,
        player_transform.BBR_PROFILE_SOURCE_KEY,
        player_game_transform.PLAYER_SOURCE_KEY,
        player_game_transform.BOXSCORE_SOURCE_KEY,
        player_game_transform.SCHEDULE_SOURCE_KEY,
        player_game_transform.TEAM_GAME_SOURCE_KEY,
        player_game_transform.TEAM_GAME_USAGE_SOURCE_KEY,
        player_game_transform.PLAYER_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        player_game_transform.PLAYER_GAME_OPPORTUNITY_CONTEXT_SOURCE_KEY,
        player_game_transform.PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        team_transform.SCHEDULE_SOURCE_KEY,
        team_transform.TEAM_GAME_SOURCE_KEY,
        team_transform.TEAM_HISTORIES_SOURCE_KEY,
        team_transform.GAME_SOURCE_KEY,
        team_game_transform.TEAM_GAME_SOURCE_KEY,
        team_game_transform.BOXSCORE_SOURCE_KEY,
        team_game_transform.SCHEDULE_SOURCE_KEY,
        team_game_transform.TEAM_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        team_game_transform.TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        player_season_transform.PLAYER_SOURCE_KEY,
        player_season_transform.BOXSCORE_SOURCE_KEY,
        player_season_transform.SCHEDULE_SOURCE_KEY,
        player_season_transform.TEAM_GAME_SOURCE_KEY,
        player_season_transform.TEAM_GAME_USAGE_SOURCE_KEY,
        player_season_transform.PLAYER_BIO_SOURCE_KEY,
        player_season_transform.BBR_BRIDGE_SOURCE_KEY,
        player_season_transform.BBR_PROFILE_SOURCE_KEY,
        player_season_transform.PLAYER_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        player_season_transform.PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        player_season_transform.PLAYER_GAME_OPPORTUNITY_CONTEXT_SOURCE_KEY,
        player_season_team_transform.PLAYER_SOURCE_KEY,
        player_season_team_transform.BOXSCORE_SOURCE_KEY,
        player_season_team_transform.SCHEDULE_SOURCE_KEY,
        player_season_team_transform.TEAM_GAME_SOURCE_KEY,
        player_season_team_transform.TEAM_GAME_USAGE_SOURCE_KEY,
        player_season_team_transform.PLAYER_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        player_season_team_transform.PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        player_season_team_transform.PLAYER_GAME_OPPORTUNITY_CONTEXT_SOURCE_KEY,
        team_season_transform.TEAM_GAME_SOURCE_KEY,
        team_season_transform.BOXSCORE_SOURCE_KEY,
        team_season_transform.SCHEDULE_SOURCE_KEY,
        team_season_transform.TEAM_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        team_season_transform.TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
    ]
    assert all(key.startswith("silver/") for key in source_keys)


def test_attribute_inventory_covers_current_semantic_contract() -> None:
    payload = json.loads(ATTRIBUTE_INVENTORY_PATH.read_text(encoding="utf-8"))
    inventory_by_table = {table["table_name"]: table for table in payload["tables"]}
    schema_by_table = {
        "player": PLAYER_SCHEMA,
        "team": TEAM_SCHEMA,
        "arena": ARENA_SCHEMA,
        "game": GAME_SCHEMA,
        "player_game": PLAYER_GAME_SCHEMA,
        "team_game": TEAM_GAME_SCHEMA,
        "player_season": PLAYER_SEASON_SCHEMA,
        "player_season_team": PLAYER_SEASON_TEAM_SCHEMA,
        "team_season": TEAM_SEASON_SCHEMA,
    }

    assert set(inventory_by_table) == set(schema_by_table)

    allowed_kinds = {"primary_key", "dimension", "measure"}
    allowed_visibility = {"public", "internal"}

    for table_name, schema in schema_by_table.items():
        table_inventory = inventory_by_table[table_name]["columns"]
        inventory_names = [column["name"] for column in table_inventory]
        assert inventory_names == schema.names
        for column in table_inventory:
            assert column["attribute_kind"] in allowed_kinds
            assert isinstance(column["link_key"], bool)
            assert column["visibility"] in allowed_visibility


def test_attribute_inventory_has_expected_key_classifications() -> None:
    payload = json.loads(ATTRIBUTE_INVENTORY_PATH.read_text(encoding="utf-8"))
    inventory = {
        (table["table_name"], column["name"]): column
        for table in payload["tables"]
        for column in table["columns"]
    }

    assert inventory[("player", "person_id")]["attribute_kind"] == "primary_key"
    assert inventory[("player", "latest_team_id")]["link_key"] is True
    assert inventory[("arena", "arena_id")]["attribute_kind"] == "primary_key"
    assert inventory[("game", "home_team_id")]["link_key"] is True
    assert inventory[("game", "arena_id")]["link_key"] is True
    assert inventory[("player_game", "points")]["attribute_kind"] == "measure"
    assert inventory[("player_game", "usage_percentage")]["attribute_kind"] == "measure"
    assert inventory[("player_game", "defensive_rating")]["attribute_kind"] == "measure"
    assert inventory[("player_game", "block_percentage")]["attribute_kind"] == "measure"
    assert inventory[("player_game", "person_id")]["link_key"] is True
    assert inventory[("team_game", "opponent_team_id")]["link_key"] is True
    assert inventory[("team_game", "win_loss_result")]["attribute_kind"] == "dimension"
    assert inventory[("team_game", "game_date")]["attribute_kind"] == "dimension"
    assert inventory[("team_game", "team_id")]["link_key"] is True
    assert inventory[("team_game", "score")]["attribute_kind"] == "measure"
    assert inventory[("team_game", "block_percentage")]["attribute_kind"] == "measure"
    assert ("team_game", "point_differential") not in inventory
    assert ("team_game", "pace") not in inventory
    assert ("team_game", "defensive_rating") not in inventory
    assert ("team_game", "net_rating") not in inventory
    assert ("team_game", "offensive_rebound_percentage") not in inventory
    assert ("team_game", "defensive_rebound_percentage") not in inventory
    assert ("team_game", "rebound_percentage") not in inventory
    assert ("team_game", "opponent_field_goals_percentage") not in inventory
    assert ("team_game", "opponent_two_pointers_percentage") not in inventory
    assert ("team_game", "opponent_three_pointers_percentage") not in inventory
    assert ("team_game", "opponent_free_throws_percentage") not in inventory
    assert inventory[("player_season", "person_id")]["attribute_kind"] == "primary_key"
    assert inventory[("player_season", "person_id")]["link_key"] is True
    assert inventory[("player_season", "age_on_jan_31")]["attribute_kind"] == "dimension"
    assert inventory[("player_season", "minutes_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "opponent_blocks_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "offensive_fouls_committed_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "fouls_drawn_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "personal_fouls_committed_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "technical_fouls_committed_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "fast_break_points_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "points_in_paint_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "second_chance_points_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "steals_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "blocks_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "turnovers_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "plus_minus_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "offensive_possessions_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "defensive_possessions_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "field_goals_made_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "field_goals_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "three_pointers_made_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "three_pointers_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "two_pointers_made_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "two_pointers_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "free_throws_made_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "free_throws_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "offensive_rebounds_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "defensive_rebounds_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "usage_percentage")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "team_id")]["link_key"] is True
    assert inventory[("player_season_team", "minutes_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "assists_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "rebounds_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "offensive_rebounds_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "defensive_rebounds_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "steals_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "blocks_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "opponent_blocks_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "turnovers_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "plus_minus_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "offensive_fouls_committed_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "personal_fouls_committed_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "technical_fouls_committed_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "fouls_drawn_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "fast_break_points_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "points_in_paint_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "second_chance_points_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "field_goals_made_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "field_goals_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "two_pointers_made_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "two_pointers_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "three_pointers_made_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "three_pointers_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "free_throws_made_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "free_throws_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "offensive_possessions_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "defensive_possessions_total")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "pace")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "defensive_rating")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "net_rating")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "usage_percentage")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "offensive_rebound_percentage")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "defensive_rebound_percentage")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "rebound_percentage")]["attribute_kind"] == "measure"
    assert inventory[("player_season_team", "block_percentage")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "wins")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "points_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "assists_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "turnovers_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "steals_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "blocks_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "rebounds_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "field_goals_made_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "field_goals_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "three_pointers_made_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "three_pointers_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "two_pointers_made_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "two_pointers_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "free_throws_made_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "free_throws_attempted_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "offensive_fouls_committed_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "fouls_drawn_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "personal_fouls_committed_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "technical_fouls_committed_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "offensive_rebounds_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "defensive_rebounds_total")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "team_id")]["link_key"] is True
