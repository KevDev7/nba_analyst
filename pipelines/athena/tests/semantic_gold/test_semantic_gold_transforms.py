from __future__ import annotations

from datetime import date

import pyarrow as pa
import pytest

from pipelines.athena.transform.semantic_gold.transform_to_arena_parquet import build_arena_rows_from_tables
from pipelines.athena.transform.semantic_gold.transform_to_game_parquet import build_game_rows_from_tables
from pipelines.athena.transform.semantic_gold.transform_to_player_game_parquet import build_player_game_rows_from_tables
from pipelines.athena.transform.semantic_gold.transform_to_player_parquet import build_player_rows_from_tables
from pipelines.athena.transform.semantic_gold.transform_to_player_season_parquet import (
    build_player_season_rows_from_player_game_rows,
    build_player_season_rows_from_tables,
)
from pipelines.athena.transform.semantic_gold.transform_to_player_season_team_parquet import (
    build_player_season_team_rows_from_tables,
)
from pipelines.athena.transform.semantic_gold.transform_to_team_game_parquet import build_team_game_rows_from_tables
from pipelines.athena.transform.semantic_gold.transform_to_team_season_parquet import (
    build_team_season_rows_from_tables,
)
from pipelines.athena.transform.semantic_gold.transform_to_team_parquet import build_team_rows_from_tables


def _table(rows: list[dict]) -> pa.Table:
    return pa.Table.from_pylist(rows)


def sample_schedule_table() -> pa.Table:
    return _table(
        [
            {
                "gameId": "0022400001",
                "gameCode": "20241022/LALGSW",
                "seasonYear": "2024-25",
                "leagueId": "00",
                "gameSequence": 1,
                "gameDate": "2024-10-22",
                "gameDateTimeUTC": "2024-10-23T02:00:00Z",
                "gameStatus": 3,
                "gameStatusText": "Final",
                "postponedStatus": None,
                "ifNecessary": False,
                "gameLabel": None,
                "gameSubLabel": None,
                "gameSubtype": None,
                "seriesGameNumber": None,
                "seriesText": None,
                "isNeutral": False,
                "arenaName": "Chase Center",
                "arenaCity": "San Francisco",
                "arenaState": "CA",
                "homeTeamId": 1610612744,
                "homeTeamName": "Warriors",
                "homeTeamCity": "Golden State",
                "homeTeamTricode": "GSW",
                "homeTeamSlug": "warriors",
                "awayTeamId": 1610612747,
                "awayTeamName": "Lakers",
                "awayTeamCity": "Los Angeles",
                "awayTeamTricode": "LAL",
                "awayTeamSlug": "lakers",
            }
        ]
    )


def sample_boxscore_game_table() -> pa.Table:
    return _table(
        [
            {
                "gameId": "0022400001",
                "gameCode": "20241022/LALGSW",
                "gameTimeUTC": "2024-10-23T02:00:00Z",
                "gameTimeLocal": "2024-10-22T19:00:00Z",
                "gameTimeHome": "2024-10-22T19:00:00Z",
                "gameTimeAway": "2024-10-22T19:00:00Z",
                "gameEt": "2024-10-22T22:00:00Z",
                "gameStatus": 3,
                "gameStatusText": "Final",
                "duration": 144,
                "attendance": 18064,
                "sellout": 1,
                "regulationPeriods": 4,
                "period": 4,
                "gameClock": "00:00",
                "arenaId": 1,
                "arenaName": "Chase Center",
                "arenaCity": "San Francisco",
                "arenaState": "CA",
                "arenaCountry": "USA",
                "arenaTimezone": "America/Los_Angeles",
                "meta_version": 1,
                "meta_code": 200,
                "meta_request": "boxscore",
                "meta_time": "2024-10-23T04:30:00Z",
            }
        ]
    )


def sample_team_game_table() -> pa.Table:
    return _table(
        [
            {
                "gameId": "0022400001",
                "team_side": "home",
                "teamId": 1610612744,
                "teamName": "Warriors",
                "teamCity": "Golden State",
                "teamTricode": "GSW",
                "score": 120,
                "inBonus": 1,
                "timeoutsRemaining": 2,
                "assists": 30,
                "blocks": 5,
                "blocksReceived": 4,
                "fieldGoalsAttempted": 90,
                "fieldGoalsMade": 44,
                "fieldGoalsPercentage": 48.9,
                "foulsOffensive": 2,
                "foulsDrawn": 18,
                "foulsPersonal": 17,
                "foulsTechnical": 0,
                "freeThrowsAttempted": 20,
                "freeThrowsMade": 16,
                "freeThrowsPercentage": 80.0,
                "reboundsDefensive": 33,
                "reboundsOffensive": 10,
                "reboundsTotal": 43,
                "steals": 9,
                "turnovers": 12,
                "threePointersAttempted": 38,
                "threePointersMade": 16,
                "threePointersPercentage": 42.1,
                "twoPointersAttempted": 52,
                "twoPointersMade": 28,
                "twoPointersPercentage": 53.8,
                "pointsFastBreak": 15,
                "pointsFromTurnovers": 19,
                "pointsInThePaint": 40,
                "pointsSecondChance": 14,
                "minutesCalculated": "PT240M",
            },
            {
                "gameId": "0022400001",
                "team_side": "away",
                "teamId": 1610612747,
                "teamName": "Lakers",
                "teamCity": "Los Angeles",
                "teamTricode": "LAL",
                "score": 115,
                "inBonus": 0,
                "timeoutsRemaining": 1,
                "assists": 28,
                "blocks": 4,
                "blocksReceived": 5,
                "fieldGoalsAttempted": 88,
                "fieldGoalsMade": 42,
                "fieldGoalsPercentage": 47.7,
                "foulsOffensive": 3,
                "foulsDrawn": 19,
                "foulsPersonal": 18,
                "foulsTechnical": 0,
                "freeThrowsAttempted": 22,
                "freeThrowsMade": 19,
                "freeThrowsPercentage": 86.4,
                "reboundsDefensive": 31,
                "reboundsOffensive": 9,
                "reboundsTotal": 40,
                "steals": 7,
                "turnovers": 13,
                "threePointersAttempted": 35,
                "threePointersMade": 12,
                "threePointersPercentage": 34.3,
                "twoPointersAttempted": 53,
                "twoPointersMade": 30,
                "twoPointersPercentage": 56.6,
                "pointsFastBreak": 12,
                "pointsFromTurnovers": 16,
                "pointsInThePaint": 42,
                "pointsSecondChance": 11,
                "minutesCalculated": "PT240M",
            },
        ]
    )


def sample_team_game_possession_context_table() -> pa.Table:
    return _table(
        [
            {
                "game_id": "0022400001",
                "team_id": 1610612744,
                "offensive_possessions": 100.0,
                "defensive_possessions": 98.0,
            },
            {
                "game_id": "0022400001",
                "team_id": 1610612747,
                "offensive_possessions": 98.0,
                "defensive_possessions": 100.0,
            },
        ]
    )


