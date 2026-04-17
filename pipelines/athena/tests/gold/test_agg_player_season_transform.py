from __future__ import annotations

import math
from datetime import date

import pyarrow as pa

from pipelines.athena.transform.gold import transform_to_agg_player_season_parquet as aps


def _table_from_rows(rows: list[dict[str, object]], columns: list[str]) -> pa.Table:
    normalized_rows = [{column: row.get(column) for column in columns} for row in rows]
    return pa.Table.from_pylist(normalized_rows)


def test_build_agg_rows_matches_databricks_fact_driven_contract() -> None:
    fact_table = _table_from_rows(
        [
            {
                "game_id": "0022400001",
                "person_id": 42,
                "team_id": 1610612737,
                "did_play": 1,
                "is_starter": 1,
                "seconds_played_total": 1800.0,
                "points": 20,
                "assists": 5,
                "rebounds_total": 10,
                "rebounds_offensive": 3,
                "rebounds_defensive": 7,
                "steals": 1,
                "blocks": 1,
                "turnovers": 2,
                "raw_plus_value": 4,
                "raw_minus_value": 1,
                "plus_minus_points": 3,
                "field_goals_made": 8,
                "field_goals_attempted": 16,
                "three_pointers_made": 2,
                "three_pointers_attempted": 5,
                "free_throws_made": 2,
                "free_throws_attempted": 2,
                "points_fast_break": 4,
                "points_in_the_paint": 8,
                "points_second_chance": 2,
                "fouls_offensive": 0,
                "fouls_drawn": 2,
                "fouls_personal": 3,
                "fouls_technical": 0,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
            },
            {
                "game_id": "0022400002",
                "person_id": 42,
                "team_id": 1610612737,
                "did_play": 1,
                "is_starter": 1,
                "seconds_played_total": 1950.0,
                "points": 11,
                "assists": 10,
                "rebounds_total": 10,
                "rebounds_offensive": 1,
                "rebounds_defensive": 9,
                "steals": 0,
                "blocks": 0,
                "turnovers": 1,
                "raw_plus_value": 2,
                "raw_minus_value": 1,
                "plus_minus_points": 1,
                "field_goals_made": 5,
                "field_goals_attempted": 10,
                "three_pointers_made": 1,
                "three_pointers_attempted": 2,
                "free_throws_made": 0,
                "free_throws_attempted": 0,
                "points_fast_break": 0,
                "points_in_the_paint": 4,
                "points_second_chance": 0,
                "fouls_offensive": 1,
                "fouls_drawn": 1,
                "fouls_personal": 2,
                "fouls_technical": 0,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
            },
            {
                "game_id": "0022400003",
                "person_id": 42,
                "team_id": 1610612751,
                "did_play": 0,
                "is_starter": 0,
                "seconds_played_total": None,
                "points": 0,
                "assists": 0,
                "rebounds_total": 0,
                "rebounds_offensive": 0,
                "rebounds_defensive": 0,
                "steals": 0,
                "blocks": 0,
                "turnovers": 0,
                "raw_plus_value": 0,
                "raw_minus_value": 0,
                "plus_minus_points": 0,
                "field_goals_made": 0,
                "field_goals_attempted": 0,
                "three_pointers_made": 0,
                "three_pointers_attempted": 0,
                "free_throws_made": 0,
                "free_throws_attempted": 0,
                "points_fast_break": 0,
                "points_in_the_paint": 0,
                "points_second_chance": 0,
                "fouls_offensive": 0,
                "fouls_drawn": 0,
                "fouls_personal": 0,
                "fouls_technical": 0,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
            },
        ],
        aps.FACT_REQUIRED_COLUMNS,
    )
    team_fact_table = _table_from_rows(
        [
            {
                "game_id": "0022400001",
                "team_id": 1610612737,
                "opponent_team_id": 1610612738,
                "score": 100,
                "opponent_score": 98,
                "seconds_played_total": 14400.0,
                "field_goals_attempted": 85,
                "two_pointers_attempted": 55,
                "free_throws_attempted": 20,
                "rebounds_offensive": 10,
                "turnovers": 12,
                "is_win": 1,
                "is_loss": 0,
            },
            {
                "game_id": "0022400001",
                "team_id": 1610612738,
                "opponent_team_id": 1610612737,
                "score": 98,
                "opponent_score": 100,
                "seconds_played_total": 14400.0,
                "field_goals_attempted": 88,
                "two_pointers_attempted": 60,
                "free_throws_attempted": 18,
                "rebounds_offensive": 9,
                "turnovers": 13,
                "is_win": 0,
                "is_loss": 1,
            },
            {
                "game_id": "0022400002",
                "team_id": 1610612737,
                "opponent_team_id": 1610612738,
                "score": 97,
                "opponent_score": 101,
                "seconds_played_total": 14400.0,
                "field_goals_attempted": 80,
                "two_pointers_attempted": 52,
                "free_throws_attempted": 16,
                "rebounds_offensive": 8,
                "turnovers": 11,
                "is_win": 0,
                "is_loss": 1,
            },
            {
                "game_id": "0022400002",
                "team_id": 1610612738,
                "opponent_team_id": 1610612737,
                "score": 101,
                "opponent_score": 97,
                "seconds_played_total": 14400.0,
                "field_goals_attempted": 82,
                "two_pointers_attempted": 40,
                "free_throws_attempted": 21,
                "rebounds_offensive": 10,
                "turnovers": 12,
                "is_win": 1,
                "is_loss": 0,
            },
            {
                "game_id": "0022400003",
                "team_id": 1610612751,
                "opponent_team_id": 1610612748,
                "score": 110,
                "opponent_score": 102,
                "seconds_played_total": 14400.0,
                "field_goals_attempted": 90,
                "two_pointers_attempted": 58,
                "free_throws_attempted": 22,
                "rebounds_offensive": 11,
                "turnovers": 10,
                "is_win": 1,
                "is_loss": 0,
            },
        ],
        aps.TEAM_FACT_REQUIRED_COLUMNS,
    )
    player_game_possession_map = {
        ("0022400001", 42): {
            "on_court_games_covered_total": 1,
            "ot_fallback_games_played": 0,
            "event_estimated_games_played": 0,
            "boxscore_estimated_games_played": 0,
            "missing_possession_games_played": 0,
            "offensive_possessions_total": 48.0,
            "defensive_possessions_total": 50.0,
            "team_points_for_while_on_court_total": 100.0,
            "team_points_against_while_on_court_total": 98.0,
        },
        ("0022400002", 42): {
            "on_court_games_covered_total": 0,
            "ot_fallback_games_played": 0,
            "event_estimated_games_played": 1,
            "boxscore_estimated_games_played": 0,
            "missing_possession_games_played": 0,
            "offensive_possessions_total": 44.0,
            "defensive_possessions_total": 40.0,
            "team_points_for_while_on_court_total": 97.0,
            "team_points_against_while_on_court_total": 101.0,
        },
    }
    rows = aps.build_agg_rows(
        fact_table,
        aps.build_team_game_result_map(team_fact_table),
        current_player_attrs_map={
            42: {
                "current_player_sk": 9001,
                "birth_date": date(2002, 6, 29),
            }
        },
        current_team_attrs_map={
            1610612737: {"team_abbreviation": "ATL", "team_name": "Hawks"},
            1610612751: {"team_abbreviation": "BKN", "team_name": "Nets"},
        },
        player_game_possession_map=player_game_possession_map,
    )

    assert len(rows) == 1
    row = rows[0]

    assert row["season_year"] == "2024-25"
    assert row["season_start_year"] == 2024
    assert row["season_type"] == "regular_season"
    assert row["games_on_roster"] == 3
    assert row["games_played"] == 2
    assert row["games_started"] == 2
    assert row["wins"] == 1
    assert row["losses"] == 1
    assert row["team_count"] == 2
    assert row["primary_team_id"] == 1610612737
    assert row["primary_team_abbreviation"] == "ATL"
    assert row["primary_team_name"] == "Hawks"
    assert row["is_multi_team_season"] == 1
    assert row["current_player_sk"] == 9001
    assert row["age_on_jan_31"] == 22
    assert row["points_total"] == 31
    assert row["rebounds_total"] == 20
    assert row["assists_total"] == 15
    assert row["double_doubles"] == 2
    assert row["triple_doubles"] == 1
    assert row["quadruple_doubles"] == 0
    assert math.isclose(row["seconds_played_total"], 3750.0)
    assert math.isclose(row["seconds_played_average"], 1875.0)
    assert math.isclose(row["minutes_per_game"], 31.2)
    assert math.isclose(row["field_goals_percentage"], 13 / 26)
    assert math.isclose(row["three_pointers_percentage"], 3 / 7)
    assert math.isclose(row["free_throws_percentage"], 1.0)
    assert math.isclose(row["points_per_game"], 15.5)
    assert math.isclose(row["assists_per_game"], 7.5)
    assert math.isclose(row["rebounds_per_game"], 10.0)
    assert math.isclose(row["possessions_total"], 182.0)
    assert "fantasy_points_total" not in row


