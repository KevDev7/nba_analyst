from __future__ import annotations

import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

SILVER_TRANSFORM_DIR = (
    Path(__file__).resolve().parents[2] / "transform" / "silver"
)
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_playbyplay_events as pbp_silver


class _CaptureS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = {"Body": Body, "ContentType": ContentType}


def test_target_schema_matches_phase1_contract_shape():
    assert "blockTotal" not in pbp_silver.TARGET_SCHEMA.names
    for column in (
        "_meta_pipeline_run_id",
        "_meta_ingested_at_utc",
        "_meta_source_system",
        "_meta_source_key",
        "_meta_source_last_modified_utc",
        "_meta_schema_version",
    ):
        assert column in pbp_silver.TARGET_SCHEMA.names


def test_build_rows_from_payload_normalizes_game_id_to_ten_digits():
    payload = {
        "game": {
            "gameId": "12000001",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 1,
                    "clock": "PT12M00.00S",
                    "actionType": "period",
                    "subType": "start",
                }
            ],
        }
    }

    rows, game_id = pbp_silver.build_rows_from_payload(payload, fallback_game_id=None)

    assert game_id == "0012000001"
    assert rows[0]["gameId"] == "0012000001"
    assert pbp_silver.destination_key_for_game(game_id) == "silver/playbyplay/game_id=0012000001.parquet"


def test_write_game_parquet_to_s3_persists_silver_metadata_columns():
    captured_s3 = _CaptureS3Client()
    ingested_at_utc = datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc)
    source_last_modified_utc = datetime(2026, 3, 27, 11, 30, tzinfo=timezone.utc)
    rows = pbp_silver.add_silver_metadata(
        [
            {
                "gameId": "0022400999",
                "actionNumber": 1,
                "actionType": "period",
            }
        ],
        pipeline_run_id="playbyplay_events_test",
        ingested_at_utc=ingested_at_utc,
        source_key="raw/cdn/playbyplay/game_id=0022400999.json",
        source_last_modified_utc=source_last_modified_utc,
    )

    pbp_silver.write_game_parquet_to_s3("0022400999", rows, captured_s3)

    payload = captured_s3.objects[
        (
            pbp_silver.S3_BUCKET,
            "silver/playbyplay/game_id=0022400999.parquet",
        )
    ]["Body"]
    table = pq.read_table(io.BytesIO(payload))
    row = table.to_pylist()[0]

    assert row["_meta_pipeline_run_id"] == "playbyplay_events_test"
    assert row["_meta_ingested_at_utc"] == ingested_at_utc
    assert row["_meta_source_system"] == pbp_silver.META_SOURCE_SYSTEM
    assert row["_meta_source_key"] == "raw/cdn/playbyplay/game_id=0022400999.json"
    assert row["_meta_source_last_modified_utc"] == source_last_modified_utc
    assert row["_meta_schema_version"] == pbp_silver.META_SCHEMA_VERSION


def test_write_game_parquet_to_s3_normalizes_destination_game_id():
    captured_s3 = _CaptureS3Client()
    rows = pbp_silver.add_silver_metadata(
        [
            {
                "gameId": "0012000001",
                "actionNumber": 1,
                "actionType": "period",
            }
        ],
        pipeline_run_id="playbyplay_events_test",
        ingested_at_utc=datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc),
        source_key="raw/cdn/playbyplay/game_id=0012000001.json",
        source_last_modified_utc=datetime(2026, 3, 27, 11, 30, tzinfo=timezone.utc),
    )

    pbp_silver.write_game_parquet_to_s3("12000001", rows, captured_s3)

    assert (
        pbp_silver.S3_BUCKET,
        "silver/playbyplay/game_id=0012000001.parquet",
    ) in captured_s3.objects


def test_parse_clock_to_seconds_remaining_handles_live_clock_formats():
    assert pbp_silver.parse_clock_to_seconds_remaining("PT12M00.00S") == 720.0
    assert pbp_silver.parse_clock_to_seconds_remaining("PT00M05.50S") == 5.5
    assert pbp_silver.parse_clock_to_seconds_remaining("11:23.5") == 683.5
    assert pbp_silver.parse_clock_to_seconds_remaining(None) is None


