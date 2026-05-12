"""
Build silver shot-location events from existing silver play-by-play.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/playbyplay/game_id=<GAME_ID>.parquet

Writes:
  s3://nba-analytics-lakehouse-dev/silver/shot_location_events/game_id=<GAME_ID>.parquet

Grain:
  One row per field-goal event, keyed by (game_id, action_number).
"""

from __future__ import annotations

import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from heavy_silver_runtime import (
    build_source_index_from_objects,
    checkpoint_rows_with_updates,
    normalize_utc_datetime,
    parse_target_game_ids,
    read_checkpoint_index,
    select_game_ids_for_processing,
    write_checkpoint_index,
)
from silver_pipeline_helpers import write_audit_artifacts, write_rows_as_parquet

load_dotenv(override=True)
if os.environ.get("AWS_PROFILE") == "":
    os.environ.pop("AWS_PROFILE")

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "silver/playbyplay/"
DESTINATION_PREFIX = "silver/shot_location_events/"
TABLE_NAME = "shot_location_events"
META_SOURCE_SYSTEM = "silver_playbyplay_shot_location_projection"
META_SCHEMA_VERSION = 1
FORCE_FULL_REFRESH = (
    os.getenv("SHOT_LOCATION_EVENTS_FORCE_FULL_REFRESH", "false").strip().lower() == "true"
)
TARGET_GAME_IDS = parse_target_game_ids(os.getenv("SHOT_LOCATION_EVENTS_TARGET_GAME_IDS", ""))

