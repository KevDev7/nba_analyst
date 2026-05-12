"""Build Athena silver on-court lineup stints from projection events and boxscore starters.

Inputs:
  s3://nba-analytics-lakehouse-dev/silver/event_projection_v2/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_player_game.parquet

Output (upsert by game_id):
  s3://nba-analytics-lakehouse-dev/silver/on_court_state/game_id=<GAME_ID>.parquet
"""

from __future__ import annotations

import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

from heavy_silver_runtime import (
    add_source_artifact,
    build_source_index_from_objects,
    checkpoint_rows_with_updates,
    datetime_to_iso,
    normalize_utc_datetime,
    parse_target_game_ids,
    read_checkpoint_index,
    select_game_ids_for_processing,
    selection_audit_fields,
    write_checkpoint_index,
)
from pbpstats_projection_common import add_silver_metadata
from silver_pipeline_helpers import run_date, write_audit_artifacts

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"
PROJECTION_PREFIX = "silver/event_projection_v2/"
BOXSCORE_PLAYER_KEY = "silver/boxscore_player_game.parquet"
DESTINATION_PREFIX = "silver/on_court_state/"
TABLE_NAME = "on_court_state"
STATE_KEY = "silver/_state/on_court_state_state.json"
SOURCE_SYSTEM = "silver_event_projection_v2_and_boxscore"
META_SCHEMA_VERSION = 1

PROCESS_ALL_FILES = os.getenv("ON_COURT_STATE_PROCESS_ALL_FILES", "true").strip().lower() != "false"
INCREMENTAL_MODE = os.getenv("ON_COURT_STATE_INCREMENTAL_MODE", "true").strip().lower() != "false"
FORCE_FULL_REFRESH = os.getenv("ON_COURT_STATE_FORCE_FULL_REFRESH", "false").strip().lower() == "true"
TARGET_GAME_IDS = parse_target_game_ids(os.getenv("ON_COURT_STATE_TARGET_GAME_IDS", ""))

OPENING_CLOCKS = {"PT12M00.00S", "PT05M00.00S"}

PROJECTION_REQUIRED_COLUMNS = [
    "game_id",
    "event_num",
    "event_order",
    "period",
    "clock",
    "description",
    "action_type",
    "sub_type",
    "team_id",
    "player1_id",
    "is_substitution_event",
]

BOXSCORE_REQUIRED_COLUMNS = [
    "gameId",
    "teamId",
    "team_side",
    "personId",
    "starter",
]

TARGET_COLUMNS = [
    "gameId",
    "period",
    "stint_id",
    "start_orderNumber",
    "end_orderNumber",
    "start_actionNumber",
    "end_actionNumber",
    "start_clock",
    "end_clock",
    "start_timeActual_utc",
    "end_timeActual_utc",
    "home_teamId",
    "away_teamId",
    "home_personIds",
    "away_personIds",
    "lineup_valid_flag",
    "lineup_issue",
]