def test_build_rows_from_payload_adds_phase1_linkage_timing_and_flags():
    payload = {
        "game": {
            "gameId": "0022400001",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 1,
                    "clock": "PT12M00.00S",
                    "actionType": "jumpball",
                    "subType": "recovered",
                },
                {
                    "actionNumber": 2,
                    "orderNumber": 110,
                    "period": 1,
                    "clock": "PT11M45.50S",
                    "actionType": "2pt",
                    "isFieldGoal": 1,
                    "shotResult": "Made",
                },
                {
                    "actionNumber": 3,
                    "orderNumber": 120,
                    "period": 1,
                    "clock": "PT11M30.50S",
                    "actionType": "rebound",
                },
                {
                    "actionNumber": 4,
                    "orderNumber": 130,
                    "period": 1,
                    "clock": "PT11M30.50S",
                    "actionType": "foul",
                },
                {
                    "actionNumber": 5,
                    "orderNumber": 140,
                    "period": 1,
                    "clock": "PT11M30.50S",
                    "actionType": "freethrow",
                    "shotResult": "Made",
                },
                {
                    "actionNumber": 6,
                    "orderNumber": 150,
                    "period": 1,
                    "clock": "PT11M10.50S",
                    "actionType": "turnover",
                },
                {
                    "actionNumber": 7,
                    "orderNumber": 160,
                    "period": 1,
                    "clock": "PT11M00.50S",
                    "actionType": "timeout",
                },
                {
                    "actionNumber": 8,
                    "orderNumber": 170,
                    "period": 1,
                    "clock": "PT10M45.50S",
                    "actionType": "substitution",
                    "subType": "out",
                },
                {
                    "actionNumber": 9,
                    "orderNumber": 180,
                    "period": 1,
                    "clock": "PT10M30.50S",
                    "actionType": "3pt",
                    "isFieldGoal": 1,
                    "shotResult": "Missed",
                },
                {
                    "actionNumber": 10,
                    "orderNumber": 200,
                    "period": 2,
                    "clock": "PT12M00.00S",
                    "actionType": "period",
                    "subType": "start",
                },
                {
                    "actionNumber": 11,
                    "orderNumber": 210,
                    "period": 2,
                    "clock": "PT12M00.00S",
                    "actionType": "2pt",
                    "isFieldGoal": 1,
                    "shotResult": "Missed",
                },
            ],
        }
    }

    rows, game_id = pbp_silver.build_rows_from_payload(payload, fallback_game_id=None)

    assert game_id == "0022400001"
    assert [row["actionNumber"] for row in rows] == list(range(1, 12))

    first_row = rows[0]
    assert first_row["prevActionNumber"] is None
    assert first_row["nextActionNumber"] == 2
    assert first_row["prevOrderNumber"] is None
    assert first_row["nextOrderNumber"] == 110
    assert first_row["secondsRemainingInPeriod"] == 720.0
    assert first_row["secondsSincePreviousEvent"] == 0.0
    assert first_row["isJumpBall"] is True

    made_shot_row = rows[1]
    assert made_shot_row["prevActionNumber"] == 1
    assert made_shot_row["nextActionNumber"] == 3
    assert made_shot_row["secondsRemainingInPeriod"] == 705.5
    assert made_shot_row["secondsSincePreviousEvent"] == 14.5
    assert made_shot_row["isMadeShot"] is True
    assert made_shot_row["isMissedShot"] is False

    free_throw_row = rows[4]
    assert free_throw_row["isFreeThrow"] is True
    assert free_throw_row["isMadeShot"] is False
    assert free_throw_row["isMissedShot"] is False

    rebound_row = rows[2]
    assert rebound_row["isRebound"] is True

    foul_row = rows[3]
    assert foul_row["isFoul"] is True

    turnover_row = rows[5]
    assert turnover_row["isTurnover"] is True

    timeout_row = rows[6]
    assert timeout_row["isTimeout"] is True

    substitution_row = rows[7]
    assert substitution_row["isSubstitution"] is True

    missed_shot_row = rows[8]
    assert missed_shot_row["isMissedShot"] is True
    assert missed_shot_row["nextActionNumber"] is None
    assert missed_shot_row["nextOrderNumber"] is None

    period_start_row = rows[9]
    assert period_start_row["prevActionNumber"] is None
    assert period_start_row["prevOrderNumber"] is None
    assert period_start_row["nextActionNumber"] == 11
    assert period_start_row["nextOrderNumber"] == 210
    assert period_start_row["secondsRemainingInPeriod"] == 720.0
    assert period_start_row["secondsSincePreviousEvent"] == 0.0

    next_period_row = rows[10]
    assert next_period_row["prevActionNumber"] == 10
    assert next_period_row["prevOrderNumber"] == 200
    assert next_period_row["secondsRemainingInPeriod"] == 720.0
    assert next_period_row["secondsSincePreviousEvent"] == 0.0


