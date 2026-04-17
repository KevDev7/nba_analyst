from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_on_court_state as on_court_silver


def make_event_row(
    *,
    event_num: int,
    event_order: int,
    period: int,
    clock: str,
    action_type: str,
    sub_type: str | None = None,
    description: str | None = None,
    is_substitution_event: bool = False,
    team_id: int | None = None,
    player1_id: int | None = None,
    home_players: list[int] | None = None,
    away_players: list[int] | None = None,
    home_team_id: int = 1,
    away_team_id: int = 2,
) -> dict[str, object]:
    return {
        "game_id": "TEST",
        "event_num": event_num,
        "event_order": event_order,
        "period": period,
        "clock": clock,
        "description": description,
        "action_type": action_type,
        "sub_type": sub_type,
        "is_substitution_event": is_substitution_event,
        "team_id": team_id,
        "player1_id": player1_id,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "home_current_player_ids": home_players,
        "away_current_player_ids": away_players,
    }


def test_preserves_target_columns_shape():
    assert on_court_silver.TARGET_COLUMNS == [
        "gameId",
        "period",
        "stint_id",
        "start_orderNumber",
        "end_orderNumber",
        "start_actionNumber",
        "end_actionNumber",
        "start_clock",
        "end_clock",
        "start_timeActual_utc",
        "end_timeActual_utc",
        "home_teamId",
        "away_teamId",
        "home_personIds",
        "away_personIds",
        "lineup_valid_flag",
        "lineup_issue",
    ]


def test_target_schema_adds_silver_metadata_columns():
    schema_names = set(on_court_silver.TARGET_SCHEMA.names)
    for column in on_court_silver.META_COLUMNS:
        assert column in schema_names


def test_on_court_state_reads_from_event_projection_v2():
    assert on_court_silver.PROJECTION_PREFIX == "silver/event_projection_v2/"
    assert on_court_silver.SOURCE_SYSTEM == "silver_event_projection_v2_and_boxscore"


def test_target_schema_stays_lineup_state_only():
    assert {
        "pointsFor",
        "pointsAgainst",
        "possessions",
        "offensiveRating",
        "defensiveRating",
        "netRating",
        "wowyBucket",
    }.isdisjoint(set(on_court_silver.TARGET_COLUMNS))


def test_build_boxscore_starter_index_accepts_exactly_five_unique_players_per_team():
    df = pd.DataFrame(
        [
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 101, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 102, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 103, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 104, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 105, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 201, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 202, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 203, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 204, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 205, "starter": 1},
        ]
    )

    starter_index = on_court_silver.build_boxscore_starter_index(df)

    assert starter_index == {
        "TEST": {
            1: [101, 102, 103, 104, 105],
            2: [201, 202, 203, 204, 205],
        }
    }


def test_build_boxscore_starter_index_rejects_duplicate_and_non_five_teams():
    df = pd.DataFrame(
        [
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 101, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 101, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 103, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 104, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 105, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 201, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 202, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 203, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 204, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 205, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 206, "starter": 1},
        ]
    )

    starter_index = on_court_silver.build_boxscore_starter_index(df)

    assert starter_index == {}


def test_build_boxscore_game_index_tracks_home_away_orientation_and_valid_starters():
    df = pd.DataFrame(
        [
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 101, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 102, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 103, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 104, "starter": 1},
            {"gameId": "TEST", "teamId": 1, "team_side": "home", "personId": 105, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 201, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 202, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 203, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 204, "starter": 1},
            {"gameId": "TEST", "teamId": 2, "team_side": "away", "personId": 205, "starter": 1},
        ]
    )

    game_index = on_court_silver.build_boxscore_game_index(df)

    assert game_index == {
        "TEST": {
            "home_team_id": 1,
            "away_team_id": 2,
            "starters_by_team": {
                1: [101, 102, 103, 104, 105],
                2: [201, 202, 203, 204, 205],
            },
        }
    }


def test_period_one_seeds_from_boxscore_starters_even_when_first_rows_are_not_stable():
    rows_df = pd.DataFrame(
        [
            make_event_row(
                event_num=1,
                event_order=100,
                period=1,
                clock="PT12M00.00S",
                action_type="substitution",
                sub_type="out",
                is_substitution_event=True,
                team_id=1,
                player1_id=101,
                home_players=None,
                away_players=None,
            ),
            make_event_row(
                event_num=2,
                event_order=110,
                period=1,
                clock="PT12M00.00S",
                action_type="substitution",
                sub_type="in",
                is_substitution_event=True,
                team_id=1,
                player1_id=106,
                home_players=None,
                away_players=None,
            ),
            make_event_row(
                event_num=3,
                event_order=200,
                period=1,
                clock="PT11M40.00S",
                action_type="2pt",
                sub_type="layup",
                home_players=None,
                away_players=None,
            ),
        ]
    )

    rows, game_invalid = on_court_silver.build_stints_for_game(
        "TEST",
        rows_df,
        home_team_id=1,
        away_team_id=2,
        boxscore_starters_by_team={
            1: [101, 102, 103, 104, 105],
            2: [201, 202, 203, 204, 205],
        },
    )

    assert game_invalid is False
    assert len(rows) == 1
    assert rows[0]["lineup_valid_flag"] == 1
    assert rows[0]["start_actionNumber"] == 1
    assert rows[0]["home_personIds"] == [102, 103, 104, 105, 106]


