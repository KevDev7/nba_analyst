"""
Transform raw Basketball Reference player profile HTML snapshots into a structured silver awards table.
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

from bbr.awards_parser import SOURCE_PREFIX, build_award_artifacts, parse_source_key
from bbr.sources import get_latest_sources, iter_latest_raw_snapshots

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"
DESTINATION_KEY = "silver/bbr_player_awards.parquet"
TABLE_NAME = "bbr_player_awards"
META_SOURCE_SYSTEM = "basketball_reference_player_profile_html"
META_SCHEMA_VERSION = 1

TARGET_SCHEMA = pa.schema(
    [
        pa.field("basketball_reference_player_id", pa.string()),
        pa.field("player_profile_url", pa.string()),
        pa.field("page_player_name", pa.string()),
        pa.field("source_section", pa.string()),
        pa.field("award_family", pa.string()),
        pa.field("league_code", pa.string()),
        pa.field("season_label", pa.string()),
        pa.field("team_tier", pa.int64()),
        pa.field("award_label_raw", pa.string()),
        pa.field("award_reference_url", pa.string()),
        pa.field("source_snapshot_fetched_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def add_metadata_columns(rows: list[dict[str, Any]], *, pipeline_run_id: str, ingested_at_utc: datetime) -> None:
    for row in rows:
        row["_meta_pipeline_run_id"] = pipeline_run_id
        row["_meta_ingested_at_utc"] = ingested_at_utc
        row["_meta_source_system"] = META_SOURCE_SYSTEM
        row["_meta_schema_version"] = META_SCHEMA_VERSION


def write_parquet(rows: list[dict[str, Any]], s3_client) -> None:
    table = pa.Table.from_pylist(rows, schema=TARGET_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(Bucket=S3_BUCKET, Key=DESTINATION_KEY, Body=buffer.getvalue(), ContentType="application/octet-stream")


def main() -> None:
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"bbr_player_awards_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    source_objects, latest_sources = get_latest_sources(
        s3_client,
        bucket=S3_BUCKET,
        prefix=SOURCE_PREFIX,
        key_parser=parse_source_key,
    )
    rows, parse_failures, warning_reason_counts = build_award_artifacts(
        list(iter_latest_raw_snapshots(s3_client, bucket=S3_BUCKET, latest_sources=latest_sources))
    )
    add_metadata_columns(rows, pipeline_run_id=pipeline_run_id, ingested_at_utc=ingested_at_utc)
    write_parquet(rows, s3_client)

    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": "success_with_warnings" if warning_reason_counts else "success",
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_prefix": SOURCE_PREFIX,
        "destination_key": DESTINATION_KEY,
        "input_object_count": len(source_objects),
        "selected_latest_object_count": len(latest_sources),
        "output_row_count": len(rows),
        "warning_count": sum(warning_reason_counts.values()),
        "error_count": 0,
        "warning_reason_counts": json.dumps(dict(warning_reason_counts), sort_keys=True),
        "error_reason_counts": "{}",
    }
    write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )


if __name__ == "__main__":
    main()
