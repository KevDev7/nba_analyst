from __future__ import annotations

import pyarrow as pa

from pipelines.athena.transform.gold import transform_to_player_season_percentiles_parquet as percentiles


def _table_from_rows(rows: list[dict[str, object]], columns: list[str]) -> pa.Table:
    normalized_rows = [{column: row.get(column) for column in columns} for row in rows]
    return pa.Table.from_pylist(normalized_rows)


def test_build_player_percentile_rows_applies_curated_thresholds_and_inverse_metrics() -> None:
    agg_player_table = _table_from_rows(
        [
            {
                "person_id": 101,
                "current_player_sk": 9001,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "games_played": 10,
                "seconds_played_total": 7200.0,
                "field_goals_attempted_total": 100,
                "three_pointers_attempted_total": 40,
                "free_throws_attempted_total": 50,
                "seconds_played_average": 720.0,
                "field_goals_percentage": 0.55,
                "three_pointers_percentage": 0.42,
                "free_throws_percentage": 0.90,
                "points_per_game": 30.0,
                "assists_per_game": 9.0,
                "rebounds_per_game": 8.0,
            },
            {
                "person_id": 102,
                "current_player_sk": 9002,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "games_played": 10,
                "seconds_played_total": 6600.0,
                "field_goals_attempted_total": 80,
                "three_pointers_attempted_total": 30,
                "free_throws_attempted_total": 20,
                "seconds_played_average": 660.0,
                "field_goals_percentage": 0.50,
                "three_pointers_percentage": 0.37,
                "free_throws_percentage": 0.82,
                "points_per_game": 20.0,
                "assists_per_game": 7.0,
                "rebounds_per_game": 6.0,
            },
            {
                "person_id": 103,
                "current_player_sk": 9003,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "games_played": 10,
                "seconds_played_total": 6300.0,
                "field_goals_attempted_total": 20,
                "three_pointers_attempted_total": 5,
                "free_throws_attempted_total": 5,
                "seconds_played_average": 630.0,
                "field_goals_percentage": 0.60,
                "three_pointers_percentage": 0.45,
                "free_throws_percentage": 0.88,
                "points_per_game": 10.0,
                "assists_per_game": 4.0,
                "rebounds_per_game": 4.0,
            },
            {
                "person_id": 104,
                "current_player_sk": 9004,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "games_played": 3,
                "seconds_played_total": 1200.0,
                "field_goals_attempted_total": 40,
                "three_pointers_attempted_total": 12,
                "free_throws_attempted_total": 10,
                "seconds_played_average": 400.0,
                "field_goals_percentage": 0.48,
                "three_pointers_percentage": 0.35,
                "free_throws_percentage": 0.80,
                "points_per_game": 12.0,
                "assists_per_game": 5.0,
                "rebounds_per_game": 5.0,
            },
        ],
        [
            "person_id",
            "current_player_sk",
            "season_year",
            "season_start_year",
            "raw_season_type_code",
            "season_type",
            "games_played",
            "seconds_played_total",
            "field_goals_attempted_total",
            "three_pointers_attempted_total",
            "free_throws_attempted_total",
            "seconds_played_average",
            "field_goals_percentage",
            "three_pointers_percentage",
            "free_throws_percentage",
            "points_per_game",
            "assists_per_game",
            "rebounds_per_game",
        ],
    )
    advanced_source_table = _table_from_rows(
        [
            {
                "person_id": 101,
                "season_year": "2024-25",
                "season_type": "regular_season",
                "minutes": 1200.0,
                "offensive_rating": 120.0,
                "defensive_rating": 108.0,
                "net_rating": 12.0,
                "assist_percentage": 30.0,
                "ast_to_turnover_ratio": 3.0,
                "assist_ratio": 20.0,
                "offensive_rebound_percentage": 5.0,
                "defensive_rebound_percentage": 20.0,
                "rebound_percentage": 12.0,
                "turnover_ratio": 10.0,
                "effective_field_goal_percentage": 60.0,
                "three_point_attempt_rate": 0.40,
                "free_throw_attempt_rate": 0.30,
                "true_shooting_percentage": 65.0,
                "usage_percentage": 30.0,
                "pace": 101.0,
                "pie": 0.20,
                "steal_percentage": 2.0,
                "block_percentage": 1.0,
            },
            {
                "person_id": 102,
                "season_year": "2024-25",
                "season_type": "regular_season",
                "minutes": 1100.0,
                "offensive_rating": 112.0,
                "defensive_rating": 104.0,
                "net_rating": 8.0,
                "assist_percentage": 25.0,
                "ast_to_turnover_ratio": 2.5,
                "assist_ratio": 18.0,
                "offensive_rebound_percentage": 6.0,
                "defensive_rebound_percentage": 18.0,
                "rebound_percentage": 11.0,
                "turnover_ratio": 12.0,
                "effective_field_goal_percentage": 55.0,
                "three_point_attempt_rate": 0.35,
                "free_throw_attempt_rate": 0.25,
                "true_shooting_percentage": 58.0,
                "usage_percentage": 26.0,
                "pace": 99.0,
                "pie": 0.15,
                "steal_percentage": 1.5,
                "block_percentage": 1.2,
            },
            {
                "person_id": 103,
                "season_year": "2024-25",
                "season_type": "regular_season",
                "minutes": 1050.0,
                "offensive_rating": 104.0,
                "defensive_rating": 100.0,
                "net_rating": 4.0,
                "assist_percentage": 18.0,
                "ast_to_turnover_ratio": 1.5,
                "assist_ratio": 14.0,
                "offensive_rebound_percentage": 7.0,
                "defensive_rebound_percentage": 16.0,
                "rebound_percentage": 10.0,
                "turnover_ratio": 14.0,
                "effective_field_goal_percentage": 52.0,
                "three_point_attempt_rate": 0.20,
                "free_throw_attempt_rate": 0.10,
                "true_shooting_percentage": 54.0,
                "usage_percentage": 22.0,
                "pace": 97.0,
                "pie": 0.10,
                "steal_percentage": 1.0,
                "block_percentage": 1.5,
            },
            {
                "person_id": 104,
                "season_year": "2024-25",
                "season_type": "regular_season",
                "minutes": 200.0,
                "offensive_rating": 109.0,
                "defensive_rating": 107.0,
                "net_rating": 2.0,
                "assist_percentage": 21.0,
                "ast_to_turnover_ratio": 2.1,
                "assist_ratio": 16.0,
                "offensive_rebound_percentage": 5.5,
                "defensive_rebound_percentage": 15.0,
                "rebound_percentage": 9.0,
                "turnover_ratio": 11.0,
                "effective_field_goal_percentage": 54.0,
                "three_point_attempt_rate": 0.32,
                "free_throw_attempt_rate": 0.22,
                "true_shooting_percentage": 56.0,
                "usage_percentage": 24.0,
                "pace": 100.0,
                "pie": 0.11,
                "steal_percentage": 1.3,
                "block_percentage": 0.9,
            },
        ],
        [
            "person_id",
            "season_year",
            "season_type",
            "minutes",
            "offensive_rating",
            "defensive_rating",
            "net_rating",
            "assist_percentage",
            "ast_to_turnover_ratio",
            "assist_ratio",
            "offensive_rebound_percentage",
            "defensive_rebound_percentage",
            "rebound_percentage",
            "turnover_ratio",
            "effective_field_goal_percentage",
            "three_point_attempt_rate",
            "free_throw_attempt_rate",
            "true_shooting_percentage",
            "usage_percentage",
            "pace",
            "pie",
            "steal_percentage",
            "block_percentage",
        ],
    )

    rows = percentiles.build_player_percentile_rows(agg_player_table, advanced_source_table)
    by_person = {row["person_id"]: row for row in rows}

    assert [row["person_id"] for row in rows] == [101, 102, 103, 104]

    assert by_person[101]["points_per_game_percentile"] == 100
    assert by_person[102]["points_per_game_percentile"] == 50
    assert by_person[103]["points_per_game_percentile"] == 0
    assert by_person[104]["points_per_game_percentile"] is None

    assert by_person[101]["defensive_rating_percentile"] == 0
    assert by_person[102]["defensive_rating_percentile"] == 50
    assert by_person[103]["defensive_rating_percentile"] == 100
    assert by_person[104]["defensive_rating_percentile"] is None

    assert by_person[103]["field_goals_percentage_percentile"] is None
    assert by_person[103]["three_pointers_percentage_percentile"] is None
    assert by_person[103]["free_throws_percentage_percentile"] is None
    assert by_person[103]["effective_field_goal_percentage_percentile"] is None
    assert by_person[103]["true_shooting_percentage_percentile"] is None
    assert by_person[103]["minutes_percentile"] == 0


def test_finalize_rows_adds_surrogate_key_and_metadata() -> None:
    finalized = percentiles.finalize_rows(
        [
            {
                "person_id": 101,
                "current_player_sk": 9001,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
            },
            {
                "person_id": 102,
                "current_player_sk": 9002,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
            },
        ]
    )

    assert [row["player_season_percentiles_sk"] for row in finalized] == [1, 2]
    assert all(row["record_source"] == percentiles.RECORD_SOURCE for row in finalized)
    assert all(row["created_at_utc"] is not None for row in finalized)
    assert all(row["updated_at_utc"] is not None for row in finalized)


def test_target_schema_exposes_keys_metrics_and_metadata() -> None:
    assert percentiles.TARGET_SCHEMA.names[:6] == [
        "player_season_percentiles_sk",
        "person_id",
        "current_player_sk",
        "season_year",
        "season_start_year",
        "raw_season_type_code",
    ]
    assert "points_per_game_percentile" in percentiles.TARGET_SCHEMA.names
    assert "defensive_rating_percentile" in percentiles.TARGET_SCHEMA.names
    assert percentiles.TARGET_SCHEMA.names[-3:] == [
        "record_source",
        "created_at_utc",
        "updated_at_utc",
    ]
