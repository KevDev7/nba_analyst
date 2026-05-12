from __future__ import annotations

from pipelines.athena.quality.gold_parity_lock import (
    build_grain_query,
    gold_registry_artifacts,
    grain_distinct_expression,
    quote_ident,
    schema_for_layer,
)
from pipelines.athena.quality.quality_manifest import load_registry


def test_quote_ident_escapes_double_quotes():
    assert quote_ident('weird"name') == '"weird""name"'


def test_schema_for_layer_maps_current_gold_layers():
    assert schema_for_layer("legacy_gold") == "legacy_gold"
    assert schema_for_layer("semantic_gold") == "semantic_gold"


def test_grain_distinct_expression_uses_null_sentinel_for_multi_column_grains():
    expression = grain_distinct_expression(["game_id", "team_id"])

    assert 'COALESCE(CAST("game_id" AS VARCHAR), \'<NULL>\')' in expression
    assert " || '|' || " in expression


def test_build_grain_query_quotes_schema_table_and_columns():
    query = build_grain_query(
        schema_name="semantic_gold",
        table_name="team_game",
        grain_columns=["game_id", "team_id"],
    )

    assert 'FROM "semantic_gold"."team_game"' in query
    assert 'COUNT(DISTINCT COALESCE(CAST("game_id" AS VARCHAR)' in query


def test_gold_registry_artifacts_include_legacy_and_semantic_tables():
    artifacts = gold_registry_artifacts(load_registry())
    artifact_ids = {artifact["id"] for artifact in artifacts}

    assert "legacy_gold.fct_player_game" in artifact_ids
    assert "semantic_gold.player_game" in artifact_ids
    assert all(artifact["layer"] in {"legacy_gold", "semantic_gold"} for artifact in artifacts)
