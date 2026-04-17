from __future__ import annotations

import math

from pipelines.athena.transform.silver import (
    build_silver_player_game_defensive_shot_context as pgdsc,
)


def _played_players() -> dict[int, dict[str, object]]:
    return {
        person_id: {
            "person_id": person_id,
            "team_id": 1 if person_id <= 5 else 2,
            "minutes_seconds_total": 600.0,
        }
        for person_id in range(1, 11)
    }


def _on_court_rows() -> list[dict[str, object]]:
    return [
        {
            "start_orderNumber": 1000,
            "end_orderNumber": 9999,
            "home_teamId": 1,
            "away_teamId": 2,
            "home_personIds": [1, 2, 3, 4, 5],
            "away_personIds": [6, 7, 8, 9, 10],
            "lineup_valid_flag": 1,
        }
    ]


def test_build_exact_player_game_shot_stats_credits_defenders_for_two_point_attempts() -> None:
    stats = pgdsc.build_exact_player_game_shot_stats(
        [
            {
                "actionNumber": 1,
                "orderNumber": 1200,
                "resolvedOffenseTeamId": 1,
                "resolvedDefenseTeamId": 2,
                "isFieldGoal": True,
                "isMadeShot": False,
                "isMissedShot": True,
                "shotValue": 2,
            }
        ],
        _on_court_rows(),
        _played_players(),
    )

    assert stats is not None
    assert stats[6]["opponent_two_point_attempts_while_on_court"] == 1.0
    assert stats[6]["exact_two_point_attempts_count"] == 1.0
    assert stats[6]["exact_game_flag"] == 1
    assert stats[1]["opponent_two_point_attempts_while_on_court"] == 0.0


def test_build_exact_player_game_shot_stats_excludes_three_point_attempts() -> None:
    stats = pgdsc.build_exact_player_game_shot_stats(
        [
            {
                "actionNumber": 1,
                "orderNumber": 1200,
                "resolvedOffenseTeamId": 1,
                "resolvedDefenseTeamId": 2,
                "isFieldGoal": True,
                "isMadeShot": False,
                "isMissedShot": True,
                "shotValue": 3,
            }
        ],
        _on_court_rows(),
        _played_players(),
    )

    assert stats is None


def test_build_event_estimated_player_game_shot_stats_uses_event_context() -> None:
    stats = pgdsc.build_event_estimated_player_game_shot_stats(
        [
            {
                "actionNumber": 7,
                "orderNumber": 1400,
                "resolvedOffenseTeamId": 1,
                "resolvedDefenseTeamId": 2,
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
                "home_current_player_ids": [1, 2, 3, 4, 5],
                "away_current_player_ids": [6, 7, 8, 9, 10],
            }
        ],
        _played_players(),
    )

    assert stats is not None
    assert stats[6]["opponent_two_point_attempts_while_on_court"] == 1.0
    assert stats[6]["event_estimated_two_point_attempts_count"] == 1.0
    assert stats[6]["event_estimated_game_flag"] == 1


def test_build_boxscore_estimated_player_game_shot_stats_uses_minute_share() -> None:
    stats = pgdsc.build_boxscore_estimated_player_game_shot_stats(
        {
            11: {"person_id": 11, "team_id": 1, "minutes_seconds_total": 900.0},
        },
        {
            ("0022400001", 1): {
                "opponent_team_id": 2,
                "minutes_seconds_total": 2400.0,
            },
            ("0022400001", 2): {
                "opponent_team_id": 1,
                "minutes_seconds_total": 2400.0,
                "field_goals_attempted": 80,
                "three_pointers_attempted": 30,
            },
        },
        game_id="0022400001",
    )

    assert stats is not None
    assert stats[11]["boxscore_estimated_game_flag"] == 1
    assert math.isclose(stats[11]["opponent_two_point_attempts_while_on_court"], 93.75)
    assert math.isclose(stats[11]["boxscore_estimated_two_point_attempts_count"], 93.75)


def test_choose_game_stats_marks_missing_when_no_path_is_usable() -> None:
    stats = pgdsc.choose_game_stats(
        game_id="0022400001",
        played_players=_played_players(),
        team_context_map={},
        playbyplay_rows=None,
        on_court_rows=None,
        event_context_rows=None,
    )

    assert stats[1]["missing_game_flag"] == 1
    assert stats[1]["shot_context_source_method"] == "missing"
    assert stats[1]["opponent_two_point_attempts_while_on_court"] == 0.0
