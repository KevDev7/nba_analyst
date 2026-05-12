"""Build Athena standalone pbpstats event projection from raw CDN play-by-play JSON."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pyarrow as pa
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
from pbpstats.resources.enhanced_pbp import (
    EndOfPeriod,
    Ejection,
    FieldGoal,
    Foul,
    FreeThrow,
    JumpBall,
    Rebound,
    Replay,
    StartOfPeriod,
    Substitution,
    Timeout,
    Turnover,
    Violation,
)
from pbpstats.resources.enhanced_pbp.rebound import EventOrderError
from pbpstats_projection_common import (
    ProjectionFailure,
    add_silver_metadata,
    load_live_enhanced_pbp_items,
    normalize_boolean,
    normalize_double,
    normalize_long,
    normalize_string,
    normalize_string_list,
)
from silver_pipeline_helpers import run_date, write_audit_artifacts, write_rows_as_parquet

import build_silver_playbyplay_events as pbp_silver

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "raw/cdn/playbyplay/"
DESTINATION_PREFIX = "silver/pbpstats_event_projection_v1/"
TABLE_NAME = "pbpstats_event_projection_v1"
SOURCE_SYSTEM = "pbpstats_live_enhanced_pbp"
META_SCHEMA_VERSION = 1
FORCE_FULL_REFRESH = os.getenv("PBPSTATS_EVENT_PROJECTION_FORCE_FULL_REFRESH", "false").strip().lower() == "true"
TARGET_GAME_IDS = parse_target_game_ids(os.getenv("PBPSTATS_EVENT_PROJECTION_TARGET_GAME_IDS", ""))

IDENTITY_COLUMNS = [
    "game_id",
    "event_num",
    "event_order",
    "period",
]

BASE_SOURCE_COLUMNS = [
    "clock",
    "description",
    "action_type",
    "sub_type",
    "descriptor",
    "team_id",
    "player1_id",
    "player2_id",
    "player3_id",
    "offense_team_id",
    "home_score",
    "away_score",
    "shot_action_number",
    "qualifiers",
    "loc_x_legacy",
    "loc_y_legacy",
]

DERIVED_CONTEXT_COLUMNS = [
    "seconds_remaining",
    "seconds_since_previous_event",
    "score_margin",
    "is_possession_ending_event",
    "count_as_possession",
    "is_second_chance_event",
    "is_penalty_event",
]

LINKED_REFERENCE_COLUMNS = [
    "previous_event_num",
    "next_event_num",
    "missed_shot_event_num",
    "foul_that_led_to_ft_event_num",
]

EVENT_CLASS_FLAG_COLUMNS = [
    "is_field_goal_event",
    "is_free_throw_event",
    "is_rebound_event",
    "is_foul_event",
    "is_turnover_event",
    "is_substitution_event",
    "is_jump_ball_event",
    "is_timeout_event",
    "is_violation_event",
    "is_replay_event",
    "is_ejection_event",
    "is_period_start_event",
    "is_period_end_event",
    "is_other_event",
]

FIELD_GOAL_COLUMNS = [
    "is_made",
    "shot_value",
    "shot_type",
    "is_blocked",
    "is_assisted",
    "is_putback",
    "is_and1",
    "is_heave",
    "is_corner_3",
    "shot_distance",
]

FREE_THROW_COLUMNS = [
    "is_technical_ft",
    "is_flagrant_ft",
    "is_away_from_play_ft",
    "is_inbound_foul_ft",
    "is_transition_take_foul_ft",
    "free_throw_trip_sequence_num",
    "free_throw_trip_size",
]

REBOUND_COLUMNS = [
    "is_placeholder_rebound",
    "is_real_rebound",
    "is_oreb",
    "is_dreb",
    "is_turnover_placeholder_rebound",
    "is_non_live_ft_placeholder_rebound",
    "is_buzzer_beater_placeholder_rebound",
    "is_buzzer_beater_rebound_at_shot_time",
    "is_self_rebound",
]

FOUL_COLUMNS = [
    "counts_towards_penalty",
    "counts_as_personal_foul",
    "foul_type_string",
    "number_of_fta_for_foul",
    "is_personal_foul",
    "is_shooting_foul",
    "is_loose_ball_foul",
    "is_offensive_foul",
    "is_inbound_foul",
    "is_away_from_play_foul",
    "is_clear_path_foul",
    "is_double_foul",
    "is_technical_foul",
    "is_flagrant1_foul",
    "is_flagrant2_foul",
    "is_double_technical_foul",
    "is_defensive_3_seconds_foul",
    "is_delay_of_game_foul",
    "is_charge",
    "is_personal_block_foul",
    "is_personal_take_foul",
    "is_shooting_block_foul",
    "is_transition_take_foul",
]

TURNOVER_COLUMNS = [
    "is_no_turnover",
    "is_steal",
    "is_bad_pass_turnover",
    "is_lost_ball_turnover",
    "is_travel_turnover",
    "is_3_second_violation_turnover",
    "is_shot_clock_violation_turnover",
    "is_offensive_goaltending_turnover",
    "is_lane_violation_turnover",
    "is_kicked_ball_turnover",
    "is_step_out_of_bounds_turnover",
    "is_lost_ball_out_of_bounds_turnover",
    "is_bad_pass_out_of_bounds_turnover",
]

SUBSTITUTION_COLUMNS = [
    "incoming_player_id",
    "outgoing_player_id",
]

JUMPBALL_COLUMNS = [
    "winning_team_id",
]

VIOLATION_COLUMNS = [
    "is_delay_of_game_violation",
    "is_goaltend_violation",
    "is_lane_violation",
    "is_jumpball_violation",
    "is_kicked_ball_violation",
    "is_double_lane_violation",
]

REPLAY_COLUMNS = [
    "support_ruling",
    "overturn_ruling",
    "ruling_stands",
]

PERIOD_COLUMNS = [
    "team_starting_with_ball",
]

PROJECTION_COLUMNS = (
    IDENTITY_COLUMNS
    + BASE_SOURCE_COLUMNS
    + DERIVED_CONTEXT_COLUMNS
    + LINKED_REFERENCE_COLUMNS
    + EVENT_CLASS_FLAG_COLUMNS
    + FIELD_GOAL_COLUMNS
    + FREE_THROW_COLUMNS
    + REBOUND_COLUMNS
    + FOUL_COLUMNS
    + TURNOVER_COLUMNS
    + SUBSTITUTION_COLUMNS
    + JUMPBALL_COLUMNS
    + VIOLATION_COLUMNS
    + REPLAY_COLUMNS
    + PERIOD_COLUMNS
)

STRING_COLUMNS = {
    "game_id",
    "clock",
    "description",
    "action_type",
    "sub_type",
    "descriptor",
    "shot_type",
    "foul_type_string",
}

ARRAY_STRING_COLUMNS = {
    "qualifiers",
}

DOUBLE_COLUMNS = {
    "seconds_remaining",
    "seconds_since_previous_event",
    "shot_distance",
}

BOOLEAN_COLUMNS = set(EVENT_CLASS_FLAG_COLUMNS) | {
    "is_possession_ending_event",
    "count_as_possession",
    "is_second_chance_event",
    "is_penalty_event",
    "is_made",
    "is_blocked",
    "is_assisted",
    "is_putback",
    "is_and1",
    "is_heave",
    "is_corner_3",
    "is_technical_ft",
    "is_flagrant_ft",
    "is_away_from_play_ft",
    "is_inbound_foul_ft",
    "is_transition_take_foul_ft",
    "is_placeholder_rebound",
    "is_real_rebound",
    "is_oreb",
    "is_dreb",
    "is_turnover_placeholder_rebound",
    "is_non_live_ft_placeholder_rebound",
    "is_buzzer_beater_placeholder_rebound",
    "is_buzzer_beater_rebound_at_shot_time",
    "is_self_rebound",
    "counts_towards_penalty",
    "counts_as_personal_foul",
    "is_personal_foul",
    "is_shooting_foul",
    "is_loose_ball_foul",
    "is_offensive_foul",
    "is_inbound_foul",
    "is_away_from_play_foul",
    "is_clear_path_foul",
    "is_double_foul",
    "is_technical_foul",
    "is_flagrant1_foul",
    "is_flagrant2_foul",
    "is_double_technical_foul",
    "is_defensive_3_seconds_foul",
    "is_delay_of_game_foul",
    "is_charge",
    "is_personal_block_foul",
    "is_personal_take_foul",
    "is_shooting_block_foul",
    "is_transition_take_foul",
    "is_no_turnover",
    "is_steal",
    "is_bad_pass_turnover",
    "is_lost_ball_turnover",
    "is_travel_turnover",
    "is_3_second_violation_turnover",
    "is_shot_clock_violation_turnover",
    "is_offensive_goaltending_turnover",
    "is_lane_violation_turnover",
    "is_kicked_ball_turnover",
    "is_step_out_of_bounds_turnover",
    "is_lost_ball_out_of_bounds_turnover",
    "is_bad_pass_out_of_bounds_turnover",
    "is_delay_of_game_violation",
    "is_goaltend_violation",
    "is_lane_violation",
    "is_jumpball_violation",
    "is_kicked_ball_violation",
    "is_double_lane_violation",
    "support_ruling",
    "overturn_ruling",
    "ruling_stands",
}

LONG_COLUMNS = set(PROJECTION_COLUMNS) - STRING_COLUMNS - ARRAY_STRING_COLUMNS - DOUBLE_COLUMNS - BOOLEAN_COLUMNS

_projection_schema_fields: list[pa.Field] = []
for _column in PROJECTION_COLUMNS:
    if _column in STRING_COLUMNS:
        _projection_schema_fields.append(pa.field(_column, pa.string()))
    elif _column in ARRAY_STRING_COLUMNS:
        _projection_schema_fields.append(pa.field(_column, pa.list_(pa.string())))
    elif _column in DOUBLE_COLUMNS:
        _projection_schema_fields.append(pa.field(_column, pa.float64()))
    elif _column in BOOLEAN_COLUMNS:
        _projection_schema_fields.append(pa.field(_column, pa.bool_()))
    else:
        _projection_schema_fields.append(pa.field(_column, pa.int64()))
TARGET_SCHEMA = pa.schema(
    _projection_schema_fields
    + [
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


def extract_event_class_flags(event: Any) -> dict[str, bool]:
    flags = {column: False for column in EVENT_CLASS_FLAG_COLUMNS}
    if isinstance(event, FieldGoal):
        flags["is_field_goal_event"] = True
    elif isinstance(event, FreeThrow):
        flags["is_free_throw_event"] = True
    elif isinstance(event, Rebound):
        flags["is_rebound_event"] = True
    elif isinstance(event, Foul):
        flags["is_foul_event"] = True
    elif isinstance(event, Turnover):
        flags["is_turnover_event"] = True
    elif isinstance(event, Substitution):
        flags["is_substitution_event"] = True
    elif isinstance(event, JumpBall):
        flags["is_jump_ball_event"] = True
    elif isinstance(event, Timeout):
        flags["is_timeout_event"] = True
    elif isinstance(event, Violation):
        flags["is_violation_event"] = True
    elif isinstance(event, Replay):
        flags["is_replay_event"] = True
    elif isinstance(event, Ejection):
        flags["is_ejection_event"] = True
    elif isinstance(event, StartOfPeriod):
        flags["is_period_start_event"] = True
    elif isinstance(event, EndOfPeriod):
        flags["is_period_end_event"] = True
    else:
        flags["is_other_event"] = True
    return flags


def _linked_event_num(event: Any | None) -> int | None:
    if event is None:
        return None
    return normalize_long(getattr(event, "event_num", None))


def build_event_projection_row(
    event: Any,
    *,
    source_file: str,
    source_last_modified_utc: Any,
) -> dict[str, Any]:
    flags = extract_event_class_flags(event)
    row = empty_projection_payload()
    row.update(
        {
            "game_id": normalize_string(getattr(event, "game_id", None)),
            "event_num": normalize_long(getattr(event, "event_num", None)),
            "event_order": normalize_long(getattr(event, "order", None)),
            "period": normalize_long(getattr(event, "period", None)),
            "clock": normalize_string(getattr(event, "clock", None)),
            "description": normalize_string(getattr(event, "description", "")),
            "action_type": normalize_string(getattr(event, "action_type", None)),
            "sub_type": normalize_string(getattr(event, "sub_type", None)),
            "descriptor": normalize_string(getattr(event, "descriptor", None)),
            "team_id": normalize_long(getattr(event, "team_id", None)),
            "player1_id": normalize_long(getattr(event, "player1_id", None)),
            "player2_id": normalize_long(getattr(event, "player2_id", None)),
            "player3_id": normalize_long(getattr(event, "player3_id", None)),
            "offense_team_id": normalize_long(getattr(event, "offense_team_id", None)),
            "home_score": normalize_long(getattr(event, "home_score", None)),
            "away_score": normalize_long(getattr(event, "away_score", None)),
            "shot_action_number": normalize_long(getattr(event, "shot_action_number", None)),
            "qualifiers": normalize_string_list(getattr(event, "qualifiers", None)),
            "loc_x_legacy": normalize_long(getattr(event, "locX", None)),
            "loc_y_legacy": normalize_long(getattr(event, "locY", None)),
            "seconds_remaining": normalize_double(event.seconds_remaining),
            "seconds_since_previous_event": normalize_double(event.seconds_since_previous_event),
            "score_margin": normalize_long(event.score_margin),
            "is_possession_ending_event": normalize_boolean(event.is_possession_ending_event),
            "count_as_possession": normalize_boolean(event.count_as_possession),
            "is_second_chance_event": normalize_boolean(event.is_second_chance_event()),
            "is_penalty_event": normalize_boolean(event.is_penalty_event()),
            "previous_event_num": _linked_event_num(getattr(event, "previous_event", None)),
            "next_event_num": _linked_event_num(getattr(event, "next_event", None)),
        }
    )
    row.update(flags)

    if isinstance(event, (FieldGoal, FreeThrow)):
        row["is_made"] = normalize_boolean(event.is_made)
        row["shot_value"] = normalize_long(event.shot_value)

    if isinstance(event, FieldGoal):
        row.update(
            {
                "shot_type": normalize_string(event.shot_type),
                "is_blocked": normalize_boolean(event.is_blocked),
                "is_assisted": normalize_boolean(event.is_assisted),
                "is_putback": normalize_boolean(event.is_putback),
                "is_and1": normalize_boolean(event.is_and1),
                "is_heave": normalize_boolean(event.is_heave),
                "is_corner_3": normalize_boolean(event.is_corner_3),
                "shot_distance": normalize_double(event.distance),
            }
        )

    if isinstance(event, FreeThrow):
        foul_event = event.foul_that_led_to_ft
        row.update(
            {
                "is_technical_ft": normalize_boolean(event.is_technical_ft),
                "is_flagrant_ft": normalize_boolean(event.is_flagrant_ft),
                "is_away_from_play_ft": normalize_boolean(event.is_away_from_play_ft),
                "is_inbound_foul_ft": normalize_boolean(event.is_inbound_foul_ft),
                "is_transition_take_foul_ft": normalize_boolean(event.is_transition_take_foul_ft),
                "free_throw_trip_sequence_num": normalize_long(
                    1
                    if getattr(event, "is_ft_1_of_1", False)
                    or getattr(event, "is_ft_1_of_2", False)
                    or getattr(event, "is_ft_1_of_3", False)
                    else 2
                    if getattr(event, "is_ft_2_of_2", False)
                    or getattr(event, "is_ft_2_of_3", False)
                    else 3
                    if getattr(event, "is_ft_3_of_3", False)
                    else 1
                    if getattr(event, "is_ft_1pt", False)
                    else 2
                    if getattr(event, "is_ft_2pt", False)
                    else 3
                    if getattr(event, "is_ft_3pt", False)
                    else None
                ),
                "free_throw_trip_size": normalize_long(
                    1
                    if getattr(event, "is_ft_1_of_1", False) or getattr(event, "is_ft_1pt", False)
                    else 2
                    if getattr(event, "is_ft_1_of_2", False)
                    or getattr(event, "is_ft_2_of_2", False)
                    or getattr(event, "is_ft_2pt", False)
                    else 3
                    if getattr(event, "is_ft_1_of_3", False)
                    or getattr(event, "is_ft_2_of_3", False)
                    or getattr(event, "is_ft_3_of_3", False)
                    or getattr(event, "is_ft_3pt", False)
                    else None
                ),
                "foul_that_led_to_ft_event_num": _linked_event_num(foul_event),
            }
        )

    if isinstance(event, Rebound):
        try:
            missed_shot = event.missed_shot
        except EventOrderError as exc:
            raise ProjectionFailure(f"Linked rebound.missed_shot resolution failed: {exc}") from exc
        row.update(
            {
                "is_placeholder_rebound": normalize_boolean(event.is_placeholder),
                "is_real_rebound": normalize_boolean(event.is_real_rebound),
                "is_oreb": normalize_boolean(event.oreb),
                "is_dreb": normalize_boolean(not event.oreb),
                "missed_shot_event_num": _linked_event_num(missed_shot),
                "is_turnover_placeholder_rebound": normalize_boolean(event.is_turnover_placeholder),
                "is_non_live_ft_placeholder_rebound": normalize_boolean(event.is_non_live_ft_placeholder),
                "is_buzzer_beater_placeholder_rebound": normalize_boolean(event.is_buzzer_beater_placeholder),
                "is_buzzer_beater_rebound_at_shot_time": normalize_boolean(event.is_buzzer_beater_rebound_at_shot_time),
                "is_self_rebound": normalize_boolean(event.self_reb),
            }
        )

    if isinstance(event, Foul):
        row.update(
            {
                "counts_towards_penalty": normalize_boolean(event.counts_towards_penalty),
                "counts_as_personal_foul": normalize_boolean(event.counts_as_personal_foul),
                "foul_type_string": normalize_string(event.foul_type_string),
                "number_of_fta_for_foul": normalize_long(event.number_of_fta_for_foul),
                "is_personal_foul": normalize_boolean(event.is_personal_foul),
                "is_shooting_foul": normalize_boolean(event.is_shooting_foul),
                "is_loose_ball_foul": normalize_boolean(event.is_loose_ball_foul),
                "is_offensive_foul": normalize_boolean(event.is_offensive_foul),
                "is_inbound_foul": normalize_boolean(event.is_inbound_foul),
                "is_away_from_play_foul": normalize_boolean(event.is_away_from_play_foul),
                "is_clear_path_foul": normalize_boolean(event.is_clear_path_foul),
                "is_double_foul": normalize_boolean(event.is_double_foul),
                "is_technical_foul": normalize_boolean(event.is_technical),
                "is_flagrant1_foul": normalize_boolean(event.is_flagrant1),
                "is_flagrant2_foul": normalize_boolean(event.is_flagrant2),
                "is_double_technical_foul": normalize_boolean(event.is_double_technical),
                "is_defensive_3_seconds_foul": normalize_boolean(event.is_defensive_3_seconds),
                "is_delay_of_game_foul": normalize_boolean(event.is_delay_of_game),
                "is_charge": normalize_boolean(event.is_charge),
                "is_personal_block_foul": normalize_boolean(event.is_personal_block_foul),
                "is_personal_take_foul": normalize_boolean(event.is_personal_take_foul),
                "is_shooting_block_foul": normalize_boolean(event.is_shooting_block_foul),
                "is_transition_take_foul": normalize_boolean(event.is_transition_take_foul),
            }
        )

    if isinstance(event, Turnover):
        row.update(
            {
                "is_no_turnover": normalize_boolean(event.is_no_turnover),
                "is_steal": normalize_boolean(event.is_steal),
                "is_bad_pass_turnover": normalize_boolean(event.is_bad_pass),
                "is_lost_ball_turnover": normalize_boolean(event.is_lost_ball),
                "is_travel_turnover": normalize_boolean(event.is_travel),
                "is_3_second_violation_turnover": normalize_boolean(event.is_3_second_violation),
                "is_shot_clock_violation_turnover": normalize_boolean(event.is_shot_clock_violation),
                "is_offensive_goaltending_turnover": normalize_boolean(event.is_offensive_goaltending),
                "is_lane_violation_turnover": normalize_boolean(event.is_lane_violation),
                "is_kicked_ball_turnover": normalize_boolean(event.is_kicked_ball),
                "is_step_out_of_bounds_turnover": normalize_boolean(event.is_step_out_of_bounds),
                "is_lost_ball_out_of_bounds_turnover": normalize_boolean(event.is_lost_ball_out_of_bounds),
                "is_bad_pass_out_of_bounds_turnover": normalize_boolean(event.is_bad_pass_out_of_bounds),
            }
        )

    if isinstance(event, Substitution):
        row.update(
            {
                "incoming_player_id": normalize_long(event.incoming_player_id),
                "outgoing_player_id": normalize_long(event.outgoing_player_id),
            }
        )

    if isinstance(event, JumpBall):
        row["winning_team_id"] = normalize_long(event.winning_team)

    if isinstance(event, Violation):
        row.update(
            {
                "is_delay_of_game_violation": normalize_boolean(event.is_delay_of_game),
                "is_goaltend_violation": normalize_boolean(event.is_goaltend_violation),
                "is_lane_violation": normalize_boolean(event.is_lane_violation),
                "is_jumpball_violation": normalize_boolean(event.is_jumpball_violation),
                "is_kicked_ball_violation": normalize_boolean(event.is_kicked_ball_violation),
                "is_double_lane_violation": normalize_boolean(event.is_double_lane_violation),
            }
        )

    if isinstance(event, Replay):
        row.update(
            {
                "support_ruling": None,
                "overturn_ruling": None,
                "ruling_stands": None,
            }
        )

    if isinstance(event, StartOfPeriod):
        row["team_starting_with_ball"] = normalize_long(getattr(event, "team_starting_with_ball", None))

    return row


def project_payload_to_rows(
    payload: dict[str, Any],
    *,
    source_file: str,
    source_last_modified_utc: Any,
    fallback_game_id: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    game_id, items = load_live_enhanced_pbp_items(payload, fallback_game_id=fallback_game_id)
    rows = [
        build_event_projection_row(
            event,
            source_file=source_file,
            source_last_modified_utc=source_last_modified_utc,
        )
        for event in items
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
            f"[{index}/{len(keys)}] Processing pbpstats projection game_id={fallback_game_id or 'unknown'} key={key}"
        )
        try:
            payload = pbp_silver.read_json_payload(s3_client, key)
            game_id, rows = project_payload_to_rows(
                payload,
                source_file=key,
                source_last_modified_utc=source_last_modified,
                fallback_game_id=fallback_game_id,
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
        f"Done: {TABLE_NAME} (selected={len(keys)}, successful={success_game_count}, "
        f"failed={failed_game_count}, rows={total_rows_written})"
    )


if __name__ == "__main__":
    main()
