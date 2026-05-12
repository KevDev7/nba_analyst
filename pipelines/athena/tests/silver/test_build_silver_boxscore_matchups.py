from __future__ import annotations

import sys
import io
import tarfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_boxscore_matchups as matchups_silver


def sample_payload() -> dict:
    return {
        "boxScoreMatchups": {
            "gameId": "22400001",
            "awayTeamId": 1610612737,
            "homeTeamId": 1610612738,
            "homeTeam": {
                "teamId": 1610612738,
                "teamName": "Celtics",
                "teamCity": "Boston",
                "teamTricode": "BOS",
                "teamSlug": "celtics",
                "players": [
                    {
                        "personId": 1627759,
                        "firstName": "Jaylen",
                        "familyName": "Brown",
                        "nameI": "J. Brown",
                        "playerSlug": "jaylen-brown",
                        "position": "F",
                        "comment": "",
                        "jerseyNum": "7",
                        "matchups": [
                            {
                                "personId": 203991,
                                "firstName": "Clint",
                                "familyName": "Capela",
                                "nameI": "C. Capela",
                                "playerSlug": "clint-capela",
                                "jerseyNum": "15",
                                "statistics": {
                                    "matchupMinutes": "0:34",
                                    "matchupMinutesSort": 34,
                                    "partialPossessions": 3.2,
                                    "percentageDefenderTotalTime": 0.083,
                                    "percentageOffensiveTotalTime": 0.011,
                                    "percentageTotalTimeBothOn": 0.012,
                                    "switchesOn": 0,
                                    "playerPoints": 0,
                                    "teamPoints": 2,
                                    "matchupAssists": 0,
                                    "matchupPotentialAssists": 0,
                                    "matchupTurnovers": 0,
                                    "matchupBlocks": 0,
                                    "matchupFieldGoalsMade": 0,
                                    "matchupFieldGoalsAttempted": 1,
                                    "matchupFieldGoalsPercentage": 0,
                                    "matchupThreePointersMade": 0,
                                    "matchupThreePointersAttempted": 0,
                                    "matchupThreePointersPercentage": 0,
                                    "helpBlocks": 0,
                                    "helpFieldGoalsMade": 0,
                                    "helpFieldGoalsAttempted": 0,
                                    "helpFieldGoalsPercentage": 0,
                                    "matchupFreeThrowsMade": 0,
                                    "matchupFreeThrowsAttempted": 0,
                                    "shootingFouls": 0,
                                },
                            }
                        ],
                    }
                ],
            },
            "awayTeam": {
                "teamId": 1610612737,
                "teamName": "Hawks",
                "teamCity": "Atlanta",
                "teamTricode": "ATL",
                "teamSlug": "hawks",
                "players": [],
            },
        }
    }


def test_build_rows_from_payload_flattens_matchups_and_normalizes_game_id():
    rows = matchups_silver.build_rows_from_payload(sample_payload())

    assert len(rows) == 1
    row = rows[0]
    assert row["game_id"] == "0022400001"
    assert row["team_side"] == "home"
    assert row["team_id"] == 1610612738
    assert row["person_id"] == 1627759
    assert row["matchups_person_id"] == 203991
    assert row["matchup_minutes"] == "0:34"
    assert row["matchup_minutes_sort"] == 34.0
    assert row["partial_possessions"] == 3.2
    assert row["matchup_field_goals_attempted"] == 1


def test_validate_and_dedupe_rows_enforces_grain_by_quality():
    rows = matchups_silver.build_rows_from_payload(sample_payload())
    duplicate = deepcopy(rows[0])
    duplicate["partial_possessions"] = None
    rows.append(duplicate)

    output, quarantine_rows, metrics = matchups_silver.validate_and_dedupe_rows(
        rows,
        detected_at_utc=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    assert len(output) == 1
    assert output[0]["partial_possessions"] == 3.2
    assert quarantine_rows == []
    assert metrics["warning_reason_counts"] == {"duplicate_matchup_grain": 1}


def test_validate_and_dedupe_rows_quarantines_missing_grain_columns():
    rows = matchups_silver.build_rows_from_payload(sample_payload())
    rows[0]["matchups_person_id"] = None

    output, quarantine_rows, metrics = matchups_silver.validate_and_dedupe_rows(
        rows,
        detected_at_utc=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    assert output == []
    assert len(quarantine_rows) == 1
    assert metrics["error_reason_counts"] == {"missing_required_grain_column": 1}


def test_build_rows_from_archive_reads_source_csv_shape():
    csv_bytes = (
        "game_id,away_team_id,home_team_id,team_side,team_id,team_name,team_city,team_tricode,team_slug,"
        "person_id,first_name,family_name,name_i,player_slug,position,comment,jersey_num,"
        "matchups_person_id,matchups_first_name,matchups_family_name,matchups_name_i,matchups_player_slug,"
        "matchups_jersey_num,matchup_minutes,matchup_minutes_sort,partial_possessions,"
        "percentage_defender_total_time,percentage_offensive_total_time,percentage_total_time_both_on,"
        "switches_on,player_points,team_points,matchup_assists,matchup_potential_assists,matchup_turnovers,"
        "matchup_blocks,matchup_field_goals_made,matchup_field_goals_attempted,matchup_field_goals_percentage,"
        "matchup_three_pointers_made,matchup_three_pointers_attempted,matchup_three_pointers_percentage,"
        "help_blocks,help_field_goals_made,help_field_goals_attempted,help_field_goals_percentage,"
        "matchup_free_throws_made,matchup_free_throws_attempted,shooting_fouls\n"
        "22400001,1610612737,1610612738,home,1610612738,Celtics,Boston,BOS,celtics,"
        "1627759,Jaylen,Brown,J. Brown,jaylen-brown,F,,7,"
        "203991,Clint,Capela,C. Capela,clint-capela,15,0:34,34,3.2,"
        "0.083,0.011,0.012,0,0,2,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0\n"
    ).encode("utf-8")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
        info = tarfile.TarInfo("matchups_2024.csv")
        info.size = len(csv_bytes)
        archive.addfile(info, io.BytesIO(csv_bytes))

    rows = matchups_silver.build_rows_from_archive(buffer.getvalue())

    assert len(rows) == 1
    assert rows[0]["game_id"] == "0022400001"
    assert rows[0]["matchups_person_id"] == 203991
    assert rows[0]["partial_possessions"] == 3.2
