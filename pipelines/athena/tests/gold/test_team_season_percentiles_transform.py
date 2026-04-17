from __future__ import annotations

import pyarrow as pa

from pipelines.athena.transform.gold import transform_to_team_season_percentiles_parquet as percentiles


def _table_from_rows(rows: list[dict[str, object]], columns: list[str]) -> pa.Table:
    normalized_rows = [{column: row.get(column) for column in columns} for row in rows]
    return pa.Table.from_pylist(normalized_rows)


def test_build_team_percentile_rows_respects_season_cohorts_and_inverse_metrics() -> None:
    agg_team_table = _table_from_rows(
        [
            {
                "team_id": 201,
                "current_team_sk": 7001,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "games_played": 10,
                "win_percentage": 0.80,
                "points_for_per_game": 120.0,
                "points_against_per_game": 105.0,
                "point_differential_per_game": 15.0,
                "field_goals_percentage": 0.52,
                "free_throws_percentage": 0.82,
                "three_pointers_percentage": 0.39,
                "two_pointers_percentage": 0.58,
            },
            {
                "team_id": 202,
                "current_team_sk": 7002,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "games_played": 10,
                "win_percentage": 0.50,
                "points_for_per_game": 110.0,
                "points_against_per_game": 110.0,
                "point_differential_per_game": 0.0,
                "field_goals_percentage": 0.48,
                "free_throws_percentage": 0.78,
                "three_pointers_percentage": 0.35,
                "two_pointers_percentage": 0.54,
            },
            {
                "team_id": 203,
                "current_team_sk": 7003,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "games_played": 10,
                "win_percentage": 0.20,
                "points_for_per_game": 100.0,
                "points_against_per_game": 115.0,
                "point_differential_per_game": -15.0,
                "field_goals_percentage": 0.44,
                "free_throws_percentage": 0.74,
                "three_pointers_percentage": 0.31,
                "two_pointers_percentage": 0.50,
            },
            {
                "team_id": 204,
                "current_team_sk": 7004,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "004",
                "season_type": "playoffs",
                "games_played": 6,
                "win_percentage": 0.83,
                "points_for_per_game": 118.0,
                "points_against_per_game": 104.0,
                "point_differential_per_game": 14.0,
                "field_goals_percentage": 0.51,
                "free_throws_percentage": 0.80,
                "three_pointers_percentage": 0.38,
                "two_pointers_percentage": 0.57,
            },
        ],
        [
            "team_id",
            "current_team_sk",
            "season_year",
            "season_start_year",
            "raw_season_type_code",
            "season_type",
            "games_played",
            "win_percentage",
            "points_for_per_game",
            "points_against_per_game",
            "point_differential_per_game",
            "field_goals_percentage",
            "free_throws_percentage",
            "three_pointers_percentage",
            "two_pointers_percentage",
        ],
    )
    advanced_source_table = _table_from_rows(
        [
            {
                "team_id": 201,
                "season_year": "2024-25",
                "season_type": "regular_season",
                "offensive_rating": 121.0,
                "defensive_rating": 105.0,
                "net_rating": 16.0,
                "assist_percentage": 68.0,
                "ast_to_turnover_ratio": 2.0,
                "assist_ratio": 19.0,
                "offensive_rebound_percentage": 30.0,
                "defensive_rebound_percentage": 74.0,
                "rebound_percentage": 52.0,
                "steal_percentage": 8.0,
                "block_percentage": 5.0,
                "turnover_ratio": 12.0,
                "effective_field_goal_percentage": 57.0,
                "three_point_attempt_rate": 0.42,
                "free_throw_attempt_rate": 0.25,
                "true_shooting_percentage": 61.0,
                "pace": 101.0,
                "pie": 0.58,
            },
            {
                "team_id": 202,
                "season_year": "2024-25",
                "season_type": "regular_season",
                "offensive_rating": 112.0,
                "defensive_rating": 110.0,
                "net_rating": 2.0,
                "assist_percentage": 63.0,
                "ast_to_turnover_ratio": 1.6,
                "assist_ratio": 17.0,
                "offensive_rebound_percentage": 28.0,
                "defensive_rebound_percentage": 71.0,
                "rebound_percentage": 50.0,
                "steal_percentage": 7.0,
                "block_percentage": 4.0,
                "turnover_ratio": 14.0,
                "effective_field_goal_percentage": 53.0,
                "three_point_attempt_rate": 0.38,
                "free_throw_attempt_rate": 0.22,
                "true_shooting_percentage": 57.0,
                "pace": 99.0,
                "pie": 0.50,
            },
            {
                "team_id": 203,
                "season_year": "2024-25",
                "season_type": "regular_season",
                "offensive_rating": 103.0,
                "defensive_rating": 115.0,
                "net_rating": -12.0,
                "assist_percentage": 58.0,
                "ast_to_turnover_ratio": 1.2,
                "assist_ratio": 15.0,
                "offensive_rebound_percentage": 26.0,
                "defensive_rebound_percentage": 68.0,
                "rebound_percentage": 48.0,
                "steal_percentage": 6.0,
                "block_percentage": 3.0,
                "turnover_ratio": 16.0,
                "effective_field_goal_percentage": 49.0,
                "three_point_attempt_rate": 0.34,
                "free_throw_attempt_rate": 0.19,
                "true_shooting_percentage": 53.0,
                "pace": 97.0,
                "pie": 0.42,
            },
            {
                "team_id": 204,
                "season_year": "2024-25",
                "season_type": "playoffs",
                "offensive_rating": 119.0,
                "defensive_rating": 104.0,
                "net_rating": 15.0,
                "assist_percentage": 67.0,
                "ast_to_turnover_ratio": 1.9,
                "assist_ratio": 18.0,
                "offensive_rebound_percentage": 29.0,
                "defensive_rebound_percentage": 73.0,
                "rebound_percentage": 51.0,
                "steal_percentage": 7.5,
                "block_percentage": 4.5,
                "turnover_ratio": 12.5,
                "effective_field_goal_percentage": 56.0,
                "three_point_attempt_rate": 0.40,
                "free_throw_attempt_rate": 0.24,
                "true_shooting_percentage": 60.0,
                "pace": 100.0,
                "pie": 0.56,
            },
        ],
        [
            "team_id",
            "season_year",
            "season_type",
            "offensive_rating",
            "defensive_rating",
            "net_rating",
            "assist_percentage",
            "ast_to_turnover_ratio",
            "assist_ratio",
            "offensive_rebound_percentage",
            "defensive_rebound_percentage",
            "rebound_percentage",
            "steal_percentage",
            "block_percentage",
            "turnover_ratio",
            "effective_field_goal_percentage",
            "three_point_attempt_rate",
            "free_throw_attempt_rate",
            "true_shooting_percentage",
            "pace",
            "pie",
        ],
    )

    rows = percentiles.build_team_percentile_rows(agg_team_table, advanced_source_table)
    by_team = {row["team_id"]: row for row in rows}

    assert [row["team_id"] for row in rows] == [201, 202, 203, 204]

    assert by_team[201]["win_percentage_percentile"] == 100
    assert by_team[202]["win_percentage_percentile"] == 50
    assert by_team[203]["win_percentage_percentile"] == 0
    assert by_team[204]["win_percentage_percentile"] == 100

    assert by_team[201]["points_against_per_game_percentile"] == 100
    assert by_team[202]["points_against_per_game_percentile"] == 50
    assert by_team[203]["points_against_per_game_percentile"] == 0

    assert by_team[201]["turnover_ratio_percentile"] == 100
    assert by_team[202]["turnover_ratio_percentile"] == 50
    assert by_team[203]["turnover_ratio_percentile"] == 0

    assert by_team[201]["offensive_rating_percentile"] == 100
    assert by_team[203]["defensive_rating_percentile"] == 0
    assert by_team[204]["defensive_rating_percentile"] == 100


def test_finalize_rows_adds_surrogate_key_and_metadata() -> None:
    finalized = percentiles.finalize_rows(
        [
            {
                "team_id": 201,
                "current_team_sk": 7001,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
            },
            {
                "team_id": 202,
                "current_team_sk": 7002,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
            },
        ]
    )

    assert [row["team_season_percentiles_sk"] for row in finalized] == [1, 2]
    assert all(row["record_source"] == percentiles.RECORD_SOURCE for row in finalized)
    assert all(row["created_at_utc"] is not None for row in finalized)
    assert all(row["updated_at_utc"] is not None for row in finalized)


def test_target_schema_exposes_keys_metrics_and_metadata() -> None:
    assert percentiles.TARGET_SCHEMA.names[:6] == [
        "team_season_percentiles_sk",
        "team_id",
        "current_team_sk",
        "season_year",
        "season_start_year",
        "raw_season_type_code",
    ]
    assert "win_percentage_percentile" in percentiles.TARGET_SCHEMA.names
    assert "defensive_rating_percentile" in percentiles.TARGET_SCHEMA.names
    assert percentiles.TARGET_SCHEMA.names[-3:] == [
        "record_source",
        "created_at_utc",
        "updated_at_utc",
    ]
