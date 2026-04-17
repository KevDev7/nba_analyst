from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

QUARANTINE_REASON_CODE_COL = "_dq_reason_code"
QUARANTINE_REASON_LEVEL_COL = "_dq_reason_level"
QUARANTINE_REASON_DETAIL_COL = "_dq_reason_detail"
QUARANTINE_DETECTED_AT_COL = "_dq_detected_at_utc"
QUARANTINE_TABLE_COL = "_dq_table_name"


def to_utc(value: datetime | None) -> datetime | None:
    """Normalize datetime to timezone-aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def run_date(ingested_at_utc: datetime) -> str:
    """Render run date partition in UTC."""
    return to_utc(ingested_at_utc).strftime("%Y-%m-%d")


def quarantine_key(table_name: str, pipeline_run_id: str, ingested_at_utc: datetime) -> str:
    """Build quarantine output key for a table run."""
    return (
        f"silver/_quarantine/{table_name}/"
        f"run_date={run_date(ingested_at_utc)}/{pipeline_run_id}.parquet"
    )


def audit_json_key(table_name: str, pipeline_run_id: str, ingested_at_utc: datetime) -> str:
    """Build JSON audit key for a table run."""
    return (
        f"silver/_audit/{table_name}/"
        f"run_date={run_date(ingested_at_utc)}/{pipeline_run_id}.json"
    )


def audit_parquet_key(table_name: str, pipeline_run_id: str, ingested_at_utc: datetime) -> str:
    """Build parquet audit key for a table run."""
    return (
        f"silver/_audit/{table_name}/"
        f"run_date={run_date(ingested_at_utc)}/{pipeline_run_id}.parquet"
    )


def build_quarantine_schema(target_schema: pa.Schema) -> pa.Schema:
    """Create quarantine schema from target schema + DQ metadata columns."""
    return pa.schema(
        list(target_schema)
        + [
            pa.field(QUARANTINE_REASON_CODE_COL, pa.string()),
            pa.field(QUARANTINE_REASON_LEVEL_COL, pa.string()),
            pa.field(QUARANTINE_REASON_DETAIL_COL, pa.string()),
            pa.field(QUARANTINE_DETECTED_AT_COL, pa.timestamp("us", tz="UTC")),
            pa.field(QUARANTINE_TABLE_COL, pa.string()),
        ]
    )


def make_quarantine_row(
    row: dict[str, Any],
    *,
    table_name: str,
    reason_code: str,
    reason_level: str,
    reason_detail: str,
    detected_at_utc: datetime,
) -> dict[str, Any]:
    """Copy row and append standardized quarantine metadata fields."""
    q = dict(row)
    q[QUARANTINE_REASON_CODE_COL] = reason_code
    q[QUARANTINE_REASON_LEVEL_COL] = reason_level
    q[QUARANTINE_REASON_DETAIL_COL] = reason_detail
    q[QUARANTINE_DETECTED_AT_COL] = to_utc(detected_at_utc)
    q[QUARANTINE_TABLE_COL] = table_name
    return q


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        as_utc = to_utc(value)
        return as_utc.isoformat().replace("+00:00", "Z")
    return str(value)


def write_rows_as_parquet(
    *,
    s3_client,
    bucket: str,
    key: str,
    rows: list[dict[str, Any]],
    schema: pa.Schema,
) -> None:
    """Write rows to S3 parquet with explicit schema."""
    table = pa.Table.from_pylist(rows, schema=schema)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )


def write_quarantine_rows(
    *,
    s3_client,
    bucket: str,
    table_name: str,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    rows: list[dict[str, Any]],
    target_schema: pa.Schema,
) -> str | None:
    """Write quarantine rows if any and return S3 key (None when no rows)."""
    if not rows:
        return None
    key = quarantine_key(table_name, pipeline_run_id, ingested_at_utc)
    write_rows_as_parquet(
        s3_client=s3_client,
        bucket=bucket,
        key=key,
        rows=rows,
        schema=build_quarantine_schema(target_schema),
    )
    return key


def write_audit_artifacts(
    *,
    s3_client,
    bucket: str,
    table_name: str,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    audit_row: dict[str, Any],
) -> tuple[str, str]:
    """Write JSON + parquet audit artifacts and return both keys."""
    json_key = audit_json_key(table_name, pipeline_run_id, ingested_at_utc)
    parquet_key = audit_parquet_key(table_name, pipeline_run_id, ingested_at_utc)

    json_body = json.dumps(audit_row, default=_json_default, sort_keys=True).encode("utf-8")
    s3_client.put_object(
        Bucket=bucket,
        Key=json_key,
        Body=json_body,
        ContentType="application/json",
    )

    table = pa.Table.from_pylist([audit_row])
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=bucket,
        Key=parquet_key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )

    return json_key, parquet_key