def test_build_rows_from_payload_adds_phase2_offense_margin_and_possession_fields():
    payload = {
        "game": {
            "gameId": "0022400002",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 1,
                    "clock": "PT12M00.00S",
                    "actionType": "period",
                    "subType": "start",
                    "scoreHome": 10,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 2,
                    "orderNumber": 110,
                    "period": 1,
                    "clock": "PT10M00.00S",
                    "actionType": "2pt",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "isFieldGoal": 1,
                    "shotResult": "Made",
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 3,
                    "orderNumber": 120,
                    "period": 1,
                    "clock": "PT00M01.50S",
                    "actionType": "turnover",
                    "teamId": 1610612738,
                    "possession": 1610612738,
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 4,
                    "orderNumber": 130,
                    "period": 1,
                    "clock": "PT00M00.50S",
                    "actionType": "timeout",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 5,
                    "orderNumber": 140,
                    "period": 1,
                    "clock": "PT00M00.40S",
                    "actionType": "3pt",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "isFieldGoal": 1,
                    "shotResult": "Missed",
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 6,
                    "orderNumber": 150,
                    "period": 1,
                    "clock": "PT00M00.20S",
                    "actionType": "rebound",
                    "teamId": 1610612738,
                    "possession": 1610612737,
                    "subType": "defensive",
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
            ],
        }
    }
    boxscore_context = {
        "teams": {
            1610612737: {"location": "h"},
            1610612738: {"location": "v"},
        }
    }

    rows, _ = pbp_silver.build_rows_from_payload(
        payload,
        fallback_game_id=None,
        boxscore_context=boxscore_context,
    )

    period_start_row = rows[0]
    assert period_start_row["resolvedOffenseTeamId"] == 1610612737
    assert period_start_row["resolvedDefenseTeamId"] == 1610612738
    assert period_start_row["offenseHomeAway"] == "h"
    assert period_start_row["defenseHomeAway"] == "v"
    assert period_start_row["scoreMarginBefore"] == 2
    assert period_start_row["scoreMarginAfter"] == 2
    assert period_start_row["isPossessionEndingEvent"] is False
    assert period_start_row["countAsPossession"] is False

    made_shot_row = rows[1]
    assert made_shot_row["resolvedOffenseTeamId"] == 1610612737
    assert made_shot_row["resolvedDefenseTeamId"] == 1610612738
    assert made_shot_row["scoreMarginBefore"] == 2
    assert made_shot_row["scoreMarginAfter"] == 4
    assert made_shot_row["isPossessionEndingEvent"] is True
    assert made_shot_row["countAsPossession"] is True
    assert made_shot_row["possessionBoundaryReason"] == "made_shot"

    turnover_row = rows[2]
    assert turnover_row["resolvedOffenseTeamId"] == 1610612738
    assert turnover_row["resolvedDefenseTeamId"] == 1610612737
    assert turnover_row["offenseHomeAway"] == "v"
    assert turnover_row["defenseHomeAway"] == "h"
    assert turnover_row["scoreMarginBefore"] == -4
    assert turnover_row["scoreMarginAfter"] == -4
    assert turnover_row["isPossessionEndingEvent"] is True
    assert turnover_row["countAsPossession"] is True
    assert turnover_row["possessionBoundaryReason"] == "turnover"

    timeout_row = rows[3]
    assert timeout_row["resolvedOffenseTeamId"] == 1610612737
    assert timeout_row["isPossessionEndingEvent"] is False
    assert timeout_row["countAsPossession"] is False

    final_rebound_row = rows[5]
    assert final_rebound_row["resolvedOffenseTeamId"] == 1610612737
    assert final_rebound_row["resolvedDefenseTeamId"] == 1610612738
    assert final_rebound_row["scoreMarginBefore"] == 4
    assert final_rebound_row["scoreMarginAfter"] == 4
    assert final_rebound_row["isPossessionEndingEvent"] is True
    assert final_rebound_row["countAsPossession"] is False
    assert final_rebound_row["possessionBoundaryReason"] == "period_end"


