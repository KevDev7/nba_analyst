"""
Transform raw Kaggle TeamHistories CSV to a silver parquet file.

Reads:
  s3://nba-analytics-lakehouse-dev/raw/kaggle/TeamHistories.csv

Writes:
  s3://nba-analytics-lakehouse-dev/silver/team_histories.parquet
"""

from __future__ import annotations

import csv
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
SOURCE_KEY = "raw/kaggle/TeamHistories.csv"
DESTINATION_KEY = "silver/team_histories.parquet"
TABLE_NAME = "team_histories"
META_SOURCE_SYSTEM = "kaggle_team_histories_csv"
META_SCHEMA_VERSION = 1


def null_if_empty(value: Any) -> Any:
    """Convert empty/blank strings to None; keep all other values unchanged."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def read_source_rows(s3_client) -> tuple[list[str], list[dict[str, Any]], datetime | None]:
    """Read source CSV from S3 and return columns, normalized rows, and last-modified."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=SOURCE_KEY)
    payload = response["Body"].read().decode("utf-8-sig")
    source_last_modified = response.get("LastModified")
    if isinstance(source_last_modified, datetime) and source_last_modified.tzinfo is None:
        source_last_modified = source_last_modified.replace(tzinfo=timezone.utc)

    reader = csv.DictReader(io.StringIO(payload))
    columns = reader.fieldnames or []
    if not columns:
        raise ValueError("TeamHistories.csv has no header columns.")

    rows: list[dict[str, Any]] = []
    for row in reader:
        rows.append({column: null_if_empty(row.get(column)) for column in columns})

    return columns, rows, source_last_modified


def build_schema(columns: list[str]) -> pa.Schema:
    """Build schema preserving CSV columns plus standardized metadata fields."""
    fields = [pa.field(column, pa.string()) for column in columns]
    fields.extend(
        [
            pa.field("_meta_pipeline_run_id", pa.string()),
            pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
            pa.field("_meta_source_system", pa.string()),
            pa.field("_meta_source_key", pa.string()),
            pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
            pa.field("_meta_schema_version", pa.int64()),
        ]
    )
    return pa.schema(fields)


def add_metadata_columns(
    rows: list[dict[str, Any]],
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    source_last_modified_utc: datetime | None,
) -> None:
    """Attach standardized metadata contract columns to each row."""
    for row in rows:
        row["_meta_pipeline_run_id"] = pipeline_run_id
        row["_meta_ingested_at_utc"] = ingested_at_utc
        row["_meta_source_system"] = META_SOURCE_SYSTEM
        row["_meta_source_key"] = SOURCE_KEY
        row["_meta_source_last_modified_utc"] = source_last_modified_utc
        row["_meta_schema_version"] = META_SCHEMA_VERSION


def write_parquet_to_s3(columns: list[str], rows: list[dict[str, Any]], s3_client) -> None:
    """Write rows to S3 as one parquet object."""
    table = pa.Table.from_pylist(rows, schema=build_schema(columns))
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
    """Run transform from raw TeamHistories CSV to silver parquet."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"team_histories_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    print(f"Reading s3://{S3_BUCKET}/{SOURCE_KEY}")
    columns, rows, source_last_modified_utc = read_source_rows(s3_client)
    print(f"Loaded {len(rows)} rows and {len(columns)} columns")

    add_metadata_columns(
        rows,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        source_last_modified_utc=source_last_modified_utc,
    )
    write_parquet_to_s3(columns, rows, s3_client)
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
        "source_column_count": len(columns),
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
