from __future__ import annotations

import pyarrow as pa

from pipelines.athena.transform.gold import deploy_gold_tables as tables


def test_athena_type_for_field_maps_supported_types() -> None:
    assert tables.athena_type_for_field(pa.field("flag", pa.bool_())) == "boolean"
    assert tables.athena_type_for_field(pa.field("name", pa.string())) == "string"
    assert tables.athena_type_for_field(pa.field("count", pa.int64())) == "bigint"
    assert tables.athena_type_for_field(pa.field("ratio", pa.float64())) == "double"
    assert tables.athena_type_for_field(pa.field("game_date", pa.date32())) == "date"
    assert tables.athena_type_for_field(pa.field("created_at", pa.timestamp("us", tz="UTC"))) == "timestamp"


def test_build_create_table_ddl_uses_folder_location() -> None:
    spec = tables.GoldTableSpec(
        table_name="dim_date",
        data_key="legacy_gold/dim_date/dim_date.parquet",
        table_location="s3://nba-analytics-lakehouse-dev/legacy_gold/dim_date/",
    )
    schema = pa.schema(
        [
            pa.field("date_sk", pa.int64()),
            pa.field("calendar_date", pa.date32()),
            pa.field("is_weekend", pa.bool_()),
        ]
    )

    ddl = tables.build_create_table_ddl(spec, schema)

    assert "CREATE EXTERNAL TABLE dim_date" in ddl
    assert "`date_sk` bigint" in ddl
    assert "`calendar_date` date" in ddl
    assert "`is_weekend` boolean" in ddl
    assert "LOCATION 's3://nba-analytics-lakehouse-dev/legacy_gold/dim_date/'" in ddl


def test_table_specs_include_player_game_shot_profiles() -> None:
    table_names = {spec.table_name for spec in tables.TABLE_SPECS}

    assert "fct_player_game_shot_profile_standard" in table_names
    assert "fct_player_game_shot_profile_source" in table_names
    assert "fct_player_game_shot_type_source" in table_names


def test_table_specs_include_season_percentile_sidecars() -> None:
    table_names = {spec.table_name for spec in tables.TABLE_SPECS}

    assert "player_season_percentiles" in table_names
    assert "team_season_percentiles" in table_names


def test_table_specs_include_player_award_history() -> None:
    table_names = {spec.table_name for spec in tables.TABLE_SPECS}

    assert "player_award_history" in table_names
