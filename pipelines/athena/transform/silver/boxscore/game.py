"""
Transform raw CDN boxscore JSON files into a silver game-level parquet table.

Reads all objects under:
  s3://nba-analytics-lakehouse-dev/raw/cdn/boxscore/

Writes (single object, rewritten on each run):
  s3://nba-analytics-lakehouse-dev/silver/boxscore_game.parquet

Deduplication / upsert semantics:
  - Grain is one row per gameId.
  - If duplicate gameId appears across source files, keep the latest version:
    1) Higher meta_time from JSON wins.
    2) If meta_time ties (or both missing), higher S3 LastModified wins.
"""

from __future__ import annotations

import io
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from boxscore.contracts import (
    CDN_BOXSCORE_SOURCE_PREFIX,
    CDN_BOXSCORE_SOURCE_SYSTEM,
    META_SCHEMA_VERSION,
    S3_BUCKET,
)
from boxscore.sources import (
    build_latest_cdn_boxscore_candidates,
    null_if_empty,
    parse_iso_to_utc,
    parse_meta_time_to_utc,
    to_int_or_none,
)
from silver_pipeline_helpers import make_quarantine_row, write_audit_artifacts, write_quarantine_rows

load_dotenv(override=True)  # Ensure .env credentials override any system variables

SOURCE_PREFIX = CDN_BOXSCORE_SOURCE_PREFIX
DESTINATION_KEY = "silver/boxscore_game.parquet"
TABLE_NAME = "boxscore_game"
META_SOURCE_SYSTEM = CDN_BOXSCORE_SOURCE_SYSTEM

