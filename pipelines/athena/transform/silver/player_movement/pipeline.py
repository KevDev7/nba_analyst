from __future__ import annotations

import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

try:
    from silver_pipeline_helpers import write_audit_artifacts
except ModuleNotFoundError:
    from pipelines.athena.transform.silver.silver_pipeline_helpers import write_audit_artifacts

from .contracts import (
    DESTINATION_KEY,
    S3_BUCKET,
    SOURCE_KEY,
    TABLE_NAME,
    TARGET_SCHEMA,
)
from .transform import add_metadata_columns, build_rows


load_dotenv(override=True)


def read_source_payload(s3_client) -> tuple[dict[str, Any], datetime | None]:
    """Read source JSON payload from S3 with source last-modified."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=SOURCE_KEY)
    payload_bytes = response["Body"].read()
    source_last_modified = response.get("LastModified")
    if isinstance(source_last_modified, datetime) and source_last_modified.tzinfo is None:
        source_last_modified = source_last_modified.replace(tzinfo=timezone.utc)
    return json.loads(payload_bytes), source_last_modified


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


def build_audit_row(
    *,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    source_last_modified_utc: datetime | None,
    row_count: int,
    warning_reason_counts: dict[str, int],
) -> dict[str, Any]:
    warning_count = sum(warning_reason_counts.values())
    run_status = "success_with_warnings" if warning_count > 0 else "success"
    return {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": run_status,
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_key": SOURCE_KEY,
        "source_last_modified_utc": source_last_modified_utc,
        "destination_key": DESTINATION_KEY,
        "input_row_count": row_count,
        "output_row_count": row_count,
        "warning_count": warning_count,
        "error_count": 0,
        "warning_reason_counts": json.dumps(warning_reason_counts, sort_keys=True),
        "error_reason_counts": "{}",
    }


def main() -> None:
    """Run transform for the configured snapshot partition."""
    if os.getenv("AWS_PROFILE") == "":
        os.environ.pop("AWS_PROFILE", None)
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

    warning_reason_counts: dict[str, int] = {}
    if len(rows) == 0:
        warning_reason_counts["empty_source_rows"] = 1

    audit_row = build_audit_row(
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        source_last_modified_utc=source_last_modified_utc,
        row_count=len(rows),
        warning_reason_counts=warning_reason_counts,
    )
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
