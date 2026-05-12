from __future__ import annotations

import sys
from pathlib import Path


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_shot_location_events as shot_location


def test_build_shot_location_rows_prefers_source_area_when_present():
    rows = shot_location.build_shot_location_rows(
        [
            {
                "gameId": "22400001",
                "actionNumber": 7,
                "orderNumber": 7000,
                "period": 1,
                "clock": "PT11M42.00S",
                "secondsRemainingInPeriod": 702,
                "personId": 1628369,
                "teamId": 1610612738,
                "teamTricode": "BOS",
                "actionType": "3pt",
                "subType": "Jump Shot",
                "descriptor": None,
                "shotResult": "Missed",
                "shotValue": 3,
                "isFieldGoal": 1,
                "isMadeShot": False,
                "shotDistance": 26.51,
                "area": "Above the Break 3",
                "areaDetail": "24+ Left Center",
                "x": 27.4,
                "y": 83.5,
                "xLegacy": -168,
                "yLegacy": 205,
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["game_id"] == "0022400001"
    assert row["shot_zone_area"] == "Above the Break 3"
    assert row["shot_zone_area_detail"] == "24+ Left Center"
    assert row["zone_source"] == "source_area"
    assert row["source_area_available_flag"] is True
    assert row["coordinate_available_flag"] is True
    assert row["source_derived_area_mismatch_flag"] is False


def test_build_shot_location_rows_derives_area_for_older_source_without_area():
    rows = shot_location.build_shot_location_rows(
        [
            {
                "gameId": "22000001",
                "actionNumber": 12,
                "actionType": "2pt",
                "subType": "Jump Shot",
                "shotResult": "Made",
                "shotValue": 2,
                "isFieldGoal": True,
                "isMadeShot": True,
                "shotDistance": 21.97,
                "area": None,
                "areaDetail": None,
                "xLegacy": -2,
                "yLegacy": 220,
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["game_id"] == "0022000001"
    assert row["source_area_available_flag"] is False
    assert row["coordinate_available_flag"] is True
    assert row["derived_area"] == "Mid-Range"
    assert row["derived_area_detail"] == "16-24 Center"
    assert row["shot_zone_area"] == "Mid-Range"
    assert row["zone_source"] == "derived_from_legacy_coordinates"


def test_build_shot_location_rows_derives_corner_three_from_coordinates():
    rows = shot_location.build_shot_location_rows(
        [
            {
                "gameId": "22100001",
                "actionNumber": 21,
                "actionType": "3pt",
                "shotValue": 3,
                "isFieldGoal": True,
                "shotDistance": 23.5,
                "xLegacy": -225,
                "yLegacy": 80,
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["derived_area"] == "Left Corner 3"
    assert row["derived_area_detail"] == "24+ Left"
    assert row["shot_zone_area"] == "Left Corner 3"


def test_build_shot_location_rows_derives_above_break_detail_center_band():
    rows = shot_location.build_shot_location_rows(
        [
            {
                "gameId": "22100001",
                "actionNumber": 22,
                "actionType": "3pt",
                "shotValue": 3,
                "isFieldGoal": True,
                "shotDistance": 26.5,
                "xLegacy": -168,
                "yLegacy": 205,
            }
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["derived_area"] == "Above the Break 3"
    assert row["derived_area_detail"] == "24+ Left Center"


def test_build_shot_location_rows_marks_missing_coordinates_unavailable():
    rows = shot_location.build_shot_location_rows(
        [
            {
                "gameId": "22100001",
                "actionNumber": 30,
                "actionType": "2pt",
                "isFieldGoal": True,
                "area": None,
                "areaDetail": None,
            },
            {
                "gameId": "22100001",
                "actionNumber": 31,
                "actionType": "rebound",
                "isFieldGoal": False,
            },
        ]
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["coordinate_available_flag"] is False
    assert row["shot_zone_area"] is None
    assert row["zone_source"] == "unavailable"
    assert row["derivation_warning"] == "missing_legacy_coordinates"
