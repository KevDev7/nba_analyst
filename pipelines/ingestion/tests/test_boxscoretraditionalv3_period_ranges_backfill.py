from __future__ import annotations

from pipelines.ingestion.nba_stats import backfill_boxscoretraditionalv3_period_ranges as period_ranges


def test_period_range_tenths_for_regulation_and_overtime_periods():
    assert period_ranges.period_range_tenths(1) == (5, 7195)
    assert period_ranges.period_range_tenths(4) == (21605, 28795)
    assert period_ranges.period_range_tenths(5) == (28805, 31795)
    assert period_ranges.period_range_tenths(6) == (31805, 34795)


def test_destination_key_normalizes_game_id_and_keeps_period_json():
    assert (
        period_ranges.destination_key("22400001", 2)
        == "raw/boxscoretraditionalv3/period_player_stats/game_id=0022400001/period=2.json"
    )


def test_request_params_use_range_type_two_period_window():
    params = period_ranges.request_params("0022500001", 3)

    assert params == {
        "GameID": "0022500001",
        "StartPeriod": 0,
        "EndPeriod": 0,
        "StartRange": 14405,
        "EndRange": 21595,
        "RangeType": 2,
    }
