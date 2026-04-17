from __future__ import annotations

import math

from pipelines.athena.transform.silver import build_silver_player_game_possession_context as pgpc


def _played_players() -> dict[int, dict[str, object]]:
    return {
        person_id: {
            "person_id": person_id,
            "team_id": 1 if person_id <= 5 else 2,
            "seconds_played_total": 600.0,
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


def test_build_exact_or_ot_player_game_stats_credits_exact_lineups() -> None:
    stats = pgpc.build_exact_or_ot_player_game_stats(
        [
            {
                "startOrderNumber": 1200,
                "endOrderNumber": 1500,
                "offenseTeamId": 1,
                "defenseTeamId": 2,
                "offenseHomeAway": "h",
                "defenseHomeAway": "v",
                "pointsScoredOnPossession": 2,
                "countsAsPossession": True,
                "homeLineupId": "1-2-3-4-5",
                "awayLineupId": "6-7-8-9-10",
            }
        ],
        _on_court_rows(),
        _played_players(),
        source_method="exact",
    )

    assert stats is not None
    assert stats[1]["offensive_possessions"] == 1.0
    assert stats[1]["team_points_for_while_on_court"] == 2.0
    assert stats[1]["exact_possessions_count"] == 1.0
    assert stats[1]["exact_game_flag"] == 1
    assert stats[6]["defensive_possessions"] == 1.0
    assert stats[6]["team_points_against_while_on_court"] == 2.0


def test_build_exact_or_ot_player_game_stats_recovers_missing_lineup_from_on_court() -> None:
    stats = pgpc.build_exact_or_ot_player_game_stats(
        [
            {
                "startOrderNumber": 1200,
                "endOrderNumber": 1500,
                "offenseTeamId": 1,
                "defenseTeamId": 2,
                "offenseHomeAway": "h",
                "defenseHomeAway": "v",
                "pointsScoredOnPossession": 3,
                "countsAsPossession": True,
                "homeLineupId": None,
                "awayLineupId": "6-7-8-9-10",
            }
        ],
        _on_court_rows(),
        _played_players(),
        source_method="exact",
    )

    assert stats is not None
    assert stats[1]["offensive_possessions"] == 1.0
    assert stats[1]["recovered_from_on_court_count"] == 1.0
    assert stats[6]["recovered_from_on_court_count"] == 1.0


def test_build_exact_or_ot_player_game_stats_marks_ot_fallback_separately() -> None:
    stats = pgpc.build_exact_or_ot_player_game_stats(
        [
            {
                "startOrderNumber": 1200,
                "endOrderNumber": 1500,
                "offenseTeamId": 1,
                "defenseTeamId": 2,
                "offenseHomeAway": "h",
                "defenseHomeAway": "v",
                "pointsScoredOnPossession": 0,
                "countsAsPossession": True,
                "homeLineupId": "1-2-3-4-5",
                "awayLineupId": "6-7-8-9-10",
            }
        ],
        _on_court_rows(),
        _played_players(),
        source_method="ot_fallback",
    )

    assert stats is not None
    assert stats[1]["ot_fallback_possessions_count"] == 1.0
    assert stats[1]["ot_fallback_game_flag"] == 1
    assert stats[1]["exact_game_flag"] == 0


def test_build_event_estimated_player_game_stats_uses_on_court_state() -> None:
    stats = pgpc.build_event_estimated_player_game_stats(
        [
            {
                "actionNumber": 1,
                "orderNumber": 1000,
                "scoreHome": 0,
                "scoreAway": 0,
                "resolvedOffenseTeamId": 1,
                "resolvedDefenseTeamId": 2,
                "countAsPossession": False,
            },
            {
                "actionNumber": 2,
                "orderNumber": 2000,
                "scoreHome": 2,
                "scoreAway": 0,
                "resolvedOffenseTeamId": 1,
                "resolvedDefenseTeamId": 2,
                "countAsPossession": True,
            },
        ],
        _on_court_rows(),
        _played_players(),
    )

    assert stats is not None
    assert stats[1]["offensive_possessions"] == 1.0
    assert stats[1]["team_points_for_while_on_court"] == 2.0
    assert stats[6]["defensive_possessions"] == 1.0
    assert stats[6]["team_points_against_while_on_court"] == 2.0
    assert stats[1]["event_estimated_game_flag"] == 1


def test_build_boxscore_estimated_player_game_stats_allocates_by_minute_share() -> None:
    stats = pgpc.build_boxscore_estimated_player_game_stats(
        _played_players(),
        {
            ("0022400001", 1): {
                "opponent_team_id": 2,
                "score": 110,
                "points_against": 100,
                "seconds_played_total": 2400.0,
                "field_goals_attempted": 80,
                "free_throws_attempted": 20,
                "rebounds_offensive": 10,
                "turnovers_total": 12,
            },
            ("0022400001", 2): {
                "opponent_team_id": 1,
                "score": 100,
                "points_against": 110,
                "seconds_played_total": 2400.0,
                "field_goals_attempted": 78,
                "free_throws_attempted": 18,
                "rebounds_offensive": 9,
                "turnovers_total": 11,
            },
        },
        game_id="0022400001",
    )

    assert stats is not None
    assert stats[1]["boxscore_estimated_game_flag"] == 1
    assert stats[1]["offensive_possessions"] > 0
    assert stats[1]["defensive_possessions"] > 0
    assert stats[1]["team_points_for_while_on_court"] > 0
    assert stats[1]["team_points_against_while_on_court"] > 0
    assert math.isclose(
        stats[1]["boxscore_estimated_possessions_count"],
        stats[1]["offensive_possessions"] + stats[1]["defensive_possessions"],
    )


def test_choose_game_stats_marks_missing_when_no_path_is_usable() -> None:
    stats = pgpc.choose_game_stats(
        game_id="0022400001",
        played_players=_played_players(),
        team_context_map={},
        exact_rows=None,
        ot_fallback_rows=None,
        on_court_rows=None,
        playbyplay_rows=None,
    )

    assert stats[1]["missing_game_flag"] == 1
    assert stats[1]["possession_source_method"] == "missing"
    assert stats[1]["offensive_possessions"] == 0.0
