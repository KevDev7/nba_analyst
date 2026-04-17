from __future__ import annotations

from datetime import date, datetime, timezone

from pipelines.athena.transform.gold import (
    transform_to_player_game_shot_profiles_parquet as shot_profiles,
)


def test_aggregate_standard_rows_buckets_field_goals() -> None:
    stats_by_key, unknown_labels = shot_profiles.aggregate_standard_rows(
        [
            {
                "game_id": "0022400001",
                "player1_id": 11,
                "is_field_goal_event": True,
                "is_made": True,
                "shot_value": 3,
                "shot_type": "Corner3",
            },
            {
                "game_id": "0022400001",
                "player1_id": 11,
                "is_field_goal_event": True,
                "is_made": False,
                "shot_value": 2,
                "shot_type": "AtRim",
            },
            {
                "game_id": "0022400001",
                "player1_id": 22,
                "is_field_goal_event": True,
                "is_made": True,
                "shot_value": 2,
                "shot_type": "MysteryShotType",
            },
        ]
    )

    assert unknown_labels == {"MysteryShotType"}
    assert stats_by_key[("0022400001", 11)] == {
        "field_goals_attempted": 2,
        "field_goals_made": 1,
        "three_pointers_attempted": 1,
        "three_pointers_made": 1,
        "points_from_field_goals": 3,
        "at_rim_field_goals_attempted": 1,
        "at_rim_field_goals_made": 0,
        "short_mid_range_field_goals_attempted": 0,
        "short_mid_range_field_goals_made": 0,
        "long_mid_range_field_goals_attempted": 0,
        "long_mid_range_field_goals_made": 0,
        "corner_3_field_goals_attempted": 1,
        "corner_3_field_goals_made": 1,
        "arc_3_field_goals_attempted": 0,
        "arc_3_field_goals_made": 0,
        "unknown_distance_2pt_field_goals_attempted": 0,
        "unknown_distance_2pt_field_goals_made": 0,
    }
    assert stats_by_key[("0022400001", 22)]["field_goals_attempted"] == 1
    assert stats_by_key[("0022400001", 22)]["field_goals_made"] == 1
    assert stats_by_key[("0022400001", 22)]["points_from_field_goals"] == 2


def test_aggregate_source_rows_buckets_area_and_detail() -> None:
    stats_by_key, unknown_area_labels, unknown_area_detail_labels = shot_profiles.aggregate_source_rows(
        [
            {
                "gameId": "0022400001",
                "personId": 11,
                "isFieldGoal": 1,
                "isMadeShot": True,
                "shotValue": 2,
                "area": "Restricted Area",
                "areaDetail": "0-8 Center",
            },
            {
                "gameId": "0022400001",
                "personId": 11,
                "isFieldGoal": 1,
                "isMadeShot": False,
                "shotValue": 3,
                "area": "Left Corner 3",
                "areaDetail": "24+ Left",
            },
            {
                "gameId": "0022400001",
                "personId": 22,
                "isFieldGoal": 1,
                "isMadeShot": False,
                "shotValue": 2,
                "area": "Mystery Area",
                "areaDetail": "Mystery Detail",
            },
        ]
    )

    assert unknown_area_labels == {"Mystery Area"}
    assert unknown_area_detail_labels == {"Mystery Detail"}
    assert stats_by_key[("0022400001", 11)]["field_goals_attempted"] == 2
    assert stats_by_key[("0022400001", 11)]["field_goals_made"] == 1
    assert stats_by_key[("0022400001", 11)]["three_pointers_attempted"] == 1
    assert stats_by_key[("0022400001", 11)]["three_pointers_made"] == 0
    assert stats_by_key[("0022400001", 11)]["points_from_field_goals"] == 2
    assert stats_by_key[("0022400001", 11)]["restricted_area_field_goals_attempted"] == 1
    assert stats_by_key[("0022400001", 11)]["restricted_area_field_goals_made"] == 1
    assert stats_by_key[("0022400001", 11)]["left_corner_3_field_goals_attempted"] == 1
    assert stats_by_key[("0022400001", 11)]["left_corner_3_field_goals_made"] == 0
    assert stats_by_key[("0022400001", 11)]["center_0_8_field_goals_attempted"] == 1
    assert stats_by_key[("0022400001", 11)]["center_0_8_field_goals_made"] == 1
    assert stats_by_key[("0022400001", 11)]["left_24_plus_field_goals_attempted"] == 1
    assert stats_by_key[("0022400001", 11)]["left_24_plus_field_goals_made"] == 0
    assert stats_by_key[("0022400001", 11)]["unmapped_source_area_field_goals_attempted"] == 0
    assert stats_by_key[("0022400001", 11)]["unmapped_source_area_detail_field_goals_attempted"] == 0
    assert stats_by_key[("0022400001", 22)]["unmapped_source_area_field_goals_attempted"] == 1
    assert stats_by_key[("0022400001", 22)]["unmapped_source_area_detail_field_goals_attempted"] == 1


