from __future__ import annotations

from datetime import datetime, timezone

from pipelines.athena.transform.silver.player_movement.pipeline import build_audit_row
from pipelines.athena.transform.silver.player_movement.transform import (
    add_metadata_columns,
    build_rows,
    null_if_empty,
    parse_transaction_datetime,
    to_int_or_none,
)


def test_player_movement_transform_normalizes_source_rows():
    source_last_modified = datetime(2026, 3, 1, tzinfo=timezone.utc)
    payload = {
        "NBA_Player_Movement": {
            "rows": [
                {
                    "Transaction_Type": "Waived",
                    "TRANSACTION_DATE": "2026-02-28T00:00:00",
                    "TRANSACTION_DESCRIPTION": "Example",
                    "TEAM_ID": "1610612738",
                    "TEAM_SLUG": "celtics",
                    "PLAYER_ID": "123",
                    "PLAYER_SLUG": "example-player",
                    "Additional_Sort": "7",
                    "GroupSort": "",
                }
            ]
        }
    }

    rows = build_rows(payload, source_last_modified_utc=source_last_modified)

    assert rows == [
        {
            "Transaction_Type": "Waived",
            "TRANSACTION_DATE": datetime(2026, 2, 28),
            "TRANSACTION_DESCRIPTION": "Example",
            "TEAM_ID": 1610612738,
            "TEAM_SLUG": "celtics",
            "PLAYER_ID": 123,
            "PLAYER_SLUG": "example-player",
            "Additional_Sort": 7,
            "GroupSort": None,
            "_meta_source_key": (
                "raw/cdn/player_movement/snapshot_date=2026-03-01/player_movement.json"
            ),
            "_meta_source_last_modified_utc": source_last_modified,
        }
    ]


def test_player_movement_adds_standard_metadata():
    rows = [{"PLAYER_ID": 123}]
    ingested_at = datetime(2026, 5, 11, tzinfo=timezone.utc)

    add_metadata_columns(rows, pipeline_run_id="run_1", ingested_at_utc=ingested_at)

    assert rows[0]["_meta_pipeline_run_id"] == "run_1"
    assert rows[0]["_meta_ingested_at_utc"] == ingested_at
    assert rows[0]["_meta_source_system"] == "nba_cdn_player_movement"
    assert rows[0]["_meta_schema_version"] == 1


def test_player_movement_small_conversion_helpers():
    assert null_if_empty("  ") is None
    assert to_int_or_none("42") == 42
    assert parse_transaction_datetime("2026-02-28T00:00:00") == datetime(2026, 2, 28)


def test_player_movement_audit_row_marks_empty_source_warning():
    audit_row = build_audit_row(
        pipeline_run_id="run_1",
        ingested_at_utc=datetime(2026, 5, 11, tzinfo=timezone.utc),
        source_last_modified_utc=None,
        row_count=0,
        warning_reason_counts={"empty_source_rows": 1},
    )

    assert audit_row["run_status"] == "success_with_warnings"
    assert audit_row["warning_count"] == 1
    assert audit_row["error_count"] == 0
