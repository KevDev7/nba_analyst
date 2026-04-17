"""
Transform raw CDN boxscore JSON files into a silver team-game-period parquet table.

Reads all objects under:
  s3://nba-analytics-lakehouse-dev/raw/cdn/boxscore/

Writes (single object, rewritten on each run):
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_period.parquet

Deduplication / upsert semantics:
  - Final grain is one row per (gameId, team_side, period_number).
  - Source dedup is first done at gameId level.
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
from silver_pipeline_helpers import make_quarantine_row, write_audit_artifacts, write_quarantine_rows

load_dotenv(override=True)  # Ensure .env credentials override any system variables

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "raw/cdn/boxscore/"
DESTINATION_KEY = "silver/boxscore_team_period.parquet"
TABLE_NAME = "boxscore_team_period"
META_SOURCE_SYSTEM = "nba_cdn_boxscore"
META_SCHEMA_VERSION = 1

TARGET_SCHEMA = pa.schema(
    [
        pa.field("gameId", pa.string()),
        pa.field("teamId", pa.int64()),
        pa.field("team_side", pa.string()),
        pa.field("period_number", pa.int64()),
        pa.field("periodType", pa.string()),
        pa.field("period_score", pa.int64()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def null_if_empty(value: Any) -> Any:
    """Convert empty/blank strings to None; keep all other values unchanged."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def to_int_or_none(value: Any) -> int | None:
    """Convert numeric-like input into int; return None for empty-like values."""
    value = null_if_empty(value)
    if value is None:
        return None
    return int(value)


def parse_iso_to_utc(value: Any) -> datetime | None:
    """Parse ISO-like datetime strings to timezone-aware UTC datetime."""
    value = null_if_empty(value)
    if value is None:
        return None

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_meta_time_to_utc(value: Any) -> datetime | None:
    """Parse meta_time into timezone-aware UTC datetime."""
    value = null_if_empty(value)
    if value is None:
        return None

    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return parse_iso_to_utc(text)


def extract_game_id_from_key(key: str) -> str | None:
    """Fallback parser for keys like raw/cdn/boxscore/game_id=0022500857.json."""
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id=") or not filename.endswith(".json"):
        return None
    return filename[len("game_id=") : -len(".json")] or None


def list_source_json_objects(s3_client) -> list[dict[str, Any]]:
    """List all source JSON objects under the boxscore raw prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".json"):
                objects.append(obj)

    return objects


def read_json_object(s3_client, key: str) -> dict[str, Any]:
    """Read and decode one JSON object from S3."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload_bytes = response["Body"].read()
    return json.loads(payload_bytes)