def test_build_shot_profile_rows_merges_base_context(monkeypatch) -> None:
    run_game_id = "0022400001"
    player_fact_rows = [
        {
            "fct_player_game_sk": 101,
            "game_sk": 1001,
            "date_sk": 20241112,
            "player_sk": 5001,
            "team_sk": 7001,
            "game_id": run_game_id,
            "person_id": 11,
            "team_id": 1610612737,
            "game_datetime_utc": datetime(2024, 11, 13, 1, 0, tzinfo=timezone.utc),
            "game_date": date(2024, 11, 12),
            "season_year": "2024-25",
            "season_start_year": 2024,
            "raw_season_type_code": "002",
            "season_type": "regular_season",
            "did_play": 1,
        },
        {
            "fct_player_game_sk": 102,
            "game_sk": 1001,
            "date_sk": 20241112,
            "player_sk": 5002,
            "team_sk": 7001,
            "game_id": run_game_id,
            "person_id": 12,
            "team_id": 1610612737,
            "game_datetime_utc": datetime(2024, 11, 13, 1, 0, tzinfo=timezone.utc),
            "game_date": date(2024, 11, 12),
            "season_year": "2024-25",
            "season_start_year": 2024,
            "raw_season_type_code": "002",
            "season_type": "regular_season",
            "did_play": 0,
        },
    ]
    team_fact_rows = [
        {
            "game_id": run_game_id,
            "team_id": 1610612737,
            "opponent_team_id": 1610612738,
            "opponent_team_sk": 7002,
        }
    ]

    def fake_aggregate_game_shot_profiles(game_id: str):
        assert game_id == run_game_id
        return (
            {
                (run_game_id, 11): {
                    **shot_profiles._new_standard_stats(),
                    "field_goals_attempted": 2,
                    "field_goals_made": 1,
                    "three_pointers_attempted": 1,
                    "three_pointers_made": 1,
                    "points_from_field_goals": 3,
                    "corner_3_field_goals_attempted": 1,
                    "corner_3_field_goals_made": 1,
                    "at_rim_field_goals_attempted": 1,
                }
            },
            {
                (run_game_id, 11): {
                    **shot_profiles._new_source_stats(),
                    "field_goals_attempted": 2,
                    "field_goals_made": 1,
                    "three_pointers_attempted": 1,
                    "three_pointers_made": 1,
                    "points_from_field_goals": 3,
                    "restricted_area_field_goals_attempted": 1,
                    "restricted_area_field_goals_made": 0,
                    "left_corner_3_field_goals_attempted": 1,
                    "left_corner_3_field_goals_made": 1,
                    "center_0_8_field_goals_attempted": 1,
                    "left_24_plus_field_goals_attempted": 1,
                    "left_24_plus_field_goals_made": 1,
                }
            },
            set(),
            set(),
            set(),
        )

    monkeypatch.setattr(shot_profiles, "aggregate_game_shot_profiles", fake_aggregate_game_shot_profiles)

    standard_rows, source_rows, diagnostics = shot_profiles.build_shot_profile_rows(
        player_fact_rows,
        team_fact_rows,
        max_workers=1,
    )

    assert diagnostics == {
        "unknown_standard_shot_types": [],
        "unknown_source_area_labels": [],
        "unknown_source_area_detail_labels": [],
    }
    assert len(standard_rows) == 1
    assert len(source_rows) == 1

    standard_row = standard_rows[0]
    assert standard_row["fct_player_game_shot_profile_standard_sk"] == 1
    assert standard_row["fct_player_game_sk"] == 101
    assert standard_row["opponent_team_id"] == 1610612738
    assert standard_row["opponent_team_sk"] == 7002
    assert standard_row["field_goals_attempted"] == 2
    assert standard_row["field_goals_made"] == 1
    assert standard_row["three_pointers_attempted"] == 1
    assert standard_row["three_pointers_made"] == 1
    assert standard_row["points_from_field_goals"] == 3
    assert standard_row["corner_3_field_goals_attempted"] == 1
    assert standard_row["corner_3_field_goals_made"] == 1
    assert standard_row["at_rim_field_goals_attempted"] == 1

    source_row = source_rows[0]
    assert source_row["fct_player_game_shot_profile_source_sk"] == 1
    assert source_row["fct_player_game_sk"] == 101
    assert source_row["restricted_area_field_goals_attempted"] == 1
    assert source_row["restricted_area_field_goals_made"] == 0
    assert source_row["left_corner_3_field_goals_attempted"] == 1
    assert source_row["left_corner_3_field_goals_made"] == 1
    assert source_row["center_0_8_field_goals_attempted"] == 1
    assert source_row["unmapped_source_area_field_goals_attempted"] == 0