def test_period_two_opening_lineup_uses_prior_period_ending_lineup_without_opening_subs():
    rows_df = pd.DataFrame(
        [
            make_event_row(
                event_num=1,
                event_order=100,
                period=1,
                clock="PT12M00.00S",
                action_type="period",
                sub_type="start",
                home_players=[101, 102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=2,
                event_order=200,
                period=1,
                clock="PT00M00.10S",
                action_type="period",
                sub_type="end",
                home_players=[101, 102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=3,
                event_order=300,
                period=2,
                clock="PT12M00.00S",
                action_type="period",
                sub_type="start",
                home_players=[101, 102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=4,
                event_order=320,
                period=2,
                clock="PT11M40.00S",
                action_type="2pt",
                home_players=[101, 102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
        ]
    )

    rows, game_invalid = on_court_silver.build_stints_for_game(
        "TEST",
        rows_df,
        home_team_id=1,
        away_team_id=2,
        boxscore_starters_by_team={
            1: [101, 102, 103, 104, 105],
            2: [201, 202, 203, 204, 205],
        },
    )

    assert game_invalid is False
    assert len(rows) == 2
    assert rows[1]["period"] == 2
    assert rows[1]["start_actionNumber"] == 3
    assert rows[1]["home_personIds"] == [101, 102, 103, 104, 105]


def test_build_stints_for_period_two_opening_cluster_uses_carry_forward():
    rows_df = pd.DataFrame(
        [
            make_event_row(
                event_num=1,
                event_order=100,
                period=1,
                clock="PT12M00.00S",
                action_type="period",
                sub_type="start",
                home_players=[101, 102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=2,
                event_order=200,
                period=1,
                clock="PT00M00.10S",
                action_type="period",
                sub_type="end",
                home_players=[101, 102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=3,
                event_order=300,
                period=2,
                clock="PT12M00.00S",
                action_type="substitution",
                sub_type="out",
                is_substitution_event=True,
                team_id=1,
                player1_id=101,
                home_players=[102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=4,
                event_order=310,
                period=2,
                clock="PT12M00.00S",
                action_type="substitution",
                sub_type="in",
                is_substitution_event=True,
                team_id=1,
                player1_id=106,
                home_players=[102, 103, 104, 105, 106],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=5,
                event_order=320,
                period=2,
                clock="PT12M00.00S",
                action_type="period",
                sub_type="start",
                home_players=[102, 103, 104, 105, 106],
                away_players=[201, 202, 203, 204, 205],
            ),
        ]
    )

    rows, game_invalid = on_court_silver.build_stints_for_game(
        "TEST",
        rows_df,
        boxscore_starters_by_team={
            1: [101, 102, 103, 104, 105],
            2: [201, 202, 203, 204, 205],
        },
    )

    assert game_invalid is False
    assert len(rows) == 2
    assert rows[0]["period"] == 1
    assert rows[1]["period"] == 2
    assert rows[1]["start_actionNumber"] == 3
    assert rows[1]["home_personIds"] == [102, 103, 104, 105, 106]


def test_invalid_boxscore_starter_map_marks_period_one_invalid_without_context_bootstrap():
    rows_df = pd.DataFrame(
        [
            make_event_row(
                event_num=1,
                event_order=100,
                period=1,
                clock="PT12M00.00S",
                action_type="substitution",
                sub_type="out",
                is_substitution_event=True,
                team_id=1,
                player1_id=101,
                home_players=[102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=2,
                event_order=110,
                period=1,
                clock="PT12M00.00S",
                action_type="substitution",
                sub_type="in",
                is_substitution_event=True,
                team_id=1,
                player1_id=106,
                home_players=[102, 103, 104, 105, 106],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=3,
                event_order=200,
                period=1,
                clock="PT11M40.00S",
                action_type="2pt",
                sub_type="layup",
                home_players=[102, 103, 104, 105, 106],
                away_players=[201, 202, 203, 204, 205],
            ),
        ]
    )

    rows, game_invalid = on_court_silver.build_stints_for_game(
        "TEST",
        rows_df,
        home_team_id=1,
        away_team_id=2,
        boxscore_starters_by_team={
            1: [101, 102, 103, 104],
            2: [201, 202, 203, 204, 205],
        },
    )

    assert game_invalid is True
    assert len(rows) == 1
    assert rows[0]["lineup_issue"] == "missing_boxscore_starters_period_1"
    assert rows[0]["lineup_valid_flag"] == 0


def test_same_clock_non_sub_rows_do_not_break_substitution_cluster():
    rows_df = pd.DataFrame(
        [
            make_event_row(
                event_num=1,
                event_order=100,
                period=1,
                clock="PT12M00.00S",
                action_type="period",
                sub_type="start",
                home_players=[101, 102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=2,
                event_order=200,
                period=1,
                clock="PT10M00.00S",
                action_type="substitution",
                sub_type="out",
                is_substitution_event=True,
                team_id=1,
                player1_id=101,
                home_players=[102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=3,
                event_order=210,
                period=1,
                clock="PT10M00.00S",
                action_type="jumpball",
                sub_type="recovered",
                is_substitution_event=False,
                home_players=[102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=4,
                event_order=220,
                period=1,
                clock="PT10M00.00S",
                action_type="substitution",
                sub_type="in",
                is_substitution_event=True,
                team_id=1,
                player1_id=106,
                home_players=[102, 103, 104, 105, 106],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=5,
                event_order=300,
                period=1,
                clock="PT09M40.00S",
                action_type="2pt",
                home_players=[102, 103, 104, 105, 106],
                away_players=[201, 202, 203, 204, 205],
            ),
        ]
    )

    rows, game_invalid = on_court_silver.build_stints_for_game(
        "TEST",
        rows_df,
        home_team_id=1,
        away_team_id=2,
        boxscore_starters_by_team={
            1: [101, 102, 103, 104, 105],
            2: [201, 202, 203, 204, 205],
        },
    )

    assert game_invalid is False
    assert len(rows) == 2
    assert rows[0]["end_actionNumber"] == 2
    assert rows[1]["start_actionNumber"] == 2
    assert rows[1]["home_personIds"] == [102, 103, 104, 105, 106]


def test_invalid_transient_non_five_player_cluster_stays_invalid():
    rows_df = pd.DataFrame(
        [
            make_event_row(
                event_num=1,
                event_order=100,
                period=1,
                clock="PT12M00.00S",
                action_type="period",
                sub_type="start",
                home_players=[101, 102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=2,
                event_order=200,
                period=1,
                clock="PT10M00.00S",
                action_type="substitution",
                sub_type="out",
                is_substitution_event=True,
                home_players=[102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=3,
                event_order=210,
                period=1,
                clock="PT10M00.00S",
                action_type="substitution",
                sub_type="in",
                is_substitution_event=True,
                team_id=1,
                player1_id=106,
                home_players=[102, 103, 104, 105, 106, 107],
                away_players=[201, 202, 203, 204, 205],
            ),
        ]
    )

    rows, game_invalid = on_court_silver.build_stints_for_game(
        "TEST",
        rows_df,
        home_team_id=1,
        away_team_id=2,
        boxscore_starters_by_team={
            1: [101, 102, 103, 104, 105],
            2: [201, 202, 203, 204, 205],
        },
    )

    assert game_invalid is True
    assert rows[-1]["lineup_valid_flag"] == 0
    assert rows[-1]["lineup_issue"] == "substitution_produces_duplicate_or_non_five_lineup"


def test_invalid_mid_period_substitution_that_removes_unknown_player_is_labeled_explicitly():
    rows_df = pd.DataFrame(
        [
            make_event_row(
                event_num=1,
                event_order=100,
                period=1,
                clock="PT12M00.00S",
                action_type="period",
                sub_type="start",
                home_players=[101, 102, 103, 104, 105],
                away_players=[201, 202, 203, 204, 205],
            ),
            make_event_row(
                event_num=2,
                event_order=200,
                period=1,
                clock="PT10M00.00S",
                action_type="substitution",
                sub_type="out",
                is_substitution_event=True,
                team_id=1,
                player1_id=999,
                home_players=[101, 102, 103, 104, 999],
                away_players=[201, 202, 203, 204, 205],
            ),
        ]
    )

    rows, game_invalid = on_court_silver.build_stints_for_game(
        "TEST",
        rows_df,
        home_team_id=1,
        away_team_id=2,
        boxscore_starters_by_team={
            1: [101, 102, 103, 104, 105],
            2: [201, 202, 203, 204, 205],
        },
    )

    assert game_invalid is True
    assert rows[-1]["lineup_valid_flag"] == 0
    assert rows[-1]["lineup_issue"] == "substitution_removes_player_not_on_court"
