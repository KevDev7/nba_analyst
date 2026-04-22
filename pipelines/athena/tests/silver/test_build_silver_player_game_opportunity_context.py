from __future__ import annotations

import math

from pipelines.athena.transform.silver import (
    build_silver_player_game_opportunity_context as pgoc,
)


def _played_players() -> dict[int, dict[str, object]]:
    return {
        person_id: {
            "person_id": person_id,
            "team_id": 1 if person_id <= 5 else 2,
            "minutes_seconds_total": 600.0,
            "field_goals_made": 1 if person_id == 1 else 0,
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


def test_build_exact_assist_context_stats_credits_teammates_but_not_scorer() -> None:
    stats = pgoc.build_exact_assist_context_stats(
        [
            {
                "orderNumber": 1200,
                "teamId": 1,
                "personId": 1,
                "isFieldGoal": True,
                "isMadeShot": True,
            }
        ],
        _on_court_rows(),
        _played_players(),
    )

    assert stats is not None
    assert stats[1]["teammate_field_goals_made_while_on_court"] == 0.0
    assert stats[2]["teammate_field_goals_made_while_on_court"] == 1.0
    assert stats[5]["assist_exact_count"] == 1.0
    assert stats[6]["teammate_field_goals_made_while_on_court"] == 0.0
    assert stats[2]["assist_exact_game_flag"] == 1


def test_build_event_estimated_assist_context_stats_uses_event_context() -> None:
    stats = pgoc.build_event_estimated_assist_context_stats(
        [
            {
                "actionNumber": 7,
                "teamId": 2,
                "personId": 6,
                "isFieldGoal": True,
                "isMadeShot": True,
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
    assert stats[6]["teammate_field_goals_made_while_on_court"] == 0.0
    assert stats[7]["teammate_field_goals_made_while_on_court"] == 1.0
    assert stats[10]["assist_event_estimated_count"] == 1.0
    assert stats[7]["assist_event_estimated_game_flag"] == 1


def test_build_exact_rebound_context_stats_credits_on_court_opportunities() -> None:
    stats = pgoc.build_exact_rebound_context_stats(
        [
            {
                "orderNumber": 1400,
                "teamId": 2,
                "isRebound": True,
                "reboundOfMissedShotFlag": True,
                "isPlaceholderRebound": False,
                "isOreb": False,
                "isDreb": True,
            }
        ],
        _on_court_rows(),
        _played_players(),
    )

    assert stats is not None
    assert stats[1]["offensive_rebound_opportunities_while_on_court"] == 1.0
    assert stats[1]["rebound_opportunities_while_on_court"] == 1.0
    assert stats[6]["defensive_rebound_opportunities_while_on_court"] == 1.0
    assert stats[6]["rebound_exact_count"] == 1.0
    assert stats[6]["rebound_exact_game_flag"] == 1


def test_build_event_estimated_rebound_context_stats_uses_event_context() -> None:
    stats = pgoc.build_event_estimated_rebound_context_stats(
        [
            {
                "actionNumber": 8,
                "teamId": 1,
                "isRebound": True,
                "reboundOfMissedShotFlag": True,
                "isPlaceholderRebound": False,
                "isOreb": True,
                "isDreb": False,
            }
        ],
        [
            {
                "event_num": 8,
                "home_team_id": 1,
                "away_team_id": 2,
                "home_current_player_ids": [1, 2, 3, 4, 5],
                "away_current_player_ids": [6, 7, 8, 9, 10],
            }
        ],
        _played_players(),
    )

    assert stats is not None
    assert stats[1]["offensive_rebound_opportunities_while_on_court"] == 1.0
    assert stats[6]["defensive_rebound_opportunities_while_on_court"] == 1.0
    assert stats[6]["rebound_event_estimated_count"] == 1.0
    assert stats[1]["rebound_event_estimated_game_flag"] == 1


def test_build_boxscore_estimated_opportunity_context_stats_use_minute_share() -> None:
    assist_stats = pgoc.build_boxscore_estimated_assist_context_stats(
        {
            11: {
                "person_id": 11,
                "team_id": 1,
                "minutes_seconds_total": 900.0,
                "field_goals_made": 2,
            },
        },
        {
            ("0022400001", 1): {
                "opponent_team_id": 2,
                "minutes_seconds_total": 2400.0,
                "field_goals_made": 40,
                "rebounds_offensive": 10,
                "rebounds_defensive": 30,
                "rebounds_total": 40,
            },
            ("0022400001", 2): {
                "opponent_team_id": 1,
                "minutes_seconds_total": 2400.0,
                "field_goals_made": 35,
                "rebounds_offensive": 9,
                "rebounds_defensive": 28,
                "rebounds_total": 37,
            },
        },
        game_id="0022400001",
    )
    rebound_stats = pgoc.build_boxscore_estimated_rebound_context_stats(
        {
            11: {
                "person_id": 11,
                "team_id": 1,
                "minutes_seconds_total": 900.0,
                "field_goals_made": 2,
            },
        },
        {
            ("0022400001", 1): {
                "opponent_team_id": 2,
                "minutes_seconds_total": 2400.0,
                "field_goals_made": 40,
                "rebounds_offensive": 10,
                "rebounds_defensive": 30,
                "rebounds_total": 40,
            },
            ("0022400001", 2): {
                "opponent_team_id": 1,
                "minutes_seconds_total": 2400.0,
                "field_goals_made": 35,
                "rebounds_offensive": 9,
                "rebounds_defensive": 28,
                "rebounds_total": 37,
            },
        },
        game_id="0022400001",
    )

    assert assist_stats is not None
    assert rebound_stats is not None
    assert assist_stats[11]["assist_boxscore_estimated_game_flag"] == 1
    assert math.isclose(assist_stats[11]["teammate_field_goals_made_while_on_court"], 73.0)
    assert rebound_stats[11]["rebound_boxscore_estimated_game_flag"] == 1
    assert math.isclose(rebound_stats[11]["offensive_rebound_opportunities_while_on_court"], 71.25)
    assert math.isclose(rebound_stats[11]["defensive_rebound_opportunities_while_on_court"], 73.125)
    assert math.isclose(rebound_stats[11]["rebound_opportunities_while_on_court"], 144.375)


def test_choose_game_stats_marks_missing_when_no_path_is_usable() -> None:
    stats = pgoc.choose_game_stats(
        game_id="0022400001",
        played_players=_played_players(),
        team_context_map={},
        playbyplay_rows=None,
        on_court_rows=None,
        event_context_rows=None,
    )

    assert stats[1]["assist_context_source_method"] == "missing"
    assert stats[1]["assist_missing_game_flag"] == 1
    assert stats[1]["rebound_context_source_method"] == "missing"
    assert stats[1]["rebound_missing_game_flag"] == 1
