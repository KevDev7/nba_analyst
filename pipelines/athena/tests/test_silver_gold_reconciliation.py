from __future__ import annotations

from pipelines.athena.quality.silver_gold_reconciliation import (
    SILVER_GOLD_RECONCILIATION_CHECKS,
    ReconciliationCheck,
    build_reconciliation_row,
    key_set_mapping_check_sql,
    row_count_check_sql,
)


def test_row_count_check_sql_compares_source_and_target_counts():
    sql = row_count_check_sql(
        source_schema="silver",
        source_table="boxscore_player_game",
        target_schema="legacy_gold",
        target_table="fct_player_game",
    )

    assert 'FROM "silver"."boxscore_player_game"' in sql
    assert 'FROM "legacy_gold"."fct_player_game"' in sql
    assert "ABS(source_row_count - target_row_count) AS mismatch_count" in sql


def test_key_set_mapping_check_sql_supports_different_column_names():
    sql = key_set_mapping_check_sql(
        source_schema="silver",
        source_table="boxscore_player_game",
        target_schema="legacy_gold",
        target_table="fct_player_game",
        key_columns=(("gameId", "game_id"), ("personId", "person_id")),
    )

    assert '"gameId" AS "gameId"' in sql
    assert '"game_id" AS "gameId"' in sql
    assert 'source."gameId" = target."gameId"' in sql
    assert 'target."personId" IS NULL' in sql


def test_silver_gold_reconciliation_checks_cover_core_lineage():
    check_ids = {check.check_id for check in SILVER_GOLD_RECONCILIATION_CHECKS}

    assert "silver_player_game_to_legacy_fact_row_count" in check_ids
    assert "silver_team_game_to_legacy_fact_key_coverage" in check_ids
    assert "legacy_player_fact_to_player_season_key_coverage" in check_ids
    assert "legacy_team_fact_to_semantic_team_game_key_coverage" in check_ids


def test_build_reconciliation_row_marks_mismatch_status():
    row = build_reconciliation_row(
        run_id="run_1",
        run_date="2026-05-11",
        check=ReconciliationCheck(
            check_id="check",
            check_group="group",
            source_artifact_id="source",
            target_artifact_id="target",
            sql="SELECT 1",
        ),
        result={"source_row_count": 10, "target_row_count": 9, "mismatch_count": 1},
    )

    assert row["reconciliation_status"] == "mismatch"
    assert row["mismatch_count"] == 1
