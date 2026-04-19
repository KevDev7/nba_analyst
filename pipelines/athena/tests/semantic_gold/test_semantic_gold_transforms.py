from __future__ import annotations

import pyarrow as pa

from pipelines.athena.transform.semantic_gold.transform_to_arena_parquet import build_arena_rows_from_tables
from pipelines.athena.transform.semantic_gold.transform_to_game_parquet import build_game_rows_from_tables
from pipelines.athena.transform.semantic_gold.transform_to_player_game_parquet import build_player_game_rows_from_tables
from pipelines.athena.transform.semantic_gold.transform_to_player_parquet import build_player_rows_from_tables
from pipelines.athena.transform.semantic_gold.transform_to_player_season_parquet import (
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
                "pointsInThePaint": 42,
                "pointsSecondChance": 11,
                "minutesCalculated": "PT240M",
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


def test_build_player_rows_combines_core_and_enrichment() -> None:
    rows = build_player_rows_from_tables(
        sample_player_game_table(),
        sample_boxscore_game_table(),
        sample_player_bio_table(),
        sample_bridge_table(),
        sample_bbr_profile_table(),
    )
    by_person = {row["person_id"]: row for row in rows}
    assert by_person[201939]["display_name"] == "Stephen Curry"
    assert by_person[201939]["basketball_reference_player_id"] == "curryst01"
    assert by_person[2544]["position_group"] == "forward"
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
    )
    keys = {(row["game_id"], row["person_id"]) for row in rows}
    assert len(rows) == len(keys) == 2
    assert rows[0]["season_type"] == "regular_season"


def test_build_player_game_rows_drop_non_semantic_team_links() -> None:
    rows = build_player_game_rows_from_tables(
        _table(sample_player_game_table().to_pylist() + [{"gameId": "0022400001", "teamId": 50013, "personId": 42}]),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
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
    )
    by_key = {(row["game_id"], row["team_id"]): row for row in rows}
    home_row = by_key[("0022400001", 1610612744)]
    away_row = by_key[("0022400001", 1610612747)]
    assert home_row["opponent_team_id"] == 1610612747
    assert away_row["opponent_team_id"] == 1610612744
    assert home_row["point_diff"] == 5
    assert away_row["is_loss"] == 1


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
    )

    by_key = {(row["person_id"], row["season_year"], row["season_type"]): row for row in rows}
    assert set(by_key) == {
        (2544, "2024-25", "regular_season"),
        (201939, "2024-25", "regular_season"),
    }
    curry = by_key[(201939, "2024-25", "regular_season")]
    assert curry["player_name"] == "Stephen Curry"
    assert curry["games_played"] == 1
    assert curry["total_points"] == 33
    assert curry["average_points"] == 33.0
    assert curry["team_count"] == 1
    assert curry["is_multi_team_season"] == 0


def test_build_player_season_team_rows_keep_team_stint_grain() -> None:
    rows = build_player_season_team_rows_from_tables(
        sample_player_game_table(),
        sample_boxscore_game_table(),
        sample_schedule_table(),
        sample_team_game_table(),
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
    assert lebron["player_name"] == "LeBron James"
    assert lebron["games_played"] == 1
    assert lebron["total_points"] == 30
    assert lebron["average_points"] == 30.0


def test_build_team_season_rows_aggregate_team_results() -> None:
    rows = build_team_season_rows_from_tables(
        sample_team_game_table(),
        sample_boxscore_game_table(),
        sample_schedule_table(),
    )

    by_key = {(row["team_id"], row["season_year"], row["season_type"]): row for row in rows}
    warriors = by_key[(1610612744, "2024-25", "regular_season")]
    lakers = by_key[(1610612747, "2024-25", "regular_season")]

    assert warriors["games_played"] == 1
    assert warriors["wins"] == 1
    assert warriors["losses"] == 0
    assert warriors["win_percentage"] == 1.0
    assert warriors["average_points"] == 120.0

    assert lakers["wins"] == 0
    assert lakers["losses"] == 1
    assert lakers["win_percentage"] == 0.0
    assert lakers["average_points"] == 115.0