META_COLUMNS = [
    "_meta_pipeline_run_id",
    "_meta_ingested_at_utc",
    "_meta_source_system",
    "_meta_source_key",
    "_meta_source_last_modified_utc",
    "_meta_schema_version",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("gameId", pa.string()),
        pa.field("period", pa.int64()),
        pa.field("stint_id", pa.int64()),
        pa.field("start_orderNumber", pa.int64()),
        pa.field("end_orderNumber", pa.int64()),
        pa.field("start_actionNumber", pa.int64()),
        pa.field("end_actionNumber", pa.int64()),
        pa.field("start_clock", pa.string()),
        pa.field("end_clock", pa.string()),
        pa.field("start_timeActual_utc", pa.timestamp("us", tz="UTC")),
        pa.field("end_timeActual_utc", pa.timestamp("us", tz="UTC")),
        pa.field("home_teamId", pa.int64()),
        pa.field("away_teamId", pa.int64()),
        pa.field("home_personIds", pa.list_(pa.int64())),
        pa.field("away_personIds", pa.list_(pa.int64())),
        pa.field("lineup_valid_flag", pa.int64()),
        pa.field("lineup_issue", pa.string()),
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
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_player_ids(value: Any) -> list[int] | None:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    elif isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return None
    normalized = [to_int_or_none(item) for item in value]
    if any(item is None for item in normalized):
        return None
    return [int(item) for item in normalized if item is not None]


def normalized_unique_sorted_players(value: Any) -> list[int] | None:
    players = normalize_player_ids(value)
    if players is None:
        return None
    unique_players = sorted(set(players))
    if len(unique_players) != len(players):
        return None
    return unique_players


def normalize_game_id(value: Any) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    return str(value)


def build_boxscore_starter_index(boxscore_df: pd.DataFrame) -> dict[str, dict[int, list[int]]]:
    return {
        game_id: game_meta["starters_by_team"]
        for game_id, game_meta in build_boxscore_game_index(boxscore_df).items()
        if game_meta["starters_by_team"]
    }


def build_boxscore_game_index(boxscore_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    starters_by_game: dict[str, dict[int, list[int]]] = {}
    game_index: dict[str, dict[str, Any]] = {}
    grouped: dict[tuple[str, int], list[int]] = {}

    for row in boxscore_df.to_dict("records"):
        game_id = normalize_game_id(row.get("gameId"))
        team_id = to_int_or_none(row.get("teamId"))
        team_side = null_if_empty(row.get("team_side"))
        if game_id is None or team_id is None:
            continue
        game_meta = game_index.setdefault(
            game_id,
            {
                "home_team_id": None,
                "away_team_id": None,
                "starters_by_team": {},
            },
        )
        if team_side == "home":
            current_home = game_meta["home_team_id"]
            if current_home is None:
                game_meta["home_team_id"] = team_id
            elif current_home != team_id:
                game_meta["home_team_id"] = None
        elif team_side == "away":
            current_away = game_meta["away_team_id"]
            if current_away is None:
                game_meta["away_team_id"] = team_id
            elif current_away != team_id:
                game_meta["away_team_id"] = None

        if to_int_or_none(row.get("starter")) != 1:
            continue
        person_id = to_int_or_none(row.get("personId"))
        if person_id is None:
            continue
        grouped.setdefault((game_id, team_id), []).append(person_id)

    for (game_id, team_id), player_ids in grouped.items():
        normalized = normalized_unique_sorted_players(player_ids)
        if normalized is None or len(normalized) != 5 or len(player_ids) != 5:
            continue
        starters_by_game.setdefault(game_id, {})[team_id] = normalized

    for game_id, game_meta in game_index.items():
        game_meta["starters_by_team"] = starters_by_game.get(game_id, {})

    return game_index


def marker_from_event(event: dict[str, Any]) -> tuple[int | None, int | None, str | None]:
    return (
        to_int_or_none(event.get("event_order")),
        to_int_or_none(event.get("event_num")),
        null_if_empty(event.get("clock")),
    )


def end_marker_for_period(period_events: list[dict[str, Any]]) -> tuple[int | None, int | None, str | None]:
    last_event = period_events[-1]
    max_order = max(
        [
            to_int_or_none(event.get("event_order"))
            for event in period_events
            if to_int_or_none(event.get("event_order")) is not None
        ],
        default=None,
    )
    return (
        (max_order + 1) if max_order is not None else None,
        to_int_or_none(last_event.get("event_num")),
        null_if_empty(last_event.get("clock")),
    )


def build_stint_row(
    *,
    game_id: str,
    period: int,
    stint_id: int,
    start_marker: tuple[int | None, int | None, str | None],
    end_marker: tuple[int | None, int | None, str | None],
    home_team_id: int | None,
    away_team_id: int | None,
    home_person_ids: list[int] | None,
    away_person_ids: list[int] | None,
    lineup_issue: str | None,
) -> dict[str, Any]:
    home_valid = home_person_ids is not None and len(home_person_ids) == 5
    away_valid = away_person_ids is not None and len(away_person_ids) == 5
    return {
        "gameId": game_id,
        "period": period,
        "stint_id": stint_id,
        "start_orderNumber": start_marker[0],
        "end_orderNumber": end_marker[0],
        "start_actionNumber": start_marker[1],
        "end_actionNumber": end_marker[1],
        "start_clock": start_marker[2],
        "end_clock": end_marker[2],
        "start_timeActual_utc": None,
        "end_timeActual_utc": None,
        "home_teamId": home_team_id,
        "away_teamId": away_team_id,
        "home_personIds": home_person_ids,
        "away_personIds": away_person_ids,
        "lineup_valid_flag": int(home_valid and away_valid and lineup_issue is None),
        "lineup_issue": lineup_issue,
    }


def resolve_single_unique_int(values: pd.Series) -> int | None:
    unique_values = {
        to_int_or_none(value)
        for value in values.tolist()
        if to_int_or_none(value) is not None
    }
    if len(unique_values) == 1:
        return next(iter(unique_values))
    return None


def find_substitution_cluster_end(period_events: list[dict[str, Any]], start_index: int) -> int:
    cluster_clock = null_if_empty(period_events[start_index].get("clock"))
    index = start_index
    while index + 1 < len(period_events):
        candidate = period_events[index + 1]
        if null_if_empty(candidate.get("clock")) != cluster_clock:
            break
        index += 1
    return index


def is_opening_substitution_cluster(period: int, period_events: list[dict[str, Any]], cluster_start: int) -> bool:
    if period <= 1 or cluster_start != 0:
        return False
    if not bool(period_events[cluster_start].get("is_substitution_event")):
        return False
    return null_if_empty(period_events[cluster_start].get("clock")) in OPENING_CLOCKS


def apply_substitution_event_to_lineup(
    current_players: list[int],
    *,
    sub_type: Any,
    player_id: Any,
) -> tuple[list[int] | None, str | None]:
    direction = str(null_if_empty(sub_type) or "").lower()
    person_id = to_int_or_none(player_id)
    if person_id is None:
        return None, "substitution_produces_duplicate_or_non_five_lineup"

    next_players = list(current_players)
    if direction == "out":
        if person_id not in next_players:
            return None, "substitution_removes_player_not_on_court"
        next_players = [value for value in next_players if value != person_id]
    elif direction == "in":
        if person_id in next_players:
            return None, "substitution_produces_duplicate_or_non_five_lineup"
        next_players.append(person_id)
        next_players = sorted(next_players)
    else:
        return None, "substitution_produces_duplicate_or_non_five_lineup"

    if len(set(next_players)) != len(next_players):
        return None, "substitution_produces_duplicate_or_non_five_lineup"
    return next_players, None


def apply_substitution_cluster(
    *,
    current_home: list[int],
    current_away: list[int],
    period_events: list[dict[str, Any]],
    cluster_start: int,
    cluster_end: int,
    home_team_id: int | None,
    away_team_id: int | None,
) -> tuple[list[int], list[int], str | None]:
    next_home = list(current_home)
    next_away = list(current_away)

    for index in range(cluster_start, cluster_end + 1):
        event = period_events[index]
        if not bool(event.get("is_substitution_event")):
            continue
        event_team_id = to_int_or_none(event.get("team_id"))
        if event_team_id == home_team_id:
            updated_home, home_issue = apply_substitution_event_to_lineup(
                next_home,
                sub_type=event.get("sub_type"),
                player_id=event.get("player1_id"),
            )
            if home_issue is not None or updated_home is None:
                return next_home, next_away, home_issue or "substitution_produces_duplicate_or_non_five_lineup"
            next_home = updated_home
            continue
        if event_team_id == away_team_id:
            updated_away, away_issue = apply_substitution_event_to_lineup(
                next_away,
                sub_type=event.get("sub_type"),
                player_id=event.get("player1_id"),
            )
            if away_issue is not None or updated_away is None:
                return next_home, next_away, away_issue or "substitution_produces_duplicate_or_non_five_lineup"
            next_away = updated_away
            continue
        return next_home, next_away, "substitution_produces_duplicate_or_non_five_lineup"

    if len(next_home) != 5 or len(next_away) != 5:
        return next_home, next_away, "substitution_produces_duplicate_or_non_five_lineup"

    return next_home, next_away, None


def build_stints_for_game(
    game_id: str,
    events_df: pd.DataFrame,
    *,
    home_team_id: int | None = None,
    away_team_id: int | None = None,
    boxscore_starters_by_team: dict[int, list[int]] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    game_invalid = False

    if home_team_id is None and "home_team_id" in events_df.columns:
        home_team_id = resolve_single_unique_int(events_df["home_team_id"])
    if away_team_id is None and "away_team_id" in events_df.columns:
        away_team_id = resolve_single_unique_int(events_df["away_team_id"])
    if home_team_id is None or away_team_id is None or home_team_id == away_team_id:
        raise ValueError("Missing or ambiguous home/away team ids in boxscore starter input")

    working = events_df.copy()
    working["period_num"] = working["period"].map(to_int_or_none)
    working["event_order_num"] = working["event_order"].map(to_int_or_none)
    working["event_num_num"] = working["event_num"].map(to_int_or_none)
    working["_row_idx"] = range(len(working))
    working = working.sort_values(
        by=["period_num", "event_order_num", "event_num_num", "_row_idx"],
        ascending=[True, True, True, True],
        na_position="last",
    )

    periods = [int(value) for value in working["period_num"].dropna().unique().tolist()]
    if not periods:
        return rows, game_invalid

    stint_id = 1
    prior_period_stable: tuple[list[int], list[int]] | None = None
    for period in periods:
        period_df = working[working["period_num"] == period].copy()
        period_events = period_df.to_dict("records")
        if not period_events:
            continue

        period_end_marker = end_marker_for_period(period_events)
        current_home: list[int] | None = None
        current_away: list[int] | None = None
        current_start_marker: tuple[int | None, int | None, str | None] | None = None
        index = 0

        if period == 1:
            if (
                boxscore_starters_by_team is not None
                and home_team_id in boxscore_starters_by_team
                and away_team_id in boxscore_starters_by_team
                and len(boxscore_starters_by_team[home_team_id]) == 5
                and len(boxscore_starters_by_team[away_team_id]) == 5
            ):
                current_home = list(boxscore_starters_by_team[home_team_id])
                current_away = list(boxscore_starters_by_team[away_team_id])
                current_start_marker = marker_from_event(period_events[0])
            else:
                game_invalid = True
                rows.append(
                    build_stint_row(
                        game_id=game_id,
                        period=period,
                        stint_id=stint_id,
                        start_marker=marker_from_event(period_events[0]),
                        end_marker=period_end_marker,
                        home_team_id=home_team_id,
                        away_team_id=away_team_id,
                        home_person_ids=None,
                        away_person_ids=None,
                        lineup_issue="missing_boxscore_starters_period_1",
                    )
                )
                stint_id += 1
                prior_period_stable = None
                continue
        else:
            if prior_period_stable is None:
                game_invalid = True
                rows.append(
                    build_stint_row(
                        game_id=game_id,
                        period=period,
                        stint_id=stint_id,
                        start_marker=marker_from_event(period_events[0]),
                        end_marker=period_end_marker,
                        home_team_id=home_team_id,
                        away_team_id=away_team_id,
                        home_person_ids=None,
                        away_person_ids=None,
                        lineup_issue="carry_forward_unavailable_period_start",
                    )
                )
                stint_id += 1
                continue

            current_home, current_away = list(prior_period_stable[0]), list(prior_period_stable[1])
            current_start_marker = marker_from_event(period_events[0])
            if is_opening_substitution_cluster(period, period_events, 0):
                cluster_end = find_substitution_cluster_end(period_events, 0)
                updated_home, updated_away, cluster_issue = apply_substitution_cluster(
                    current_home=current_home,
                    current_away=current_away,
                    period_events=period_events,
                    cluster_start=0,
                    cluster_end=cluster_end,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                )
                if cluster_issue is not None:
                    game_invalid = True
                    rows.append(
                        build_stint_row(
                            game_id=game_id,
                            period=period,
                            stint_id=stint_id,
                            start_marker=current_start_marker,
                            end_marker=period_end_marker,
                            home_team_id=home_team_id,
                            away_team_id=away_team_id,
                            home_person_ids=None,
                            away_person_ids=None,
                            lineup_issue="invalid_opening_substitution_cluster",
                        )
                    )
                    stint_id += 1
                    prior_period_stable = None
                    continue
                current_home, current_away = updated_home, updated_away
                index = cluster_end + 1

        assert current_home is not None and current_away is not None and current_start_marker is not None

        while index < len(period_events):
            event = period_events[index]
            if not bool(event.get("is_substitution_event")):
                index += 1
                continue

            cluster_start = index
            cluster_end = find_substitution_cluster_end(period_events, cluster_start)
            boundary_marker = marker_from_event(period_events[cluster_start])

            if current_start_marker != boundary_marker:
                rows.append(
                    build_stint_row(
                        game_id=game_id,
                        period=period,
                        stint_id=stint_id,
                        start_marker=current_start_marker,
                        end_marker=boundary_marker,
                        home_team_id=home_team_id,
                        away_team_id=away_team_id,
                        home_person_ids=current_home,
                        away_person_ids=current_away,
                        lineup_issue=None,
                    )
                )
                stint_id += 1

            updated_home, updated_away, cluster_issue = apply_substitution_cluster(
                current_home=current_home,
                current_away=current_away,
                period_events=period_events,
                cluster_start=cluster_start,
                cluster_end=cluster_end,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
            )
            current_start_marker = boundary_marker
            if cluster_issue is not None:
                game_invalid = True
                rows.append(
                    build_stint_row(
                        game_id=game_id,
                        period=period,
                        stint_id=stint_id,
                        start_marker=current_start_marker,
                        end_marker=period_end_marker,
                        home_team_id=home_team_id,
                        away_team_id=away_team_id,
                        home_person_ids=None,
                        away_person_ids=None,
                        lineup_issue=cluster_issue,
                    )
                )
                stint_id += 1
                current_home = []
                current_away = []
                break

            current_home, current_away = updated_home, updated_away
            index = cluster_end + 1
        else:
            rows.append(
                build_stint_row(
                    game_id=game_id,
                    period=period,
                    stint_id=stint_id,
                    start_marker=current_start_marker,
                    end_marker=period_end_marker,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    home_person_ids=current_home,
                    away_person_ids=current_away,
                    lineup_issue=None,
                )
            )
            prior_period_stable = (current_home, current_away)
            stint_id += 1
            continue

        prior_period_stable = None

    return rows, game_invalid


def ensure_columns(df: pd.DataFrame, required_columns: list[str]) -> pd.DataFrame:
    for column in required_columns:
        if column not in df.columns:
            df[column] = None
    return df


def read_parquet_df_from_s3(s3_client, key: str, columns: list[str] | None = None) -> pd.DataFrame:
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload = response["Body"].read()
    table = pq.read_table(pa.BufferReader(payload), columns=columns)
    return table.to_pandas()


def list_parquet_game_objects(s3_client, prefix: str) -> list[dict[str, Any]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = str(obj.get("Key") or "")
            if key.endswith(".parquet") and extract_game_id_from_parquet_key(key) is not None:
                objects.append(obj)
    return objects


def extract_game_id_from_parquet_key(key: str) -> str | None:
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id=") or not filename.endswith(".parquet"):
        return None
    return filename[len("game_id=") : -len(".parquet")] or None


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
    return f"{DESTINATION_PREFIX}game_id={str(game_id).zfill(10)}.parquet"


def write_state(s3_client, state: dict[str, Any]) -> None:
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=STATE_KEY,
        Body=json.dumps(state, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
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
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"{TABLE_NAME}_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    checkpoint_exists, checkpoint_rows = read_checkpoint_index(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
    )

    try:
        boxscore_player_head = s3_client.head_object(Bucket=S3_BUCKET, Key=BOXSCORE_PLAYER_KEY)
        boxscore_player_last_modified = normalize_utc_datetime(boxscore_player_head.get("LastModified"))
    except ClientError:
        boxscore_player_last_modified = None

    try:
        boxscore_df = read_parquet_df_from_s3(
            s3_client,
            BOXSCORE_PLAYER_KEY,
            BOXSCORE_REQUIRED_COLUMNS,
        )
        boxscore_df = ensure_columns(boxscore_df, BOXSCORE_REQUIRED_COLUMNS)
        boxscore_game_index = build_boxscore_game_index(boxscore_df)
    except (BotoCoreError, ClientError, OSError, pa.ArrowInvalid, pa.ArrowException) as exc:
        print(f"Warning: unable to load boxscore starter seed table ({type(exc).__name__}: {exc})")
        boxscore_game_index = {}

    projection_objects = list_parquet_game_objects(s3_client, PROJECTION_PREFIX)
    projection_index = build_source_index_from_objects(
        projection_objects,
        game_id_from_key=extract_game_id_from_parquet_key,
    )

    available_game_ids = sorted(set(projection_index) & set(boxscore_game_index))
    source_index: dict[str, list[dict[str, Any]]] = {
        game_id: [*projection_index[game_id]]
        for game_id in available_game_ids
    }

    for game_id in list(source_index):
        add_source_artifact(
            source_index,
            game_id=game_id,
            key=BOXSCORE_PLAYER_KEY,
            last_modified=boxscore_player_last_modified,
        )

    if not PROCESS_ALL_FILES and not TARGET_GAME_IDS:
        raise ValueError(
            "ON_COURT_STATE_PROCESS_ALL_FILES=false requires ON_COURT_STATE_TARGET_GAME_IDS."
        )

    selected_game_ids, selection_meta = (
        select_game_ids_for_processing(
            source_index=source_index,
            target_game_ids=TARGET_GAME_IDS if not PROCESS_ALL_FILES else TARGET_GAME_IDS,
            force_full_refresh=(FORCE_FULL_REFRESH or not INCREMENTAL_MODE or not PROCESS_ALL_FILES),
            checkpoint_exists=checkpoint_exists,
            checkpoint_rows=checkpoint_rows,
            legacy_state={},
            legacy_fallback_selector=None,
        )
        if source_index
        else (set(), {"selection_mode": "empty_source", "checkpoint_enabled": True, "legacy_state_fallback_used": False})
    )
    selected_game_ids = {game_id for game_id in selected_game_ids if game_id in source_index}

    projection_key_by_game = {
        game_id: next(
            artifact["key"]
            for artifact in source_index[game_id]
            if str(artifact.get("key", "")).startswith(PROJECTION_PREFIX)
        )
        for game_id in selected_game_ids
    }
    selection_meta["target_game_ids"] = sorted(TARGET_GAME_IDS)
    selection_meta["selected_game_count"] = len(selected_game_ids)
    selection_meta["files_discovered"] = len(projection_objects)
    selection_meta["files_selected"] = len(selected_game_ids) * 2

    games_upserted: set[str] = set()
    total_stints_written = 0
    invalid_lineup_games = 0
    processed_games = 0
    skipped_games: list[dict[str, Any]] = []
    empty_input_games = 0
    empty_stint_games = 0
    max_source_last_modified_seen: datetime | None = None
    checkpoint_key_written: str | None = None

    print(f"Mode: {selection_meta.get('selection_mode')}")
    print(f"Games discovered: {len(available_game_ids)}")
    print(f"Games selected: {len(selected_game_ids)}")

    for index, game_id in enumerate(sorted(selected_game_ids), start=1):
        projection_key = projection_key_by_game[game_id]
        source_last_modified = max(
            [
                normalize_utc_datetime(artifact.get("last_modified_utc"))
                for artifact in source_index.get(game_id, [])
                if normalize_utc_datetime(artifact.get("last_modified_utc")) is not None
            ],
            default=None,
        )
        if source_last_modified is not None and (
            max_source_last_modified_seen is None or source_last_modified > max_source_last_modified_seen
        ):
            max_source_last_modified_seen = source_last_modified

        print(f"[{index}/{len(selected_game_ids)}] Processing game_id={game_id}")
        try:
            projection_df = ensure_columns(
                read_parquet_df_from_s3(s3_client, projection_key, PROJECTION_REQUIRED_COLUMNS),
                PROJECTION_REQUIRED_COLUMNS,
            )
        except (BotoCoreError, ClientError, OSError, pa.ArrowInvalid, pa.ArrowException) as exc:
            skipped_games.append(
                {
                    "game_id": game_id,
                    "projection_key": projection_key,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"Skipping unreadable inputs for game_id={game_id} ({type(exc).__name__}: {exc})")
            continue

        processed_games += 1
        events_df = projection_df[PROJECTION_REQUIRED_COLUMNS].copy()
        events_df["game_id"] = events_df["game_id"].map(null_if_empty)
        events_df = events_df[events_df["game_id"].astype(str) == game_id].copy()

        if events_df.empty:
            empty_input_games += 1
            print(f"[{index}/{len(selected_game_ids)}] Completed with skip (empty projected events) game_id={game_id}")
            continue

        try:
            game_rows, game_invalid = build_stints_for_game(
                game_id=game_id,
                events_df=events_df,
                home_team_id=boxscore_game_index[game_id].get("home_team_id"),
                away_team_id=boxscore_game_index[game_id].get("away_team_id"),
                boxscore_starters_by_team=boxscore_game_index[game_id].get("starters_by_team"),
            )
        except Exception as exc:  # noqa: BLE001
            skipped_games.append(
                {
                    "game_id": game_id,
                    "projection_key": projection_key,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"Skipping invalid projected events for game_id={game_id} ({type(exc).__name__}: {exc})")
            continue

        if game_invalid:
            invalid_lineup_games += 1

        if not game_rows:
            empty_stint_games += 1
            print(f"[{index}/{len(selected_game_ids)}] Completed with skip (no stints) game_id={game_id}")
            continue

        source_key = json.dumps(
                {
                    "projection_key": projection_key,
                    "boxscore_player_key": BOXSCORE_PLAYER_KEY,
                },
                sort_keys=True,
        )
        write_game_parquet_to_s3(
            game_id,
            game_rows,
            pipeline_run_id=pipeline_run_id,
            ingested_at_utc=ingested_at_utc,
            source_key=source_key,
            source_last_modified_utc=source_last_modified,
            s3_client=s3_client,
        )
        games_upserted.add(game_id)
        total_stints_written += len(game_rows)
        print(f"[{index}/{len(selected_game_ids)}] Completed game_id={game_id} stints_written={len(game_rows)}")

    warning_reason_counts: dict[str, int] = {}
    if invalid_lineup_games > 0:
        warning_reason_counts["invalid_lineup_games"] = invalid_lineup_games
    if skipped_games:
        warning_reason_counts["skipped_games"] = len(skipped_games)
    if empty_input_games > 0:
        warning_reason_counts["empty_joined_event_games"] = empty_input_games
    if empty_stint_games > 0:
        warning_reason_counts["empty_stint_games"] = empty_stint_games
    warning_count = sum(warning_reason_counts.values())

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
            "legacy_state_fallback_used": False,
            "warning_reason_counts": warning_reason_counts,
            "skipped_games": skipped_games[:1000],
        },
    )

    run_status = "success_with_warnings" if warning_count > 0 else "success"
    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": run_status,
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "projection_prefix": PROJECTION_PREFIX,
        "boxscore_player_key": BOXSCORE_PLAYER_KEY,
        "destination_prefix": DESTINATION_PREFIX,
        "process_all_files": int(PROCESS_ALL_FILES),
        "incremental_mode": int(INCREMENTAL_MODE),
        "force_full_refresh": int(FORCE_FULL_REFRESH),
        **selection_audit_fields(
            selection_meta,
            checkpoint_key_written=checkpoint_key_written,
        ),
        "selected_game_count": selection_meta.get("selected_game_count", 0),
        "written_game_count": len(games_upserted),
        "files_scanned": len(selected_game_ids) * 2,
        "files_processed": processed_games * 2,
        "games_upserted": len(games_upserted),
        "stints_written": total_stints_written,
        "invalid_lineup_games": invalid_lineup_games,
        "files_with_empty_playbyplay": empty_input_games,
        "files_with_no_stints": empty_stint_games,
        "skipped_file_count": len(skipped_games),
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

    if PROCESS_ALL_FILES:
        state_after = {
            "table_name": TABLE_NAME,
            "updated_at_utc": datetime_to_iso(ingested_at_utc),
            "pipeline_run_id": pipeline_run_id,
            "max_source_last_modified_utc": datetime_to_iso(max_source_last_modified_seen),
            "files_selected": len(selected_game_ids) * 2,
            "games_upserted": len(games_upserted),
        }
        write_state(s3_client, state_after)
        print(f"Wrote state: s3://{S3_BUCKET}/{STATE_KEY}")


if __name__ == "__main__":
    main()