def sample_player_game_possession_context_table() -> pa.Table:
    return _table(
        [
            {
                "game_id": "0022400001",
                "person_id": 201939,
                "offensive_possessions": 74.0,
                "defensive_possessions": 72.0,
                "possessions_total": 146.0,
                "used_offensive_possessions": 24.0,
                "team_points_for_while_on_court": 90.0,
                "team_points_against_while_on_court": 82.0,
            },
            {
                "game_id": "0022400001",
                "person_id": 2544,
                "offensive_possessions": 71.0,
                "defensive_possessions": 75.0,
                "possessions_total": 146.0,
                "used_offensive_possessions": 22.0,
                "team_points_for_while_on_court": 84.0,
                "team_points_against_while_on_court": 89.0,
            },
        ]
    )


def sample_player_game_defensive_shot_context_table() -> pa.Table:
    return _table(
        [
            {
                "game_id": "0022400001",
                "person_id": 201939,
                "opponent_two_point_attempts_while_on_court": 40.0,
            },
            {
                "game_id": "0022400001",
                "person_id": 2544,
                "opponent_two_point_attempts_while_on_court": 44.0,
            },
        ]
    )


def sample_player_game_opportunity_context_table() -> pa.Table:
    return _table(
        [
            {
                "game_id": "0022400001",
                "person_id": 201939,
                "teammate_field_goals_made_while_on_court": 28.0,
                "offensive_rebound_opportunities_while_on_court": 9.0,
                "defensive_rebound_opportunities_while_on_court": 24.0,
                "rebound_opportunities_while_on_court": 33.0,
            },
            {
                "game_id": "0022400001",
                "person_id": 2544,
                "teammate_field_goals_made_while_on_court": 31.0,
                "offensive_rebound_opportunities_while_on_court": 10.0,
                "defensive_rebound_opportunities_while_on_court": 22.0,
                "rebound_opportunities_while_on_court": 32.0,
            },
        ]
    )


def sample_team_game_defensive_shot_context_table() -> pa.Table:
    return _table(
        [
            {
                "game_id": "0022400001",
                "team_id": 1610612744,
                "opponent_two_point_attempts": 53.0,
            },
            {
                "game_id": "0022400001",
                "team_id": 1610612747,
                "opponent_two_point_attempts": 52.0,
            },
        ]
    )


def sample_player_game_table() -> pa.Table:
    return _table(
        [
            {
                "gameId": "0022400001",
                "teamId": 1610612744,
                "team_side": "home",
                "personId": 201939,
                "name": "Stephen Curry",
                "nameI": "S. Curry",
                "firstName": "Stephen",
                "familyName": "Curry",
                "jerseyNum": "30",
                "position": "PG",
                "status": "Active",
                "order": 1,
                "starter": 1,
                "oncourt": 1,
                "played": 1,
                "minutes": "PT36M12S",
                "minutesCalculated": "PT36M12S",
                "plusMinusPoints": 8,
                "assists": 7,
                "blocks": 1,
                "blocksReceived": 0,
                "fieldGoalsAttempted": 20,
                "fieldGoalsMade": 12,
                "fieldGoalsPercentage": 60.0,
                "foulsOffensive": 0,
                "foulsDrawn": 4,
                "foulsPersonal": 2,
                "foulsTechnical": 0,
                "freeThrowsAttempted": 5,
                "freeThrowsMade": 5,
                "freeThrowsPercentage": 100.0,
                "reboundsDefensive": 4,
                "reboundsOffensive": 1,
                "reboundsTotal": 5,
                "steals": 2,
                "turnovers": 3,
                "points": 33,
                "threePointersAttempted": 11,
                "threePointersMade": 6,
                "threePointersPercentage": 54.5,
                "twoPointersAttempted": 9,
                "twoPointersMade": 6,
                "twoPointersPercentage": 66.7,
                "pointsFastBreak": 2,
                "pointsInThePaint": 6,
                "pointsSecondChance": 0,
            },
            {
                "gameId": "0022400001",
                "teamId": 1610612747,
                "team_side": "away",
                "personId": 2544,
                "name": "LeBron James",
                "nameI": "L. James",
                "firstName": "LeBron",
                "familyName": "James",
                "jerseyNum": "23",
                "position": "SF",
                "status": "Active",
                "order": 1,
                "starter": 1,
                "oncourt": 1,
                "played": 1,
                "minutes": "PT34M00S",
                "minutesCalculated": "PT34M00S",
                "plusMinusPoints": -4,
                "assists": 9,
                "blocks": 1,
                "blocksReceived": 1,
                "fieldGoalsAttempted": 18,
                "fieldGoalsMade": 11,
                "fieldGoalsPercentage": 61.1,
                "foulsOffensive": 1,
                "foulsDrawn": 6,
                "foulsPersonal": 3,
                "foulsTechnical": 0,
                "freeThrowsAttempted": 8,
                "freeThrowsMade": 6,
                "freeThrowsPercentage": 75.0,
                "reboundsDefensive": 7,
                "reboundsOffensive": 1,
                "reboundsTotal": 8,
                "steals": 1,
                "turnovers": 4,
                "points": 30,
                "threePointersAttempted": 5,
                "threePointersMade": 2,
                "threePointersPercentage": 40.0,
                "twoPointersAttempted": 13,
                "twoPointersMade": 9,
                "twoPointersPercentage": 69.2,
                "pointsFastBreak": 4,
                "pointsInThePaint": 12,
                "pointsSecondChance": 2,
            },
        ]
    )


def sample_player_bio_table() -> pa.Table:
    return _table(
        [
            {
                "personId": 201939,
                "firstName": "Stephen",
                "lastName": "Curry",
                "birthDate": "1988-03-14",
                "school": "Davidson",
                "country": "USA",
                "heightInches": 74,
                "bodyWeightLbs": 185,
                "draftYear": 2009,
                "draftRound": 1,
                "draftNumber": 7,
                "guard": 1,
                "forward": 0,
                "center": 0,
            },
            {
                "personId": 2544,
                "firstName": "LeBron",
                "lastName": "James",
                "birthDate": "1984-12-30",
                "school": "St. Vincent-St. Mary HS",
                "country": "USA",
                "heightInches": 81,
                "bodyWeightLbs": 250,
                "draftYear": 2003,
                "draftRound": 1,
                "draftNumber": 1,
                "guard": 0,
                "forward": 1,
                "center": 0,
            },
        ]
    )


