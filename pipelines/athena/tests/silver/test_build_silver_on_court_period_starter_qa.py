from __future__ import annotations

import sys
from pathlib import Path


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_on_court_period_starter_qa as starter_qa


def event_row(
    *,
    event_num: int,
    event_order: int,
    period: int,
    team_id: int,
    player_id: int,
    sub_type: str,
) -> dict[str, object]:
    return {
        "game_id": "0022500001",
        "event_num": event_num,
        "event_order": event_order,
        "period": period,
        "is_substitution_event": True,
        "team_id": team_id,
        "player1_id": player_id,
        "sub_type": sub_type,
    }


def on_court_row(
    *,
    period: int,
    home_players: list[int],
    away_players: list[int] | None = None,
    valid: int = 1,
) -> dict[str, object]:
    return {
        "gameId": "0022500001",
        "period": period,
        "stint_id": 1,
        "start_orderNumber": period * 100,
        "home_teamId": 1,
        "away_teamId": 2,
        "home_personIds": home_players,
        "away_personIds": away_players or [201, 202, 203, 204, 205],
        "lineup_valid_flag": valid,
        "lineup_issue": None if valid else "test_invalid",
    }


def test_derive_reference_starters_excludes_players_whose_first_sub_is_in():
    starters = starter_qa.derive_reference_starters(
        [101, 102, 103, 104, 105, 106],
        period=2,
        team_id=1,
        event_rows=[
            event_row(event_num=10, event_order=1000, period=2, team_id=1, player_id=106, sub_type="in"),
            event_row(event_num=11, event_order=1010, period=2, team_id=1, player_id=101, sub_type="out"),
        ],
    )

    assert starters == [101, 102, 103, 104, 105]


def test_build_qa_rows_marks_match_when_current_starters_equal_reference_set():
    rows = starter_qa.build_qa_rows_for_game(
        game_id="0022500001",
        period_presence_rows=[
            {"gameId": "0022500001", "period": 2, "team_side": "home", "teamId": 1, "personId": person_id}
            for person_id in [101, 102, 103, 104, 105, 106]
        ],
        event_rows=[
            event_row(event_num=10, event_order=1000, period=2, team_id=1, player_id=106, sub_type="in"),
            event_row(event_num=11, event_order=1010, period=2, team_id=1, player_id=101, sub_type="out"),
        ],
        on_court_rows=[on_court_row(period=2, home_players=[101, 102, 103, 104, 105])],
    )

    assert len(rows) == 1
    assert rows[0]["qa_status"] == "match"
    assert rows[0]["match_flag"] == 1
    assert rows[0]["missing_from_current_personIds"] == []
    assert rows[0]["extra_in_current_personIds"] == []


def test_build_qa_rows_marks_mismatch_with_missing_and_extra_players():
    rows = starter_qa.build_qa_rows_for_game(
        game_id="0022500001",
        period_presence_rows=[
            {"gameId": "0022500001", "period": 2, "team_side": "home", "teamId": 1, "personId": person_id}
            for person_id in [101, 102, 103, 104, 105, 106]
        ],
        event_rows=[
            event_row(event_num=10, event_order=1000, period=2, team_id=1, player_id=106, sub_type="in"),
            event_row(event_num=11, event_order=1010, period=2, team_id=1, player_id=101, sub_type="out"),
        ],
        on_court_rows=[on_court_row(period=2, home_players=[101, 102, 103, 104, 107])],
    )

    assert rows[0]["qa_status"] == "mismatch"
    assert rows[0]["match_flag"] == 0
    assert rows[0]["missing_from_current_personIds"] == [105]
    assert rows[0]["extra_in_current_personIds"] == [107]


def test_build_qa_rows_marks_incomplete_reference_when_reference_does_not_resolve_to_five():
    rows = starter_qa.build_qa_rows_for_game(
        game_id="0022500001",
        period_presence_rows=[
            {"gameId": "0022500001", "period": 2, "team_side": "home", "teamId": 1, "personId": person_id}
            for person_id in [101, 102, 103, 104, 105, 106, 107]
        ],
        event_rows=[
            event_row(event_num=10, event_order=1000, period=2, team_id=1, player_id=106, sub_type="in"),
        ],
        on_court_rows=[on_court_row(period=2, home_players=[101, 102, 103, 104, 105])],
    )

    assert rows[0]["qa_status"] == "incomplete_reference"
    assert rows[0]["qa_issue"] == "reference_starter_count=6"


def test_extract_period_presence_rows_supports_v3_nested_payload_and_filters_zero_minutes():
    payload = {
        "boxScoreTraditional": {
            "gameId": "0022500001",
            "homeTeam": {
                "teamId": 1,
                "players": [
                    {"personId": 101, "statistics": {"minutesCalculated": "PT12M00.00S"}},
                    {"personId": 102, "statistics": {"minutesCalculated": "PT00M00.00S", "points": 0}},
                    {"personId": 103, "statistics": {"minutesCalculated": "PT00M00.00S", "points": 2}},
                ],
            },
            "awayTeam": {
                "teamId": 2,
                "players": [
                    {"personId": 201, "statistics": {"minutes": "5:30"}},
                ],
            },
        }
    }

    rows = starter_qa.extract_period_presence_rows(payload, fallback_game_id=None, period=3)

    assert rows == [
        {"gameId": "0022500001", "period": 3, "team_side": "home", "teamId": 1, "personId": 101},
        {"gameId": "0022500001", "period": 3, "team_side": "home", "teamId": 1, "personId": 103},
        {"gameId": "0022500001", "period": 3, "team_side": "away", "teamId": 2, "personId": 201},
    ]


def test_target_schema_keeps_qa_out_of_gold_contract_shape():
    assert starter_qa.TARGET_SCHEMA.names == starter_qa.TARGET_COLUMNS + starter_qa.META_COLUMNS
    assert "net_rating" not in starter_qa.TARGET_SCHEMA.names
