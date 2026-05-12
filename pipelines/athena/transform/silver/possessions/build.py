"""
Build silver possessions from raw CDN play-by-play JSON using pbpstats logic.

Source:
  s3://nba-analytics-lakehouse-dev/raw/cdn/playbyplay/

Destination (upsert by game_id):
  s3://nba-analytics-lakehouse-dev/silver/possessions/game_id=<GAME_ID>.parquet
"""

from __future__ import annotations

import io
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
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
from silver_pipeline_helpers import run_date, write_audit_artifacts

try:
    from incremental_state import select_incremental_game_ids_from_watermark_state
except ModuleNotFoundError:
    from pipelines.athena.transform.silver.incremental_state import (
        select_incremental_game_ids_from_watermark_state,
    )

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pipelines").is_dir())
PBPSTATS_ROOT_CANDIDATES = [
    REPO_ROOT / "references" / "pbpstats",
    REPO_ROOT / "reference" / "pbpstats",
]
PBPSTATS_ROOT = next((path for path in PBPSTATS_ROOT_CANDIDATES if path.exists()), PBPSTATS_ROOT_CANDIDATES[0])
if PBPSTATS_ROOT.exists() and str(PBPSTATS_ROOT) not in sys.path:
    sys.path.insert(0, str(PBPSTATS_ROOT))

import build_silver_playbyplay_events as pbp_silver
from pbpstats.resources.enhanced_pbp import (
    FieldGoal,
    FreeThrow,
    JumpBall,
    Rebound,
    Substitution,
    Timeout,
    Turnover,
)
from pbpstats.resources.possessions.possession import Possession
from pbpstats_projection_common import ProjectionFailure, add_silver_metadata, load_live_possession_items
import possessions.exact as possession_exact
from possessions.exact import (
    build_playbyplay_lookup,
    build_possession_rows_from_events,
    ending_event_row,
    is_real_rebound_event,
    known_team_ids_from_rows,
    last_non_substitution_event,
    last_non_substitution_row,
    linked_shot_row,
    normalize_pbpstats_start_type,
    other_team_id,
    pbpstats_points_scored_on_possession,
    pbpstats_possession_end_type,
    possession_end_type,
    possession_ending_event,
    possession_event_row_lookup,
    possession_start_type_from_previous,
    possession_timeout_flag,
    previous_possession_timeout_flag,
    score_margin_from_score_dict,
    score_points_for_location,
)
from possessions.inputs import PossessionGameInput
from possessions.pipeline import PbpstatsPossessionPipeline
from possessions.stamping import (
    can_collapse_same_moment_stints,
    first_non_null,
    lineup_id_from_person_ids,
    parse_time_actual_utc,
    sort_event_rows,
    sort_stints_for_stamping,
    stamp_lineup_context,
)

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "silver/playbyplay/"
RAW_SOURCE_PREFIX = "raw/cdn/playbyplay/"
ON_COURT_PREFIX = "silver/on_court_state/"
DESTINATION_PREFIX = "silver/possessions/"
TABLE_NAME = "possessions"
STATE_KEY = "silver/_state/possessions_state.json"
SOURCE_SYSTEM = "pbpstats_live_possessions"
META_SCHEMA_VERSION = 1

PROCESS_ALL_FILES = os.getenv("POSSESSIONS_PROCESS_ALL_FILES", "true").strip().lower() != "false"
INCREMENTAL_MODE = os.getenv("POSSESSIONS_INCREMENTAL_MODE", "true").strip().lower() != "false"
FORCE_FULL_REFRESH = os.getenv("POSSESSIONS_FORCE_FULL_REFRESH", "false").strip().lower() == "true"
INCREMENTAL_LOOKBACK_MINUTES = 60
TARGET_GAME_IDS = parse_target_game_ids(os.getenv("POSSESSIONS_TARGET_GAME_IDS", ""))
TARGET_PLAYBYPLAY_S3_PATH = os.getenv(
    "POSSESSIONS_TARGET_PLAYBYPLAY_S3_PATH",
    "s3://nba-analytics-lakehouse-dev/raw/cdn/playbyplay/game_id=0022000517.json",
)