def test_semantic_source_contracts_include_live_measure_columns() -> None:
    from pipelines.athena.transform.semantic_gold.transform_to_player_game_parquet import (
        PLAYER_REQUIRED_COLUMNS,
    )
    from pipelines.athena.transform.semantic_gold.transform_to_team_game_parquet import (
        TEAM_GAME_REQUIRED_COLUMNS,
    )

    assert "points" in PLAYER_REQUIRED_COLUMNS
    assert "minutesCalculated" in PLAYER_REQUIRED_COLUMNS
    assert "score" in TEAM_GAME_REQUIRED_COLUMNS
    assert "timeoutsRemaining" in TEAM_GAME_REQUIRED_COLUMNS


def sample_bridge_table() -> pa.Table:
    return _table(
        [
            {"nba_person_id": 201939, "basketball_reference_player_id": "curryst01", "match_method": "accepted", "match_confidence": 0.99},
            {"nba_person_id": 2544, "basketball_reference_player_id": "jamesle01", "match_method": "accepted", "match_confidence": 0.99},
        ]
    )


def sample_bbr_profile_table() -> pa.Table:
    return _table(
        [
            {
                "basketball_reference_player_id": "curryst01",
                "player_profile_url": "https://www.basketball-reference.com/players/c/curryst01.html",
                "formal_name": "Wardell Stephen Curry II",
                "birth_date": "1988-03-14",
                "pronunciation": None,
                "former_name_note": None,
                "nicknames_raw": "Steph",
                "instagram_handle": "stephencurry30",
                "position_raw": "Point Guard",
                "shoots": "Right",
                "height_raw": "6-2",
                "height_cm": 188,
                "weight_kg": 84,
                "current_team_raw": "Golden State Warriors",
                "birth_place_raw": "Akron, Ohio",
                "birth_country_code": "US",
                "death_date": None,
                "college_raw": "Davidson",
                "colleges_raw": "Davidson",
                "high_school_raw": "Charlotte Christian",
                "high_schools_raw": "Charlotte Christian",
                "recruiting_rank_raw": None,
                "recruiting_rank_year": None,
                "recruiting_rank_ordinal": None,
                "relatives_raw": None,
                "draft_raw": "2009",
                "draft_team_raw": "Golden State Warriors",
                "draft_pick_in_round": 7,
                "draft_league": "NBA",
                "draft_selection_note": None,
                "nba_debut_date": "2009-10-28",
                "aba_debut_date": None,
                "experience_years": 15,
                "career_length_years": 15,
                "hall_of_fame_flag": 0,
                "hall_of_fame_role": None,
                "hall_of_fame_year": None,
                "hall_of_fame_raw": None,
                "headshot_url": "https://example.com/steph.png",
            },
            {
                "basketball_reference_player_id": "jamesle01",
                "player_profile_url": "https://www.basketball-reference.com/players/j/jamesle01.html",
                "formal_name": "LeBron Raymone James Sr.",
                "birth_date": "1984-12-30",
                "pronunciation": None,
                "former_name_note": None,
                "nicknames_raw": "King James",
                "instagram_handle": "kingjames",
                "position_raw": "Small Forward",
                "shoots": "Right",
                "height_raw": "6-9",
                "height_cm": 206,
                "weight_kg": 113,
                "current_team_raw": "Los Angeles Lakers",
                "birth_place_raw": "Akron, Ohio",
                "birth_country_code": "US",
                "death_date": None,
                "college_raw": None,
                "colleges_raw": None,
                "high_school_raw": "St. Vincent-St. Mary",
                "high_schools_raw": "St. Vincent-St. Mary",
                "recruiting_rank_raw": None,
                "recruiting_rank_year": None,
                "recruiting_rank_ordinal": None,
                "relatives_raw": None,
                "draft_raw": "2003",
                "draft_team_raw": "Cleveland Cavaliers",
                "draft_pick_in_round": 1,
                "draft_league": "NBA",
                "draft_selection_note": None,
                "nba_debut_date": "2003-10-29",
                "aba_debut_date": None,
                "experience_years": 21,
                "career_length_years": 21,
                "hall_of_fame_flag": 0,
                "hall_of_fame_role": None,
                "hall_of_fame_year": None,
                "hall_of_fame_raw": None,
                "headshot_url": "https://example.com/lebron.png",
            },
        ]
    )


def sample_team_histories_table() -> pa.Table:
    return _table(
        [
            {"teamId": "1610612744", "teamCity": "Golden State", "teamName": "Warriors", "teamAbbrev": "GSW"},
            {"teamId": "1610612747", "teamCity": "Los Angeles", "teamName": "Lakers", "teamAbbrev": "LAL"},
        ]
    )


def test_build_game_rows_preserves_expected_business_grain() -> None:
    rows = build_game_rows_from_tables(
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
    )
    assert len(rows) == 1
    assert rows[0]["game_id"] == "0022400001"
    assert rows[0]["arena_id"] == 1
    assert "arena_name" not in rows[0]
    assert "game_sk" not in rows[0]


def test_build_game_rows_excludes_malformed_non_semantic_games() -> None:
    rows = build_game_rows_from_tables(
        _table(
            sample_boxscore_game_table().to_pylist()
            + [
                {
                    "gameId": "12200069",
                    "gameCode": None,
                    "gameTimeUTC": "0001-01-01T00:00:00Z",
                    "gameTimeLocal": "0001-01-01T00:00:00Z",
                    "gameTimeHome": "0001-01-01T00:00:00Z",
                    "gameTimeAway": "0001-01-01T00:00:00Z",
                    "gameEt": "0001-01-01T00:00:00Z",
                    "gameStatus": 0,
                    "regulationPeriods": 0,
                    "period": 0,
                }
            ]
        ),
        sample_schedule_table(),
        sample_team_game_table(),
    )
    assert {row["game_id"] for row in rows} == {"0022400001"}


def test_build_arena_rows_extracts_reusable_venue_object() -> None:
    rows = build_arena_rows_from_tables(
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
    )
    assert rows == [
        {
            "arena_id": 1,
            "arena_name": "Chase Center",
            "arena_city": "San Francisco",
            "arena_state": "CA",
            "arena_country": "USA",
            "arena_timezone": "America/Los_Angeles",
        }
    ]