def build_game_candidate(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Build one dedupe candidate at game grain."""
    meta = payload.get("meta") or {}
    game = payload.get("game") or {}

    game_id = null_if_empty(game.get("gameId")) or extract_game_id_from_key(key)
    if game_id is None:
        return None

    return {
        "gameId": game_id,
        "meta_time": parse_meta_time_to_utc(meta.get("time")),
        "homeTeam": game.get("homeTeam") or {},
        "awayTeam": game.get("awayTeam") or {},
        "_meta_source_key": key,
    }


def is_newer_candidate(
    current_meta_time: datetime | None,
    current_last_modified: datetime | None,
    candidate_meta_time: datetime | None,
    candidate_last_modified: datetime | None,
) -> bool:
    """Return True if candidate should replace current using defined precedence."""
    min_utc = datetime.min.replace(tzinfo=timezone.utc)

    current_meta_key = current_meta_time or min_utc
    candidate_meta_key = candidate_meta_time or min_utc
    if candidate_meta_key > current_meta_key:
        return True
    if candidate_meta_key < current_meta_key:
        return False

    current_lm_key = current_last_modified or min_utc
    candidate_lm_key = candidate_last_modified or min_utc
    return candidate_lm_key > current_lm_key


def to_team_period_rows(
    game_id: str,
    team_side: str,
    team_obj: dict[str, Any],
    source_key: str | None,
    source_last_modified_utc: datetime | None,
) -> list[dict[str, Any]]:
    """Build team-period rows for one side (home or away) of a game."""
    team_id = to_int_or_none(team_obj.get("teamId"))
    periods = team_obj.get("periods") or []

    rows: list[dict[str, Any]] = []
    for period_obj in periods:
        rows.append(
            {
                "gameId": game_id,
                "teamId": team_id,
                "team_side": team_side,
                "period_number": to_int_or_none(period_obj.get("period")),
                "periodType": null_if_empty(period_obj.get("periodType")),
                "period_score": to_int_or_none(period_obj.get("score")),
                "_meta_source_key": source_key,
                "_meta_source_last_modified_utc": source_last_modified_utc,
            }
        )
    return rows


def build_latest_team_period_rows(s3_client) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load source files, dedupe by gameId recency, then emit team-period rows."""
    objects = list_source_json_objects(s3_client)
    print(f"Discovered {len(objects)} source JSON objects under {SOURCE_PREFIX}")

    latest_by_game_id: dict[str, tuple[dict[str, Any], datetime | None, datetime | None]] = {}

    skipped_without_game_id = 0
    failed_reads = 0
    replaced_count = 0
    min_last_modified_utc: datetime | None = None
    max_last_modified_utc: datetime | None = None

    for obj in objects:
        key = obj.get("Key", "")
        last_modified = obj.get("LastModified")
        if isinstance(last_modified, datetime) and last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)
        if isinstance(last_modified, datetime):
            if min_last_modified_utc is None or last_modified < min_last_modified_utc:
                min_last_modified_utc = last_modified
            if max_last_modified_utc is None or last_modified > max_last_modified_utc:
                max_last_modified_utc = last_modified

        try:
            payload = read_json_object(s3_client, key)
            candidate = build_game_candidate(payload, key)
        except Exception as exc:
            failed_reads += 1
            print(f"Failed to parse {key}: {type(exc).__name__}: {exc}")
            continue

        if candidate is None:
            skipped_without_game_id += 1
            continue

        game_id = candidate["gameId"]
        candidate_meta_time = candidate.get("meta_time")
        current = latest_by_game_id.get(game_id)
        if current is None:
            latest_by_game_id[game_id] = (candidate, candidate_meta_time, last_modified)
            continue

        _, current_meta_time, current_last_modified = current
        if is_newer_candidate(
            current_meta_time=current_meta_time,
            current_last_modified=current_last_modified,
            candidate_meta_time=candidate_meta_time,
            candidate_last_modified=last_modified,
        ):
            latest_by_game_id[game_id] = (candidate, candidate_meta_time, last_modified)
            replaced_count += 1

    rows: list[dict[str, Any]] = []
    for game_id in sorted(latest_by_game_id.keys()):
        candidate, _, source_last_modified = latest_by_game_id[game_id]
        source_key = null_if_empty(candidate.get("_meta_source_key"))
        rows.extend(
            to_team_period_rows(
                game_id,
                "home",
                candidate.get("homeTeam") or {},
                source_key=source_key,
                source_last_modified_utc=source_last_modified,
            )
        )
        rows.extend(
            to_team_period_rows(
                game_id,
                "away",
                candidate.get("awayTeam") or {},
                source_key=source_key,
                source_last_modified_utc=source_last_modified,
            )
        )

    rows.sort(key=lambda x: (x.get("gameId") or "", x.get("team_side") or "", x.get("period_number") or -1))

    print(f"Built {len(rows)} team-game-period rows")
    print(f"Unique deduped games: {len(latest_by_game_id)}")
    print(f"Replaced duplicates by recency: {replaced_count}")
    print(f"Skipped rows without gameId: {skipped_without_game_id}")
    print(f"Failed source reads/parses: {failed_reads}")

    source_metrics = {
        "source_json_object_count": len(objects),
        "source_min_last_modified_utc": min_last_modified_utc,
        "source_max_last_modified_utc": max_last_modified_utc,
        "source_skipped_without_game_id": skipped_without_game_id,
        "source_failed_reads": failed_reads,
        "source_replaced_by_recency": replaced_count,
        "source_deduped_game_count": len(latest_by_game_id),
    }
    return rows, source_metrics


def quality_score(row: dict[str, Any]) -> int:
    """Score row completeness for deterministic duplicate resolution."""
    score_columns = [
        "gameId",
        "team_side",
        "period_number",
        "teamId",
        "periodType",
        "period_score",
        "_meta_source_key",
        "_meta_source_last_modified_utc",
    ]
    return sum(1 for col in score_columns if row.get(col) is not None)


