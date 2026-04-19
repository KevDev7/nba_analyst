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


def test_fact_like_schemas_keep_link_keys_and_business_grain_fields() -> None:
    player_game_names = set(PLAYER_GAME_SCHEMA.names)
    team_game_names = set(TEAM_GAME_SCHEMA.names)
    player_season_names = set(PLAYER_SEASON_SCHEMA.names)
    player_season_team_names = set(PLAYER_SEASON_TEAM_SCHEMA.names)
    team_season_names = set(TEAM_SEASON_SCHEMA.names)

    assert {"game_id", "person_id", "team_id", "points", "minutes_played_decimal"}.issubset(player_game_names)
    assert "is_on_court" not in player_game_names
    assert "seconds_played_total" not in player_game_names
    assert "shots_blocked" in player_game_names
    assert "shots_blocked_against" in player_game_names
    assert {"game_id", "team_id", "opponent_team_id", "score", "opponent_score"}.issubset(team_game_names)
    assert {"person_id", "season_year", "season_type", "games_played", "total_points", "average_points"}.issubset(player_season_names)
    assert {"person_id", "team_id", "season_year", "season_type", "games_played", "total_points"}.issubset(player_season_team_names)
    assert {"team_id", "season_year", "season_type", "wins", "losses", "win_percentage"}.issubset(team_season_names)


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
        team_transform.SCHEDULE_SOURCE_KEY,
        team_transform.TEAM_GAME_SOURCE_KEY,
        team_transform.TEAM_HISTORIES_SOURCE_KEY,
        team_transform.GAME_SOURCE_KEY,
        team_game_transform.TEAM_GAME_SOURCE_KEY,
        team_game_transform.BOXSCORE_SOURCE_KEY,
        team_game_transform.SCHEDULE_SOURCE_KEY,
        player_season_transform.PLAYER_SOURCE_KEY,
        player_season_transform.BOXSCORE_SOURCE_KEY,
        player_season_transform.SCHEDULE_SOURCE_KEY,
        player_season_transform.TEAM_GAME_SOURCE_KEY,
        player_season_team_transform.PLAYER_SOURCE_KEY,
        player_season_team_transform.BOXSCORE_SOURCE_KEY,
        player_season_team_transform.SCHEDULE_SOURCE_KEY,
        player_season_team_transform.TEAM_GAME_SOURCE_KEY,
        team_season_transform.TEAM_GAME_SOURCE_KEY,
        team_season_transform.BOXSCORE_SOURCE_KEY,
        team_season_transform.SCHEDULE_SOURCE_KEY,
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
    assert inventory[("player_game", "person_id")]["link_key"] is True
    assert inventory[("team_game", "opponent_team_id")]["link_key"] is True
    assert inventory[("team_game", "game_result")]["attribute_kind"] == "dimension"
    assert inventory[("team_game", "game_date")]["attribute_kind"] == "dimension"
    assert inventory[("team_game", "team_id")]["link_key"] is True
    assert inventory[("team_game", "score")]["attribute_kind"] == "measure"
    assert inventory[("player_season", "person_id")]["attribute_kind"] == "primary_key"
    assert inventory[("player_season", "person_id")]["link_key"] is True
    assert inventory[("player_season_team", "team_id")]["link_key"] is True
    assert inventory[("player_season_team", "average_points")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "wins")]["attribute_kind"] == "measure"
    assert inventory[("team_season", "team_id")]["link_key"] is True