def test_build_arena_rows_normalize_selected_city_labels() -> None:
    box_rows = []
    city_cases = [
        ("0022400101", 11, "New York", "NY", "USA"),
        ("0022400102", 12, "Mexico City, Mexico", "MX", "MEX"),
        ("0022400103", 13, "San Juan,Puerto Rico", "PR", "USA"),
        ("0022400104", 14, "Macao, China", None, "CHN"),
    ]
    for game_id, arena_id, arena_city, arena_state, arena_country in city_cases:
        row = sample_boxscore_game_table().to_pylist()[0].copy()
        row["gameId"] = game_id
        row["arenaId"] = arena_id
        row["arenaCity"] = arena_city
        row["arenaState"] = arena_state
        row["arenaCountry"] = arena_country
        box_rows.append(row)

    schedule_rows = []
    team_rows = []
    for game_id, _, arena_city, arena_state, _ in city_cases:
        schedule_row = sample_schedule_table().to_pylist()[0].copy()
        schedule_row["gameId"] = game_id
        schedule_row["arenaCity"] = arena_city
        schedule_row["arenaState"] = arena_state
        schedule_rows.append(schedule_row)

        for side, team_id in (("home", 1610612744), ("away", 1610612747)):
            team_row = sample_team_game_table().to_pylist()[0 if side == "home" else 1].copy()
            team_row["gameId"] = game_id
            team_row["team_side"] = side
            team_row["teamId"] = team_id
            team_rows.append(team_row)

    rows = build_arena_rows_from_tables(
        _table(box_rows),
        _table(schedule_rows),
        _table(team_rows),
    )
    by_arena = {row["arena_id"]: row for row in rows}

    assert by_arena[11]["arena_city"] == "New York City"
    assert by_arena[12]["arena_city"] == "Mexico City"
    assert by_arena[13]["arena_city"] == "San Juan"
    assert by_arena[14]["arena_city"] == "Macau"


def test_build_player_rows_combines_core_and_enrichment() -> None:
    rows = build_player_rows_from_tables(
        sample_player_game_table(),
        sample_boxscore_game_table(),
        sample_player_bio_table(),
        sample_bridge_table(),
        sample_bbr_profile_table(),
    )
    by_person = {row["person_id"]: row for row in rows}
    assert by_person[201939]["full_name"] == "Stephen Curry"
    assert by_person[201939]["last_name"] == "Curry"
    assert by_person[2544]["position_group"] == "forward"
    assert "first_season_played" not in by_person[201939]
    assert "last_season_played" not in by_person[201939]
    assert "latest_status" not in by_person[201939]
    assert "first_seen_game_date" not in by_person[201939]
    assert "last_seen_game_date" not in by_person[201939]
    assert "basketball_reference_player_id" not in by_person[201939]
    assert "player_sk" not in by_person[201939]


def test_build_team_rows_returns_current_team_objects() -> None:
    rows = build_team_rows_from_tables(
        sample_schedule_table(),
        sample_team_game_table(),
        sample_team_histories_table(),
        sample_boxscore_game_table(),
    )
    by_team = {row["team_id"]: row for row in rows}
    assert by_team[1610612744]["team_abbreviation"] == "GSW"
    assert by_team[1610612744]["team_city"] == "San Francisco"
    assert by_team[1610612744]["team_state"] == "California"
    assert by_team[1610612744]["team_country"] == "United States"
    assert by_team[1610612754]["team_city"] == "Indianapolis"
    assert by_team[1610612746]["team_city"] == "Los Angeles"
    assert by_team[1610612750]["team_city"] == "Minneapolis"
    assert by_team[1610612752]["team_city"] == "New York City"
    assert by_team[1610612752]["team_state"] == "New York"
    assert by_team[1610612761]["team_state"] == "Ontario"
    assert by_team[1610612761]["team_country"] == "Canada"
    assert by_team[1610612764]["team_state"] == "District of Columbia"
    assert by_team[1610612762]["team_city"] == "Salt Lake City"
    assert by_team[1610612747]["conference"] == "west"


def test_build_player_rows_null_non_semantic_latest_team() -> None:
    rows = build_player_rows_from_tables(
        _table(
            [
                {
                    "gameId": "0022400001",
                    "teamId": 50013,
                    "personId": 999999,
                    "name": "Future Prospect",
                    "firstName": "Future",
                    "familyName": "Prospect",
                    "position": "G",
                    "status": "Active",
                }
            ]
        ),
        sample_boxscore_game_table(),
        _table([{"personId": 999999, "firstName": "Future", "lastName": "Prospect"}]),
        _table([]),
        _table([]),
    )
    assert rows[0]["latest_team_id"] is None


def test_build_player_game_rows_preserve_expected_grain() -> None:
    rows = build_player_game_rows_from_tables(
        sample_player_game_table(),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
        sample_player_game_possession_context_table(),
        sample_player_game_opportunity_context_table(),
        None,
        sample_player_game_defensive_shot_context_table(),
    )
    keys = {(row["game_id"], row["person_id"]) for row in rows}
    by_person = {row["person_id"]: row for row in rows}
    assert len(rows) == len(keys) == 2
    assert rows[0]["season_type"] == "regular_season"
    assert "blocks" in rows[0]
    assert "opponent_blocks" in rows[0]
    assert by_person[201939]["opponent_team_id"] == 1610612747
    assert by_person[201939]["win_loss_result"] == "win"
    assert by_person[2544]["opponent_team_id"] == 1610612744
    assert by_person[2544]["win_loss_result"] == "loss"
    assert rows[0]["is_starter"] is True
    assert "game_start_time_utc" in rows[0]
    assert "minutes_played" in rows[0]
    assert "offensive_possessions" in rows[0]
    assert "defensive_possessions" in rows[0]
    assert "possessions" in rows[0]
    assert "pace" in rows[0]
    assert by_person[201939]["offensive_possessions"] == pytest.approx(74.0)
    assert by_person[201939]["defensive_possessions"] == pytest.approx(72.0)
    assert by_person[201939]["possessions"] == pytest.approx(73.0)
    assert by_person[201939]["pace"] == pytest.approx(96.8)
    assert by_person[201939]["assist_percentage"] == pytest.approx(25.0)
    assert by_person[201939]["usage_percentage"] == pytest.approx(32.4)
    assert by_person[201939]["assist_to_turnover_ratio"] == pytest.approx(2.33)
    assert by_person[201939]["three_point_attempt_rate"] == pytest.approx(0.55, abs=0.001)
    assert by_person[201939]["free_throw_attempt_rate"] == pytest.approx(0.25, abs=0.001)
    assert by_person[201939]["effective_field_goal_percentage"] == pytest.approx(75.0, abs=0.001)
    assert by_person[201939]["true_shooting_percentage"] == pytest.approx(74.3)
    assert by_person[201939]["offensive_rating"] == pytest.approx(121.6)
    assert by_person[201939]["defensive_rating"] == pytest.approx(113.9)
    assert by_person[201939]["net_rating"] == pytest.approx(7.7)
    assert by_person[201939]["offensive_rebound_percentage"] == pytest.approx(11.1)
    assert by_person[201939]["defensive_rebound_percentage"] == pytest.approx(16.7)
    assert by_person[201939]["rebound_percentage"] == pytest.approx(15.2)
    assert by_person[201939]["steal_percentage"] == pytest.approx(2.8)
    assert by_person[201939]["block_percentage"] == pytest.approx(2.5)
    assert by_person[2544]["assist_percentage"] == pytest.approx(29.0)
    assert by_person[2544]["pace"] == pytest.approx(103.1)
    assert by_person[2544]["usage_percentage"] == pytest.approx(31.0)
    assert by_person[2544]["assist_to_turnover_ratio"] == pytest.approx(2.25)
    assert by_person[2544]["three_point_attempt_rate"] == pytest.approx(0.278, abs=0.001)
    assert by_person[2544]["free_throw_attempt_rate"] == pytest.approx(0.444, abs=0.001)
    assert by_person[2544]["effective_field_goal_percentage"] == pytest.approx(66.7)
    assert by_person[2544]["true_shooting_percentage"] == pytest.approx(69.7)
    assert by_person[2544]["offensive_rating"] == pytest.approx(118.3)
    assert by_person[2544]["defensive_rating"] == pytest.approx(118.7)
    assert by_person[2544]["net_rating"] == pytest.approx(-0.4)
    assert by_person[2544]["offensive_rebound_percentage"] == pytest.approx(10.0)
    assert by_person[2544]["defensive_rebound_percentage"] == pytest.approx(31.8)
    assert by_person[2544]["rebound_percentage"] == pytest.approx(25.0)
    assert by_person[2544]["steal_percentage"] == pytest.approx(1.3)
    assert by_person[2544]["block_percentage"] == pytest.approx(2.3)
    assert "fast_break_points" in rows[0]
    assert "points_in_paint" in rows[0]
    assert "second_chance_points" in rows[0]
    assert "game_datetime_utc" not in rows[0]
    assert "team_home_or_away" in rows[0]
    assert "team_side" not in rows[0]
    assert "minutes_played_decimal" not in rows[0]
    assert "is_on_court" not in rows[0]
    assert "seconds_played_total" not in rows[0]


