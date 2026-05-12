from __future__ import annotations

from datetime import datetime, timezone

from pipelines.athena.quality.run_quality_baseline import (
    DEFAULT_EXPECTED_SEASONS,
    build_source_completeness_rows,
    build_row_count_trends,
    build_schema_drift_rows,
    latest_object,
    season_year_from_game_id,
    season_year_from_key,
    source_location,
)


def test_source_location_distinguishes_exact_keys_and_prefix_patterns():
    exact = source_location("silver/boxscore_game.parquet")
    assert exact.source_key == "silver/boxscore_game.parquet"
    assert exact.source_prefix == "silver/"
    assert exact.is_exact_key is True

    wildcard = source_location("silver/playbyplay/game_id=<GAME_ID>.parquet")
    assert wildcard.source_key == "silver/playbyplay/game_id=<GAME_ID>.parquet"
    assert wildcard.source_prefix == "silver/playbyplay/"
    assert wildcard.is_exact_key is False

    glob = source_location("raw/nba_data/matchups/season=<YYYY>/*.tar.xz")
    assert glob.source_prefix == "raw/nba_data/matchups/"
    assert glob.is_exact_key is False


def test_latest_object_ignores_folder_markers():
    objects = [
        {"Key": "silver/playbyplay/", "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)},
        {"Key": "silver/playbyplay/game_id=1.parquet", "LastModified": datetime(2026, 1, 2, tzinfo=timezone.utc)},
        {"Key": "silver/playbyplay/game_id=2.parquet", "LastModified": datetime(2026, 1, 3, tzinfo=timezone.utc)},
    ]

    assert latest_object(objects)["Key"] == "silver/playbyplay/game_id=2.parquet"


def test_source_completeness_derives_seasons_from_game_and_partition_keys():
    assert season_year_from_game_id("0022400001") == "2024-25"
    assert season_year_from_key("raw/cdn/playbyplay/game_id=0022501111.json") == "2025-26"
    assert season_year_from_key("raw/nba_data/matchups/season=2024/season_type=Regular/file.tar.xz") == "2024-25"
    assert season_year_from_key("raw/nba_data/matchups/season=2024-25/file.tar.xz") == "2024-25"


def test_build_source_completeness_rows_groups_raw_sources_by_expected_season():
    profile = {
        "run_id": "run_1",
        "run_date": "2026-05-11",
        "artifact_id": "raw.cdn_playbyplay",
        "layer": "raw",
        "artifact_type": "source",
        "source_key": "raw/cdn/playbyplay/game_id=<GAME_ID>.json",
        "source_prefix": "raw/cdn/playbyplay/",
        "is_exact_key": False,
        "object_count": 2,
        "total_size_bytes": 20,
        "latest_last_modified_utc": None,
        "sample_key": "raw/cdn/playbyplay/game_id=0022501111.json",
        "sample_row_count": None,
        "profile_status": "ok",
        "error_message": None,
    }

    rows = build_source_completeness_rows(
        artifact={
            "id": "raw.cdn_playbyplay",
            "destination_key": "raw/cdn/playbyplay/game_id=<GAME_ID>.json",
        },
        profile=profile,
        object_keys=[
            "raw/cdn/playbyplay/game_id=0022400001.json",
            "raw/cdn/playbyplay/game_id=0022501111.json",
        ],
        expected_seasons=DEFAULT_EXPECTED_SEASONS,
    )
    rows_by_season = {row["season_year"]: row for row in rows}

    assert rows_by_season["2024-25"]["source_family"] == "cdn"
    assert rows_by_season["2024-25"]["observed_object_count"] == 1
    assert rows_by_season["2024-25"]["source_completeness_status"] == "ok"
    assert rows_by_season["2020-21"]["missing_object_count"] == 1
    assert rows_by_season["2020-21"]["source_completeness_status"] == (
        "missing_expected_objects"
    )


def test_build_row_count_trends_compares_latest_history():
    current_profiles = [
        {
            "artifact_id": "silver.boxscore_game",
            "layer": "silver",
            "sample_row_count": 100,
            "profile_status": "ok",
        }
    ]
    historical_profiles = [
        {
            "run_id": "old",
            "run_date": "2026-05-10",
            "artifact_id": "silver.boxscore_game",
            "sample_row_count": 90,
            "profile_status": "ok",
        }
    ]

    rows = build_row_count_trends(
        current_profiles,
        historical_profiles,
        run_id="new",
        run_date="2026-05-11",
    )

    assert rows[0]["previous_run_id"] == "old"
    assert rows[0]["row_count_delta"] == 10
    assert rows[0]["row_count_delta_pct"] == 10 / 90
    assert rows[0]["trend_status"] == "changed"


def test_build_row_count_trends_marks_missing_history():
    rows = build_row_count_trends(
        [
            {
                "artifact_id": "silver.boxscore_game",
                "layer": "silver",
                "sample_row_count": 100,
                "profile_status": "ok",
            }
        ],
        [],
        run_id="new",
        run_date="2026-05-11",
    )

    assert rows[0]["trend_status"] == "no_history"
    assert rows[0]["previous_sample_row_count"] is None


def test_build_schema_drift_rows_detects_type_added_and_removed_columns():
    current_rows = [
        {
            "run_id": "new",
            "run_date": "2026-05-11",
            "artifact_id": "silver.boxscore_game",
            "layer": "silver",
            "column_name": "game_id",
            "data_type": "string",
            "nullable": False,
        },
        {
            "run_id": "new",
            "run_date": "2026-05-11",
            "artifact_id": "silver.boxscore_game",
            "layer": "silver",
            "column_name": "new_column",
            "data_type": "int64",
            "nullable": True,
        },
    ]
    historical_rows = [
        {
            "run_id": "old",
            "run_date": "2026-05-10",
            "artifact_id": "silver.boxscore_game",
            "layer": "silver",
            "column_name": "game_id",
            "data_type": "int64",
            "nullable": False,
        },
        {
            "run_id": "old",
            "run_date": "2026-05-10",
            "artifact_id": "silver.boxscore_game",
            "layer": "silver",
            "column_name": "old_column",
            "data_type": "string",
            "nullable": True,
        },
    ]

    rows = build_schema_drift_rows(
        current_rows,
        historical_rows,
        run_id="new",
        run_date="2026-05-11",
    )
    drift_by_column = {row["column_name"]: row["drift_type"] for row in rows}

    assert drift_by_column == {
        "game_id": "type_changed",
        "new_column": "added_column",
        "old_column": "removed_column",
    }
