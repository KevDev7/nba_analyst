"""
Build fallback silver possessions for recoverable overtime pbpstats failures.

Source:
  s3://nba-analytics-lakehouse-dev/raw/cdn/playbyplay/

Destination (upsert by game_id):
  s3://nba-analytics-lakehouse-dev/silver/possessions_ot_fallback/game_id=<GAME_ID>.parquet
"""

from __future__ import annotations

import io
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

import build_silver_possessions as base
from heavy_silver_runtime import (
    build_source_index_from_objects,
    checkpoint_rows_with_updates,
    datetime_to_iso,
    normalize_utc_datetime,
    parse_target_game_ids,
    read_checkpoint_index,
    read_json_state,
    select_game_ids_for_processing,
    write_checkpoint_index,
    write_json_state,
)
from possessions.fallback import (
    annotate_fallback_rows,
    apply_side_substitutions,
    apply_substitution_cluster,
    build_effective_on_court_rows,
    build_end_q4_drift_reconciled_on_court_rows,
    build_fallback_rows_for_game,
    build_recovered_ot_stints,
    build_stale_sub_out_repaired_on_court_rows,
    group_substitution_clusters,
    is_recoverable_reference_failure,
    is_stale_sub_out_only_token,
    last_stint_for_period,
    lineup_issue_tokens,
    normalize_person_ids,
    parse_failed_period,
    partial_side_flags,
    reconcile_side_from_q4_drift,
    row_has_complete_lineups,
    valid_closing_stint_for_period,
)
from possessions.inputs import PossessionGameInput
from possessions.pipeline import PbpstatsPossessionPipeline
from silver_pipeline_helpers import run_date, write_audit_artifacts

load_dotenv(override=True)

S3_BUCKET = base.S3_BUCKET
RAW_SOURCE_PREFIX = base.RAW_SOURCE_PREFIX
ON_COURT_PREFIX = base.ON_COURT_PREFIX
DESTINATION_PREFIX = "silver/possessions_ot_fallback/"
TABLE_NAME = "possessions_ot_fallback"
STATE_KEY = "silver/_state/possessions_ot_fallback_state.json"
SOURCE_SYSTEM = "pbpstats_live_possessions_ot_fallback"
META_SCHEMA_VERSION = 1

PROCESS_ALL_FILES = os.getenv("POSSESSIONS_OT_FALLBACK_PROCESS_ALL_FILES", "true").strip().lower() != "false"
INCREMENTAL_MODE = os.getenv("POSSESSIONS_OT_FALLBACK_INCREMENTAL_MODE", "true").strip().lower() != "false"
FORCE_FULL_REFRESH = os.getenv("POSSESSIONS_OT_FALLBACK_FORCE_FULL_REFRESH", "false").strip().lower() == "true"
INCREMENTAL_LOOKBACK_MINUTES = 60
TARGET_GAME_IDS = parse_target_game_ids(os.getenv("POSSESSIONS_OT_FALLBACK_TARGET_GAME_IDS", ""))
TARGET_PLAYBYPLAY_S3_PATH = os.getenv(
    "POSSESSIONS_OT_FALLBACK_TARGET_PLAYBYPLAY_S3_PATH",
    "s3://nba-analytics-lakehouse-dev/raw/cdn/playbyplay/game_id=0022000100.json",
)

OPENING_CLOCK = "PT05M00.00S"

