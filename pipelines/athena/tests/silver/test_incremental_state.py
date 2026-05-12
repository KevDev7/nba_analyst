from __future__ import annotations

from pipelines.athena.transform.silver.incremental_state import (
    select_incremental_game_ids_from_watermark_state,
)


def test_select_incremental_game_ids_returns_all_without_watermark():
    selected, meta = select_incremental_game_ids_from_watermark_state(
        {"0022500001": [], "0022500002": []},
        {},
        lookback_minutes=60,
    )

    assert selected == {"0022500001", "0022500002"}
    assert meta["selection_mode"] == "legacy_full_initial"
    assert meta["lookback_minutes"] == 60


def test_select_incremental_game_ids_uses_lookback_watermark():
    source_index = {
        "0022500001": [
            {
                "key": "raw/cdn/playbyplay/game_id=0022500001.json",
                "last_modified_utc": "2026-05-11T12:30:00Z",
            }
        ],
        "0022500002": [
            {
                "key": "raw/cdn/playbyplay/game_id=0022500002.json",
                "last_modified_utc": "2026-05-11T10:59:59Z",
            }
        ],
    }

    selected, meta = select_incremental_game_ids_from_watermark_state(
        source_index,
        {"max_source_last_modified_utc": "2026-05-11T12:00:00Z"},
        lookback_minutes=60,
        source_key_prefix="raw/cdn/playbyplay/",
    )

    assert selected == {"0022500001"}
    assert meta["selection_mode"] == "legacy_state_incremental"
    assert meta["effective_watermark_utc"] == "2026-05-11T11:00:00Z"


def test_select_incremental_game_ids_honors_source_key_prefix():
    source_index = {
        "0022500001": [
            {
                "key": "silver/on_court_state/game_id=0022500001.parquet",
                "last_modified_utc": "2026-05-11T12:30:00Z",
            }
        ],
    }

    selected, _meta = select_incremental_game_ids_from_watermark_state(
        source_index,
        {"max_source_last_modified_utc": "2026-05-11T12:00:00Z"},
        lookback_minutes=60,
        source_key_prefix="raw/cdn/playbyplay/",
    )

    assert selected == set()