def test_build_rows_from_payload_keeps_terminal_marker_as_possession_end_event():
    payload = {
        "game": {
            "gameId": "0022400003",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 4,
                    "clock": "PT00M01.00S",
                    "actionType": "3pt",
                    "teamId": 1610612738,
                    "possession": 1610612738,
                    "isFieldGoal": 1,
                    "shotResult": "Missed",
                    "scoreHome": 100,
                    "scoreAway": 98,
                },
                {
                    "actionNumber": 2,
                    "orderNumber": 110,
                    "period": 4,
                    "clock": "PT00M00.20S",
                    "actionType": "rebound",
                    "teamId": 1610612738,
                    "possession": 1610612738,
                    "subType": "offensive",
                    "scoreHome": 100,
                    "scoreAway": 98,
                },
                {
                    "actionNumber": 3,
                    "orderNumber": 120,
                    "period": 4,
                    "clock": "PT00M00.00S",
                    "actionType": "period",
                    "subType": "end",
                    "possession": 1610612738,
                    "scoreHome": 100,
                    "scoreAway": 98,
                },
                {
                    "actionNumber": 4,
                    "orderNumber": 130,
                    "period": 4,
                    "clock": "PT00M00.00S",
                    "actionType": "game",
                    "subType": "end",
                    "possession": 0,
                    "scoreHome": 100,
                    "scoreAway": 98,
                },
            ],
        }
    }
    boxscore_context = {
        "teams": {
            1610612737: {"location": "h"},
            1610612738: {"location": "v"},
        }
    }

    rows, _ = pbp_silver.build_rows_from_payload(
        payload,
        fallback_game_id=None,
        boxscore_context=boxscore_context,
    )

    offensive_rebound_row = rows[1]
    assert offensive_rebound_row["resolvedOffenseTeamId"] == 1610612738
    assert offensive_rebound_row["isPossessionEndingEvent"] is False
    assert offensive_rebound_row["countAsPossession"] is False

    period_end_row = rows[2]
    assert period_end_row["resolvedOffenseTeamId"] == 1610612738
    assert period_end_row["resolvedDefenseTeamId"] == 1610612737
    assert period_end_row["scoreMarginBefore"] == -2
    assert period_end_row["scoreMarginAfter"] == -2
    assert period_end_row["isPossessionEndingEvent"] is False
    assert period_end_row["countAsPossession"] is False

    game_end_row = rows[3]
    assert game_end_row["resolvedOffenseTeamId"] == 1610612738
    assert game_end_row["resolvedDefenseTeamId"] == 1610612737
    assert game_end_row["scoreMarginBefore"] == -2
    assert game_end_row["scoreMarginAfter"] == -2
    assert game_end_row["isPossessionEndingEvent"] is True