TARGET_SCHEMA = pa.schema(
    [
        pa.field("gameId", pa.string()),
        pa.field("possessionNumber", pa.int64()),
        pa.field("possessionNumberInPeriod", pa.int64()),
        pa.field("period", pa.int64()),
        pa.field("startActionNumber", pa.int64()),
        pa.field("endActionNumber", pa.int64()),
        pa.field("startOrderNumber", pa.int64()),
        pa.field("endOrderNumber", pa.int64()),
        pa.field("startClock", pa.string()),
        pa.field("endClock", pa.string()),
        pa.field("startTimeActualUtc", pa.timestamp("us", tz="UTC")),
        pa.field("endTimeActualUtc", pa.timestamp("us", tz="UTC")),
        pa.field("secondsElapsed", pa.float64()),
        pa.field("offenseTeamId", pa.int64()),
        pa.field("defenseTeamId", pa.int64()),
        pa.field("offenseHomeAway", pa.string()),
        pa.field("defenseHomeAway", pa.string()),
        pa.field("startScoreMargin", pa.int64()),
        pa.field("endScoreMargin", pa.int64()),
        pa.field("pointsScoredOnPossession", pa.int64()),
        pa.field("possessionStartType", pa.string()),
        pa.field("possessionEndType", pa.string()),
        pa.field("possessionBoundaryReason", pa.string()),
        pa.field("possessionHasTimeout", pa.bool_()),
        pa.field("previousPossessionHasTimeout", pa.bool_()),
        pa.field("isSecondChancePossession", pa.bool_()),
        pa.field("isPenaltyPossession", pa.bool_()),
        pa.field("countsAsPossession", pa.bool_()),
        pa.field("previousPossessionNumber", pa.int64()),
        pa.field("nextPossessionNumber", pa.int64()),
        pa.field("previousPossessionEndingActionNumber", pa.int64()),
        pa.field("homeLineupId", pa.string()),
        pa.field("awayLineupId", pa.string()),
        pa.field("lineupValidFlag", pa.int64()),
        pa.field("lineupIssue", pa.string()),
        pa.field("fieldGoalAttempts", pa.int64()),
        pa.field("freeThrowAttempts", pa.int64()),
        pa.field("turnovers", pa.int64()),
        pa.field("offensiveRebounds", pa.int64()),
        pa.field("madeFieldGoals", pa.int64()),
        pa.field("possessionSourceMethod", pa.string()),
        pa.field("referenceFailureType", pa.string()),
        pa.field("referenceFailurePeriod", pa.int64()),
        pa.field("fallbackApplied", pa.bool_()),
        pa.field("fallbackOpeningSubClusterApplied", pa.bool_()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)

TARGET_COLUMNS = [field.name for field in TARGET_SCHEMA if not field.name.startswith("_meta_")]


def read_state(s3_client) -> dict[str, Any]:
    return read_json_state(s3_client=s3_client, bucket=S3_BUCKET, key=STATE_KEY)


def write_state(s3_client, state: dict[str, Any]) -> None:
    write_json_state(s3_client=s3_client, bucket=S3_BUCKET, key=STATE_KEY, state=state)


def select_incremental_game_ids_from_legacy_state(
    source_index: dict[str, list[dict[str, Any]]],
    state: dict[str, Any],
) -> tuple[set[str], dict[str, Any]]:
    state_watermark = base.pbp_silver.parse_state_datetime(state.get("max_source_last_modified_utc"))
    if state_watermark is None:
        return set(source_index), {
            "selection_mode": "legacy_full_initial",
            "watermark_utc": None,
            "lookback_minutes": INCREMENTAL_LOOKBACK_MINUTES,
        }

    effective_watermark = state_watermark - timedelta(minutes=INCREMENTAL_LOOKBACK_MINUTES)
    selected_game_ids: set[str] = set()
    for game_id, artifacts in source_index.items():
        artifact_last_modified = max(
            (
                base.pbp_silver.parse_state_datetime(artifact.get("last_modified_utc"))
                for artifact in artifacts
                if artifact.get("key", "").startswith(RAW_SOURCE_PREFIX)
            ),
            default=None,
        )
        if artifact_last_modified is not None and artifact_last_modified >= effective_watermark:
            selected_game_ids.add(game_id)

    selection_meta = {
        "selection_mode": "legacy_state_incremental",
        "watermark_utc": base.pbp_silver.state_datetime_to_iso(state_watermark),
        "effective_watermark_utc": base.pbp_silver.state_datetime_to_iso(effective_watermark),
        "lookback_minutes": INCREMENTAL_LOOKBACK_MINUTES,
    }
    return selected_game_ids, selection_meta


def write_details_json(
    s3_client,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    details: dict[str, Any],
) -> str:
    key = (
        f"silver/_audit/{TABLE_NAME}/"
        f"run_date={run_date(ingested_at_utc)}/{pipeline_run_id}_details.json"
    )
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(details, default=str, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
    )
    return key


def destination_key_for_game(game_id: str) -> str:
    return f"{DESTINATION_PREFIX}game_id={game_id}.parquet"


def read_playbyplay_rows_for_game(s3_client, game_id: str) -> list[dict[str, Any]]:
    return base.read_playbyplay_rows_from_s3(
        s3_client,
        f"{base.SOURCE_PREFIX}game_id={str(game_id).zfill(10)}.parquet",
    )


def write_game_parquet_to_s3(
    game_id: str,
    rows: list[dict[str, Any]],
    *,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    source_key: str,
    source_last_modified_utc: datetime | None,
    s3_client,
) -> None:
    enriched_rows = base.add_silver_metadata(
        rows,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        source_system=SOURCE_SYSTEM,
        source_key=source_key,
        source_last_modified_utc=source_last_modified_utc,
        schema_version=META_SCHEMA_VERSION,
    )
    table = pa.Table.from_pylist(enriched_rows, schema=TARGET_SCHEMA)
    output = io.BytesIO()
    pq.write_table(table, output, compression="snappy")
    output.seek(0)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=destination_key_for_game(str(game_id).zfill(10)),
        Body=output.getvalue(),
        ContentType="application/octet-stream",
    )


def main() -> None:
    s3_client = boto3.client("s3")
    pipeline = PbpstatsPossessionPipeline()
    pipeline_run_id = f"{TABLE_NAME}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    ingested_at_utc = datetime.now(timezone.utc)
    source_index: dict[str, list[dict[str, Any]]] = {}

    checkpoint_exists, checkpoint_rows = read_checkpoint_index(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
    )
    checkpoint_key_written: str | None = None

    source_last_modified_by_key: dict[str, datetime | None] = {}
    state_before: dict[str, Any] = {}
    selection_meta: dict[str, Any] = {
        "selection_mode": "single_file" if not PROCESS_ALL_FILES else "full_refresh",
        "watermark_utc": None,
        "effective_watermark_utc": None,
        "lookback_minutes": None,
        "target_game_ids": sorted(TARGET_GAME_IDS),
        "selected_game_count": 0,
        "files_discovered": 0,
        "files_selected": 0,
        "checkpoint_enabled": False,
        "legacy_state_fallback_used": False,
    }

    if PROCESS_ALL_FILES:
        objects = base.list_raw_objects(s3_client)
        for obj in objects:
            key = obj.get("Key", "")
            source_last_modified_by_key[key] = normalize_utc_datetime(obj.get("LastModified"))
        source_index = build_source_index_from_objects(objects, game_id_from_key=base.extract_game_id_from_key)
        legacy_state = read_state(s3_client) if INCREMENTAL_MODE and not FORCE_FULL_REFRESH else {}
        state_before = legacy_state
        selected_game_ids, selection_meta = select_game_ids_for_processing(
            source_index=source_index,
            target_game_ids=TARGET_GAME_IDS,
            force_full_refresh=(FORCE_FULL_REFRESH or not INCREMENTAL_MODE),
            checkpoint_exists=checkpoint_exists,
            checkpoint_rows=checkpoint_rows,
            legacy_state=legacy_state,
            legacy_fallback_selector=(
                select_incremental_game_ids_from_legacy_state
                if INCREMENTAL_MODE and not FORCE_FULL_REFRESH
                else None
            ),
        )
        keys = [source_index[game_id][0]["key"] for game_id in selected_game_ids if source_index.get(game_id)]
        selection_meta["selected_game_count"] = len(selected_game_ids)
        selection_meta["files_discovered"] = len(objects)
        selection_meta["files_selected"] = len(keys)
        print(f"Mode: {selection_meta.get('selection_mode')}")
        if TARGET_GAME_IDS:
            print(f"Target game ids: {len(TARGET_GAME_IDS)}")
        print(f"Files discovered: {len(objects)}")
        print(f"Files selected: {len(keys)}")
    else:
        if base.pbp_silver.null_if_empty(TARGET_PLAYBYPLAY_S3_PATH) is None:
            raise ValueError("TARGET_PLAYBYPLAY_S3_PATH must be set when PROCESS_ALL_FILES is False.")
        bucket, key = base.pbp_silver.parse_s3_path(str(TARGET_PLAYBYPLAY_S3_PATH).strip())
        if bucket != S3_BUCKET:
            raise ValueError(f"TARGET_PLAYBYPLAY_S3_PATH bucket '{bucket}' must match S3_BUCKET '{S3_BUCKET}'.")
        if not key.endswith(".json"):
            raise ValueError(f"TARGET_PLAYBYPLAY_S3_PATH must point to a .json file, got key={key}")
        try:
            head_response = s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        except ClientError as exc:
            raise ValueError(
                f"TARGET_PLAYBYPLAY_S3_PATH does not exist or is inaccessible: s3://{S3_BUCKET}/{key}"
            ) from exc
        source_last_modified_by_key[key] = normalize_utc_datetime(head_response.get("LastModified"))
        single_game_id = base.extract_game_id_from_key(key)
        if single_game_id is not None:
            source_index = {
                single_game_id: [
                    {
                        "key": key,
                        "last_modified_utc": datetime_to_iso(source_last_modified_by_key[key]),
                    }
                ]
            }
        keys = [key]
        selection_meta = {
            "selection_mode": "single_file",
            "watermark_utc": None,
            "effective_watermark_utc": None,
            "lookback_minutes": None,
            "target_game_ids": sorted(TARGET_GAME_IDS),
            "selected_game_count": 1,
            "files_discovered": 1,
            "files_selected": 1,
            "checkpoint_enabled": False,
            "legacy_state_fallback_used": False,
        }
        print(f"Mode: single file ({TARGET_PLAYBYPLAY_S3_PATH})")
        print("Files selected: 1")

    total_files_processed = 0
    total_source_rows_processed = 0
    total_rows_written = 0
    games_upserted: set[str] = set()
    recovered_games: list[dict[str, Any]] = []
    skipped: list[tuple[str | None, str, str]] = []
    warning_reason_counts: dict[str, int] = {}
    max_source_last_modified_seen: datetime | None = None

    for index, key in enumerate(keys, start=1):
        source_last_modified = source_last_modified_by_key.get(key)
        if isinstance(source_last_modified, datetime) and source_last_modified.tzinfo is None:
            source_last_modified = source_last_modified.replace(tzinfo=timezone.utc)
        if isinstance(source_last_modified, datetime):
            if max_source_last_modified_seen is None or source_last_modified > max_source_last_modified_seen:
                max_source_last_modified_seen = source_last_modified

        game_id = base.extract_game_id_from_key(key)
        print(f"[{index}/{len(keys)}] Processing game_id={game_id or 'unknown'} key={key}")
        try:
            if game_id is None:
                raise base.ProjectionFailure("Missing fallback game_id from source key")
            payload = base.pbp_silver.read_json_payload(s3_client, key)
            playbyplay_rows = read_playbyplay_rows_for_game(s3_client, game_id)
            on_court_rows = base.read_on_court_rows_from_s3(s3_client, game_id)
            build_result = pipeline.build_ot_fallback_game(
                PossessionGameInput(
                    game_id=game_id,
                    payload=payload,
                    playbyplay_rows=playbyplay_rows,
                    on_court_rows=on_court_rows,
                    source_key=key,
                    source_last_modified_utc=source_last_modified,
                )
            )
            if build_result.status == "fallback_written_candidate":
                possession_rows = build_result.rows.rows
                failed_period = build_result.reference_failure_period
                opening_cluster_applied = build_result.opening_subcluster_applied
                fallback_method = build_result.possession_source_method or "fallback_ot_carry_forward"
                recovered_games.append(
                    {
                        "game_id": game_id,
                        "failed_period": failed_period,
                        "fallback_method": fallback_method,
                        "opening_cluster_applied": int(opening_cluster_applied),
                    }
                )
            else:
                skipped.append((game_id, key, build_result.warning_details or build_result.status))
                print(
                    f"Skipping file game_id={game_id} key={key} "
                    f"({build_result.warning_details or build_result.status})"
                )
                continue
        except (BotoCoreError, ClientError, OSError, pa.ArrowInvalid, pa.ArrowTypeError) as exc:
            skipped.append((game_id, key, f"{type(exc).__name__}: {exc}"))
            print(f"Skipping file game_id={game_id or 'unknown'} key={key} ({type(exc).__name__}: {exc})")
            continue
        except Exception as exc:
            skipped.append((game_id, key, f"{type(exc).__name__}: {exc}"))
            print(f"Skipping file game_id={game_id or 'unknown'} key={key} ({type(exc).__name__}: {exc})")
            continue

        total_files_processed += 1
        total_source_rows_processed += len(playbyplay_rows)
        total_rows_written += len(possession_rows)
        games_upserted.add(str(game_id).zfill(10))
        write_game_parquet_to_s3(
            str(game_id).zfill(10),
            possession_rows,
            pipeline_run_id=pipeline_run_id,
            ingested_at_utc=ingested_at_utc,
            source_key=key,
            source_last_modified_utc=source_last_modified,
            s3_client=s3_client,
        )
        print(f"[{index}/{len(keys)}] Completed game_id={game_id} rows_written={len(possession_rows)}")

    print(f"Total files scanned: {len(keys)}")
    print(f"Total files processed: {total_files_processed}")
    print(f"Total playbyplay rows processed: {total_source_rows_processed}")
    print(f"Total possession rows written: {total_rows_written}")
    print(f"Games upserted: {len(games_upserted)}")
    print(f"Recovered games: {len(recovered_games)}")
    print(f"Skipped files: {len(skipped)}")

    if skipped:
        print("Skipped game_ids:")
        for skipped_game_id, skipped_key, _ in skipped:
            print(f"- game_id={skipped_game_id or 'unknown'} key={skipped_key}")

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

    if skipped:
        warning_reason_counts["skipped_unrecoverable_or_non_eligible_files"] = len(skipped)

    details_payload = {
        "pipeline_run_id": pipeline_run_id,
        "selection_mode": selection_meta.get("selection_mode"),
        "recovered_games": recovered_games,
        "skipped_files": [
            {
                "game_id": row_game_id,
                "source_key": source_key,
                "reason": reason,
            }
            for row_game_id, source_key, reason in skipped
        ],
    }
    details_key = write_details_json(
        s3_client=s3_client,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        details=details_payload,
    )

    audit_payload = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "ingested_at_utc": ingested_at_utc.isoformat().replace("+00:00", "Z"),
        "run_status": "success_with_warnings" if skipped else "success",
        "files_selected": len(keys),
        "files_processed": total_files_processed,
        "actions_processed": total_source_rows_processed,
        "rows_written": total_rows_written,
        "games_upserted": len(games_upserted),
        "written_game_count": len(games_upserted),
        "recovered_game_count": len(recovered_games),
        "skipped_file_count": len(skipped),
        "warning_count": len(skipped),
        "warning_reason_counts": json.dumps(warning_reason_counts, sort_keys=True),
        "error_count": 0,
        "error_reason_counts": "{}",
        "source_bucket": S3_BUCKET,
        "source_prefix": RAW_SOURCE_PREFIX,
        "destination_prefix": DESTINATION_PREFIX,
        "process_all_files": int(PROCESS_ALL_FILES),
        "incremental_mode": int(INCREMENTAL_MODE),
        "force_full_refresh": int(FORCE_FULL_REFRESH),
        "target_game_ids": json.dumps(sorted(TARGET_GAME_IDS)),
        "target_source_s3_path": TARGET_PLAYBYPLAY_S3_PATH if not PROCESS_ALL_FILES else None,
        "selection_mode": selection_meta.get("selection_mode"),
        "selection_watermark_utc": selection_meta.get("watermark_utc"),
        "selection_effective_watermark_utc": selection_meta.get("effective_watermark_utc"),
        "selection_lookback_minutes": selection_meta.get("lookback_minutes"),
        "selected_game_count": selection_meta.get("selected_game_count"),
        "legacy_state_fallback_used": int(bool(selection_meta.get("legacy_state_fallback_used"))),
        "checkpoint_enabled": 1,
        "checkpoint_key": checkpoint_key_written,
        "details_key": details_key,
    }
    audit_json_key, audit_parquet_key = write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_payload,
    )
    print(f"Wrote audit JSON: s3://{S3_BUCKET}/{audit_json_key}")
    print(f"Wrote audit parquet: s3://{S3_BUCKET}/{audit_parquet_key}")

    write_state(
        s3_client,
        {
            **state_before,
            "pipeline_run_id": pipeline_run_id,
            "ingested_at_utc": ingested_at_utc.isoformat().replace("+00:00", "Z"),
            "max_source_last_modified_utc": (
                max_source_last_modified_seen.isoformat().replace("+00:00", "Z")
                if max_source_last_modified_seen is not None
                else state_before.get("max_source_last_modified_utc")
            ),
            "selection_mode": selection_meta.get("selection_mode"),
            "selection_watermark_utc": selection_meta.get("watermark_utc"),
            "selection_effective_watermark_utc": selection_meta.get("effective_watermark_utc"),
            "selection_lookback_minutes": selection_meta.get("lookback_minutes"),
            "files_processed": total_files_processed,
            "rows_written": total_rows_written,
            "recovered_game_count": len(recovered_games),
            "skipped_file_count": len(skipped),
        },
    )
    print(f"Wrote state: s3://{S3_BUCKET}/{STATE_KEY}")


if __name__ == "__main__":
    main()