def test_build_player_game_rows_fallback_usage_percentage_to_boxscore_proxy() -> None:
    possession_rows = sample_player_game_possession_context_table().to_pylist()
    possession_rows[0]["used_offensive_possessions"] = 0.0
    rows = build_player_game_rows_from_tables(
        sample_player_game_table(),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
        _table(possession_rows),
        sample_player_game_opportunity_context_table(),
        None,
        sample_player_game_defensive_shot_context_table(),
    )
    by_person = {row["person_id"]: row for row in rows}
    assert by_person[201939]["usage_percentage"] == pytest.approx(30.2)
    assert by_person[2544]["usage_percentage"] == pytest.approx(31.0)


def test_build_player_game_rows_drop_non_semantic_team_links() -> None:
    rows = build_player_game_rows_from_tables(
        _table(sample_player_game_table().to_pylist() + [{"gameId": "0022400001", "teamId": 50013, "personId": 42}]),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
        sample_player_game_possession_context_table(),
        sample_player_game_opportunity_context_table(),
        None,
        sample_player_game_defensive_shot_context_table(),
    )
    assert {(row["game_id"], row["person_id"]) for row in rows} == {
        ("0022400001", 201939),
        ("0022400001", 2544),
    }


def test_build_player_game_rows_filter_non_playing_rows() -> None:
    rows = build_player_game_rows_from_tables(
        _table(
            sample_player_game_table().to_pylist()
            + [
                {
                    "gameId": "0022400001",
                    "teamId": 1610612744,
                    "team_side": "home",
                    "personId": 999999,
                    "name": "Bench DNP",
                    "status": "Active",
                    "starter": 0,
                    "played": 0,
                    "minutes": "PT0M",
                    "minutesCalculated": "PT0M",
                    "points": 0,
                }
            ]
        ),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
        sample_player_game_possession_context_table(),
        sample_player_game_opportunity_context_table(),
        None,
        sample_player_game_defensive_shot_context_table(),
    )

    assert {(row["game_id"], row["person_id"]) for row in rows} == {
        ("0022400001", 201939),
        ("0022400001", 2544),
    }


