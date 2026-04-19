from __future__ import annotations

import pyarrow as pa

from pipelines.athena.transform.semantic_gold import deploy_semantic_gold_tables as tables


def test_athena_type_for_field_maps_supported_types() -> None:
    assert tables.athena_type_for_field(pa.field("flag", pa.bool_())) == "boolean"
    assert tables.athena_type_for_field(pa.field("name", pa.string())) == "string"
    assert tables.athena_type_for_field(pa.field("count", pa.int64())) == "bigint"
    assert tables.athena_type_for_field(pa.field("ratio", pa.float64())) == "double"
    assert tables.athena_type_for_field(pa.field("game_date", pa.date32())) == "date"
    assert tables.athena_type_for_field(pa.field("created_at", pa.timestamp("us", tz="UTC"))) == "timestamp"


def test_build_create_table_ddl_uses_semantic_gold_location() -> None:
    spec = tables.SemanticGoldTableSpec(
        table_name="player",
        data_key="semantic_gold/player/player.parquet",
        table_location="s3://nba-analytics-lakehouse-dev/semantic_gold/player/",
        schema=pa.schema([pa.field("person_id", pa.int64())]),
    )
    schema = pa.schema([pa.field("person_id", pa.int64()), pa.field("display_name", pa.string())])

    ddl = tables.build_create_table_ddl(spec, schema)

    assert "CREATE EXTERNAL TABLE player" in ddl
    assert "`person_id` bigint" in ddl
    assert "`display_name` string" in ddl
    assert "LOCATION 's3://nba-analytics-lakehouse-dev/semantic_gold/player/'" in ddl


def test_table_specs_use_clean_object_names() -> None:
    table_names = {spec.table_name for spec in tables.SEMANTIC_GOLD_TABLE_SPECS}
    assert table_names == {
        "player",
        "team",
        "arena",
        "game",
        "player_game",
        "team_game",
        "player_season",
        "player_season_team",
        "team_season",
    }