TARGET_SCHEMA = pa.schema(
    [
        pa.field("meta_version", pa.int64()),
        pa.field("meta_code", pa.int64()),
        pa.field("meta_request", pa.string()),
        pa.field("meta_time", pa.timestamp("us", tz="UTC")),
        pa.field("gameId", pa.string()),
        pa.field("gameCode", pa.string()),
        pa.field("gameTimeLocal", pa.timestamp("us", tz="UTC")),
        pa.field("gameTimeUTC", pa.timestamp("us", tz="UTC")),
        pa.field("gameTimeHome", pa.timestamp("us", tz="UTC")),
        pa.field("gameTimeAway", pa.timestamp("us", tz="UTC")),
        pa.field("gameEt", pa.timestamp("us", tz="UTC")),
        pa.field("duration", pa.int64()),
        pa.field("gameStatus", pa.int64()),
        pa.field("gameStatusText", pa.string()),
        pa.field("regulationPeriods", pa.int64()),
        pa.field("period", pa.int64()),
        pa.field("gameClock", pa.string()),
        pa.field("attendance", pa.int64()),
        pa.field("sellout", pa.int64()),
        pa.field("arenaId", pa.int64()),
        pa.field("arenaName", pa.string()),
        pa.field("arenaCity", pa.string()),
        pa.field("arenaState", pa.string()),
        pa.field("arenaCountry", pa.string()),
        pa.field("arenaTimezone", pa.string()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def build_game_row(payload: dict[str, Any]) -> dict[str, Any]:
    """Build one game-level row from a raw boxscore payload."""
    meta = payload.get("meta") or {}
    game = payload.get("game") or {}
    arena = game.get("arena") or {}

    return {
        "meta_version": to_int_or_none(meta.get("version")),
        "meta_code": to_int_or_none(meta.get("code")),
        "meta_request": null_if_empty(meta.get("request")),
        "meta_time": parse_meta_time_to_utc(meta.get("time")),
        "gameId": null_if_empty(game.get("gameId")),
        "gameCode": null_if_empty(game.get("gameCode")),
        "gameTimeLocal": parse_iso_to_utc(game.get("gameTimeLocal")),
        "gameTimeUTC": parse_iso_to_utc(game.get("gameTimeUTC")),
        "gameTimeHome": parse_iso_to_utc(game.get("gameTimeHome")),
        "gameTimeAway": parse_iso_to_utc(game.get("gameTimeAway")),
        "gameEt": parse_iso_to_utc(game.get("gameEt")),
        "duration": to_int_or_none(game.get("duration")),
        "gameStatus": to_int_or_none(game.get("gameStatus")),
        "gameStatusText": null_if_empty(game.get("gameStatusText")),
        "regulationPeriods": to_int_or_none(game.get("regulationPeriods")),
        "period": to_int_or_none(game.get("period")),
        "gameClock": null_if_empty(game.get("gameClock")),
        "attendance": to_int_or_none(game.get("attendance")),
        "sellout": to_int_or_none(game.get("sellout")),
        "arenaId": to_int_or_none(arena.get("arenaId")),
        "arenaName": null_if_empty(arena.get("arenaName")),
        "arenaCity": null_if_empty(arena.get("arenaCity")),
        "arenaState": null_if_empty(arena.get("arenaState")),
        "arenaCountry": null_if_empty(arena.get("arenaCountry")),
        "arenaTimezone": null_if_empty(arena.get("arenaTimezone")),
    }


def build_latest_game_rows(s3_client) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load all source files and keep only the latest row version for each gameId."""
    latest_by_game_id, source_metrics = build_latest_cdn_boxscore_candidates(
        s3_client,
        bucket=S3_BUCKET,
        source_prefix=SOURCE_PREFIX,
    )

    rows: list[dict[str, Any]] = []
    for game_id in sorted(latest_by_game_id):
        candidate = latest_by_game_id[game_id]
        row = build_game_row(candidate.payload)
        row["gameId"] = candidate.game_id
        row["_meta_source_key"] = candidate.source_key
        row["_meta_source_last_modified_utc"] = candidate.source_last_modified_utc
        rows.append(row)
    rows.sort(key=lambda x: (x.get("gameTimeUTC") or datetime.min.replace(tzinfo=timezone.utc), x.get("gameId") or ""))

    print(f"Built {len(rows)} deduplicated game rows")
    print(f"Replaced duplicates by recency: {source_metrics['source_replaced_by_recency']}")
    print(f"Skipped rows without gameId: {source_metrics['source_skipped_without_game_id']}")
    print(f"Failed source reads/parses: {source_metrics['source_failed_reads']}")
    return rows, source_metrics


def quality_score(row: dict[str, Any]) -> int:
    """Score row completeness for deterministic uniqueness enforcement."""
    score_columns = [
        "gameId",
        "gameCode",
        "gameTimeUTC",
        "gameStatus",
        "gameStatusText",
        "arenaName",
        "_meta_source_key",
        "_meta_source_last_modified_utc",
    ]
    return sum(1 for col in score_columns if row.get(col) is not None)


def validate_and_dedupe_rows(
    rows: list[dict[str, Any]],
    detected_at_utc: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Validate rows, quarantine hard failures, and enforce one row per gameId."""
    deduped: dict[str, dict[str, Any]] = {}
    quarantine_rows: list[dict[str, Any]] = []
    dropped_missing_game_id = 0
    replaced_for_quality = 0
    warning_count = 0
    error_reason_counts: Counter[str] = Counter()
    warning_reason_counts: Counter[str] = Counter()

    for row in rows:
        game_id = null_if_empty(row.get("gameId"))
        if game_id is None:
            dropped_missing_game_id += 1
            error_reason_counts["missing_game_id"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="missing_game_id",
                    reason_level="error",
                    reason_detail="gameId is null/blank",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue
        row["gameId"] = str(game_id)

        duration = to_int_or_none(row.get("duration"))
        if duration is not None and duration < 0:
            error_reason_counts["negative_duration"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="negative_duration",
                    reason_level="error",
                    reason_detail="duration is negative",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        attendance = to_int_or_none(row.get("attendance"))
        if attendance is not None and attendance < 0:
            error_reason_counts["negative_attendance"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="negative_attendance",
                    reason_level="error",
                    reason_detail="attendance is negative",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        sellout = to_int_or_none(row.get("sellout"))
        if sellout is not None and sellout not in {0, 1}:
            error_reason_counts["invalid_sellout_flag"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="invalid_sellout_flag",
                    reason_level="error",
                    reason_detail=f"sellout has invalid value={sellout}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        period = to_int_or_none(row.get("period"))
        if period is not None and period < 0:
            error_reason_counts["negative_period"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="negative_period",
                    reason_level="error",
                    reason_detail=f"period has invalid negative value={period}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue
        if period is not None and period > 10:
            warning_count += 1
            warning_reason_counts["high_period_value"] += 1

        game_status = to_int_or_none(row.get("gameStatus"))
        if game_status is not None and game_status not in {0, 1, 2, 3}:
            warning_count += 1
            warning_reason_counts["unexpected_game_status"] += 1

        if row.get("gameTimeUTC") is None:
            warning_count += 1
            warning_reason_counts["missing_game_time_utc"] += 1

        current = deduped.get(row["gameId"])
        if current is None:
            deduped[row["gameId"]] = row
            continue

        if quality_score(row) > quality_score(current):
            deduped[row["gameId"]] = row
            replaced_for_quality += 1

    output = sorted(
        deduped.values(),
        key=lambda x: (
            x.get("gameTimeUTC") or datetime.min.replace(tzinfo=timezone.utc),
            x.get("gameId") or "",
        ),
    )

    print(f"Quality gate: dropped rows missing gameId: {dropped_missing_game_id}")
    print(f"Quality gate: replacements by higher-quality duplicate gameId: {replaced_for_quality}")
    print(f"Quality gate: unique gameId rows: {len(output)}")
    print(f"Quality gate: warning count: {warning_count}")
    print(f"Quality gate: quarantined error rows: {len(quarantine_rows)}")

    dq_metrics = {
        "input_rows": len(rows),
        "output_rows": len(output),
        "quarantine_rows": len(quarantine_rows),
        "warning_count": warning_count,
        "error_count": len(quarantine_rows),
        "dropped_missing_game_id": dropped_missing_game_id,
        "replaced_for_quality": replaced_for_quality,
        "error_reason_counts": dict(error_reason_counts),
        "warning_reason_counts": dict(warning_reason_counts),
    }
    return output, quarantine_rows, dq_metrics


def add_metadata_columns(rows: list[dict[str, Any]], pipeline_run_id: str, ingested_at_utc: datetime) -> None:
    """Attach standardized metadata contract columns to each row."""
    for row in rows:
        source_last_modified = row.get("_meta_source_last_modified_utc")
        if isinstance(source_last_modified, datetime) and source_last_modified.tzinfo is None:
            source_last_modified = source_last_modified.replace(tzinfo=timezone.utc)

        row["_meta_pipeline_run_id"] = pipeline_run_id
        row["_meta_ingested_at_utc"] = ingested_at_utc
        row["_meta_source_system"] = META_SOURCE_SYSTEM
        row["_meta_source_key"] = null_if_empty(row.get("_meta_source_key"))
        row["_meta_source_last_modified_utc"] = source_last_modified
        row["_meta_schema_version"] = META_SCHEMA_VERSION


def write_parquet_to_s3(rows: list[dict[str, Any]], s3_client) -> None:
    """Write final game-level parquet to S3 (rewrites same destination key)."""
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
    """Run the boxscore game silver transform."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"boxscore_game_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    rows, source_metrics = build_latest_game_rows(s3_client)
    input_row_count = len(rows)
    rows, quarantine_rows, dq_metrics = validate_and_dedupe_rows(rows, detected_at_utc=ingested_at_utc)
    add_metadata_columns(rows, pipeline_run_id=pipeline_run_id, ingested_at_utc=ingested_at_utc)
    add_metadata_columns(quarantine_rows, pipeline_run_id=pipeline_run_id, ingested_at_utc=ingested_at_utc)

    quarantine_output_key = write_quarantine_rows(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        rows=quarantine_rows,
        target_schema=TARGET_SCHEMA,
    )
    if quarantine_output_key:
        print(f"Wrote quarantine rows to s3://{S3_BUCKET}/{quarantine_output_key}")

    run_status = "success"
    if dq_metrics["error_count"] > 0:
        run_status = "failed"
    elif dq_metrics["warning_count"] > 0:
        run_status = "success_with_warnings"

    if dq_metrics["error_count"] == 0:
        write_parquet_to_s3(rows, s3_client)
        print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")
    else:
        print(
            "Skipping main silver write because hard validation errors were quarantined: "
            f"{dq_metrics['error_count']}"
        )

    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": run_status,
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_prefix": SOURCE_PREFIX,
        "source_json_object_count": source_metrics["source_json_object_count"],
        "source_min_last_modified_utc": source_metrics["source_min_last_modified_utc"],
        "source_max_last_modified_utc": source_metrics["source_max_last_modified_utc"],
        "source_skipped_without_game_id": source_metrics["source_skipped_without_game_id"],
        "source_failed_reads": source_metrics["source_failed_reads"],
        "source_replaced_by_recency": source_metrics["source_replaced_by_recency"],
        "source_deduped_game_count": source_metrics["source_deduped_game_count"],
        "destination_key": DESTINATION_KEY,
        "quarantine_key": quarantine_output_key,
        "input_row_count": input_row_count,
        "output_row_count": len(rows),
        "quarantine_row_count": dq_metrics["quarantine_rows"],
        "warning_count": dq_metrics["warning_count"],
        "error_count": dq_metrics["error_count"],
        "dropped_missing_game_id": dq_metrics["dropped_missing_game_id"],
        "replaced_for_quality": dq_metrics["replaced_for_quality"],
        "error_reason_counts": json.dumps(dq_metrics["error_reason_counts"], sort_keys=True),
        "warning_reason_counts": json.dumps(dq_metrics["warning_reason_counts"], sort_keys=True),
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

    if dq_metrics["error_count"] > 0:
        raise RuntimeError(
            f"{TABLE_NAME} run failed: quarantined error rows={dq_metrics['error_count']}"
        )


if __name__ == "__main__":
    main()