def test_build_team_game_rows_resolve_opponent_links() -> None:
    rows = build_team_game_rows_from_tables(
        sample_team_game_table(),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_possession_context_table(),
        sample_team_game_defensive_shot_context_table(),
    )
    by_key = {(row["game_id"], row["team_id"]): row for row in rows}
    home_row = by_key[("0022400001", 1610612744)]
    away_row = by_key[("0022400001", 1610612747)]
    assert home_row["opponent_team_id"] == 1610612747
    assert away_row["opponent_team_id"] == 1610612744
    assert home_row["blocks"] == 5
    assert home_row["opponent_blocks"] == 4
    assert home_row["point_differential"] == 5
    assert home_row["win_loss_result"] == "win"
    assert away_row["win_loss_result"] == "loss"
    assert home_row["possessions"] == pytest.approx(99.0)
    assert home_row["offensive_possessions"] == pytest.approx(100.0)
    assert home_row["defensive_possessions"] == pytest.approx(98.0)
    assert home_row["pace"] == pytest.approx(99.0)
    assert home_row["offensive_rating"] == pytest.approx(121.2)
    assert home_row["defensive_rating"] == pytest.approx(116.2)
    assert home_row["net_rating"] == pytest.approx(5.1)
    assert home_row["assist_percentage"] == pytest.approx(68.2)
    assert home_row["assist_to_turnover_ratio"] == pytest.approx(2.5)
    assert home_row["effective_field_goal_percentage"] == pytest.approx(57.8)
    assert home_row["three_point_attempt_rate"] == pytest.approx(0.422, abs=0.001)
    assert home_row["free_throw_attempt_rate"] == pytest.approx(0.222, abs=0.001)
    assert home_row["true_shooting_percentage"] == pytest.approx(60.7)
    assert home_row["offensive_rebound_percentage"] == pytest.approx(24.4)
    assert home_row["defensive_rebound_percentage"] == pytest.approx(78.6)
    assert home_row["rebound_percentage"] == pytest.approx(51.8)
    assert home_row["steal_percentage"] == pytest.approx(9.2)
    assert home_row["block_percentage"] == pytest.approx(9.4)
    assert away_row["possessions"] == pytest.approx(99.0)
    assert away_row["offensive_possessions"] == pytest.approx(98.0)
    assert away_row["defensive_possessions"] == pytest.approx(100.0)
    assert away_row["pace"] == pytest.approx(99.0)
    assert away_row["assist_percentage"] == pytest.approx(66.7)
    assert away_row["assist_to_turnover_ratio"] == pytest.approx(2.15)
    assert away_row["three_point_attempt_rate"] == pytest.approx(0.398, abs=0.001)
    assert away_row["free_throw_attempt_rate"] == pytest.approx(0.25, abs=0.001)
    assert away_row["offensive_rebound_percentage"] == pytest.approx(21.4)
    assert away_row["defensive_rebound_percentage"] == pytest.approx(75.6)
    assert away_row["rebound_percentage"] == pytest.approx(48.2)
    assert away_row["steal_percentage"] == pytest.approx(7.0, abs=0.001)
    assert away_row["block_percentage"] == pytest.approx(7.7)
    assert home_row["opponent_field_goals_attempted"] == 88
    assert home_row["opponent_field_goals_made"] == 42
    assert home_row["opponent_field_goals_percentage"] == 47.7
    assert home_row["opponent_offensive_fouls_committed"] == 3
    assert home_row["opponent_technical_fouls_committed"] == 0
    assert home_row["opponent_three_pointers_attempted"] == 35
    assert home_row["opponent_three_pointers_made"] == 12
    assert home_row["opponent_three_pointers_percentage"] == 34.3
    assert home_row["opponent_free_throws_attempted"] == 22
    assert home_row["opponent_free_throws_made"] == 19
    assert home_row["opponent_free_throws_percentage"] == 86.4
    assert home_row["opponent_offensive_rebounds"] == 9
    assert home_row["opponent_defensive_rebounds"] == 31
    assert home_row["opponent_total_rebounds"] == 40
    assert home_row["opponent_two_pointers_attempted"] == 53
    assert home_row["opponent_two_pointers_made"] == 30
    assert home_row["opponent_two_pointers_percentage"] == 56.6
    assert home_row["opponent_assists"] == 28
    assert home_row["opponent_turnovers"] == 13
    assert home_row["opponent_steals"] == 7
    assert home_row["opponent_personal_fouls_committed"] == 18
    assert home_row["opponent_fouls_drawn"] == 19
    assert away_row["opponent_field_goals_attempted"] == 90
    assert away_row["opponent_field_goals_made"] == 44
    assert away_row["opponent_field_goals_percentage"] == 48.9
    assert away_row["opponent_offensive_fouls_committed"] == 2
    assert away_row["opponent_technical_fouls_committed"] == 0
    assert away_row["opponent_three_pointers_attempted"] == 38
    assert away_row["opponent_three_pointers_made"] == 16
    assert away_row["opponent_three_pointers_percentage"] == 42.1
    assert away_row["opponent_free_throws_attempted"] == 20
    assert away_row["opponent_free_throws_made"] == 16
    assert away_row["opponent_free_throws_percentage"] == 80.0
    assert away_row["opponent_offensive_rebounds"] == 10
    assert away_row["opponent_defensive_rebounds"] == 33
    assert away_row["opponent_total_rebounds"] == 43
    assert away_row["opponent_two_pointers_attempted"] == 52
    assert away_row["opponent_two_pointers_made"] == 28
    assert away_row["opponent_two_pointers_percentage"] == 53.8
    assert away_row["opponent_assists"] == 30
    assert away_row["opponent_turnovers"] == 12
    assert away_row["opponent_steals"] == 9
    assert away_row["opponent_personal_fouls_committed"] == 17
    assert away_row["opponent_fouls_drawn"] == 18
    assert "game_start_time_utc" in home_row
    assert "minutes_played" in home_row
    assert "fast_break_points" in home_row
    assert "points_in_paint" in home_row
    assert "second_chance_points" in home_row
    assert "game_datetime_utc" not in home_row
    assert "minutes_played_decimal" not in home_row
    assert "points_fast_break" not in home_row
    assert "points_in_the_paint" not in home_row
    assert "points_second_chance" not in home_row


def test_build_team_game_rows_drop_non_semantic_team_pairs() -> None:
    rows = build_team_game_rows_from_tables(
        _table(
            sample_team_game_table().to_pylist()
            + [
                {
                    "gameId": "0022400999",
                    "team_side": "home",
                    "teamId": 50013,
                    "teamName": "Exhibition",
                    "teamCity": "Nowhere",
                    "teamTricode": "EXH",
                    "score": 100,
                },
                {
                    "gameId": "0022400999",
                    "team_side": "away",
                    "teamId": 1610612747,
                    "teamName": "Lakers",
                    "teamCity": "Los Angeles",
                    "teamTricode": "LAL",
                    "score": 90,
                },
            ]
        ),
        _table(
            sample_boxscore_game_table().to_pylist()
            + [
                {
                    "gameId": "0022400999",
                    "gameCode": "20241023/EXHLAL",
                    "gameTimeUTC": "2024-10-24T02:00:00Z",
                    "gameStatus": 3,
                    "gameStatusText": "Final",
                }
            ]
        ),
        _table(
            sample_schedule_table().to_pylist()
            + [
                {
                    "gameId": "0022400999",
                    "gameDate": "2024-10-23",
                    "gameDateTimeUTC": "2024-10-24T02:00:00Z",
                    "homeTeamId": 50013,
                    "homeTeamName": "Exhibition",
                    "homeTeamCity": "Nowhere",
                    "homeTeamTricode": "EXH",
                    "homeTeamSlug": "exhibition",
                    "awayTeamId": 1610612747,
                    "awayTeamName": "Lakers",
                    "awayTeamCity": "Los Angeles",
                    "awayTeamTricode": "LAL",
                    "awayTeamSlug": "lakers",
                }
            ]
        ),
        sample_team_game_possession_context_table(),
    )
    assert {(row["game_id"], row["team_id"]) for row in rows} == {
        ("0022400001", 1610612744),
        ("0022400001", 1610612747),
    }


