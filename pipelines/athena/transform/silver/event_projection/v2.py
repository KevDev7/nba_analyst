"""Build raw-first Athena event projection v2 from raw CDN play-by-play JSON."""

from __future__ import annotations

from collections import defaultdict
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pipelines").is_dir())
PBPSTATS_ROOT_CANDIDATES = [
    REPO_ROOT / "references" / "pbpstats",
    REPO_ROOT / "reference" / "pbpstats",
]
PBPSTATS_ROOT = next((path for path in PBPSTATS_ROOT_CANDIDATES if path.exists()), PBPSTATS_ROOT_CANDIDATES[0])
if PBPSTATS_ROOT.exists() and str(PBPSTATS_ROOT) not in sys.path:
    sys.path.insert(0, str(PBPSTATS_ROOT))

from heavy_silver_runtime import (
    build_source_index_from_objects,
    checkpoint_rows_with_updates,
    normalize_utc_datetime,
    parse_target_game_ids,
    read_checkpoint_index,
    select_game_ids_for_processing,
    selection_audit_fields,
    write_checkpoint_index,
)
from pbpstats.resources.enhanced_pbp import FieldGoal, Foul, FreeThrow, Rebound, StartOfPeriod
from pbpstats.resources.enhanced_pbp.live.enhanced_pbp_factory import LiveEnhancedPbpFactory
from pbpstats_projection_common import (
    ProjectionFailure,
    add_silver_metadata,
    normalize_long,
)
from silver_pipeline_helpers import run_date, write_audit_artifacts, write_rows_as_parquet

import build_silver_pbpstats_event_projection_v1 as projection_v1
import build_silver_playbyplay_events as pbp_silver

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "raw/cdn/playbyplay/"
DESTINATION_PREFIX = "silver/event_projection_v2/"
TABLE_NAME = "event_projection_v2"
SOURCE_SYSTEM = "nba_cdn_playbyplay_raw_first_projection_v2"
META_SCHEMA_VERSION = 1
FORCE_FULL_REFRESH = os.getenv("EVENT_PROJECTION_V2_FORCE_FULL_REFRESH", "false").strip().lower() == "true"
TARGET_GAME_IDS = parse_target_game_ids(os.getenv("EVENT_PROJECTION_V2_TARGET_GAME_IDS", ""))

PROJECTION_COLUMNS = projection_v1.PROJECTION_COLUMNS
EVENT_CLASS_FLAG_COLUMNS = projection_v1.EVENT_CLASS_FLAG_COLUMNS
TARGET_SCHEMA = projection_v1.TARGET_SCHEMA

_EVENT_FACTORY = LiveEnhancedPbpFactory()


def _filtered_actions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    actions = payload.get("game", {}).get("actions") or []
    return [action for action in actions if isinstance(action, dict)]


def _action_richness_score(action: dict[str, Any]) -> tuple[int, int]:
    populated = 0
    sequence_bonus = 0
    for value in action.values():
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                populated += 1
        elif isinstance(value, list):
            if value:
                populated += 1
                sequence_bonus += len(value)
        else:
            populated += 1
    return populated, sequence_bonus