def test_build_exact_player_game_possession_stats_credits_lineups_and_points() -> None:
    played_players = {
        person_id: {"person_id": person_id, "team_id": 1 if person_id <= 5 else 2, "seconds_played_total": 600.0}
        for person_id in range(1, 11)
    }
    possession_rows = [
        {
            "offenseTeamId": 1,
            "defenseTeamId": 2,
            "offenseHomeAway": "h",
            "defenseHomeAway": "v",
            "pointsScoredOnPossession": 2,
            "countsAsPossession": True,
            "homeLineupId": "1-2-3-4-5",
            "awayLineupId": "6-7-8-9-10",
            "lineupValidFlag": 1,
        }
    ]
    event_context_rows = [
        {
            "home_team_id": 1,
            "away_team_id": 2,
            "home_lineup_id": "1-2-3-4-5",
            "away_lineup_id": "6-7-8-9-10",
            "home_current_player_ids": [1, 2, 3, 4, 5],
            "away_current_player_ids": [6, 7, 8, 9, 10],
        }
    ]

    stats = aps.build_exact_player_game_possession_stats(possession_rows, event_context_rows, played_players)

    assert stats is not None
    assert stats[1]["offensive_possessions_total"] == 1.0
    assert stats[1]["team_points_for_while_on_court_total"] == 2.0
    assert stats[1]["on_court_games_covered_total"] == 1
    assert stats[6]["defensive_possessions_total"] == 1.0
    assert stats[6]["team_points_against_while_on_court_total"] == 2.0
    assert stats[6]["on_court_games_covered_total"] == 1