def test_build_rows_from_payload_adds_phase3_foul_state_and_second_chance_flags():
    payload = {
        "game": {
            "gameId": "0022400004",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 1,
                    "clock": "PT12M00.00S",
                    "actionType": "period",
                    "subType": "start",
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 2,
                    "orderNumber": 110,
                    "period": 1,
                    "clock": "PT06M00.00S",
                    "actionType": "foul",
                    "subType": "personal",
                    "teamId": 1610612738,
                    "possession": 1610612737,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 3,
                    "orderNumber": 120,
                    "period": 1,
                    "clock": "PT05M00.00S",
                    "actionType": "foul",
                    "subType": "personal",
                    "teamId": 1610612738,
                    "possession": 1610612737,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 4,
                    "orderNumber": 130,
                    "period": 1,
                    "clock": "PT04M00.00S",
                    "actionType": "foul",
                    "subType": "personal",
                    "teamId": 1610612738,
                    "possession": 1610612737,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 5,
                    "orderNumber": 140,
                    "period": 1,
                    "clock": "PT03M00.00S",
                    "actionType": "foul",
                    "subType": "personal",
                    "teamId": 1610612738,
                    "possession": 1610612737,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 6,
                    "orderNumber": 150,
                    "period": 1,
                    "clock": "PT02M50.00S",
                    "actionType": "2pt",
                    "subType": "Jump Shot",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "isFieldGoal": 1,
                    "shotResult": "Missed",
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 7,
                    "orderNumber": 160,
                    "period": 1,
                    "clock": "PT02M49.00S",
                    "actionType": "rebound",
                    "subType": "offensive",
                    "teamId": 1610612737,
                    "personId": 1,
                    "possession": 1610612737,
                    "shotActionNumber": 6,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 8,
                    "orderNumber": 170,
                    "period": 1,
                    "clock": "PT02M40.00S",
                    "actionType": "2pt",
                    "subType": "Layup",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "isFieldGoal": 1,
                    "shotResult": "Made",
                    "scoreHome": 2,
                    "scoreAway": 0,
                },
            ],
        }
    }
    boxscore_context = {
        "teams": {
            1610612737: {"location": "h"},
            1610612738: {"location": "v"},
        }
    }

    rows, _ = pbp_silver.build_rows_from_payload(
        payload,
        fallback_game_id=None,
        boxscore_context=boxscore_context,
    )

    first_foul_row = rows[1]
    assert first_foul_row["foulsToGiveOffense"] == 4
    assert first_foul_row["foulsToGiveDefense"] == 3
    assert first_foul_row["isPenaltyEvent"] is False

    fourth_foul_row = rows[4]
    assert fourth_foul_row["foulsToGiveOffense"] == 4
    assert fourth_foul_row["foulsToGiveDefense"] == 0
    assert fourth_foul_row["isPenaltyEvent"] is False

    missed_shot_row = rows[5]
    assert missed_shot_row["isPenaltyEvent"] is True
    assert missed_shot_row["isSecondChanceEvent"] is False

    oreb_row = rows[6]
    assert oreb_row["isOreb"] is True
    assert oreb_row["isDreb"] is False
    assert oreb_row["inferredReboundType"] == "offensive"
    assert oreb_row["reboundTypeSourceMismatchFlag"] is False
    assert oreb_row["isPlaceholderRebound"] is False
    assert oreb_row["isSecondChanceEvent"] is False
    assert oreb_row["isPenaltyEvent"] is True

    made_shot_row = rows[7]
    assert made_shot_row["isSecondChanceEvent"] is True
    assert made_shot_row["isPenaltyEvent"] is True


def test_build_rows_from_payload_adds_phase3_turnover_ft_and_rebound_flags():
    payload = {
        "game": {
            "gameId": "0022400005",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 1,
                    "clock": "PT08M00.00S",
                    "actionType": "foul",
                    "subType": "personal",
                    "descriptor": "shooting",
                    "teamId": 1610612738,
                    "possession": 1610612737,
                    "scoreHome": 10,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 2,
                    "orderNumber": 110,
                    "period": 1,
                    "clock": "PT07M50.00S",
                    "actionType": "freethrow",
                    "subType": "1 of 1",
                    "descriptor": "technical",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "shotResult": "Made",
                    "scoreHome": 11,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 3,
                    "orderNumber": 120,
                    "period": 1,
                    "clock": "PT07M40.00S",
                    "actionType": "freethrow",
                    "subType": "1 of 1",
                    "descriptor": "flagrant",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "shotResult": "Made",
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 4,
                    "orderNumber": 130,
                    "period": 1,
                    "clock": "PT07M20.00S",
                    "actionType": "turnover",
                    "subType": "bad pass",
                    "teamId": 1610612737,
                    "personId": 10,
                    "stealPersonId": 20,
                    "possession": 1610612737,
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 5,
                    "orderNumber": 140,
                    "period": 1,
                    "clock": "PT07M00.00S",
                    "actionType": "turnover",
                    "subType": "lost ball",
                    "teamId": 1610612737,
                    "personId": 10,
                    "stealPersonId": 20,
                    "possession": 1610612737,
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 6,
                    "orderNumber": 150,
                    "period": 1,
                    "clock": "PT06M40.00S",
                    "actionType": "turnover",
                    "subType": "traveling",
                    "teamId": 1610612737,
                    "personId": 10,
                    "possession": 1610612737,
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 7,
                    "orderNumber": 160,
                    "period": 1,
                    "clock": "PT06M20.00S",
                    "actionType": "turnover",
                    "subType": "shot clock",
                    "teamId": 1610612737,
                    "personId": 10,
                    "possession": 1610612737,
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 8,
                    "orderNumber": 170,
                    "period": 1,
                    "clock": "PT06M00.00S",
                    "actionType": "freethrow",
                    "subType": "1 of 2",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "shotResult": "Missed",
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
                {
                    "actionNumber": 9,
                    "orderNumber": 180,
                    "period": 1,
                    "clock": "PT06M00.00S",
                    "actionType": "rebound",
                    "subType": "offensive",
                    "teamId": 1610612737,
                    "personId": 0,
                    "possession": 1610612737,
                    "shotActionNumber": 8,
                    "qualifiers": ["deadball", "team"],
                    "scoreHome": 12,
                    "scoreAway": 8,
                },
            ],
        }
    }
    boxscore_context = {
        "teams": {
            1610612737: {"location": "h"},
            1610612738: {"location": "v"},
        }
    }

    rows, _ = pbp_silver.build_rows_from_payload(
        payload,
        fallback_game_id=None,
        boxscore_context=boxscore_context,
    )

    assert rows[0]["isShootingFoul"] is True
    assert rows[1]["isTechnicalFt"] is True
    assert rows[1]["isFlagrantFt"] is False
    assert rows[2]["isTechnicalFt"] is False
    assert rows[2]["isFlagrantFt"] is True

    assert rows[3]["isBadPassTurnover"] is True
    assert rows[3]["isLostBallTurnover"] is False
    assert rows[4]["isBadPassTurnover"] is False
    assert rows[4]["isLostBallTurnover"] is True
    assert rows[5]["isTravelTurnover"] is True
    assert rows[6]["isShotClockTurnover"] is True

    placeholder_rebound_row = rows[8]
    assert placeholder_rebound_row["isOreb"] is True
    assert placeholder_rebound_row["isPlaceholderRebound"] is True


