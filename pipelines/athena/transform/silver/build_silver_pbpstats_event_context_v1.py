"""Build Athena standalone pbpstats event-context sidecar."""

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
from botocore.exceptions import ClientError
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]
PBPSTATS_ROOT = REPO_ROOT / "reference" / "pbpstats"
if str(PBPSTATS_ROOT) not in sys.path:
    sys.path.insert(0, str(PBPSTATS_ROOT))

from heavy_silver_runtime import (
    add_source_artifact,
    build_source_index_from_objects,
    checkpoint_rows_with_updates,
    normalize_utc_datetime,
    parse_target_game_ids,
    read_checkpoint_index,
    select_game_ids_for_processing,
    write_checkpoint_index,
)
from pbpstats.resources.enhanced_pbp import StartOfPeriod
from pbpstats_projection_common import (
    ProjectionFailure,
    add_silver_metadata,
    list_size,
    load_live_enhanced_pbp_items_with_period_starter_warnings,
    normalize_long,
    normalize_long_list,
    normalize_string,
    sort_long_list,
)
from silver_pipeline_helpers import run_date, write_audit_artifacts, write_rows_as_parquet

import build_silver_playbyplay_events as pbp_silver

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "raw/cdn/playbyplay/"
PROJECTION_PREFIX = "silver/pbpstats_event_projection_v1/"
BOXSCORE_PLAYER_KEY = "silver/boxscore_player_game.parquet"
DESTINATION_PREFIX = "silver/pbpstats_event_context_v1/"
TABLE_NAME = "pbpstats_event_context_v1"
SOURCE_SYSTEM = "pbpstats_live_enhanced_pbp_event_context"
META_SCHEMA_VERSION = 1
FORCE_FULL_REFRESH = os.getenv("PBPSTATS_EVENT_CONTEXT_FORCE_FULL_REFRESH", "false").strip().lower() == "true"
TARGET_GAME_IDS = parse_target_game_ids(os.getenv("PBPSTATS_EVENT_CONTEXT_TARGET_GAME_IDS", ""))

PROJECTION_COLUMNS = [
    "game_id",
    "event_num",
    "home_team_id",
    "away_team_id",
    "home_current_player_ids",
    "away_current_player_ids",
    "home_lineup_id",
    "away_lineup_id",
    "home_fouls_to_give",
    "away_fouls_to_give",
    "home_period_starter_ids",
    "away_period_starter_ids",
]

STRING_COLUMNS = {
    "game_id",
    "home_lineup_id",
    "away_lineup_id",
}

ARRAY_LONG_COLUMNS = {
    "home_current_player_ids",
    "away_current_player_ids",
    "home_period_starter_ids",
    "away_period_starter_ids",
}

LONG_COLUMNS = set(PROJECTION_COLUMNS) - STRING_COLUMNS - ARRAY_LONG_COLUMNS

TARGET_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("event_num", pa.int64()),
        pa.field("home_team_id", pa.int64()),
        pa.field("away_team_id", pa.int64()),
        pa.field("home_current_player_ids", pa.list_(pa.int64())),
        pa.field("away_current_player_ids", pa.list_(pa.int64())),
        pa.field("home_lineup_id", pa.string()),
        pa.field("away_lineup_id", pa.string()),
        pa.field("home_fouls_to_give", pa.int64()),
        pa.field("away_fouls_to_give", pa.int64()),
        pa.field("home_period_starter_ids", pa.list_(pa.int64())),
        pa.field("away_period_starter_ids", pa.list_(pa.int64())),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def empty_projection_payload() -> dict[str, Any]:
    return {column: None for column in PROJECTION_COLUMNS}


def lineup_id_from_player_ids(player_ids: list[int] | None) -> str | None:
    if player_ids is None:
        return None
    return "-".join(str(player_id) for player_id in sorted(player_ids, key=str))


def _team_value(mapping: Any, team_id: int, *, field_name: str) -> Any:
    if mapping is None:
        raise ProjectionFailure(f"Missing {field_name}")
    try:
        return mapping[team_id]
    except KeyError as exc:
        raise ProjectionFailure(f"Missing {field_name} for team_id={team_id}") from exc
    except TypeError as exc:
        raise ProjectionFailure(f"Invalid {field_name} mapping type: {type(mapping).__name__}") from exc


def _team_player_ids(mapping: Any, team_id: int, *, field_name: str) -> list[int]:
    values = normalize_long_list(_team_value(mapping, team_id, field_name=field_name))
    values = sort_long_list(values)
    if values is None:
        raise ProjectionFailure(f"Invalid {field_name} for team_id={team_id}")
    return values


def _team_long_value(mapping: Any, team_id: int, *, field_name: str) -> int:
    value = normalize_long(_team_value(mapping, team_id, field_name=field_name))
    if value is None:
        raise ProjectionFailure(f"Invalid {field_name} for team_id={team_id}")
    return value