def test_build_player_game_possession_map_from_table_uses_canonical_silver_rows() -> None:
    context_table = _table_from_rows(
        [
            {
                "game_id": "0022400001",
                "person_id": 42,
                "exact_game_flag": 1,
                "ot_fallback_game_flag": 0,
                "event_estimated_game_flag": 0,
                "boxscore_estimated_game_flag": 0,
                "missing_game_flag": 0,
                "offensive_possessions": 51.0,
                "defensive_possessions": 50.0,
                "team_points_for_while_on_court": 108.0,
                "team_points_against_while_on_court": 103.0,
            }
        ],
        aps.PLAYER_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS,
    )

    possession_map = aps.build_player_game_possession_map_from_table(context_table)

    assert possession_map[("0022400001", 42)] == {
        "on_court_games_covered_total": 1,
        "ot_fallback_games_played": 0,
        "event_estimated_games_played": 0,
        "boxscore_estimated_games_played": 0,
        "missing_possession_games_played": 0,
        "offensive_possessions_total": 51.0,
        "defensive_possessions_total": 50.0,
        "team_points_for_while_on_court_total": 108.0,
        "team_points_against_while_on_court_total": 103.0,
    }


def test_build_player_game_defensive_shot_context_map_from_table_uses_canonical_silver_rows() -> None:
    context_table = _table_from_rows(
        [
            {
                "game_id": "0022400001",
                "person_id": 42,
                "exact_game_flag": 1,
                "event_estimated_game_flag": 0,
                "boxscore_estimated_game_flag": 0,
                "missing_game_flag": 0,
                "opponent_two_point_attempts_while_on_court": 17.0,
            }
        ],
        aps.PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS,
    )

    shot_context_map = aps.build_player_game_defensive_shot_context_map_from_table(context_table)

    assert shot_context_map[("0022400001", 42)] == {
        "exact_shot_context_games": 1,
        "event_estimated_shot_context_games": 0,
        "boxscore_estimated_shot_context_games": 0,
        "missing_shot_context_games": 0,
        "opponent_two_point_attempts_while_on_court_total": 17.0,
    }


