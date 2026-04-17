from __future__ import annotations

from pipelines.athena.transform.semantic_gold.contracts import (
    GAME_SCHEMA,
    PLAYER_GAME_SCHEMA,
    PLAYER_SCHEMA,
    SEMANTIC_GOLD_TABLE_SPECS,
    TEAM_GAME_SCHEMA,
    TEAM_SCHEMA,
)
from pipelines.athena.transform.semantic_gold import (
    transform_to_game_parquet as game_transform,
    transform_to_player_game_parquet as player_game_transform,
    transform_to_player_parquet as player_transform,
    transform_to_team_game_parquet as team_game_transform,
    transform_to_team_parquet as team_transform,
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
    assert "display_name" in names
    assert "basketball_reference_player_id" in names
    assert "position_group" in names
    assert "player_sk" not in names


def test_game_schema_keeps_business_context_without_internal_meta() -> None:
    names = set(GAME_SCHEMA.names)
    assert {"game_id", "season_year", "home_team_id", "away_team_id"}.issubset(names)
    assert "source_meta_version" not in names
    assert "record_source" not in names


def test_fact_like_schemas_keep_link_keys_and_business_grain_fields() -> None:
    player_game_names = set(PLAYER_GAME_SCHEMA.names)
    team_game_names = set(TEAM_GAME_SCHEMA.names)

    assert {"game_id", "person_id", "team_id", "points", "minutes_played_decimal"}.issubset(player_game_names)
    assert {"game_id", "team_id", "opponent_team_id", "score", "opponent_score"}.issubset(team_game_names)


def test_semantic_transforms_read_from_silver_only() -> None:
    source_keys = [
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
    ]
    assert all(key.startswith("silver/") for key in source_keys)