SOURCE_COLUMNS = [
    "gameId",
    "actionNumber",
    "orderNumber",
    "period",
    "clock",
    "secondsRemainingInPeriod",
    "personId",
    "teamId",
    "teamTricode",
    "actionType",
    "subType",
    "descriptor",
    "shotResult",
    "shotValue",
    "isFieldGoal",
    "isMadeShot",
    "shotDistance",
    "area",
    "areaDetail",
    "x",
    "y",
    "xLegacy",
    "yLegacy",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("action_number", pa.int64()),
        pa.field("order_number", pa.int64()),
        pa.field("period", pa.int64()),
        pa.field("clock", pa.string()),
        pa.field("seconds_remaining_in_period", pa.float64()),
        pa.field("person_id", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("team_tricode", pa.string()),
        pa.field("action_type", pa.string()),
        pa.field("sub_type", pa.string()),
        pa.field("descriptor", pa.string()),
        pa.field("shot_result", pa.string()),
        pa.field("shot_value", pa.int64()),
        pa.field("is_made_shot", pa.bool_()),
        pa.field("shot_distance", pa.float64()),
        pa.field("x", pa.float64()),
        pa.field("y", pa.float64()),
        pa.field("x_legacy", pa.float64()),
        pa.field("y_legacy", pa.float64()),
        pa.field("source_area", pa.string()),
        pa.field("source_area_detail", pa.string()),
        pa.field("derived_area", pa.string()),
        pa.field("derived_area_detail", pa.string()),
        pa.field("shot_zone_area", pa.string()),
        pa.field("shot_zone_area_detail", pa.string()),
        pa.field("zone_source", pa.string()),
        pa.field("source_area_available_flag", pa.bool_()),
        pa.field("coordinate_available_flag", pa.bool_()),
        pa.field("source_derived_area_mismatch_flag", pa.bool_()),
        pa.field("derivation_warning", pa.string()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def null_if_empty(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def to_int_or_none(value: Any) -> int | None:
    value = null_if_empty(value)
    if value is None:
        return None
    return int(float(value))


def to_float_or_none(value: Any) -> float | None:
    value = null_if_empty(value)
    if value is None:
        return None
    return float(value)


def to_bool_or_none(value: Any) -> bool | None:
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def to_str_or_none(value: Any) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    return str(value)


def normalize_game_id(value: Any) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return text.zfill(10)
    return text


def extract_game_id_from_key(key: str) -> str | None:
    filename = key.rsplit("/", 1)[-1]
    match = re.fullmatch(r"game_id=(.+)\.parquet", filename)
    if match is None:
        return None
    return normalize_game_id(match.group(1))


def destination_key_for_game(game_id: str) -> str:
    normalized_game_id = normalize_game_id(game_id)
    if normalized_game_id is None:
        raise ValueError("game_id is required to build shot location destination key")
    return f"{DESTINATION_PREFIX}game_id={normalized_game_id}.parquet"


def list_source_objects(s3_client) -> list[dict[str, Any]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = str(obj.get("Key") or "")
            if key.endswith(".parquet") and extract_game_id_from_key(key) is not None:
                objects.append(obj)
    return objects


def read_source_rows(s3_client, key: str) -> list[dict[str, Any]]:
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload = response["Body"].read()
    schema = pq.read_schema(pa.BufferReader(payload))
    available_columns = [column for column in SOURCE_COLUMNS if column in schema.names]
    table = pq.read_table(pa.BufferReader(payload), columns=available_columns)
    rows = table.to_pylist()
    for row in rows:
        for column in SOURCE_COLUMNS:
            row.setdefault(column, None)
    return rows


def _side_label(x_ft: float | None) -> str:
    if x_ft is None:
        return "Center"
    if x_ft < -8:
        return "Left"
    if x_ft > 8:
        return "Right"
    return "Center"


def _wide_side_label(x_ft: float | None) -> str:
    if x_ft is None:
        return "Center"
    if x_ft < -16:
        return "Left"
    if x_ft < -8:
        return "Left Center"
    if x_ft > 16:
        return "Right"
    if x_ft > 8:
        return "Right Center"
    return "Center"


def _above_break_side_label(x_ft: float | None) -> str:
    if x_ft is None:
        return "Center"
    if x_ft < -8:
        return "Left Center"
    if x_ft > 8:
        return "Right Center"
    return "Center"


def _range_side_detail(distance_ft: float | None, x_ft: float | None) -> str | None:
    if distance_ft is None:
        return None
    if distance_ft < 8:
        return "0-8 Center"
    if distance_ft < 16:
        return f"8-16 {_side_label(x_ft)}"
    if distance_ft < 24:
        return f"16-24 {_wide_side_label(x_ft)}"
    return f"24+ {_above_break_side_label(x_ft)}"


def is_three_point_attempt(action_type: Any, shot_value: Any, shot_distance: Any) -> bool:
    action_text = (to_str_or_none(action_type) or "").strip().lower()
    shot_value_int = to_int_or_none(shot_value)
    distance = to_float_or_none(shot_distance)
    if shot_value_int == 3 or action_text == "3pt":
        return True
    return bool(distance is not None and distance >= 22.0)


def derive_location_from_coordinates(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Derive source-like NBA shot zones from legacy coordinates when source labels are absent."""
    x_legacy = to_float_or_none(row.get("xLegacy"))
    y_legacy = to_float_or_none(row.get("yLegacy"))
    distance = to_float_or_none(row.get("shotDistance"))
    if distance is None and x_legacy is not None and y_legacy is not None:
        distance = ((x_legacy / 10.0) ** 2 + (y_legacy / 10.0) ** 2) ** 0.5

    if x_legacy is None or y_legacy is None:
        return None, None, "missing_legacy_coordinates"

    x_ft = x_legacy / 10.0
    y_ft = y_legacy / 10.0

    if distance is not None and distance <= 4.3:
        return "Restricted Area", "0-8 Center", None

    if abs(x_ft) <= 8.0 and y_ft <= 13.75:
        return "In The Paint (Non-RA)", _range_side_detail(distance, x_ft), None

    if is_three_point_attempt(row.get("actionType"), row.get("shotValue"), row.get("shotDistance")):
        if abs(x_ft) >= 22.0 and y_ft <= 9.0:
            area = "Left Corner 3" if x_ft < 0 else "Right Corner 3"
            detail = "24+ Left" if x_ft < 0 else "24+ Right"
            return area, detail, None
        return "Above the Break 3", _range_side_detail(distance, x_ft), None

    return "Mid-Range", _range_side_detail(distance, x_ft), None


def is_field_goal_row(row: dict[str, Any]) -> bool:
    if to_bool_or_none(row.get("isFieldGoal")) is True:
        return True
    action_type = (to_str_or_none(row.get("actionType")) or "").strip().lower()
    return action_type in {"2pt", "3pt"}


def build_shot_location_rows(
    source_rows: list[dict[str, Any]],
    *,
    fallback_game_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_row in source_rows:
        if not is_field_goal_row(source_row):
            continue

        game_id = normalize_game_id(source_row.get("gameId")) or normalize_game_id(fallback_game_id)
        source_area = to_str_or_none(source_row.get("area"))
        source_area_detail = to_str_or_none(source_row.get("areaDetail"))
        derived_area, derived_area_detail, derivation_warning = derive_location_from_coordinates(source_row)

        source_area_available = source_area is not None
        coordinate_available = (
            to_float_or_none(source_row.get("xLegacy")) is not None
            and to_float_or_none(source_row.get("yLegacy")) is not None
        )
        shot_zone_area = source_area if source_area_available else derived_area
        shot_zone_area_detail = source_area_detail if source_area_detail is not None else derived_area_detail
        zone_source = "source_area" if source_area_available else "derived_from_legacy_coordinates"
        if shot_zone_area is None:
            zone_source = "unavailable"

        mismatch = (
            source_area is not None
            and derived_area is not None
            and source_area.strip().lower() != derived_area.strip().lower()
        )

        rows.append(
            {
                "game_id": game_id,
                "action_number": to_int_or_none(source_row.get("actionNumber")),
                "order_number": to_int_or_none(source_row.get("orderNumber")),
                "period": to_int_or_none(source_row.get("period")),
                "clock": to_str_or_none(source_row.get("clock")),
                "seconds_remaining_in_period": to_float_or_none(
                    source_row.get("secondsRemainingInPeriod")
                ),
                "person_id": to_int_or_none(source_row.get("personId")),
                "team_id": to_int_or_none(source_row.get("teamId")),
                "team_tricode": to_str_or_none(source_row.get("teamTricode")),
                "action_type": to_str_or_none(source_row.get("actionType")),
                "sub_type": to_str_or_none(source_row.get("subType")),
                "descriptor": to_str_or_none(source_row.get("descriptor")),
                "shot_result": to_str_or_none(source_row.get("shotResult")),
                "shot_value": to_int_or_none(source_row.get("shotValue")),
                "is_made_shot": to_bool_or_none(source_row.get("isMadeShot")),
                "shot_distance": to_float_or_none(source_row.get("shotDistance")),
                "x": to_float_or_none(source_row.get("x")),
                "y": to_float_or_none(source_row.get("y")),
                "x_legacy": to_float_or_none(source_row.get("xLegacy")),
                "y_legacy": to_float_or_none(source_row.get("yLegacy")),
                "source_area": source_area,
                "source_area_detail": source_area_detail,
                "derived_area": derived_area,
                "derived_area_detail": derived_area_detail,
                "shot_zone_area": shot_zone_area,
                "shot_zone_area_detail": shot_zone_area_detail,
                "zone_source": zone_source,
                "source_area_available_flag": source_area_available,
                "coordinate_available_flag": coordinate_available,
                "source_derived_area_mismatch_flag": mismatch,
                "derivation_warning": derivation_warning,
            }
        )
    return rows


def add_silver_metadata(
    rows: list[dict[str, Any]],
    *,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    source_key: str,
    source_last_modified_utc: datetime | None,
) -> list[dict[str, Any]]:
    normalized_last_modified = normalize_utc_datetime(source_last_modified_utc)
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        enriched["_meta_pipeline_run_id"] = pipeline_run_id
        enriched["_meta_ingested_at_utc"] = ingested_at_utc
        enriched["_meta_source_system"] = META_SOURCE_SYSTEM
        enriched["_meta_source_key"] = source_key
        enriched["_meta_source_last_modified_utc"] = normalized_last_modified
        enriched["_meta_schema_version"] = META_SCHEMA_VERSION
        enriched_rows.append(enriched)
    return enriched_rows


def write_game_parquet_to_s3(game_id: str, rows: list[dict[str, Any]], s3_client) -> None:
    write_rows_as_parquet(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        key=destination_key_for_game(game_id),
        rows=rows,
        schema=TARGET_SCHEMA,
    )


def main() -> None:
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = (
        f"shot_location_events_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_"
        f"{uuid.uuid4().hex[:8]}"
    )

    checkpoint_exists, checkpoint_rows = read_checkpoint_index(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
    )
    objects = list_source_objects(s3_client)
    source_last_modified_by_key = {
        str(obj.get("Key") or ""): normalize_utc_datetime(obj.get("LastModified"))
        for obj in objects
    }
    source_index = build_source_index_from_objects(objects, game_id_from_key=extract_game_id_from_key)
    selected_game_ids, selection_meta = select_game_ids_for_processing(
        source_index=source_index,
        target_game_ids=TARGET_GAME_IDS,
        force_full_refresh=FORCE_FULL_REFRESH,
        checkpoint_exists=checkpoint_exists,
        checkpoint_rows=checkpoint_rows,
    )
    keys = [
        source_index[game_id][0]["key"]
        for game_id in selected_game_ids
        if source_index.get(game_id)
    ]

    print(f"Mode: {selection_meta.get('selection_mode')}")
    if TARGET_GAME_IDS:
        print(f"Target game ids: {len(TARGET_GAME_IDS)}")
    print(f"Files discovered: {len(objects)}")
    print(f"Files selected: {len(keys)}")

    games_upserted: set[str] = set()
    total_source_rows = 0
    total_rows_written = 0
    skipped: list[tuple[str | None, str]] = []
    warning_reason_counts: dict[str, int] = {}
    source_area_available_count = 0
    coordinate_available_count = 0
    source_derived_area_mismatch_count = 0

    for index, key in enumerate(keys, start=1):
        game_id = extract_game_id_from_key(key)
        source_last_modified = source_last_modified_by_key.get(key)
        print(f"[{index}/{len(keys)}] Processing game_id={game_id or 'unknown'} key={key}")
        try:
            source_rows = read_source_rows(s3_client, key)
            rows = build_shot_location_rows(source_rows, fallback_game_id=game_id)
        except (BotoCoreError, ClientError, OSError, pa.ArrowInvalid) as exc:
            skipped.append((game_id, key))
            print(
                f"Skipping file game_id={game_id or 'unknown'} key={key} "
                f"({type(exc).__name__}: {exc})"
            )
            continue

        total_source_rows += len(source_rows)
        if game_id is None:
            skipped.append((None, key))
            print(f"Skipping file with missing game id: key={key}")
            continue

        rows = add_silver_metadata(
            rows,
            pipeline_run_id=pipeline_run_id,
            ingested_at_utc=ingested_at_utc,
            source_key=key,
            source_last_modified_utc=source_last_modified,
        )
        write_game_parquet_to_s3(game_id, rows, s3_client)
        games_upserted.add(game_id)
        total_rows_written += len(rows)
        source_area_available_count += sum(
            1 for row in rows if row.get("source_area_available_flag") is True
        )
        coordinate_available_count += sum(
            1 for row in rows if row.get("coordinate_available_flag") is True
        )
        source_derived_area_mismatch_count += sum(
            1 for row in rows if row.get("source_derived_area_mismatch_flag") is True
        )
        print(f"[{index}/{len(keys)}] Completed game_id={game_id} rows_written={len(rows)}")

    if skipped:
        warning_reason_counts["skipped_unreadable_or_invalid_files"] = len(skipped)
    if source_derived_area_mismatch_count:
        warning_reason_counts["source_derived_area_mismatch"] = source_derived_area_mismatch_count
    warning_count = sum(warning_reason_counts.values())

    checkpoint_key_written = None
    if source_index and games_upserted:
        checkpoint_rows_to_write = checkpoint_rows_with_updates(
            existing_rows=checkpoint_rows,
            source_index=source_index,
            written_game_ids=games_upserted,
            processed_at_utc=ingested_at_utc,
            pipeline_run_id=pipeline_run_id,
        )
        checkpoint_key_written = write_checkpoint_index(
            s3_client=s3_client,
            bucket=S3_BUCKET,
            table_name=TABLE_NAME,
            checkpoint_rows=checkpoint_rows_to_write,
        )
        print(f"Wrote checkpoint parquet: s3://{S3_BUCKET}/{checkpoint_key_written}")

    print(f"Total source files discovered: {len(objects)}")
    print(f"Total source files selected: {len(keys)}")
    print(f"Games upserted: {len(games_upserted)}")
    print(f"Source rows scanned: {total_source_rows}")
    print(f"Shot-location rows written: {total_rows_written}")
    print(f"Source area available rows: {source_area_available_count}")
    print(f"Coordinate available rows: {coordinate_available_count}")
    print(f"Source/derived area mismatches: {source_derived_area_mismatch_count}")
    print(f"Skipped files: {len(skipped)}")
    print(f"Wrote parquet files under s3://{S3_BUCKET}/{DESTINATION_PREFIX}")

    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": "success_with_warnings" if warning_count else "success",
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_prefix": SOURCE_PREFIX,
        "destination_prefix": DESTINATION_PREFIX,
        "force_full_refresh": int(FORCE_FULL_REFRESH),
        "selection_mode": selection_meta.get("selection_mode"),
        "selected_game_count": len(keys),
        "written_game_count": len(games_upserted),
        "target_game_ids": json.dumps(selection_meta.get("target_game_ids", []), sort_keys=True),
        "checkpoint_enabled": 1,
        "checkpoint_key": checkpoint_key_written,
        "source_rows_scanned": total_source_rows,
        "rows_written": total_rows_written,
        "source_area_available_count": source_area_available_count,
        "coordinate_available_count": coordinate_available_count,
        "source_derived_area_mismatch_count": source_derived_area_mismatch_count,
        "skipped_file_count": len(skipped),
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