def build_event_context_row(
    event: Any,
    *,
    home_team_id: int,
    away_team_id: int,
    starter_warning_event_nums: set[int],
    source_file: str,
    source_last_modified_utc: Any,
) -> dict[str, Any]:
    current_players = getattr(event, "current_players", None)
    lineup_ids = getattr(event, "lineup_ids", None)
    fouls_to_give = getattr(event, "fouls_to_give", None)

    home_players = _team_player_ids(current_players, home_team_id, field_name="current_players")
    away_players = _team_player_ids(current_players, away_team_id, field_name="current_players")

    home_lineup_id = normalize_string(_team_value(lineup_ids, home_team_id, field_name="lineup_ids"))
    away_lineup_id = normalize_string(_team_value(lineup_ids, away_team_id, field_name="lineup_ids"))
    if home_lineup_id is None or away_lineup_id is None:
        raise ProjectionFailure("Missing lineup_ids")

    expected_home_lineup_id = lineup_id_from_player_ids(home_players)
    expected_away_lineup_id = lineup_id_from_player_ids(away_players)
    if home_lineup_id != expected_home_lineup_id or away_lineup_id != expected_away_lineup_id:
        raise ProjectionFailure("Lineup id mismatch against sorted current_players arrays")

    row = empty_projection_payload()
    row.update(
        {
            "game_id": normalize_string(getattr(event, "game_id", None)),
            "event_num": normalize_long(getattr(event, "event_num", None)),
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "home_current_player_ids": home_players,
            "away_current_player_ids": away_players,
            "home_lineup_id": home_lineup_id,
            "away_lineup_id": away_lineup_id,
            "home_fouls_to_give": _team_long_value(fouls_to_give, home_team_id, field_name="fouls_to_give"),
            "away_fouls_to_give": _team_long_value(fouls_to_give, away_team_id, field_name="fouls_to_give"),
        }
    )

    if isinstance(event, StartOfPeriod):
        if row["event_num"] in starter_warning_event_nums:
            row["home_period_starter_ids"] = None
            row["away_period_starter_ids"] = None
        else:
            period_starters = getattr(event, "period_starters", None)
            row["home_period_starter_ids"] = _team_player_ids(
                period_starters,
                home_team_id,
                field_name="period_starters",
            )
            row["away_period_starter_ids"] = _team_player_ids(
                period_starters,
                away_team_id,
                field_name="period_starters",
            )

    return row