PBP_REQUIRED_COLUMNS = [
    "gameId",
    "period",
    "actionNumber",
    "orderNumber",
    "clock",
    "secondsRemainingInPeriod",
    "timeActual",
    "scoreHome",
    "scoreAway",
    "scoreMarginBefore",
    "scoreMarginAfter",
    "resolvedOffenseTeamId",
    "resolvedDefenseTeamId",
    "offenseHomeAway",
    "defenseHomeAway",
    "shotResult",
    "shotActionNumber",
    "shotValue",
    "blockPersonId",
    "personId",
    "teamId",
    "stealPersonId",
    "qualifiers",
    "subType",
    "descriptor",
    "actionType",
    "isMadeShot",
    "isMissedShot",
    "isFreeThrow",
    "isRebound",
    "isTurnover",
    "isSubstitution",
    "isTimeout",
    "isJumpBall",
    "isOreb",
    "isDreb",
    "isPlaceholderRebound",
    "isTechnicalFt",
    "isFlagrantFt",
    "isSecondChanceEvent",
    "isPenaltyEvent",
    "isPossessionEndingEvent",
    "countAsPossession",
    "possessionBoundaryReason",
]

ON_COURT_REQUIRED_COLUMNS = [
    "gameId",
    "period",
    "stint_id",
    "start_orderNumber",
    "end_orderNumber",
    "start_clock",
    "home_teamId",
    "away_teamId",
    "home_personIds",
    "away_personIds",
    "lineup_valid_flag",
    "lineup_issue",
]

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
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)

TARGET_COLUMNS = [field.name for field in TARGET_SCHEMA if not field.name.startswith("_meta_")]


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


def extract_game_id_from_key(key: str) -> str | None:
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id="):
        return None
    suffix = ".parquet" if filename.endswith(".parquet") else ".json" if filename.endswith(".json") else None
    if suffix is None:
        return None
    raw_game_id = filename[len("game_id=") : -len(suffix)] or None
    if raw_game_id is None:
        return None
    return str(raw_game_id).strip().zfill(10)


def list_raw_objects(s3_client) -> list[dict[str, Any]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=RAW_SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".json") and extract_game_id_from_key(key) is not None:
                objects.append(obj)
    return objects