def validate_and_dedupe_rows(
    rows: list[dict[str, Any]],
    detected_at_utc: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Validate rows, quarantine hard failures, and enforce one row per key grain."""
    deduped: dict[tuple[str, str, int], dict[str, Any]] = {}
    quarantine_rows: list[dict[str, Any]] = []
    dropped_missing_game_id = 0
    dropped_missing_team_side = 0
    dropped_missing_period_number = 0
    replaced_for_quality = 0
    warning_count = 0
    error_reason_counts: Counter[str] = Counter()
    warning_reason_counts: Counter[str] = Counter()

    for row in rows:
        game_id = null_if_empty(row.get("gameId"))
        team_side = null_if_empty(row.get("team_side"))
        period_number = to_int_or_none(row.get("period_number"))

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
        if team_side is None:
            dropped_missing_team_side += 1
            error_reason_counts["missing_team_side"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="missing_team_side",
                    reason_level="error",
                    reason_detail="team_side is null/blank",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue
        if period_number is None:
            dropped_missing_period_number += 1
            error_reason_counts["missing_period_number"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="missing_period_number",
                    reason_level="error",
                    reason_detail="period_number is null",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        row["gameId"] = str(game_id)
        row["team_side"] = str(team_side)
        row["period_number"] = period_number

        if row["team_side"] not in {"home", "away"}:
            error_reason_counts["invalid_team_side"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="invalid_team_side",
                    reason_level="error",
                    reason_detail=f"team_side must be home/away, got={row['team_side']}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        if period_number < 1:
            error_reason_counts["invalid_period_number"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="invalid_period_number",
                    reason_level="error",
                    reason_detail=f"period_number must be >= 1, got={period_number}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        period_score = to_int_or_none(row.get("period_score"))
        if period_score is not None and period_score < 0:
            error_reason_counts["negative_period_score"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="negative_period_score",
                    reason_level="error",
                    reason_detail=f"period_score is negative={period_score}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        if period_number > 10:
            warning_count += 1
            warning_reason_counts["high_period_number"] += 1

        team_id = to_int_or_none(row.get("teamId"))
        if team_id is None:
            warning_count += 1
            warning_reason_counts["missing_team_id"] += 1
        else:
            row["teamId"] = team_id

        key = (row["gameId"], row["team_side"], period_number)
        current = deduped.get(key)
        if current is None:
            deduped[key] = row
            continue

        if quality_score(row) > quality_score(current):
            deduped[key] = row
            replaced_for_quality += 1

    output = sorted(
        deduped.values(),
        key=lambda x: (x.get("gameId") or "", x.get("team_side") or "", x.get("period_number") or -1),
    )

    print(f"Quality gate: dropped rows missing gameId: {dropped_missing_game_id}")
    print(f"Quality gate: dropped rows missing team_side: {dropped_missing_team_side}")
    print(f"Quality gate: dropped rows missing period_number: {dropped_missing_period_number}")
    print(
        "Quality gate: replacements by higher-quality duplicate "
        f"(gameId, team_side, period_number): {replaced_for_quality}"
    )
    print(f"Quality gate: unique (gameId, team_side, period_number) rows: {len(output)}")
    print(f"Quality gate: warning count: {warning_count}")
    print(f"Quality gate: quarantined error rows: {len(quarantine_rows)}")

    dq_metrics = {
        "input_rows": len(rows),
        "output_rows": len(output),
        "quarantine_rows": len(quarantine_rows),
        "warning_count": warning_count,
        "error_count": len(quarantine_rows),
        "dropped_missing_game_id": dropped_missing_game_id,
        "dropped_missing_team_side": dropped_missing_team_side,
        "dropped_missing_period_number": dropped_missing_period_number,
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
    """Write final team-game-period parquet to S3 (rewrites same destination key)."""
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
    """Run the boxscore team-game-period silver transform."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"boxscore_team_period_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    rows, source_metrics = build_latest_team_period_rows(s3_client)
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
        "dropped_missing_team_side": dq_metrics["dropped_missing_team_side"],
        "dropped_missing_period_number": dq_metrics["dropped_missing_period_number"],
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