def project_payload_to_rows(
    payload: dict[str, Any],
    *,
    home_team_id: int | None,
    away_team_id: int | None,
    source_file: str,
    source_last_modified_utc: Any,
    fallback_game_id: str | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    if home_team_id is None or away_team_id is None or home_team_id == away_team_id:
        raise ProjectionFailure("Missing usable home/away team orientation from latest raw boxscore")

    game_id, items, starter_warnings = load_live_enhanced_pbp_items_with_period_starter_warnings(
        payload,
        fallback_game_id=fallback_game_id,
    )
    starter_warning_event_nums = {
        warning["event_num"]
        for warning in starter_warnings
        if warning.get("event_num") is not None
    }
    rows = [
        build_event_context_row(
            event,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            starter_warning_event_nums=starter_warning_event_nums,
            source_file=source_file,
            source_last_modified_utc=source_last_modified_utc,
        )
        for event in items
    ]
    seen_keys: set[tuple[str | None, int | None]] = set()
    duplicate_keys: list[tuple[str | None, int | None]] = []
    for row in rows:
        key = (row["game_id"], row["event_num"])
        if key in seen_keys:
            duplicate_keys.append(key)
        else:
            seen_keys.add(key)
    if duplicate_keys:
        raise ProjectionFailure(f"Duplicate projected event keys: {duplicate_keys[:10]}")
    return game_id, rows, starter_warnings


def list_parquet_game_objects(s3_client, prefix: str) -> list[dict[str, Any]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = str(obj.get("Key") or "")
            if not key.endswith(".parquet"):
                continue
            game_id = key.rsplit("/", 1)[-1]
            if not game_id.startswith("game_id="):
                continue
            objects.append(obj)
    return objects


def extract_game_id_from_parquet_key(key: str) -> str | None:
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id=") or not filename.endswith(".parquet"):
        return None
    return filename[len("game_id=") : -len(".parquet")] or None


def read_projection_key_set_from_s3(s3_client, game_id: str) -> set[tuple[str, int]]:
    key = f"{PROJECTION_PREFIX}game_id={game_id}.parquet"
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload = response["Body"].read()
    table = pq.read_table(pa.BufferReader(payload), columns=["game_id", "event_num"])
    output: set[tuple[str, int]] = set()
    for row in table.to_pylist():
        row_game_id = normalize_string(row.get("game_id"))
        row_event_num = normalize_long(row.get("event_num"))
        if row_game_id is None or row_event_num is None:
            continue
        output.add((row_game_id, row_event_num))
    return output


def boxscore_team_orientation_for_game(s3_client, game_id: str) -> tuple[int | None, int | None]:
    boxscore_context = pbp_silver.load_boxscore_context_for_game(s3_client, game_id)
    teams = boxscore_context.get("teams") or {}
    home_team_id = None
    away_team_id = None
    for team_id, team_meta in teams.items():
        location = team_meta.get("location")
        if location == "h":
            home_team_id = normalize_long(team_id)
        elif location == "v":
            away_team_id = normalize_long(team_id)
    return home_team_id, away_team_id


def write_game_parquet_to_s3(game_id: str, rows: list[dict[str, Any]], s3_client) -> str:
    key = f"{DESTINATION_PREFIX}game_id={str(game_id).zfill(10)}.parquet"
    write_rows_as_parquet(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        key=key,
        rows=rows,
        schema=TARGET_SCHEMA,
    )
    return key


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


def main() -> None:
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"{TABLE_NAME}_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    checkpoint_exists, checkpoint_rows = read_checkpoint_index(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
    )

    raw_objects = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = str(obj.get("Key") or "")
            if key.endswith(".json") and pbp_silver.extract_game_id_from_key(key) is not None:
                raw_objects.append(obj)

    projection_objects = list_parquet_game_objects(s3_client, PROJECTION_PREFIX)
    projection_game_ids = {
        extract_game_id_from_parquet_key(str(obj.get("Key") or ""))
        for obj in projection_objects
    }
    projection_game_ids = {game_id for game_id in projection_game_ids if game_id}

    source_last_modified_by_key = {
        str(obj.get("Key") or ""): normalize_utc_datetime(obj.get("LastModified"))
        for obj in raw_objects
    }
    source_index = build_source_index_from_objects(
        raw_objects,
        game_id_from_key=pbp_silver.extract_game_id_from_key,
    )
    source_index = {
        game_id: artifacts
        for game_id, artifacts in source_index.items()
        if game_id in projection_game_ids
    }

    try:
        boxscore_player_head = s3_client.head_object(Bucket=S3_BUCKET, Key=BOXSCORE_PLAYER_KEY)
        boxscore_player_last_modified = normalize_utc_datetime(boxscore_player_head.get("LastModified"))
    except ClientError:
        boxscore_player_last_modified = None

    for game_id in list(source_index):
        add_source_artifact(
            source_index,
            game_id=game_id,
            key=BOXSCORE_PLAYER_KEY,
            last_modified=boxscore_player_last_modified,
        )

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
    selection_meta["selected_game_count"] = len(selected_game_ids)
    selection_meta["files_discovered"] = len(raw_objects)
    selection_meta["files_selected"] = len(keys)
    selection_meta["projection_game_count"] = len(projection_game_ids)

    games_upserted: set[str] = set()
    failed_games: list[dict[str, Any]] = []
    warning_games: list[dict[str, Any]] = []
    total_rows_written = 0
    total_files_processed = 0
    duplicate_key_count = 0
    orphan_row_count = 0
    non_five_player_row_count = 0
    checkpoint_key_written: str | None = None

    for index, key in enumerate(keys, start=1):
        fallback_game_id = pbp_silver.extract_game_id_from_key(key)
        source_last_modified = source_last_modified_by_key.get(key)
        print(
            f"[{index}/{len(keys)}] Processing pbpstats context game_id={fallback_game_id or 'unknown'} key={key}"
        )
        try:
            if fallback_game_id is None:
                raise ProjectionFailure("Missing fallback game_id from source key")
            payload = pbp_silver.read_json_payload(s3_client, key)
            home_team_id, away_team_id = boxscore_team_orientation_for_game(s3_client, fallback_game_id)
            game_id, rows, starter_warnings = project_payload_to_rows(
                payload,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                source_file=key,
                source_last_modified_utc=source_last_modified,
                fallback_game_id=fallback_game_id,
            )
            projection_key_set = read_projection_key_set_from_s3(s3_client, game_id)
            context_key_set = {
                (normalize_string(row.get("game_id")) or "", normalize_long(row.get("event_num")) or -1)
                for row in rows
            }
            orphans = sorted(context_key_set - projection_key_set)
            missing = sorted(projection_key_set - context_key_set)
            if orphans or missing:
                orphan_row_count += len(orphans)
                raise ProjectionFailure(
                    f"Projection/context key mismatch: orphan_count={len(orphans)} missing_count={len(missing)}"
                )
            if len(context_key_set) != len(rows):
                duplicate_key_count += len(rows) - len(context_key_set)
                raise ProjectionFailure("Duplicate projected event keys")

            bad_lineup_rows = [
                {
                    "event_num": row["event_num"],
                    "home_player_count": list_size(row.get("home_current_player_ids")),
                    "away_player_count": list_size(row.get("away_current_player_ids")),
                }
                for row in rows
                if list_size(row.get("home_current_player_ids")) != 5
                or list_size(row.get("away_current_player_ids")) != 5
            ]
            non_five_player_row_count += len(bad_lineup_rows)

            rows = add_silver_metadata(
                rows,
                pipeline_run_id=pipeline_run_id,
                ingested_at_utc=ingested_at_utc,
                source_system=SOURCE_SYSTEM,
                source_key=key,
                source_last_modified_utc=source_last_modified,
                schema_version=META_SCHEMA_VERSION,
            )
            write_game_parquet_to_s3(game_id, rows, s3_client)
            games_upserted.add(game_id)
            total_rows_written += len(rows)
            total_files_processed += 1
            if starter_warnings or bad_lineup_rows:
                warning_games.append(
                    {
                        "game_id": game_id,
                        "starter_warning_count": len(starter_warnings),
                        "bad_lineup_row_count": len(bad_lineup_rows),
                        "starter_warning_examples": starter_warnings[:5],
                        "bad_lineup_examples": bad_lineup_rows[:5],
                    }
                )
        except Exception as exc:
            failed_games.append(
                {
                    "game_id": fallback_game_id,
                    "source_key": key,
                    "error_type": type(exc).__name__,
                    "error_detail": str(exc)[:2000],
                }
            )

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

    success_game_count = len(games_upserted)
    failed_game_count = len(failed_games)
    warning_count = sum(
        warning.get("starter_warning_count", 0) + warning.get("bad_lineup_row_count", 0)
        for warning in warning_games
    )
    run_status = "success"
    if failed_game_count > 0 and success_game_count > 0:
        run_status = "success_with_warnings"
    elif failed_game_count > 0:
        run_status = "error"
    elif warning_count > 0:
        run_status = "success_with_warnings"

    warning_reason_counts: dict[str, int] = {}
    if failed_game_count > 0 and success_game_count > 0:
        warning_reason_counts["failed_game_projection"] = failed_game_count
    if warning_games:
        warning_reason_counts["period_starter_inference_gap"] = sum(
            warning.get("starter_warning_count", 0) for warning in warning_games
        )
        warning_reason_counts["non_five_player_context_rows"] = non_five_player_row_count
    error_reason_counts = {"failed_game_projection": failed_game_count} if run_status == "error" else {}

    details_key = write_details_json(
        s3_client=s3_client,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        details={
            "pipeline_run_id": pipeline_run_id,
            "selection_mode": selection_meta.get("selection_mode"),
            "force_full_refresh": FORCE_FULL_REFRESH,
            "target_game_ids": sorted(TARGET_GAME_IDS),
            "selected_game_count": selection_meta.get("selected_game_count", 0),
            "written_game_count": len(games_upserted),
            "checkpoint_enabled": True,
            "legacy_state_fallback_used": bool(selection_meta.get("legacy_state_fallback_used")),
            "failed_games": failed_games[:1000],
            "warning_games": warning_games[:1000],
        },
    )

    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": run_status,
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_prefix": SOURCE_PREFIX,
        "destination_prefix": DESTINATION_PREFIX,
        "force_full_refresh": int(FORCE_FULL_REFRESH),
        "selection_mode": selection_meta.get("selection_mode"),
        "selected_game_count": selection_meta.get("selected_game_count", len(keys)),
        "written_game_count": len(games_upserted),
        "target_game_ids": json.dumps(sorted(TARGET_GAME_IDS), sort_keys=True),
        "checkpoint_enabled": 1,
        "legacy_state_fallback_used": int(bool(selection_meta.get("legacy_state_fallback_used"))),
        "checkpoint_key": checkpoint_key_written,
        "files_selected": len(keys),
        "files_processed": total_files_processed,
        "games_upserted": len(games_upserted),
        "rows_written": total_rows_written,
        "warning_count": warning_count if run_status == "success_with_warnings" else 0,
        "error_count": failed_game_count if run_status == "error" else 0,
        "warning_reason_counts": json.dumps(warning_reason_counts, sort_keys=True),
        "error_reason_counts": json.dumps(error_reason_counts, sort_keys=True),
        "details_key": details_key,
        "duplicate_key_count": duplicate_key_count,
        "orphan_row_count": orphan_row_count,
        "non_five_player_row_count": non_five_player_row_count,
    }
    write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )

    print(
        f"Done: {TABLE_NAME} (selected={len(keys)}, successful={success_game_count}, failed={failed_game_count}, "
        f"warnings={warning_count}, rows={total_rows_written})"
    )


if __name__ == "__main__":
    main()