def test_build_player_season_rows_aggregate_one_row_per_player_season() -> None:
    rows = build_player_season_rows_from_tables(
        sample_player_game_table(),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
        sample_player_bio_table(),
        None,
        None,
        sample_player_game_possession_context_table(),
        sample_player_game_defensive_shot_context_table(),
        sample_player_game_opportunity_context_table(),
    )

    by_key = {(row["person_id"], row["season_year"], row["season_type"]): row for row in rows}
    assert set(by_key) == {
        (2544, "2024-25", "regular_season"),
        (201939, "2024-25", "regular_season"),
    }
    curry = by_key[(201939, "2024-25", "regular_season")]
    assert curry["age_on_jan_31"] == 36
    assert curry["games_played"] == 1
    assert curry["games_started"] == 1
    assert curry["minutes_total"] == 36.2
    assert curry["minutes_per_game"] == 36.2
    assert curry["points_total"] == 33
    assert curry["points_per_game"] == 33.0
    assert curry["assists_total"] == 7
    assert curry["assists_per_game"] == 7.0
    assert curry["rebounds_total"] == 5
    assert curry["rebounds_per_game"] == 5.0
    assert curry["offensive_rebounds_total"] == 1
    assert curry["defensive_rebounds_total"] == 4
    assert curry["offensive_rebounds_per_game"] == 1.0
    assert curry["defensive_rebounds_per_game"] == 4.0
    assert curry["field_goals_made_total"] == 12
    assert curry["field_goals_made_per_game"] == 12.0
    assert curry["field_goals_attempted_total"] == 20
    assert curry["field_goals_attempted_per_game"] == 20.0
    assert curry["field_goals_percentage"] == 60.0
    assert curry["three_pointers_made_total"] == 6
    assert curry["three_pointers_made_per_game"] == 6.0
    assert curry["three_pointers_attempted_total"] == 11
    assert curry["three_pointers_attempted_per_game"] == 11.0
    assert curry["three_pointers_percentage"] == 54.5
    assert curry["two_pointers_made_total"] == 6
    assert curry["two_pointers_made_per_game"] == 6.0
    assert curry["two_pointers_attempted_total"] == 9
    assert curry["two_pointers_attempted_per_game"] == 9.0
    assert curry["two_pointers_percentage"] == 66.7
    assert curry["free_throws_made_total"] == 5
    assert curry["free_throws_made_per_game"] == 5.0
    assert curry["free_throws_attempted_total"] == 5
    assert curry["free_throws_attempted_per_game"] == 5.0
    assert curry["free_throws_percentage"] == 100.0
    assert curry["opponent_blocks_total"] == 0
    assert curry["offensive_fouls_committed_total"] == 0
    assert curry["fouls_drawn_total"] == 4
    assert curry["personal_fouls_committed_total"] == 2
    assert curry["personal_fouls_committed_per_game"] == 2.0
    assert curry["technical_fouls_committed_total"] == 0
    assert curry["fast_break_points_total"] == 2
    assert curry["points_in_paint_total"] == 6
    assert curry["second_chance_points_total"] == 0
    assert curry["steals_total"] == 2
    assert curry["steals_per_game"] == 2.0
    assert curry["blocks_total"] == 1
    assert curry["blocks_per_game"] == 1.0
    assert curry["turnovers_total"] == 3
    assert curry["turnovers_per_game"] == 3.0
    assert curry["plus_minus_total"] == 8
    assert curry["assist_to_turnover_ratio"] == pytest.approx(2.33)
    assert curry["assist_percentage"] == pytest.approx(25.0)
    assert curry["offensive_rebound_percentage"] == pytest.approx(11.1)
    assert curry["defensive_rebound_percentage"] == pytest.approx(16.7)
    assert curry["rebound_percentage"] == pytest.approx(15.2)
    assert curry["effective_field_goal_percentage"] == pytest.approx(75.0)
    assert curry["three_point_attempt_rate"] == pytest.approx(0.55)
    assert curry["free_throw_attempt_rate"] == pytest.approx(0.25)
    assert curry["true_shooting_percentage"] == pytest.approx(74.3)
    assert curry["usage_percentage"] == pytest.approx(32.4)
    assert curry["offensive_possessions_total"] == pytest.approx(74.0)
    assert curry["defensive_possessions_total"] == pytest.approx(72.0)
    assert curry["possessions"] == pytest.approx(73.0)
    assert curry["offensive_rating"] == pytest.approx(121.6)
    assert curry["defensive_rating"] == pytest.approx(113.9)
    assert curry["net_rating"] == pytest.approx(7.7)
    assert curry["pace"] == pytest.approx(96.8)
    assert curry["steal_percentage"] == pytest.approx(2.8)
    assert curry["block_percentage"] == pytest.approx(2.5)
    assert curry["team_count"] == 1
    assert curry["is_multi_team_season"] is False


def test_build_player_season_rows_fallback_usage_percentage_to_boxscore_proxy() -> None:
    possession_rows = sample_player_game_possession_context_table().to_pylist()
    possession_rows[0]["used_offensive_possessions"] = 0.0
    rows = build_player_season_rows_from_tables(
        sample_player_game_table(),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
        sample_player_bio_table(),
        None,
        None,
        _table(possession_rows),
        sample_player_game_defensive_shot_context_table(),
        sample_player_game_opportunity_context_table(),
    )
    by_key = {(row["person_id"], row["season_year"], row["season_type"]): row for row in rows}
    assert by_key[(201939, "2024-25", "regular_season")]["usage_percentage"] == pytest.approx(30.2)
    assert by_key[(2544, "2024-25", "regular_season")]["usage_percentage"] == pytest.approx(31.0)


def test_build_player_season_team_rows_keep_team_stint_grain() -> None:
    rows = build_player_season_team_rows_from_tables(
        sample_player_game_table(),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
        sample_player_game_possession_context_table(),
        sample_player_game_defensive_shot_context_table(),
        sample_player_game_opportunity_context_table(),
        sample_boxscore_game_table(),
    )

    by_key = {
        (row["person_id"], row["team_id"], row["season_year"], row["season_type"]): row
        for row in rows
    }
    assert set(by_key) == {
        (2544, 1610612747, "2024-25", "regular_season"),
        (201939, 1610612744, "2024-25", "regular_season"),
    }
    lebron = by_key[(2544, 1610612747, "2024-25", "regular_season")]
    assert lebron["games_played"] == 1
    assert lebron["games_started"] == 1
    assert lebron["minutes_total"] == 34.0
    assert lebron["minutes_per_game"] == 34.0
    assert lebron["points_total"] == 30
    assert lebron["points_per_game"] == 30.0
    assert lebron["assists_total"] == 9
    assert lebron["assists_per_game"] == 9.0
    assert lebron["rebounds_total"] == 8
    assert lebron["rebounds_per_game"] == 8.0
    assert lebron["offensive_rebounds_total"] == 1
    assert lebron["offensive_rebounds_per_game"] == 1.0
    assert lebron["defensive_rebounds_total"] == 7
    assert lebron["defensive_rebounds_per_game"] == 7.0
    assert lebron["steals_total"] == 1
    assert lebron["steals_per_game"] == 1.0
    assert lebron["blocks_total"] == 1
    assert lebron["blocks_per_game"] == 1.0
    assert lebron["opponent_blocks_total"] == 1
    assert lebron["turnovers_total"] == 4
    assert lebron["turnovers_per_game"] == 4.0
    assert lebron["plus_minus_total"] == -4
    assert lebron["offensive_fouls_committed_total"] == 1
    assert lebron["personal_fouls_committed_total"] == 3
    assert lebron["personal_fouls_committed_per_game"] == 3.0
    assert lebron["technical_fouls_committed_total"] == 0
    assert lebron["fouls_drawn_total"] == 6
    assert lebron["fast_break_points_total"] == 4
    assert lebron["points_in_paint_total"] == 12
    assert lebron["second_chance_points_total"] == 2
    assert lebron["field_goals_made_total"] == 11
    assert lebron["field_goals_made_per_game"] == 11.0
    assert lebron["field_goals_attempted_total"] == 18
    assert lebron["field_goals_attempted_per_game"] == 18.0
    assert lebron["field_goals_percentage"] == pytest.approx(61.1)
    assert lebron["two_pointers_made_total"] == 9
    assert lebron["two_pointers_made_per_game"] == 9.0
    assert lebron["two_pointers_attempted_total"] == 13
    assert lebron["two_pointers_attempted_per_game"] == 13.0
    assert lebron["two_pointers_percentage"] == pytest.approx(69.2)
    assert lebron["three_pointers_made_total"] == 2
    assert lebron["three_pointers_made_per_game"] == 2.0
    assert lebron["three_pointers_attempted_total"] == 5
    assert lebron["three_pointers_attempted_per_game"] == 5.0
    assert lebron["three_pointers_percentage"] == 40.0
    assert lebron["free_throws_made_total"] == 6
    assert lebron["free_throws_made_per_game"] == 6.0
    assert lebron["free_throws_attempted_total"] == 8
    assert lebron["free_throws_attempted_per_game"] == 8.0
    assert lebron["free_throws_percentage"] == 75.0
    assert lebron["offensive_possessions_total"] == 71.0
    assert lebron["defensive_possessions_total"] == 75.0
    assert lebron["possessions"] == 73.0
    assert lebron["pace"] == pytest.approx(103.1)
    assert lebron["offensive_rating"] == pytest.approx(118.3)
    assert lebron["defensive_rating"] == pytest.approx(118.7)
    assert lebron["net_rating"] == pytest.approx(-0.4)
    assert lebron["assist_to_turnover_ratio"] == pytest.approx(2.25)
    assert lebron["assist_percentage"] == pytest.approx(29.0)
    assert lebron["usage_percentage"] == pytest.approx(31.0)
    assert lebron["offensive_rebound_percentage"] == pytest.approx(10.0)
    assert lebron["defensive_rebound_percentage"] == pytest.approx(31.8)
    assert lebron["rebound_percentage"] == pytest.approx(25.0)
    assert lebron["steal_percentage"] == pytest.approx(1.3)
    assert lebron["block_percentage"] == pytest.approx(2.3)
    assert lebron["effective_field_goal_percentage"] == pytest.approx(66.7)
    assert lebron["three_point_attempt_rate"] == pytest.approx(0.278)
    assert lebron["free_throw_attempt_rate"] == pytest.approx(0.444)
    assert lebron["true_shooting_percentage"] == pytest.approx(69.7)


