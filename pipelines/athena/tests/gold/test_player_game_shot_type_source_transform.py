from __future__ import annotations

from datetime import date, datetime, timezone

from pipelines.athena.transform.gold import (
    transform_to_player_game_shot_type_source_parquet as shot_type_source,
)


def test_build_source_shot_type_label_examples() -> None:
    assert shot_type_source.build_source_shot_type_label("Jump Shot", None, 2) == "2PT Jump Shot"
    assert shot_type_source.build_source_shot_type_label("Jump Shot", None, 3) == "3PT Jump Shot"
    assert shot_type_source.build_source_shot_type_label("jumpshot", None, 3) == "3PT Jump Shot"
    assert shot_type_source.build_source_shot_type_label("shot", None, 2) == "2PT Jump Shot"
    assert shot_type_source.build_source_shot_type_label("Layup", "driving finger roll", 2) == (
        "2PT Driving Finger Roll Layup Shot"
    )
    assert shot_type_source.build_source_shot_type_label("DUNK", "running", 2) == "2PT Running Dunk Shot"
    assert shot_type_source.build_source_shot_type_label("Hook", "turnaround", 2) == "2PT Turnaround Hook Shot"
    assert shot_type_source.build_source_shot_type_label("Jump Shot", "turnaround fadeaway", 2) == (
        "2PT Turnaround Fadeaway Jump Shot"
    )


def test_shot_type_family_from_sub_type_canonicalizes_legacy_jump_shot_variants() -> None:
    assert shot_type_source.shot_type_family_from_sub_type("Jump Shot") == "Jump Shot"
    assert shot_type_source.shot_type_family_from_sub_type("jumpshot") == "Jump Shot"
    assert shot_type_source.shot_type_family_from_sub_type("shot") == "Jump Shot"
    assert shot_type_source.shot_type_family_from_sub_type("DUNK") == "Dunk"


def test_aggregate_source_shot_type_rows_groups_by_structured_combo() -> None:
    stats_by_key = shot_type_source.aggregate_source_shot_type_rows(
        [
            {
                "gameId": "0022400001",
                "personId": 11,
                "isFieldGoal": 1,
                "isMadeShot": True,
                "shotValue": 2,
                "actionType": "2pt",
                "subType": "Layup",
                "descriptor": "driving finger roll",
            },
            {
                "gameId": "0022400001",
                "personId": 11,
                "isFieldGoal": 1,
                "isMadeShot": False,
                "shotValue": 2,
                "actionType": "2pt",
                "subType": "Layup",
                "descriptor": "driving finger roll",
            },
            {
                "gameId": "0022400001",
                "personId": 11,
                "isFieldGoal": 1,
                "isMadeShot": True,
                "shotValue": 3,
                "actionType": "3pt",
                "subType": "Jump Shot",
                "descriptor": "pullup",
            },
        ]
    )

    assert stats_by_key[("0022400001", 11, "2pt", "Layup", "driving finger roll", 2)] == {
        "field_goals_attempted": 2,
        "field_goals_made": 1,
        "three_pointers_attempted": 0,
        "three_pointers_made": 0,
        "points_from_field_goals": 2,
    }
    assert stats_by_key[("0022400001", 11, "3pt", "Jump Shot", "pullup", 3)] == {
        "field_goals_attempted": 1,
        "field_goals_made": 1,
        "three_pointers_attempted": 1,
        "three_pointers_made": 1,
        "points_from_field_goals": 3,
    }


def test_build_shot_type_rows_merges_context(monkeypatch) -> None:
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

    def fake_aggregate(game_id: str):
        assert game_id == run_game_id
        return {
            (run_game_id, 11, "2pt", "Layup", "driving finger roll", 2): {
                "field_goals_attempted": 2,
                "field_goals_made": 1,
                "three_pointers_attempted": 0,
                "three_pointers_made": 0,
                "points_from_field_goals": 2,
            },
            (run_game_id, 11, "3pt", "Jump Shot", "pullup", 3): {
                "field_goals_attempted": 1,
                "field_goals_made": 1,
                "three_pointers_attempted": 1,
                "three_pointers_made": 1,
                "points_from_field_goals": 3,
            },
        }

    monkeypatch.setattr(shot_type_source, "aggregate_game_shot_type_rows", fake_aggregate)

    fact_rows = shot_type_source.build_shot_type_rows(
        player_fact_rows,
        team_fact_rows,
        max_workers=1,
    )

    assert len(fact_rows) == 2
    assert fact_rows[0]["source_shot_type_label"] == "2PT Driving Finger Roll Layup Shot"
    assert fact_rows[0]["source_shot_type_family"] == "Layup"
    assert fact_rows[0]["opponent_team_id"] == 1610612738
    assert fact_rows[0]["opponent_team_sk"] == 7002
    assert fact_rows[0]["field_goals_attempted"] == 2
    assert fact_rows[1]["source_shot_type_label"] == "3PT Pullup Jump Shot"
    assert fact_rows[1]["three_pointers_attempted"] == 1
    assert fact_rows[1]["three_pointers_made"] == 1


def test_select_preview_rows_preserves_unique_shot_types_first() -> None:
    fact_rows = [
        {
            "fct_player_game_shot_type_source_sk": 1,
            "source_shot_type_key": "2pt|Layup|driving|2",
            "source_shot_type_label": "2PT Driving Layup Shot",
            "game_id": "0022400001",
            "person_id": 11,
            "field_goals_attempted": 7,
        },
        {
            "fct_player_game_shot_type_source_sk": 2,
            "source_shot_type_key": "2pt|Layup|driving|2",
            "source_shot_type_label": "2PT Driving Layup Shot",
            "game_id": "0022400002",
            "person_id": 11,
            "field_goals_attempted": 5,
        },
        {
            "fct_player_game_shot_type_source_sk": 3,
            "source_shot_type_key": "2pt|Jump Shot|pullup|2",
            "source_shot_type_label": "2PT Pullup Jump Shot",
            "game_id": "0022400003",
            "person_id": 11,
            "field_goals_attempted": 4,
        },
    ]

    preview_rows = shot_type_source.select_preview_rows(
        fact_rows,
        row_limit=2,
    )

    assert len(preview_rows) == 2
    assert [row["source_shot_type_label"] for row in preview_rows] == [
        "2PT Driving Layup Shot",
        "2PT Pullup Jump Shot",
    ]
    assert [row["fct_player_game_shot_type_source_sk"] for row in preview_rows] == [1, 2]