def test_build_event_estimated_player_game_possession_stats_uses_event_context() -> None:
    played_players = {
        person_id: {"person_id": person_id, "team_id": 1 if person_id <= 5 else 2, "seconds_played_total": 600.0}
        for person_id in range(1, 11)
    }
    playbyplay_rows = [
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
    ]
    event_context_rows = [
        {
            "event_num": 2,
            "home_team_id": 1,
            "away_team_id": 2,
            "home_current_player_ids": [1, 2, 3, 4, 5],
            "away_current_player_ids": [6, 7, 8, 9, 10],
        }
    ]

    stats = aps.build_event_estimated_player_game_possession_stats(playbyplay_rows, event_context_rows, played_players)

    assert stats is not None
    assert stats[1]["offensive_possessions_total"] == 1.0
    assert stats[1]["team_points_for_while_on_court_total"] == 2.0
    assert stats[1]["event_estimated_games_played"] == 1
    assert stats[6]["defensive_possessions_total"] == 1.0
    assert stats[6]["team_points_against_while_on_court_total"] == 2.0
    assert stats[6]["event_estimated_games_played"] == 1


def test_build_boxscore_estimated_player_game_possession_stats_uses_minute_share() -> None:
    played_players = {
        11: {"person_id": 11, "team_id": 1, "seconds_played_total": 900.0},
    }
    team_game_context_map = {
        ("0022400001", 1): {
            "opponent_team_id": 2,
            "score": 100,
            "opponent_score": 96,
            "seconds_played_total": 14400.0,
            "field_goals_attempted": 80,
            "free_throws_attempted": 20,
            "rebounds_offensive": 10,
            "turnovers": 15,
        },
        ("0022400001", 2): {
            "opponent_team_id": 1,
            "score": 96,
            "opponent_score": 100,
            "seconds_played_total": 14400.0,
            "field_goals_attempted": 82,
            "free_throws_attempted": 18,
            "rebounds_offensive": 8,
            "turnovers": 14,
        },
    }

    stats = aps.build_boxscore_estimated_player_game_possession_stats(
        played_players,
        team_game_context_map,
        game_id="0022400001",
    )

    assert stats is not None
    assert math.isclose(stats[11]["offensive_possessions_total"], 29.64375)
    assert math.isclose(stats[11]["defensive_possessions_total"], 29.64375)
    assert math.isclose(stats[11]["team_points_for_while_on_court_total"], 31.25)
    assert math.isclose(stats[11]["team_points_against_while_on_court_total"], 30.0)
    assert stats[11]["boxscore_estimated_games_played"] == 1


def test_build_current_player_attrs_map_keeps_birth_date_from_latest_current_row() -> None:
    dim_player_table = _table_from_rows(
        [
            {
                "person_id": 42,
                "player_sk": 100,
                "birth_date": date(2002, 6, 29),
                "is_current": 1,
                "valid_from_utc": "2024-01-01T00:00:00Z",
            },
            {
                "person_id": 42,
                "player_sk": 101,
                "birth_date": date(2002, 6, 29),
                "is_current": 1,
                "valid_from_utc": "2024-02-01T00:00:00Z",
            },
        ],
        aps.DIM_PLAYER_REQUIRED_COLUMNS,
    )

    attrs_map = aps.build_current_player_attrs_map(dim_player_table)

    assert attrs_map == {
        42: {
            "current_player_sk": 101,
            "birth_date": date(2002, 6, 29),
        }
    }
