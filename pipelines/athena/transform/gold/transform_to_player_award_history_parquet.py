"""
Build gold player_award_history from structured Basketball Reference award rows.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/bbr_player_awards.parquet
  s3://nba-analytics-lakehouse-dev/silver/player_identity_bridge_bbr_nba.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/gold/player_award_history/player_award_history.parquet
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.gold.gold_transform_helpers import (
        S3_BUCKET,
        read_parquet_table_from_s3,
        to_float_or_none,
        to_positive_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        S3_BUCKET,
        read_parquet_table_from_s3,
        to_float_or_none,
        to_positive_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )

load_dotenv(override=True)

AWARDS_SOURCE_KEY = "silver/bbr_player_awards.parquet"
BRIDGE_SOURCE_KEY = "silver/player_identity_bridge_bbr_nba.parquet"
DESTINATION_KEY = "gold/player_award_history/player_award_history.parquet"
RECORD_SOURCE = "silver/bbr_player_awards.parquet|silver/player_identity_bridge_bbr_nba.parquet"

AWARDS_REQUIRED_COLUMNS = [
    "basketball_reference_player_id",
    "award_family",
    "league_code",
    "season_label",
    "team_tier",
]

BRIDGE_REQUIRED_COLUMNS = [
    "nba_person_id",
    "basketball_reference_player_id",
    "match_method",
    "match_confidence",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("player_award_history_sk", pa.int64()),
        pa.field("person_id", pa.int64()),
        pa.field("award_type", pa.string()),
        pa.field("season_year", pa.string()),
        pa.field("team_tier", pa.int64()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)


def _bridge_confidence_sort_value(value: Any) -> float:
    confidence = to_float_or_none(value)
    return float("-inf") if confidence is None else confidence


def build_bridge_by_bbr_id(bridge_table: pa.Table) -> dict[str, dict[str, Any]]:
    best_by_bbr_id: dict[str, dict[str, Any]] = {}
    for row in bridge_table.to_pylist():
        bbr_id = to_str_or_none(row.get("basketball_reference_player_id"))
        person_id = to_positive_int_or_none(row.get("nba_person_id"))
        if bbr_id is None or person_id is None:
            continue
        candidate = {
            "person_id": person_id,
            "bbr_match_method": to_str_or_none(row.get("match_method")),
            "bbr_match_confidence": to_float_or_none(row.get("match_confidence")),
        }
        current = best_by_bbr_id.get(bbr_id)
        if current is None or _bridge_confidence_sort_value(candidate.get("bbr_match_confidence")) > _bridge_confidence_sort_value(
            current.get("bbr_match_confidence")
        ):
            best_by_bbr_id[bbr_id] = candidate
    return best_by_bbr_id


def build_player_award_history_rows(bridge_table: pa.Table, awards_table: pa.Table) -> list[dict[str, Any]]:
    bridge_by_bbr_id = build_bridge_by_bbr_id(bridge_table)
    deduped_rows: dict[tuple[Any, ...], dict[str, Any]] = {}

    for row in awards_table.to_pylist():
        bbr_id = to_str_or_none(row.get("basketball_reference_player_id"))
        if bbr_id is None:
            continue
        if to_str_or_none(row.get("league_code")) != "NBA":
            continue
        bridge = bridge_by_bbr_id.get(bbr_id)
        if bridge is None:
            continue

        output_row = {
            "person_id": bridge["person_id"],
            "award_type": to_str_or_none(row.get("award_family")),
            "season_year": to_str_or_none(row.get("season_label")),
            "team_tier": to_positive_int_or_none(row.get("team_tier")),
        }
        dedupe_key = (
            output_row["person_id"],
            output_row["award_type"],
            output_row["season_year"],
            output_row["team_tier"],
        )
        deduped_rows[dedupe_key] = output_row

    return sorted(
        deduped_rows.values(),
        key=lambda row: (
            row["person_id"] or -1,
            row["season_year"] or "",
            row["award_type"] or "",
            row["team_tier"] or 0,
        ),
    )


def finalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        output.append(
            {
                "player_award_history_sk": index,
                "person_id": row.get("person_id"),
                "award_type": row.get("award_type"),
                "season_year": row.get("season_year"),
                "team_tier": row.get("team_tier"),
                "record_source": RECORD_SOURCE,
                "created_at_utc": run_ts,
                "updated_at_utc": run_ts,
            }
        )
    return output


def main() -> None:
    s3_client = boto3.client("s3")
    bridge_table = read_parquet_table_from_s3(s3_client, BRIDGE_SOURCE_KEY, BRIDGE_REQUIRED_COLUMNS)
    awards_table = read_parquet_table_from_s3(s3_client, AWARDS_SOURCE_KEY, AWARDS_REQUIRED_COLUMNS)
    rows = build_player_award_history_rows(bridge_table, awards_table)
    write_parquet_to_s3(finalize_rows(rows), TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