def list_partition_objects_for_prefix(s3_client, prefix: str) -> list[dict[str, Any]]:
    """List per-game parquet partition objects under an arbitrary prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".parquet") and extract_game_id_from_key(key) is not None:
                objects.append(obj)
    return objects


def read_state(s3_client) -> dict[str, Any]:
    return read_json_state(s3_client=s3_client, bucket=S3_BUCKET, key=STATE_KEY)


def write_state(s3_client, state: dict[str, Any]) -> None:
    write_json_state(s3_client=s3_client, bucket=S3_BUCKET, key=STATE_KEY, state=state)


def select_incremental_game_ids_from_legacy_state(
    source_index: dict[str, list[dict[str, Any]]],
    state: dict[str, Any],
) -> tuple[set[str], dict[str, Any]]:
    return select_incremental_game_ids_from_watermark_state(
        source_index,
        state,
        lookback_minutes=INCREMENTAL_LOOKBACK_MINUTES,
        source_key_prefix=RAW_SOURCE_PREFIX,
    )


def read_playbyplay_rows_from_s3(s3_client, key: str) -> list[dict[str, Any]]:
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload = response["Body"].read()
    schema = pq.read_schema(pa.BufferReader(payload))
    available_columns = set(schema.names)
    if all(column in available_columns for column in PBP_REQUIRED_COLUMNS):
        table = pq.read_table(pa.BufferReader(payload), columns=PBP_REQUIRED_COLUMNS)
        return table.to_pylist()

    game_id = extract_game_id_from_key(key)
    if game_id is None:
        raise ValueError(f"Could not derive game_id from key={key} for raw fallback")
    return load_refreshed_playbyplay_rows_from_raw(s3_client, game_id)


def load_refreshed_playbyplay_rows_from_raw(s3_client, game_id: str) -> list[dict[str, Any]]:
    raw_key = f"{pbp_silver.SOURCE_PREFIX}game_id={game_id}.json"
    payload = pbp_silver.read_json_payload(s3_client, raw_key)
    game = payload.get("game") or {}
    actions = game.get("actions") or []

    team_location_by_id: dict[int, str] = {}
    for team_key, location in (("homeTeam", "h"), ("awayTeam", "v")):
        team = game.get(team_key) or {}
        team_id = pbp_silver.to_int_or_none(team.get("teamId"))
        if team_id is not None:
            team_location_by_id[team_id] = location

    rows: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        team_id = pbp_silver.to_int_or_none(action.get("teamId"))
        offense_team_id = pbp_silver.to_int_or_none(action.get("possession"))
        offense_home_away = team_location_by_id.get(offense_team_id)
        defense_home_away = None
        if offense_home_away == "h":
            defense_home_away = "v"
        elif offense_home_away == "v":
            defense_home_away = "h"
        rows.append(
            {
                "actionNumber": pbp_silver.to_int_or_none(action.get("actionNumber")),
                "orderNumber": pbp_silver.to_int_or_none(action.get("orderNumber")),
                "timeActual": pbp_silver.null_if_empty(action.get("timeActual")),
                "scoreHome": pbp_silver.to_int_or_none(action.get("scoreHome")),
                "scoreAway": pbp_silver.to_int_or_none(action.get("scoreAway")),
                "teamId": team_id,
                "possession": offense_team_id,
                "offenseHomeAway": offense_home_away,
                "defenseHomeAway": defense_home_away,
            }
        )
    return rows


def read_on_court_rows_from_s3(s3_client, game_id: str) -> list[dict[str, Any]]:
    key = f"{ON_COURT_PREFIX}game_id={game_id}.parquet"
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    except ClientError as exc:
        code = (exc.response or {}).get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404"}:
            return []
        raise

    payload = response["Body"].read()
    schema = pq.read_schema(pa.BufferReader(payload))
    available_columns = set(schema.names)
    selected_columns = [column for column in ON_COURT_REQUIRED_COLUMNS if column in available_columns]
    table = pq.read_table(pa.BufferReader(payload), columns=selected_columns)
    return table.to_pylist()


def build_possession_rows_from_payload(
    payload: dict[str, Any],
    playbyplay_rows: list[dict[str, Any]],
    *,
    fallback_game_id: str | None = None,
    on_court_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    possession_exact.load_live_possession_items = load_live_possession_items
    possession_exact.FieldGoal = FieldGoal
    possession_exact.FreeThrow = FreeThrow
    possession_exact.JumpBall = JumpBall
    possession_exact.Rebound = Rebound
    possession_exact.Substitution = Substitution
    possession_exact.Timeout = Timeout
    possession_exact.Turnover = Turnover
    return possession_exact.build_possession_rows_from_payload(
        payload,
        playbyplay_rows,
        fallback_game_id=fallback_game_id,
        on_court_rows=on_court_rows,
    )


def destination_key_for_game(game_id: str) -> str:
    return f"{DESTINATION_PREFIX}game_id={game_id}.parquet"


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
    enriched_rows = add_silver_metadata(
        rows,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        source_system=SOURCE_SYSTEM,
        source_key=source_key,
        source_last_modified_utc=source_last_modified_utc,
        schema_version=META_SCHEMA_VERSION,
    )
    table = pa.Table.from_pylist(enriched_rows, schema=TARGET_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=destination_key_for_game(game_id),
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )


def main() -> None:
    s3_client = boto3.client("s3")
    pipeline = PbpstatsPossessionPipeline()
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"possessions_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    keys: list[str] = []
    source_last_modified_by_key: dict[str, datetime | None] = {}
    source_index: dict[str, list[dict[str, Any]]] = {}
    selection_meta: dict[str, Any] = {
        "selection_mode": "single_file" if not PROCESS_ALL_FILES else "full_refresh",
        "checkpoint_enabled": False,
        "legacy_state_fallback_used": False,
        "target_game_ids": sorted(TARGET_GAME_IDS),
    }
    state_before: dict[str, Any] = {}
    checkpoint_exists, checkpoint_rows = read_checkpoint_index(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
    )
    checkpoint_key_written: str | None = None

    if PROCESS_ALL_FILES:
        objects = list_raw_objects(s3_client)
        for obj in objects:
            key = obj.get("Key", "")
            source_last_modified_by_key[key] = normalize_utc_datetime(obj.get("LastModified"))
        source_index = build_source_index_from_objects(
            objects,
            game_id_from_key=extract_game_id_from_key,
        )

        on_court_objects = list_partition_objects_for_prefix(s3_client, ON_COURT_PREFIX)
        for obj in on_court_objects:
            game_id = extract_game_id_from_key(obj.get("Key", ""))
            if game_id is None:
                continue
            source_index.setdefault(game_id, []).append(
                {
                    "key": obj.get("Key", ""),
                    "last_modified_utc": datetime_to_iso(normalize_utc_datetime(obj.get("LastModified"))),
                }
            )

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
        keys = [
            source_index[game_id][0]["key"]
            for game_id in selected_game_ids
            if source_index.get(game_id)
        ]
        selection_meta["selected_game_count"] = len(selected_game_ids)
        selection_meta["files_discovered"] = len(objects)
        selection_meta["files_selected"] = len(keys)

        print(f"Mode: {selection_meta.get('selection_mode')}")
        if TARGET_GAME_IDS:
            print(f"Target game ids: {len(TARGET_GAME_IDS)}")

        print(f"Files discovered: {len(objects)}")
        print(f"Files selected: {len(keys)}")
    else:
        if pbp_silver.null_if_empty(TARGET_PLAYBYPLAY_S3_PATH) is None:
            raise ValueError(
                "TARGET_PLAYBYPLAY_S3_PATH must be set when PROCESS_ALL_FILES is False."
            )

        bucket, key = pbp_silver.parse_s3_path(str(TARGET_PLAYBYPLAY_S3_PATH).strip())
        if bucket != S3_BUCKET:
            raise ValueError(
                f"TARGET_PLAYBYPLAY_S3_PATH bucket '{bucket}' must match S3_BUCKET '{S3_BUCKET}'."
            )
        if not key.endswith(".json"):
            raise ValueError(
                f"TARGET_PLAYBYPLAY_S3_PATH must point to a .json file, got key={key}"
            )

        try:
            head_response = s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        except ClientError as exc:
            raise ValueError(
                f"TARGET_PLAYBYPLAY_S3_PATH does not exist or is inaccessible: s3://{S3_BUCKET}/{key}"
            ) from exc

        keys = [key]
        source_last_modified = normalize_utc_datetime(head_response.get("LastModified"))
        source_last_modified_by_key[key] = source_last_modified
        fallback_game_id = extract_game_id_from_key(key)
        if fallback_game_id is not None:
            source_index[fallback_game_id] = [
                {
                    "key": key,
                    "last_modified_utc": datetime_to_iso(source_last_modified),
                }
            ]
        selection_meta.update(
            {
                "selected_game_count": len(source_index),
                "files_discovered": 1,
                "files_selected": 1,
            }
        )
        print(f"Mode: single file ({TARGET_PLAYBYPLAY_S3_PATH})")
        print("Files selected: 1")

    games_upserted: set[str] = set()
    total_rows_written = 0
    total_source_rows_processed = 0
    total_files_processed = 0
    skipped: list[tuple[str | None, str]] = []
    max_source_last_modified_seen: datetime | None = None

    for index, key in enumerate(keys, start=1):
        source_last_modified = source_last_modified_by_key.get(key)
        if isinstance(source_last_modified, datetime) and source_last_modified.tzinfo is None:
            source_last_modified = source_last_modified.replace(tzinfo=timezone.utc)
        if isinstance(source_last_modified, datetime):
            if max_source_last_modified_seen is None or source_last_modified > max_source_last_modified_seen:
                max_source_last_modified_seen = source_last_modified

        game_id = extract_game_id_from_key(key)
        print(
            f"[{index}/{len(keys)}] Processing game_id={game_id or 'unknown'} "
            f"key={key}"
        )
        try:
            if game_id is None:
                raise ProjectionFailure("Missing fallback game_id from source key")
            payload = pbp_silver.read_json_payload(s3_client, key)
            playbyplay_rows = load_refreshed_playbyplay_rows_from_raw(s3_client, game_id)
            on_court_rows = read_on_court_rows_from_s3(s3_client, game_id)
            build_result = pipeline.build_exact_game(
                PossessionGameInput(
                    game_id=game_id,
                    payload=payload,
                    playbyplay_rows=playbyplay_rows,
                    on_court_rows=on_court_rows,
                    source_key=key,
                    source_last_modified_utc=source_last_modified,
                )
            )
        except (BotoCoreError, ClientError, OSError, pa.ArrowInvalid, pa.ArrowTypeError) as exc:
            skipped.append((game_id, key))
            print(
                f"Skipping file game_id={game_id or 'unknown'} "
                f"key={key} ({type(exc).__name__}: {exc})"
            )
            continue
        except Exception as exc:
            skipped.append((game_id, key))
            print(
                f"Skipping file game_id={game_id or 'unknown'} "
                f"key={key} ({type(exc).__name__}: {exc})"
            )
            continue

        total_files_processed += 1
        total_source_rows_processed += len(playbyplay_rows)
        possession_rows = build_result.rows.rows

        if game_id is None:
            print(f"Warning: missing gameId in parquet key={key}")
            print(f"[{index}/{len(keys)}] Completed with skip (missing gameId)")
            continue

        if build_result.status != "exact_written_candidate":
            skipped.append((game_id, key))
            print(
                f"Skipping file game_id={game_id or 'unknown'} "
                f"key={key} ({build_result.warning_details or build_result.status})"
            )
            continue

        if len(possession_rows) == 0:
            print(
                f"Info: no possession rows for game_id={game_id} key={key}; "
                "existing silver parquet left unchanged."
            )
            print(f"[{index}/{len(keys)}] Completed with skip (empty possessions) game_id={game_id}")
            continue

        write_game_parquet_to_s3(
            game_id,
            possession_rows,
            pipeline_run_id=pipeline_run_id,
            ingested_at_utc=ingested_at_utc,
            source_key=json.dumps(
                {
                    "playbyplay_key": key,
                    "on_court_key": f"{ON_COURT_PREFIX}game_id={game_id}.parquet",
                },
                sort_keys=True,
            ),
            source_last_modified_utc=source_last_modified,
            s3_client=s3_client,
        )
        games_upserted.add(game_id)
        total_rows_written += len(possession_rows)
        print(
            f"[{index}/{len(keys)}] Completed game_id={game_id} "
            f"rows_written={len(possession_rows)}"
        )

    print(f"Total files scanned: {len(keys)}")
    print(f"Total files processed: {total_files_processed}")
    print(f"Total playbyplay rows processed: {total_source_rows_processed}")
    print(f"Total possession rows written: {total_rows_written}")
    print(f"Games upserted: {len(games_upserted)}")
    print(f"Skipped files: {len(skipped)}")

    if skipped:
        print("Skipped game_ids:")
        for skipped_game_id, skipped_key in skipped:
            print(f"- game_id={skipped_game_id or 'unknown'} key={skipped_key}")

    print(f"Wrote parquet files under s3://{S3_BUCKET}/{DESTINATION_PREFIX}")

    warning_reason_counts: dict[str, int] = {}
    warning_count = 0
    if len(skipped) > 0:
        warning_reason_counts["skipped_unreadable_or_invalid_files"] = len(skipped)
        warning_count += len(skipped)

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

    run_status = "success_with_warnings" if warning_count > 0 else "success"
    details_key = write_details_json(
        s3_client=s3_client,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        details={
            "pipeline_run_id": pipeline_run_id,
            "selection_mode": selection_meta.get("selection_mode"),
            "target_game_ids": selection_meta.get("target_game_ids", []),
            "selected_game_count": selection_meta.get("selected_game_count", 0),
            "written_game_count": len(games_upserted),
            "checkpoint_enabled": True,
            "legacy_state_fallback_used": bool(selection_meta.get("legacy_state_fallback_used")),
            "warning_reason_counts": warning_reason_counts,
            "skipped_files": [
                {"game_id": row_game_id, "source_key": source_key}
                for row_game_id, source_key in skipped
            ][:1000],
        },
    )
    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": run_status,
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_prefix": RAW_SOURCE_PREFIX,
        "destination_prefix": DESTINATION_PREFIX,
        "process_all_files": int(PROCESS_ALL_FILES),
        "target_source_s3_path": TARGET_PLAYBYPLAY_S3_PATH if not PROCESS_ALL_FILES else None,
        "incremental_mode": int(INCREMENTAL_MODE),
        "force_full_refresh": int(FORCE_FULL_REFRESH),
        "selection_mode": selection_meta.get("selection_mode"),
        "selection_watermark_utc": selection_meta.get("watermark_utc"),
        "selection_effective_watermark_utc": selection_meta.get("effective_watermark_utc"),
        "selection_lookback_minutes": selection_meta.get("lookback_minutes"),
        "selected_game_count": selection_meta.get("selected_game_count", len(keys)),
        "written_game_count": len(games_upserted),
        "target_game_ids": json.dumps(selection_meta.get("target_game_ids", []), sort_keys=True),
        "checkpoint_enabled": 1,
        "legacy_state_fallback_used": int(bool(selection_meta.get("legacy_state_fallback_used"))),
        "checkpoint_key": checkpoint_key_written,
        "files_selected": len(keys),
        "files_processed": total_files_processed,
        "games_upserted": len(games_upserted),
        "actions_processed": total_source_rows_processed,
        "rows_written": total_rows_written,
        "files_with_empty_actions": 0,
        "skipped_file_count": len(skipped),
        "warning_count": warning_count,
        "error_count": 0,
        "details_key": details_key,
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

    state_after = {
        "table_name": TABLE_NAME,
        "updated_at_utc": pbp_silver.state_datetime_to_iso(ingested_at_utc),
        "pipeline_run_id": pipeline_run_id,
        "max_source_last_modified_utc": pbp_silver.state_datetime_to_iso(max_source_last_modified_seen),
        "files_selected": len(keys),
        "games_upserted": len(games_upserted),
        "previous_max_source_last_modified_utc": state_before.get("max_source_last_modified_utc"),
        "lookback_minutes": INCREMENTAL_LOOKBACK_MINUTES,
    }
    if PROCESS_ALL_FILES:
        write_state(s3_client, state_after)
        print(f"Wrote state: s3://{S3_BUCKET}/{STATE_KEY}")


if __name__ == "__main__":
    main()
