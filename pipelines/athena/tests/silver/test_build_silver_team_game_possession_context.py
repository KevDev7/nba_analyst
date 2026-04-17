from __future__ import annotations

import math

from pipelines.athena.transform.silver import build_silver_team_game_possession_context as tgpc


def test_build_exact_or_ot_team_game_stats_counts_possessions_by_team() -> None:
    stats = tgpc.build_exact_or_ot_team_game_stats(
        [
            {
                "offenseTeamId": 1,
                "defenseTeamId": 2,
                "countsAsPossession": True,
            }
        ],
        {1, 2},
        source_method="exact",
    )

    assert stats is not None
    assert stats[1]["offensive_possessions"] == 1.0
    assert stats[1]["exact_possessions_count"] == 1.0
    assert stats[1]["exact_game_flag"] == 1
    assert stats[2]["defensive_possessions"] == 1.0


def test_build_exact_or_ot_team_game_stats_marks_ot_fallback_separately() -> None:
    stats = tgpc.build_exact_or_ot_team_game_stats(
        [
            {
                "offenseTeamId": 1,
                "defenseTeamId": 2,
                "countsAsPossession": True,
            }
        ],
        {1, 2},
        source_method="ot_fallback",
    )

    assert stats is not None
    assert stats[1]["ot_fallback_possessions_count"] == 1.0
    assert stats[1]["ot_fallback_game_flag"] == 1
    assert stats[1]["exact_game_flag"] == 0


def test_build_event_estimated_team_game_stats_uses_resolved_team_ids() -> None:
    stats = tgpc.build_event_estimated_team_game_stats(
        [
            {
                "actionNumber": 2,
                "orderNumber": 2000,
                "resolvedOffenseTeamId": 1,
                "resolvedDefenseTeamId": 2,
                "countAsPossession": True,
            }
        ],
        {1, 2},
    )

    assert stats is not None
    assert stats[1]["offensive_possessions"] == 1.0
    assert stats[2]["defensive_possessions"] == 1.0
    assert stats[1]["event_estimated_game_flag"] == 1


def test_build_boxscore_estimated_team_game_stats_estimates_team_possessions() -> None:
    stats = tgpc.build_boxscore_estimated_team_game_stats(
        {1, 2},
        {
            ("0022400001", 1): {
                "opponent_team_id": 2,
                "field_goals_attempted": 80,
                "free_throws_attempted": 20,
                "rebounds_offensive": 10,
                "turnovers_total": 12,
            },
            ("0022400001", 2): {
                "opponent_team_id": 1,
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
    assert math.isclose(
        stats[1]["boxscore_estimated_possessions_count"],
        stats[1]["offensive_possessions"] + stats[1]["defensive_possessions"],
    )


def test_choose_game_stats_marks_missing_when_no_path_is_usable() -> None:
    stats = tgpc.choose_game_stats(
        game_id="0022400001",
        played_teams={1, 2},
        team_context_map={},
        exact_rows=None,
        ot_fallback_rows=None,
        playbyplay_rows=None,
    )

    assert stats[1]["missing_game_flag"] == 1
    assert stats[1]["possession_source_method"] == "missing"
    assert stats[1]["offensive_possessions"] == 0.0