def test_build_team_season_rows_aggregate_team_results() -> None:
    rows = build_team_season_rows_from_tables(
        sample_team_game_table(),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_possession_context_table(),
        sample_team_game_defensive_shot_context_table(),
    )

    by_key = {(row["team_id"], row["season_year"], row["season_type"]): row for row in rows}
    warriors = by_key[(1610612744, "2024-25", "regular_season")]
    lakers = by_key[(1610612747, "2024-25", "regular_season")]

    assert warriors["games_played"] == 1
    assert warriors["wins"] == 1
    assert warriors["losses"] == 0
    assert warriors["win_percentage"] == 1.0
    assert warriors["minutes"] == 48
    assert warriors["minutes_per_game"] == 48.0
    assert warriors["points_total"] == 120
    assert warriors["points_per_game"] == 120.0
    assert warriors["assists_total"] == 30
    assert warriors["assists_per_game"] == 30.0
    assert warriors["turnovers_total"] == 12
    assert warriors["turnovers_per_game"] == 12.0
    assert warriors["steals_total"] == 9
    assert warriors["steals_per_game"] == 9.0
    assert warriors["blocks_total"] == 5
    assert warriors["blocks_per_game"] == 5.0
    assert warriors["rebounds_total"] == 43
    assert warriors["rebounds_per_game"] == 43.0
    assert warriors["offensive_rebounds_total"] == 10
    assert warriors["offensive_rebounds_per_game"] == 10.0
    assert warriors["defensive_rebounds_total"] == 33
    assert warriors["defensive_rebounds_per_game"] == 33.0
    assert warriors["field_goals_made_total"] == 44
    assert warriors["field_goals_made_per_game"] == 44.0
    assert warriors["field_goals_attempted_total"] == 90
    assert warriors["field_goals_attempted_per_game"] == 90.0
    assert warriors["field_goals_percentage"] == pytest.approx(48.9)
    assert warriors["three_pointers_made_total"] == 16
    assert warriors["three_pointers_made_per_game"] == 16.0
    assert warriors["three_pointers_attempted_total"] == 38
    assert warriors["three_pointers_attempted_per_game"] == 38.0
    assert warriors["three_pointers_percentage"] == pytest.approx(42.1)
    assert warriors["two_pointers_made_total"] == 28
    assert warriors["two_pointers_made_per_game"] == 28.0
    assert warriors["two_pointers_attempted_total"] == 52
    assert warriors["two_pointers_attempted_per_game"] == 52.0
    assert warriors["two_pointers_percentage"] == pytest.approx(53.8)
    assert warriors["free_throws_made_total"] == 16
    assert warriors["free_throws_made_per_game"] == 16.0
    assert warriors["free_throws_attempted_total"] == 20
    assert warriors["free_throws_attempted_per_game"] == 20.0
    assert warriors["free_throws_percentage"] == pytest.approx(80.0)
    assert warriors["offensive_fouls_committed_total"] == 2
    assert warriors["fouls_drawn_total"] == 18
    assert warriors["personal_fouls_committed_total"] == 17
    assert warriors["personal_fouls_committed_per_game"] == 17.0
    assert warriors["technical_fouls_committed_total"] == 0
    assert warriors["possessions"] == 99
    assert warriors["offensive_possessions"] == pytest.approx(100.0)
    assert warriors["defensive_possessions"] == pytest.approx(98.0)
    assert warriors["pace"] == pytest.approx(99.0)
    assert warriors["offensive_rating"] == pytest.approx(121.2)
    assert warriors["defensive_rating"] == pytest.approx(116.2)
    assert warriors["net_rating"] == pytest.approx(5.1)
    assert warriors["steal_percentage"] == pytest.approx(9.2)
    assert warriors["block_percentage"] == pytest.approx(9.4)
    assert warriors["assist_percentage"] == pytest.approx(68.2)
    assert warriors["assist_to_turnover_ratio"] == pytest.approx(2.5)
    assert warriors["offensive_rebound_percentage"] == pytest.approx(24.4)
    assert warriors["defensive_rebound_percentage"] == pytest.approx(78.6)
    assert warriors["rebound_percentage"] == pytest.approx(51.8)
    assert warriors["effective_field_goal_percentage"] == pytest.approx(57.8)
    assert warriors["three_point_attempt_rate"] == pytest.approx(0.422)
    assert warriors["free_throw_attempt_rate"] == pytest.approx(0.222)
    assert warriors["true_shooting_percentage"] == pytest.approx(60.7)

    assert lakers["wins"] == 0
    assert lakers["losses"] == 1
    assert lakers["offensive_possessions"] == pytest.approx(98.0)
    assert lakers["defensive_possessions"] == pytest.approx(100.0)
    assert lakers["win_percentage"] == 0.0