def test_build_rows_from_payload_excludes_non_real_orebs_from_second_chance():
    payload = {
        "game": {
            "gameId": "0022400006",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 1,
                    "clock": "PT07M49.00S",
                    "actionType": "3pt",
                    "subType": "Jump Shot",
                    "teamId": 1610612737,
                    "personId": 11,
                    "possession": 1610612737,
                    "isFieldGoal": 1,
                    "shotResult": "Missed",
                    "scoreHome": 20,
                    "scoreAway": 18,
                },
                {
                    "actionNumber": 2,
                    "orderNumber": 110,
                    "period": 1,
                    "clock": "PT07M48.00S",
                    "actionType": "rebound",
                    "subType": "offensive",
                    "teamId": 1610612737,
                    "personId": 0,
                    "possession": 1610612737,
                    "qualifiers": ["team"],
                    "shotActionNumber": 1,
                    "scoreHome": 20,
                    "scoreAway": 18,
                },
                {
                    "actionNumber": 3,
                    "orderNumber": 120,
                    "period": 1,
                    "clock": "PT07M48.00S",
                    "actionType": "turnover",
                    "subType": "shot clock",
                    "teamId": 1610612737,
                    "personId": 0,
                    "possession": 1610612737,
                    "qualifiers": ["team"],
                    "scoreHome": 20,
                    "scoreAway": 18,
                },
                {
                    "actionNumber": 4,
                    "orderNumber": 130,
                    "period": 1,
                    "clock": "PT06M59.00S",
                    "actionType": "foul",
                    "subType": "personal",
                    "descriptor": "away-from-play",
                    "teamId": 1610612738,
                    "possession": 1610612737,
                    "scoreHome": 20,
                    "scoreAway": 18,
                },
                {
                    "actionNumber": 5,
                    "orderNumber": 140,
                    "period": 1,
                    "clock": "PT06M59.00S",
                    "actionType": "freethrow",
                    "subType": "1 of 1",
                    "descriptor": "away-from-play",
                    "teamId": 1610612737,
                    "personId": 11,
                    "possession": 1610612737,
                    "shotResult": "Missed",
                    "scoreHome": 20,
                    "scoreAway": 18,
                },
                {
                    "actionNumber": 6,
                    "orderNumber": 150,
                    "period": 1,
                    "clock": "PT06M59.00S",
                    "actionType": "rebound",
                    "subType": "offensive",
                    "teamId": 1610612737,
                    "personId": 0,
                    "possession": 1610612737,
                    "qualifiers": ["team"],
                    "shotActionNumber": 5,
                    "scoreHome": 20,
                    "scoreAway": 18,
                },
                {
                    "actionNumber": 7,
                    "orderNumber": 160,
                    "period": 1,
                    "clock": "PT06M53.00S",
                    "actionType": "2pt",
                    "subType": "Layup",
                    "descriptor": "driving",
                    "teamId": 1610612737,
                    "personId": 11,
                    "possession": 1610612737,
                    "isFieldGoal": 1,
                    "shotResult": "Made",
                    "scoreHome": 22,
                    "scoreAway": 18,
                },
            ],
        }
    }
    boxscore_context = {
        "teams": {
            1610612737: {"location": "h"},
            1610612738: {"location": "v"},
        }
    }

    rows, _ = pbp_silver.build_rows_from_payload(
        payload,
        fallback_game_id=None,
        boxscore_context=boxscore_context,
    )

    shot_clock_rebound_row = rows[1]
    assert shot_clock_rebound_row["isOreb"] is True
    assert shot_clock_rebound_row["isPlaceholderRebound"] is False

    shot_clock_turnover_row = rows[2]
    assert shot_clock_turnover_row["isSecondChanceEvent"] is False

    away_from_play_rebound_row = rows[5]
    assert away_from_play_rebound_row["isOreb"] is True
    assert away_from_play_rebound_row["isPlaceholderRebound"] is False

    made_shot_row = rows[6]
    assert made_shot_row["isSecondChanceEvent"] is False


