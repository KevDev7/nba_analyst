from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sys

import pyarrow as pa

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.athena.transform.gold.transform_to_fct_player_game_parquet import (
    build_base_fact_rows,
    build_team_label_by_sk,
)
from pipelines.athena.transform.gold.transform_to_fct_team_game_parquet import (
    build_player_team_boxscore_map,
    build_team_rows,
    pick_opponent,
)


def test_fct_player_game_minutes_fallback_prefers_minutes_calculated_then_minutes() -> None:
    player_table = pa.Table.from_pylist(
        [
            {
                "gameId": "0022400151",
                "teamId": 1610612765,
                "team_side": "away",
                "personId": 1,
                "position": "G",
                "status": "ACTIVE",
                "order": 1,
                "starter": 1,
                "oncourt": 1,
                "played": 1,
                "minutes": "PT30M00.00S",
                "minutesCalculated": "PT31M15.00S",
                "plus": 1,
                "minus": 0,
                "plusMinusPoints": 1,
                "assists": 5,
                "blocks": 0,
                "blocksReceived": 0,
                "fieldGoalsAttempted": 10,
                "fieldGoalsMade": 5,
                "fieldGoalsPercentage": 0.5,
                "foulsOffensive": 0,
                "foulsDrawn": 0,
                "foulsPersonal": 2,
                "foulsTechnical": 0,
                "freeThrowsAttempted": 2,
                "freeThrowsMade": 2,
                "freeThrowsPercentage": 1.0,
                "reboundsDefensive": 3,
                "reboundsOffensive": 1,
                "reboundsTotal": 4,
                "steals": 1,
                "turnovers": 2,
                "points": 12,
                "threePointersAttempted": 4,
                "threePointersMade": 2,
                "threePointersPercentage": 0.5,
                "twoPointersAttempted": 6,
                "twoPointersMade": 3,
                "twoPointersPercentage": 0.5,
                "pointsFastBreak": 2,
                "pointsInThePaint": 4,
                "pointsSecondChance": 1,
            }
        ]
    )
    rows = build_base_fact_rows(
        player_table,
        {
            "0022400151": {
                "game_sk": 1,
                "game_date": date(2024, 11, 3),
                "game_datetime_utc": datetime(2024, 11, 4, 0, 0, tzinfo=timezone.utc),
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
            }
        },
        {date(2024, 11, 3): 20241103},
    )
    assert rows[0]["seconds_played_total"] == 1875.0
    assert rows[0]["minutes_played_decimal"] == 31.25
    assert rows[0]["season_start_year"] == 2024


def test_build_team_label_by_sk_prefers_abbreviation_then_name() -> None:
    labels = build_team_label_by_sk(
        [
            {"team_sk": 1, "team_abbreviation": "GSW", "team_name": "Warriors"},
            {"team_sk": 2, "team_abbreviation": None, "team_name": "Lakers"},
        ]
    )

    assert labels[1] == "GSW"
    assert labels[2] == "Lakers"


def test_pick_opponent_prefers_true_home_away_pairing() -> None:
    base_row = {"team_id": 1, "team_side": "home"}
    opponent = pick_opponent(
        base_row,
        [
            {"team_id": 1, "team_side": "home"},
            {"team_id": 2, "team_side": "away"},
            {"team_id": 3, "team_side": None},
        ],
    )
    assert opponent is not None
    assert opponent["team_id"] == 2


def test_build_team_rows_keeps_highest_quality_row_per_game_team() -> None:
    team_game_table = pa.Table.from_pylist(
        [
            {
                "gameId": "0022400151",
                "team_side": "home",
                "teamId": 1610612751,
                "teamName": "Nets",
                "teamCity": "Brooklyn",
                "teamTricode": "BKN",
                "score": 92,
                "inBonus": 0,
                "timeoutsRemaining": 1,
            },
            {
                "gameId": "0022400151",
                "team_side": None,
                "teamId": 1610612751,
                "teamName": "Nets",
                "teamCity": None,
                "teamTricode": "BKN",
                "score": 92,
                "inBonus": None,
                "timeoutsRemaining": None,
            },
        ]
    )
    rows, _ = build_team_rows(team_game_table)
    assert len(rows) == 1
    assert rows[0]["team_side"] == "home"
    assert rows[0]["team_city"] == "Brooklyn"


def test_build_player_team_boxscore_map_computes_percentages_from_player_totals() -> None:
    player_fact_table = pa.Table.from_pylist(
        [
            {
                "game_id": "0022400151",
                "team_id": 1610612765,
                "seconds_played_total": 1200.0,
                "assists": 5,
                "blocks": 1,
                "blocks_received": 0,
                "field_goals_attempted": 10,
                "field_goals_made": 5,
                "fouls_offensive": 0,
                "fouls_drawn": 2,
                "fouls_personal": 1,
                "fouls_technical": 0,
                "free_throws_attempted": 4,
                "free_throws_made": 3,
                "rebounds_defensive": 4,
                "rebounds_offensive": 1,
                "rebounds_total": 5,
                "steals": 2,
                "turnovers": 1,
                "three_pointers_attempted": 6,
                "three_pointers_made": 2,
                "two_pointers_attempted": 4,
                "two_pointers_made": 3,
                "points_fast_break": 2,
                "points_in_the_paint": 6,
                "points_second_chance": 1,
            },
            {
                "game_id": "0022400151",
                "team_id": 1610612765,
                "seconds_played_total": 900.0,
                "assists": 3,
                "blocks": 0,
                "blocks_received": 1,
                "field_goals_attempted": 8,
                "field_goals_made": 4,
                "fouls_offensive": 1,
                "fouls_drawn": 1,
                "fouls_personal": 2,
                "fouls_technical": 0,
                "free_throws_attempted": 2,
                "free_throws_made": 2,
                "rebounds_defensive": 2,
                "rebounds_offensive": 2,
                "rebounds_total": 4,
                "steals": 1,
                "turnovers": 3,
                "three_pointers_attempted": 2,
                "three_pointers_made": 1,
                "two_pointers_attempted": 6,
                "two_pointers_made": 3,
                "points_fast_break": 1,
                "points_in_the_paint": 4,
                "points_second_chance": 0,
            },
        ]
    )
    aggregations = build_player_team_boxscore_map(player_fact_table)
    row = aggregations[("0022400151", 1610612765)]
    assert row["seconds_played_total"] == 2100.0
    assert row["minutes_played_decimal"] == 35.0
    assert row["field_goals_percentage"] == 0.5
    assert row["free_throws_percentage"] == 5 / 6
    assert row["three_pointers_percentage"] == 3 / 8
    assert row["two_pointers_percentage"] == 6 / 10
