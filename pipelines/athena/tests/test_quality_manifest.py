from __future__ import annotations

from pipelines.athena.quality.quality_manifest import (
    KNOWN_GRAIN_COLUMNS,
    QUALITY_DATASETS,
    build_quality_manifest,
    load_registry,
    manifest_key,
    quality_result_key,
)


def test_quality_result_keys_are_rooted_under_quality():
    assert (
        quality_result_key(
            "table_profiles",
            "silver.boxscore_player_game",
            "2026-05-11",
            "run_1",
        )
        == "quality/table_profiles/silver/boxscore_player_game/run_date=2026-05-11/run_1.parquet"
    )
    assert (
        manifest_key("2026-05-11", "run_1")
        == "quality/pipeline_runs/run_date=2026-05-11/run_1.json"
    )


def test_quality_manifest_covers_core_datasets():
    manifest = build_quality_manifest(
        load_registry(),
        run_id="quality_baseline_test",
        run_date="2026-05-11",
    )

    assert manifest["quality_root_prefix"] == "quality"
    assert set(QUALITY_DATASETS) <= set(manifest["datasets"])
    assert manifest["artifact_count"] == 75
    assert manifest["check_count"] > manifest["artifact_count"]


def test_quality_manifest_has_expected_baseline_checks():
    manifest = build_quality_manifest(
        load_registry(),
        run_id="quality_baseline_test",
        run_date="2026-05-11",
    )
    checks = {check["check_id"]: check for check in manifest["checks"]}

    assert checks["pipeline.registry_snapshot"]["dataset"] == "pipeline_runs"
    assert checks["raw.cdn_playbyplay.source_completeness"]["dataset"] == "source_completeness"
    assert checks["silver.boxscore_player_game.table_profiles"]["dataset"] == "table_profiles"
    assert checks["silver.boxscore_player_game.schema_snapshots"]["dataset"] == "schema_snapshots"
    assert checks["silver.boxscore_player_game.grain_duplicates"]["grain_columns"] == [
        "gameId",
        "personId",
    ]
    assert checks["silver.boxscore_player_game.quarantine_summary"]["source_key"] == (
        "silver/_quarantine/boxscore_player_game/"
    )
    assert (
        checks["silver.boxscore_game_children_reference_parent"]["dataset"]
        == "reconciliation"
    )


def test_quality_manifest_includes_ongoing_observability_checks():
    manifest = build_quality_manifest(
        load_registry(),
        run_id="quality_baseline_test",
        run_date="2026-05-11",
    )
    checks = {check["check_id"]: check for check in manifest["checks"]}

    assert checks["silver.boxscore_player_game.row_count_trends"]["dataset"] == (
        "row_count_trends"
    )
    assert checks["silver.boxscore_player_game.schema_drift"]["dataset"] == "schema_drift"
    assert checks["silver.anomaly_summary"]["dataset"] == "anomaly_summaries"
    assert checks["serving.duckdb_snapshot.serving_snapshot_quality"]["dataset"] == (
        "serving_snapshot_quality"
    )


def test_known_grain_columns_match_current_table_contract_names():
    assert KNOWN_GRAIN_COLUMNS["silver.team_histories"] == ["teamId", "seasonFounded"]
    assert KNOWN_GRAIN_COLUMNS["silver.player_movement"] == [
        "Transaction_Type",
        "TRANSACTION_DATE",
        "TRANSACTION_DESCRIPTION",
        "TEAM_ID",
        "TEAM_SLUG",
        "PLAYER_ID",
        "Additional_Sort",
        "GroupSort",
    ]
    assert KNOWN_GRAIN_COLUMNS["silver.boxscore_team_game"] == ["gameId", "team_side"]
    assert KNOWN_GRAIN_COLUMNS["silver.boxscore_team_period"] == [
        "gameId",
        "team_side",
        "period_number",
    ]
    assert KNOWN_GRAIN_COLUMNS["silver.boxscore_matchups"] == [
        "game_id",
        "team_id",
        "person_id",
        "matchups_person_id",
    ]
    assert KNOWN_GRAIN_COLUMNS["silver.playbyplay"] == ["gameId", "actionNumber"]
    assert KNOWN_GRAIN_COLUMNS["silver.event_projection_v2"] == ["game_id", "event_num"]
    assert KNOWN_GRAIN_COLUMNS["silver.on_court_state"] == [
        "gameId",
        "period",
        "stint_id",
    ]
    assert KNOWN_GRAIN_COLUMNS["silver.possessions"] == ["gameId", "possessionNumber"]
    assert KNOWN_GRAIN_COLUMNS["silver.bbr_player_awards"] == [
        "basketball_reference_player_id",
        "award_family",
        "season_label",
    ]
    assert KNOWN_GRAIN_COLUMNS["silver.player_identity_bridge_bbr_nba"] == [
        "basketball_reference_player_id",
        "nba_person_id",
    ]
    assert KNOWN_GRAIN_COLUMNS["semantic_gold.player"] == ["person_id"]
    assert KNOWN_GRAIN_COLUMNS["semantic_gold.player_game"] == ["game_id", "person_id"]
    assert KNOWN_GRAIN_COLUMNS["semantic_gold.player_season"] == [
        "person_id",
        "season_year",
        "season_type",
    ]