def test_build_rows_from_payload_second_chance_does_not_cross_possession_ending_oreb():
    payload = {
        "game": {
            "gameId": "0022400007",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 1,
                    "clock": "PT02M00.00S",
                    "actionType": "freethrow",
                    "subType": "1 of 1",
                    "teamId": 1610612737,
                    "personId": 11,
                    "possession": 1610612737,
                    "shotResult": "Missed",
                    "scoreHome": 80,
                    "scoreAway": 78,
                },
                {
                    "actionNumber": 2,
                    "orderNumber": 110,
                    "period": 1,
                    "clock": "PT01M59.00S",
                    "actionType": "rebound",
                    "subType": "offensive",
                    "teamId": 1610612737,
                    "personId": 0,
                    "possession": 1610612737,
                    "qualifiers": ["team"],
                    "shotActionNumber": 1,
                    "scoreHome": 80,
                    "scoreAway": 78,
                },
                {
                    "actionNumber": 3,
                    "orderNumber": 120,
                    "period": 1,
                    "clock": "PT01M59.00S",
                    "actionType": "freethrow",
                    "subType": "1 of 2",
                    "descriptor": "flagrant",
                    "teamId": 1610612738,
                    "personId": 22,
                    "possession": 1610612738,
                    "shotResult": "Made",
                    "scoreHome": 80,
                    "scoreAway": 79,
                },
                {
                    "actionNumber": 4,
                    "orderNumber": 130,
                    "period": 1,
                    "clock": "PT01M58.00S",
                    "actionType": "freethrow",
                    "subType": "2 of 2",
                    "descriptor": "flagrant",
                    "teamId": 1610612738,
                    "personId": 22,
                    "possession": 1610612738,
                    "shotResult": "Made",
                    "scoreHome": 80,
                    "scoreAway": 80,
                },
            ],
        }
    }
    boxscore_context = {
        "teams": {
            1610612737: {"location": "h"},
            1610612738: {"location": "v"},
        }
    }

    rows, _ = pbp_silver.build_rows_from_payload(
        payload,
        fallback_game_id=None,
        boxscore_context=boxscore_context,
    )

    assert rows[2]["isSecondChanceEvent"] is True
    assert rows[3]["isSecondChanceEvent"] is False