def _merge_duplicate_action_pair(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in sorted(set(left) | set(right)):
        left_value = left.get(key)
        right_value = right.get(key)
        if isinstance(left_value, list) and isinstance(right_value, list):
            merged[key] = left_value if len(left_value) >= len(right_value) else right_value
        elif right_value not in (None, "", []):
            merged[key] = right_value
        else:
            merged[key] = left_value
    return merged


def _dedupe_duplicate_actions(payload: dict[str, Any]) -> dict[str, Any]:
    actions = _filtered_actions(payload)
    deduped: list[dict[str, Any]] = []
    duplicates_found = False
    for action in actions:
        if not deduped:
            deduped.append(action)
            continue
        previous = deduped[-1]
        duplicate_key = (
            action.get("actionNumber"),
            action.get("orderNumber"),
            action.get("actionType"),
            action.get("subType"),
            action.get("teamId"),
            action.get("personId"),
            action.get("description"),
        )
        previous_key = (
            previous.get("actionNumber"),
            previous.get("orderNumber"),
            previous.get("actionType"),
            previous.get("subType"),
            previous.get("teamId"),
            previous.get("personId"),
            previous.get("description"),
        )
        if duplicate_key == previous_key:
            duplicates_found = True
            if _action_richness_score(action) >= _action_richness_score(previous):
                deduped[-1] = _merge_duplicate_action_pair(previous, action)
            else:
                deduped[-1] = _merge_duplicate_action_pair(action, previous)
            continue
        deduped.append(action)

    if not duplicates_found:
        return payload

    game_payload = dict(payload.get("game", {}))
    game_payload["actions"] = deduped
    rewritten_payload = dict(payload)
    rewritten_payload["game"] = game_payload
    return rewritten_payload


def _attach_neighbor_links(events: list[Any]) -> None:
    for index, event in enumerate(events):
        if index == 0 and index == len(events) - 1:
            event.previous_event = None
            event.next_event = None
        elif isinstance(event, StartOfPeriod) or index == 0:
            event.previous_event = None
            event.next_event = events[index + 1]
        elif index == len(events) - 1 or event.period != events[index + 1].period:
            event.previous_event = events[index - 1]
            event.next_event = None
        else:
            event.previous_event = events[index - 1]
            event.next_event = events[index + 1]


def _compute_is_penalty_event(event: Any, team_ids: list[int]) -> bool | None:
    if not hasattr(event, "fouls_to_give") or len(team_ids) != 2:
        return False
    offense_team_id = event.get_offense_team_id()
    if offense_team_id in {None, 0} and getattr(event, "previous_event", None) is not None:
        defense_team_id = event.previous_event.get_offense_team_id()
    else:
        defense_team_id = team_ids[0] if offense_team_id == team_ids[1] else team_ids[1]
    if defense_team_id is None:
        return False
    if event.fouls_to_give[defense_team_id] != 0:
        return False

    if isinstance(event, (Foul, FreeThrow, Rebound)):
        if isinstance(event, Foul):
            foul_event = event
        elif isinstance(event, FreeThrow):
            foul_event = event.foul_that_led_to_ft
        else:
            if not event.oreb and isinstance(event.missed_shot, FreeThrow):
                foul_event = event.missed_shot.foul_that_led_to_ft
            else:
                return True

        if foul_event is None:
            return True
        if foul_event.previous_event is None:
            return True
        fouls_to_give_prior_to_foul = foul_event.previous_event.fouls_to_give[defense_team_id]
        if fouls_to_give_prior_to_foul > 0:
            return False

    return True


def _populate_lightweight_runtime_state(
    events: list[Any],
    raw_rows: list[dict[str, Any]],
    *,
    team_ids: list[int],
) -> None:
    player_game_fouls = defaultdict(int)
    fouls_to_give = defaultdict(lambda: 4)
    score = defaultdict(int)

    for index, (event, raw_row) in enumerate(zip(events, raw_rows)):
        if index == 0 or isinstance(event, StartOfPeriod):
            if event.period <= 4:
                fouls_to_give = defaultdict(lambda: 4)
            else:
                fouls_to_give = defaultdict(lambda: 3)

        if event.seconds_remaining <= 120:
            if len(fouls_to_give.keys()) == 0:
                fouls_to_give = defaultdict(lambda: 1)
            elif len(fouls_to_give.keys()) == 1:
                team_id = list(fouls_to_give.keys())[0]
                team_fouls_to_give = min(fouls_to_give[team_id], 1)
                fouls_to_give = defaultdict(lambda: 1)
                fouls_to_give[team_id] = team_fouls_to_give
            else:
                for team_id in list(fouls_to_give.keys()):
                    fouls_to_give[team_id] = min(fouls_to_give[team_id], 1)

        if isinstance(event, Foul):
            if event.counts_towards_penalty and fouls_to_give[event.team_id] > 0:
                fouls_to_give[event.team_id] -= 1
            if event.counts_as_personal_foul:
                player_game_fouls[event.player1_id] += 1

        if isinstance(event, (FieldGoal, FreeThrow)) and event.is_made:
            score[event.team_id] += event.shot_value

        event.team_starting_with_ball = normalize_long(raw_row.get("teamStartingPeriodWithBall"))
        event.player_game_fouls = player_game_fouls.copy()
        event.fouls_to_give = fouls_to_give.copy()
        event.score = score.copy()
        event.possession_changing_override = False
        event.non_possession_changing_override = False

        event.is_penalty_event = (
            lambda bound_event=event, known_team_ids=tuple(team_ids): _compute_is_penalty_event(
                bound_event,
                list(known_team_ids),
            )
        )


def _change_team_id_on_drebs(events: list[Any]) -> None:
    for event in events:
        if isinstance(event, Rebound):
            if event.is_real_rebound and not event.oreb and event.previous_event is not None:
                event.offense_team_id = event.previous_event.offense_team_id


def _ordered_team_ids(
    raw_rows: list[dict[str, Any]],
    *,
    boxscore_context: dict[str, Any] | None,
) -> list[int]:
    teams = (boxscore_context or {}).get("teams") or {}
    if teams:
        return list(teams.keys())
    return pbp_silver.event_team_ids(raw_rows, boxscore_context or {})


def _build_lightweight_events(
    payload: dict[str, Any],
    *,
    game_id: str,
    raw_rows: list[dict[str, Any]],
    boxscore_context: dict[str, Any] | None = None,
) -> list[Any]:
    actions = _filtered_actions(payload)
    if len(actions) != len(raw_rows):
        raise ProjectionFailure(
            f"Raw action count ({len(actions)}) does not match enriched row count ({len(raw_rows)})"
        )

    events: list[Any] = []
    for action in actions:
        action_type = action.get("actionType")
        sub_type = action.get("subType", "")
        event_class = _EVENT_FACTORY.get_event_class(action_type, sub_type)
        event = event_class(action, game_id)
        if not hasattr(event, "sub_type") and action_type in {"foul", "freethrow"}:
            event.sub_type = sub_type or ""
            event._missing_sub_type = "subType" not in action
        events.append(event)

    team_ids = _ordered_team_ids(raw_rows, boxscore_context=boxscore_context)
    _attach_neighbor_links(events)
    _populate_lightweight_runtime_state(events, raw_rows, team_ids=team_ids)
    _change_team_id_on_drebs(events)
    return events


def build_event_projection_row(
    event: Any,
    *,
    source_file: str,
    source_last_modified_utc: Any,
) -> dict[str, Any]:
    row = projection_v1.build_event_projection_row(
        event,
        source_file=source_file,
        source_last_modified_utc=source_last_modified_utc,
    )
    if getattr(event, "_missing_sub_type", False):
        row["sub_type"] = None
    return row


def project_payload_to_rows(
    payload: dict[str, Any],
    *,
    source_file: str,
    source_last_modified_utc: Any,
    fallback_game_id: str | None = None,
    boxscore_context: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    payload = _dedupe_duplicate_actions(payload)
    raw_rows, game_id = pbp_silver.build_rows_from_payload(
        payload,
        fallback_game_id,
        boxscore_context=boxscore_context or {},
    )
    if game_id is None:
        raise ProjectionFailure("Missing game_id after raw-first projection")
    events = _build_lightweight_events(
        payload,
        game_id=game_id,
        raw_rows=raw_rows,
        boxscore_context=boxscore_context or {},
    )
    rows = [
        build_event_projection_row(
            event,
            source_file=source_file,
            source_last_modified_utc=source_last_modified_utc,
        )
        for event in events
    ]
    return game_id, rows


def list_raw_objects(s3_client) -> list[dict[str, Any]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".json") and pbp_silver.extract_game_id_from_key(key) is not None:
                objects.append(obj)
    return objects


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

    objects = list_raw_objects(s3_client)
    source_last_modified_by_key = {
        str(obj.get("Key") or ""): normalize_utc_datetime(obj.get("LastModified"))
        for obj in objects
    }
    source_index = build_source_index_from_objects(
        objects,
        game_id_from_key=pbp_silver.extract_game_id_from_key,
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
    selection_meta["files_discovered"] = len(objects)
    selection_meta["files_selected"] = len(keys)

    games_upserted: set[str] = set()
    failed_games: list[dict[str, Any]] = []
    total_rows_written = 0
    total_files_processed = 0
    one_hot_violation_count = 0
    duplicate_key_count = 0
    checkpoint_key_written: str | None = None

    for index, key in enumerate(keys, start=1):
        fallback_game_id = pbp_silver.extract_game_id_from_key(key)
        source_last_modified = source_last_modified_by_key.get(key)
        print(
            f"[{index}/{len(keys)}] Processing event projection v2 game_id={fallback_game_id or 'unknown'} key={key}"
        )
        try:
            payload = pbp_silver.read_json_payload(s3_client, key)
            boxscore_context = pbp_silver.load_boxscore_context_for_game(s3_client, fallback_game_id)
            game_id, rows = project_payload_to_rows(
                payload,
                source_file=key,
                source_last_modified_utc=source_last_modified,
                fallback_game_id=fallback_game_id,
                boxscore_context=boxscore_context,
            )
            key_pairs = {(row["game_id"], row["event_num"]) for row in rows}
            if len(key_pairs) != len(rows):
                duplicate_key_count += len(rows) - len(key_pairs)
                raise ProjectionFailure("Duplicate projected event keys")
            row_flag_violations = sum(
                1
                for row in rows
                if sum(bool(row.get(column)) for column in EVENT_CLASS_FLAG_COLUMNS) != 1
            )
            one_hot_violation_count += row_flag_violations
            if row_flag_violations:
                raise ProjectionFailure(f"One-hot event class violation count={row_flag_violations}")
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
        except (ProjectionFailure, RuntimeError, ValueError, AttributeError, BotoCoreError, ClientError) as exc:
            failed_games.append(
                {
                    "game_id": fallback_game_id,
                    "source_key": key,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            print(f"Failed game_id={fallback_game_id or 'unknown'}: {type(exc).__name__}: {exc}")

    if games_upserted:
        checkpoint_rows_next = checkpoint_rows_with_updates(
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
            checkpoint_rows=checkpoint_rows_next,
        )

    details_key = write_details_json(
        s3_client=s3_client,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        details={
            "table_name": TABLE_NAME,
            "pipeline_run_id": pipeline_run_id,
            "selection_meta": selection_meta,
            "games_upserted": sorted(games_upserted),
            "games_upserted_count": len(games_upserted),
            "files_processed_count": total_files_processed,
            "rows_written_count": total_rows_written,
            "one_hot_violation_count": one_hot_violation_count,
            "duplicate_key_count": duplicate_key_count,
            "failed_games_count": len(failed_games),
            "failed_games": failed_games,
            "checkpoint_key_written": checkpoint_key_written,
        },
    )

    success_game_count = len(games_upserted)
    failed_game_count = len(failed_games)
    run_status = "success"
    if failed_game_count > 0 and success_game_count > 0:
        run_status = "success_with_warnings"
    elif failed_game_count > 0:
        run_status = "error"

    warning_reason_counts = (
        {"failed_game_projection": failed_game_count}
        if run_status == "success_with_warnings"
        else {}
    )
    error_reason_counts = (
        {"failed_game_projection": failed_game_count}
        if run_status == "error"
        else {}
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
        **selection_audit_fields(
            selection_meta,
            checkpoint_key_written=checkpoint_key_written,
        ),
        "selected_game_count": selection_meta.get("selected_game_count", len(keys)),
        "written_game_count": len(games_upserted),
        "files_selected": len(keys),
        "files_processed": total_files_processed,
        "games_upserted": len(games_upserted),
        "rows_written": total_rows_written,
        "warning_count": failed_game_count if run_status == "success_with_warnings" else 0,
        "error_count": failed_game_count if run_status == "error" else 0,
        "warning_reason_counts": json.dumps(warning_reason_counts, sort_keys=True),
        "error_reason_counts": json.dumps(error_reason_counts, sort_keys=True),
        "details_key": details_key,
        "duplicate_key_count": duplicate_key_count,
        "one_hot_violation_count": one_hot_violation_count,
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
        "Completed event projection v2 build:",
        json.dumps(
            {
                "files_processed_count": total_files_processed,
                "games_upserted_count": len(games_upserted),
                "rows_written_count": total_rows_written,
                "failed_games_count": len(failed_games),
                "details_key": details_key,
                "checkpoint_key_written": checkpoint_key_written,
            },
            default=str,
        ),
    )

    if failed_games:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
