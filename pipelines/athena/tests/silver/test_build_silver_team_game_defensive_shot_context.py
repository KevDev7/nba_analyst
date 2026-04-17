from __future__ import annotations

from pipelines.athena.transform.silver import build_silver_team_game_defensive_shot_context as tgdsc


def test_build_exact_team_game_shot_stats_counts_defensive_two_point_attempts() -> None:
    stats = tgdsc.build_exact_team_game_shot_stats(
        [
            {
                "actionNumber": 1,
                "resolvedDefenseTeamId": 2,
                "resolvedOffenseTeamId": 1,
                "isFieldGoal": True,
                "isMadeShot": False,
                "isMissedShot": True,
                "shotValue": 2,
            }
        ],
        {1, 2},
    )

    assert stats is not None
    assert stats[2]["opponent_two_point_attempts"] == 1.0
    assert stats[2]["exact_two_point_attempts_count"] == 1.0
    assert stats[2]["exact_game_flag"] == 1
    assert stats[1]["opponent_two_point_attempts"] == 0.0


def test_build_event_estimated_team_game_shot_stats_inferrs_defense_from_event_context() -> None:
    stats = tgdsc.build_event_estimated_team_game_shot_stats(
        [
            {
                "actionNumber": 7,
                "resolvedDefenseTeamId": None,
                "resolvedOffenseTeamId": 1,
                "isFieldGoal": True,
                "isMadeShot": True,
                "isMissedShot": False,
                "shotValue": 2,
            }
        ],
        [
            {
                "event_num": 7,
                "home_team_id": 1,
                "away_team_id": 2,
            }
        ],
        {1, 2},
    )

    assert stats is not None
    assert stats[2]["opponent_two_point_attempts"] == 1.0
    assert stats[2]["event_estimated_two_point_attempts_count"] == 1.0
    assert stats[2]["event_estimated_game_flag"] == 1


def test_build_boxscore_estimated_team_game_shot_stats_uses_opponent_two_point_attempts() -> None:
    stats = tgdsc.build_boxscore_estimated_team_game_shot_stats(
        {1, 2},
        {
            ("0022400001", 1): {
                "opponent_team_id": 2,
                "field_goals_attempted": 75,
                "three_pointers_attempted": 25,
            },
            ("0022400001", 2): {
                "opponent_team_id": 1,
                "field_goals_attempted": 80,
                "three_pointers_attempted": 30,
            },
        },
        game_id="0022400001",
    )

    assert stats is not None
    assert stats[1]["boxscore_estimated_game_flag"] == 1
    assert stats[1]["opponent_two_point_attempts"] == 50.0
    assert stats[1]["boxscore_estimated_two_point_attempts_count"] == 50.0


def test_choose_game_stats_marks_missing_when_no_path_is_usable() -> None:
    stats = tgdsc.choose_game_stats(
        game_id="0022400001",
        played_teams={1, 2},
        team_context_map={},
        playbyplay_rows=None,
        event_context_rows=None,
    )

    assert stats[1]["missing_game_flag"] == 1
    assert stats[1]["shot_context_source_method"] == "missing"
    assert stats[1]["opponent_two_point_attempts"] == 0.0