def test_build_rows_from_payload_adds_phase6_period_start_override_and_linkage_fields(monkeypatch):
    monkeypatch.setattr(
        pbp_silver,
        "PERIOD_START_OVERRIDES",
        {"0022400006": {"2": 1610612738}},
    )

    payload = {
        "game": {
            "gameId": "0022400006",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 1,
                    "clock": "PT12M00.00S",
                    "actionType": "period",
                    "subType": "start",
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 2,
                    "orderNumber": 110,
                    "period": 1,
                    "clock": "PT11M59.00S",
                    "actionType": "jumpball",
                    "subType": "recovered",
                    "teamId": 1610612737,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 3,
                    "orderNumber": 120,
                    "period": 1,
                    "clock": "PT11M40.00S",
                    "actionType": "2pt",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "isFieldGoal": 1,
                    "shotResult": "Missed",
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 4,
                    "orderNumber": 130,
                    "period": 1,
                    "clock": "PT11M38.00S",
                    "actionType": "rebound",
                    "teamId": 1610612738,
                    "personId": 22,
                    "possession": 1610612737,
                    "subType": "defensive",
                    "shotActionNumber": 3,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 5,
                    "orderNumber": 140,
                    "period": 1,
                    "clock": "PT00M00.00S",
                    "actionType": "period",
                    "subType": "end",
                    "possession": 1610612738,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 6,
                    "orderNumber": 200,
                    "period": 2,
                    "clock": "PT12M00.00S",
                    "actionType": "period",
                    "subType": "start",
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 7,
                    "orderNumber": 210,
                    "period": 2,
                    "clock": "PT11M50.00S",
                    "actionType": "foul",
                    "teamId": 1610612737,
                    "possession": 1610612738,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 8,
                    "orderNumber": 220,
                    "period": 2,
                    "clock": "PT11M50.00S",
                    "actionType": "freethrow",
                    "teamId": 1610612738,
                    "possession": 1610612738,
                    "subType": "1 of 2",
                    "shotResult": "Made",
                    "scoreHome": 0,
                    "scoreAway": 1,
                },
                {
                    "actionNumber": 9,
                    "orderNumber": 230,
                    "period": 2,
                    "clock": "PT11M50.00S",
                    "actionType": "freethrow",
                    "teamId": 1610612738,
                    "possession": 1610612738,
                    "subType": "2 of 2",
                    "shotResult": "Missed",
                    "scoreHome": 0,
                    "scoreAway": 1,
                },
            ],
        }
    }
    boxscore_context = {
        "teams": {
            1610612737: {"location": "h"},
            1610612738: {"location": "v"},
        }
    }

    rows, _ = pbp_silver.build_rows_from_payload(
        payload,
        fallback_game_id=None,
        boxscore_context=boxscore_context,
    )

    first_period_start = rows[0]
    assert first_period_start["isPeriodStartEvent"] is True
    assert first_period_start["teamStartingPeriodWithBall"] == 1610612737
    assert first_period_start["resolvedOffenseTeamId"] == 1610612737

    rebound_row = rows[3]
    assert rebound_row["linkedShotActionNumber"] == 3
    assert rebound_row["reboundOfMissedShotFlag"] is True
    assert rebound_row["inferredReboundType"] == "defensive"
    assert rebound_row["reboundTypeSourceMismatchFlag"] is False

    period_end_row = rows[4]
    assert period_end_row["isPeriodEndEvent"] is True

    second_period_start = rows[5]
    assert second_period_start["isPeriodStartEvent"] is True
    assert second_period_start["teamStartingPeriodWithBall"] == 1610612738
    assert second_period_start["resolvedOffenseTeamId"] == 1610612738

    first_free_throw = rows[7]
    second_free_throw = rows[8]
    assert first_free_throw["freeThrowTripSequenceNum"] == 1
    assert first_free_throw["freeThrowTripSize"] == 2
    assert second_free_throw["freeThrowTripSequenceNum"] == 2
    assert second_free_throw["freeThrowTripSize"] == 2


def test_build_rows_from_payload_flags_rebound_type_source_mismatch():
    payload = {
        "game": {
            "gameId": "0022400008",
            "actions": [
                {
                    "actionNumber": 1,
                    "orderNumber": 100,
                    "period": 1,
                    "clock": "PT11M40.00S",
                    "actionType": "2pt",
                    "teamId": 1610612737,
                    "possession": 1610612737,
                    "isFieldGoal": 1,
                    "shotResult": "Missed",
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
                {
                    "actionNumber": 2,
                    "orderNumber": 110,
                    "period": 1,
                    "clock": "PT11M38.00S",
                    "actionType": "rebound",
                    "teamId": 1610612738,
                    "personId": 22,
                    "possession": 1610612737,
                    "subType": "offensive",
                    "shotActionNumber": 1,
                    "scoreHome": 0,
                    "scoreAway": 0,
                },
            ],
        }
    }
    boxscore_context = {
        "teams": {
            1610612737: {"location": "h"},
            1610612738: {"location": "v"},
        }
    }

    rows, _ = pbp_silver.build_rows_from_payload(
        payload,
        fallback_game_id=None,
        boxscore_context=boxscore_context,
    )

    rebound_row = rows[1]
    assert rebound_row["isOreb"] is True
    assert rebound_row["isDreb"] is False
    assert rebound_row["inferredReboundType"] == "defensive"
    assert rebound_row["reboundTypeSourceMismatchFlag"] is True
