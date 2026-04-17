"""
Transform one raw NBA player movement snapshot JSON into a silver parquet file.

Reads:
  s3://nba-analytics-lakehouse-dev/raw/cdn/player_movement/
  snapshot_date=YYYY-MM-DD/player_movement.json

Writes (overwrite on rerun):
  s3://nba-analytics-lakehouse-dev/silver/player_movement.parquet
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from silver_pipeline_helpers import write_audit_artifacts

load_dotenv(override=True)  # Ensure .env credentials override any system variables

S3_BUCKET = "nba-analytics-lakehouse-dev"

# Change this to point to a newer snapshot partition, e.g. "snapshot_date=2026-03-02".
SNAPSHOT_PARTITION = "snapshot_date=2026-03-01"

SOURCE_KEY = f"raw/cdn/player_movement/{SNAPSHOT_PARTITION}/player_movement.json"
DESTINATION_KEY = "silver/player_movement.parquet"
TABLE_NAME = "player_movement"
META_SOURCE_SYSTEM = "nba_cdn_player_movement"
META_SCHEMA_VERSION = 1

TARGET_SCHEMA = pa.schema(
    [
        pa.field("Transaction_Type", pa.string()),
        pa.field("TRANSACTION_DATE", pa.timestamp("us")),
        pa.field("TRANSACTION_DESCRIPTION", pa.string()),
        pa.field("TEAM_ID", pa.int64()),
        pa.field("TEAM_SLUG", pa.string()),
        pa.field("PLAYER_ID", pa.int64()),
        pa.field("PLAYER_SLUG", pa.string()),
        pa.field("Additional_Sort", pa.int64()),
        pa.field("GroupSort", pa.string()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def null_if_empty(value: Any) -> Any:
    """Convert empty/blank strings to None; keep other values unchanged."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def to_int_or_none(value: Any) -> int | None:
    """Convert value to int when present."""
    value = null_if_empty(value)
    if value is None:
        return None
    return int(value)


def parse_transaction_datetime(value: Any) -> datetime | None:
    """Parse TRANSACTION_DATE in ISO-like format, e.g. 2026-02-28T00:00:00."""
    value = null_if_empty(value)
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def read_source_payload(s3_client) -> tuple[dict[str, Any], datetime | None]:
    """Read source JSON payload from S3 with source last-modified."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=SOURCE_KEY)
    payload_bytes = response["Body"].read()
    source_last_modified = response.get("LastModified")
    if isinstance(source_last_modified, datetime) and source_last_modified.tzinfo is None:
        source_last_modified = source_last_modified.replace(tzinfo=timezone.utc)
    return json.loads(payload_bytes), source_last_modified


def build_rows(payload: dict[str, Any], source_last_modified_utc: datetime | None) -> list[dict[str, Any]]:
    """Build row list with the exact required columns."""
    movement = payload.get("NBA_Player_Movement") or {}
    source_rows = movement.get("rows") or []

    rows: list[dict[str, Any]] = []
    for item in source_rows:
        rows.append(
            {
                "Transaction_Type": null_if_empty(item.get("Transaction_Type")),
                "TRANSACTION_DATE": parse_transaction_datetime(item.get("TRANSACTION_DATE")),
                "TRANSACTION_DESCRIPTION": null_if_empty(item.get("TRANSACTION_DESCRIPTION")),
                "TEAM_ID": to_int_or_none(item.get("TEAM_ID")),
                "TEAM_SLUG": null_if_empty(item.get("TEAM_SLUG")),
                "PLAYER_ID": to_int_or_none(item.get("PLAYER_ID")),
                "PLAYER_SLUG": null_if_empty(item.get("PLAYER_SLUG")),
                "Additional_Sort": to_int_or_none(item.get("Additional_Sort")),
                "GroupSort": null_if_empty(item.get("GroupSort")),
                "_meta_source_key": SOURCE_KEY,
                "_meta_source_last_modified_utc": source_last_modified_utc,
            }
        )
    return rows


def add_metadata_columns(rows: list[dict[str, Any]], pipeline_run_id: str, ingested_at_utc: datetime) -> None:
    """Attach standardized metadata contract columns to each row."""
    for row in rows:
        row["_meta_pipeline_run_id"] = pipeline_run_id
        row["_meta_ingested_at_utc"] = ingested_at_utc
        row["_meta_source_system"] = META_SOURCE_SYSTEM
        row["_meta_schema_version"] = META_SCHEMA_VERSION


def write_parquet_to_s3(rows: list[dict[str, Any]], s3_client) -> None:
    """Write one parquet object to S3 (overwrites same key on rerun)."""
    table = pa.Table.from_pylist(rows, schema=TARGET_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)

    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=DESTINATION_KEY,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )


def main() -> None:
    """Run transform for the configured snapshot partition."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"player_movement_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    print(f"Reading s3://{S3_BUCKET}/{SOURCE_KEY}")
    payload, source_last_modified_utc = read_source_payload(s3_client)

    rows = build_rows(payload, source_last_modified_utc=source_last_modified_utc)
    print(f"Built {len(rows)} rows")

    add_metadata_columns(rows, pipeline_run_id=pipeline_run_id, ingested_at_utc=ingested_at_utc)
    write_parquet_to_s3(rows, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")

    warning_count = 0
    warning_reason_counts: dict[str, int] = {}
    if len(rows) == 0:
        warning_count = 1
        warning_reason_counts["empty_source_rows"] = 1

    run_status = "success_with_warnings" if warning_count > 0 else "success"
    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": run_status,
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_key": SOURCE_KEY,
        "source_last_modified_utc": source_last_modified_utc,
        "destination_key": DESTINATION_KEY,
        "input_row_count": len(rows),
        "output_row_count": len(rows),
        "warning_count": warning_count,
        "error_count": 0,
        "warning_reason_counts": json.dumps(warning_reason_counts, sort_keys=True),
        "error_reason_counts": "{}",
    }
    audit_json_key, audit_parquet_key = write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )
    print(f"Wrote audit JSON: s3://{S3_BUCKET}/{audit_json_key}")
    print(f"Wrote audit parquet: s3://{S3_BUCKET}/{audit_parquet_key}")


if __name__ == "__main__":
    main()
