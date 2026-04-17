"""
Transform raw CDN boxscore JSON files into a silver player-game parquet table.

Reads all objects under:
  s3://nba-analytics-lakehouse-dev/raw/cdn/boxscore/

Writes (single object, rewritten on each run):
  s3://nba-analytics-lakehouse-dev/silver/boxscore_player_game.parquet

Deduplication / upsert semantics:
  - Final grain is one row per (gameId, personId).
  - Source dedup is first done at gameId level.
  - If duplicate gameId appears across source files, keep the latest version:
    1) Higher meta_time from JSON wins.
    2) If meta_time ties (or both missing), higher S3 LastModified wins.
"""

from __future__ import annotations

import io
import json
import re
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
DESTINATION_KEY = "silver/boxscore_player_game.parquet"
TABLE_NAME = "boxscore_player_game"
META_SOURCE_SYSTEM = "nba_cdn_boxscore"
META_SCHEMA_VERSION = 1
MINUTES_DURATION_PATTERN = re.compile(r"^PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")

TARGET_SCHEMA = pa.schema(
    [
        pa.field("gameId", pa.string()),
        pa.field("teamId", pa.int64()),
        pa.field("team_side", pa.string()),
        pa.field("personId", pa.int64()),
        pa.field("name", pa.string()),
        pa.field("nameI", pa.string()),
        pa.field("firstName", pa.string()),
        pa.field("familyName", pa.string()),
        pa.field("jerseyNum", pa.string()),
        pa.field("position", pa.string()),
        pa.field("status", pa.string()),
        pa.field("order", pa.int64()),
        pa.field("starter", pa.int64()),
        pa.field("oncourt", pa.int64()),
        pa.field("played", pa.int64()),
        pa.field("minutes", pa.string()),
        pa.field("minutesCalculated", pa.string()),
        pa.field("plus", pa.int64()),
        pa.field("minus", pa.int64()),
        pa.field("plusMinusPoints", pa.int64()),
        pa.field("assists", pa.int64()),
        pa.field("blocks", pa.int64()),
        pa.field("blocksReceived", pa.int64()),
        pa.field("fieldGoalsAttempted", pa.int64()),
        pa.field("fieldGoalsMade", pa.int64()),
        pa.field("foulsOffensive", pa.int64()),
        pa.field("foulsDrawn", pa.int64()),
        pa.field("foulsPersonal", pa.int64()),
        pa.field("foulsTechnical", pa.int64()),
        pa.field("freeThrowsAttempted", pa.int64()),
        pa.field("freeThrowsMade", pa.int64()),
        pa.field("reboundsDefensive", pa.int64()),
        pa.field("reboundsOffensive", pa.int64()),
        pa.field("reboundsTotal", pa.int64()),
        pa.field("steals", pa.int64()),
        pa.field("turnovers", pa.int64()),
        pa.field("points", pa.int64()),
        pa.field("threePointersAttempted", pa.int64()),
        pa.field("threePointersMade", pa.int64()),
        pa.field("twoPointersAttempted", pa.int64()),
        pa.field("twoPointersMade", pa.int64()),
        pa.field("pointsFastBreak", pa.int64()),
        pa.field("pointsInThePaint", pa.int64()),
        pa.field("pointsSecondChance", pa.int64()),
        pa.field("fieldGoalsPercentage", pa.float64()),
        pa.field("freeThrowsPercentage", pa.float64()),
        pa.field("threePointersPercentage", pa.float64()),
        pa.field("twoPointersPercentage", pa.float64()),
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


def to_float_or_none(value: Any) -> float | None:
    """Convert numeric-like input into float; return None for empty-like values."""
    value = null_if_empty(value)
    if value is None:
        return None
    return float(value)


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


def to_player_rows(
    game_id: str,
    team_side: str,
    team_obj: dict[str, Any],
    source_key: str | None,
    source_last_modified_utc: datetime | None,
) -> list[dict[str, Any]]:
    """Build player-game rows for one team side in a game."""
    team_id = to_int_or_none(team_obj.get("teamId"))
    players = team_obj.get("players") or []

    rows: list[dict[str, Any]] = []
    for player in players:
        stats = player.get("statistics") or {}
        rows.append(
            {
                "gameId": game_id,
                "teamId": team_id,
                "team_side": team_side,
                "personId": to_int_or_none(player.get("personId")),
                "name": null_if_empty(player.get("name")),
                "nameI": null_if_empty(player.get("nameI")),
                "firstName": null_if_empty(player.get("firstName")),
                "familyName": null_if_empty(player.get("familyName")),
                "jerseyNum": null_if_empty(player.get("jerseyNum")),
                "position": null_if_empty(player.get("position")),
                "status": null_if_empty(player.get("status")),
                "order": to_int_or_none(player.get("order")),
                "starter": to_int_or_none(player.get("starter")),
                "oncourt": to_int_or_none(player.get("oncourt")),
                "played": to_int_or_none(player.get("played")),
                "minutes": null_if_empty(stats.get("minutes")),
                "minutesCalculated": null_if_empty(stats.get("minutesCalculated")),
                "plus": to_int_or_none(stats.get("plus")),
                "minus": to_int_or_none(stats.get("minus")),
                "plusMinusPoints": to_int_or_none(stats.get("plusMinusPoints")),
                "assists": to_int_or_none(stats.get("assists")),
                "blocks": to_int_or_none(stats.get("blocks")),
                "blocksReceived": to_int_or_none(stats.get("blocksReceived")),
                "fieldGoalsAttempted": to_int_or_none(stats.get("fieldGoalsAttempted")),
                "fieldGoalsMade": to_int_or_none(stats.get("fieldGoalsMade")),
                "fieldGoalsPercentage": to_float_or_none(stats.get("fieldGoalsPercentage")),
                "foulsOffensive": to_int_or_none(stats.get("foulsOffensive")),
                "foulsDrawn": to_int_or_none(stats.get("foulsDrawn")),
                "foulsPersonal": to_int_or_none(stats.get("foulsPersonal")),
                "foulsTechnical": to_int_or_none(stats.get("foulsTechnical")),
                "freeThrowsAttempted": to_int_or_none(stats.get("freeThrowsAttempted")),
                "freeThrowsMade": to_int_or_none(stats.get("freeThrowsMade")),
                "freeThrowsPercentage": to_float_or_none(stats.get("freeThrowsPercentage")),
                "reboundsDefensive": to_int_or_none(stats.get("reboundsDefensive")),
                "reboundsOffensive": to_int_or_none(stats.get("reboundsOffensive")),
                "reboundsTotal": to_int_or_none(stats.get("reboundsTotal")),
                "steals": to_int_or_none(stats.get("steals")),
                "turnovers": to_int_or_none(stats.get("turnovers")),
                "points": to_int_or_none(stats.get("points")),
                "threePointersAttempted": to_int_or_none(stats.get("threePointersAttempted")),
                "threePointersMade": to_int_or_none(stats.get("threePointersMade")),
                "threePointersPercentage": to_float_or_none(stats.get("threePointersPercentage")),
                "twoPointersAttempted": to_int_or_none(stats.get("twoPointersAttempted")),
                "twoPointersMade": to_int_or_none(stats.get("twoPointersMade")),
                "twoPointersPercentage": to_float_or_none(stats.get("twoPointersPercentage")),
                "pointsFastBreak": to_int_or_none(stats.get("pointsFastBreak")),
                "pointsInThePaint": to_int_or_none(stats.get("pointsInThePaint")),
                "pointsSecondChance": to_int_or_none(stats.get("pointsSecondChance")),
                "_meta_source_key": source_key,
                "_meta_source_last_modified_utc": source_last_modified_utc,
            }
        )
    return rows


def build_latest_player_rows(s3_client) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load source files, dedupe by gameId recency, then emit player-game rows."""
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
            to_player_rows(
                game_id,
                "home",
                candidate.get("homeTeam") or {},
                source_key=source_key,
                source_last_modified_utc=source_last_modified,
            )
        )
        rows.extend(
            to_player_rows(
                game_id,
                "away",
                candidate.get("awayTeam") or {},
                source_key=source_key,
                source_last_modified_utc=source_last_modified,
            )
        )

    rows.sort(
        key=lambda x: (
            x.get("gameId") or "",
            x.get("team_side") or "",
            x.get("order") or -1,
            x.get("personId") or -1,
        )
    )

    print(f"Built {len(rows)} player-game rows")
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
    """Score row completeness for deterministic uniqueness enforcement."""
    score_columns = [
        "gameId",
        "personId",
        "teamId",
        "team_side",
        "minutes",
        "points",
        "reboundsTotal",
        "assists",
        "_meta_source_key",
        "_meta_source_last_modified_utc",
    ]
    return sum(1 for col in score_columns if row.get(col) is not None)


def is_minutes_duration(value: str | None) -> bool:
    """Return True when value looks like ISO-8601 PT minutes/seconds duration."""
    if value is None:
        return True
    return bool(MINUTES_DURATION_PATTERN.match(value))


def minutes_duration_seconds(value: str | None) -> float | None:
    """Parse PTxxMxx.xxS duration and return total seconds (None when absent/invalid)."""
    if value is None:
        return None
    match = MINUTES_DURATION_PATTERN.match(value)
    if match is None:
        return None
    minutes = float(match.group(1) or 0)
    seconds = float(match.group(2) or 0)
    return minutes * 60.0 + seconds


def validate_and_dedupe_rows(
    rows: list[dict[str, Any]],
    detected_at_utc: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Validate rows, quarantine hard failures, and enforce one row per (gameId, personId)."""
    deduped: dict[tuple[str, int], dict[str, Any]] = {}
    quarantine_rows: list[dict[str, Any]] = []
    dropped_missing_game_id = 0
    dropped_missing_person_id = 0
    replaced_for_quality = 0
    warning_count = 0
    error_reason_counts: Counter[str] = Counter()
    warning_reason_counts: Counter[str] = Counter()

    nonnegative_int_columns = [
        "teamId",
        "order",
        "plus",
        "minus",
        "assists",
        "blocks",
        "blocksReceived",
        "fieldGoalsAttempted",
        "fieldGoalsMade",
        "foulsOffensive",
        "foulsDrawn",
        "foulsPersonal",
        "foulsTechnical",
        "freeThrowsAttempted",
        "freeThrowsMade",
        "reboundsDefensive",
        "reboundsOffensive",
        "reboundsTotal",
        "steals",
        "turnovers",
        "points",
        "threePointersAttempted",
        "threePointersMade",
        "twoPointersAttempted",
        "twoPointersMade",
        "pointsFastBreak",
        "pointsInThePaint",
        "pointsSecondChance",
    ]
    percentage_columns = [
        "fieldGoalsPercentage",
        "freeThrowsPercentage",
        "threePointersPercentage",
        "twoPointersPercentage",
    ]

    for row in rows:
        game_id = null_if_empty(row.get("gameId"))
        person_id = to_int_or_none(row.get("personId"))
        team_side = null_if_empty(row.get("team_side"))

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
        if person_id is None:
            dropped_missing_person_id += 1
            error_reason_counts["missing_person_id"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="missing_person_id",
                    reason_level="error",
                    reason_detail="personId is null/blank",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        row["gameId"] = str(game_id)
        row["personId"] = person_id
        if team_side is None or str(team_side) not in {"home", "away"}:
            error_reason_counts["invalid_team_side"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="invalid_team_side",
                    reason_level="error",
                    reason_detail=f"team_side must be home/away, got={team_side}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue
        row["team_side"] = str(team_side)

        team_id = to_int_or_none(row.get("teamId"))
        if team_id is None:
            warning_count += 1
            warning_reason_counts["missing_team_id"] += 1
        else:
            row["teamId"] = team_id

        for col in ("played", "starter", "oncourt"):
            value = to_int_or_none(row.get(col))
            if value is not None and value not in {0, 1}:
                warning_count += 1
                warning_reason_counts[f"unexpected_{col}_flag"] += 1

        invalid_nonnegative_col: str | None = None
        invalid_nonnegative_value: int | None = None
        for col in nonnegative_int_columns:
            value = to_int_or_none(row.get(col))
            if value is not None and value < 0:
                invalid_nonnegative_col = col
                invalid_nonnegative_value = value
                break
        if invalid_nonnegative_col is not None:
            error_reason_counts["negative_stat_value"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="negative_stat_value",
                    reason_level="error",
                    reason_detail=(
                        f"{invalid_nonnegative_col} has negative value={invalid_nonnegative_value}"
                    ),
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        shot_pairs = [
            ("fieldGoalsMade", "fieldGoalsAttempted"),
            ("freeThrowsMade", "freeThrowsAttempted"),
            ("threePointersMade", "threePointersAttempted"),
            ("twoPointersMade", "twoPointersAttempted"),
        ]
        made_over_attempt_detected = False
        for made_col, att_col in shot_pairs:
            made = to_int_or_none(row.get(made_col))
            attempted = to_int_or_none(row.get(att_col))
            if made is not None and attempted is not None and made > attempted:
                error_reason_counts["made_gt_attempted"] += 1
                quarantine_rows.append(
                    make_quarantine_row(
                        row,
                        table_name=TABLE_NAME,
                        reason_code="made_gt_attempted",
                        reason_level="error",
                        reason_detail=f"{made_col}={made} exceeds {att_col}={attempted}",
                        detected_at_utc=detected_at_utc,
                    )
                )
                made_over_attempt_detected = True
                break
        if made_over_attempt_detected:
            continue

        for col in percentage_columns:
            value = to_float_or_none(row.get(col))
            if value is not None and (value < 0.0 or value > 1.0):
                warning_count += 1
                warning_reason_counts[f"{col}_out_of_range"] += 1

        minutes = null_if_empty(row.get("minutes"))
        if not is_minutes_duration(minutes):
            warning_count += 1
            warning_reason_counts["invalid_minutes_format"] += 1
        minutes_calculated = null_if_empty(row.get("minutesCalculated"))
        if not is_minutes_duration(minutes_calculated):
            warning_count += 1
            warning_reason_counts["invalid_minutes_calculated_format"] += 1
        played = to_int_or_none(row.get("played"))
        minutes_seconds = minutes_duration_seconds(minutes)
        minutes_calculated_seconds = minutes_duration_seconds(minutes_calculated)
        if played == 0 and (
            (minutes_seconds is not None and minutes_seconds > 0.0)
            or (minutes_calculated_seconds is not None and minutes_calculated_seconds > 0.0)
        ):
            warning_count += 1
            warning_reason_counts["played_zero_nonzero_minutes"] += 1

        key = (row["gameId"], person_id)

        current = deduped.get(key)
        if current is None:
            deduped[key] = row
            continue

        if quality_score(row) > quality_score(current):
            deduped[key] = row
            replaced_for_quality += 1

    output = sorted(
        deduped.values(),
        key=lambda x: (
            x.get("gameId") or "",
            x.get("team_side") or "",
            x.get("order") or -1,
            x.get("personId") or -1,
        ),
    )

    print(f"Quality gate: dropped rows missing gameId: {dropped_missing_game_id}")
    print(f"Quality gate: dropped rows missing personId: {dropped_missing_person_id}")
    print(f"Quality gate: replacements by higher-quality duplicate (gameId, personId): {replaced_for_quality}")
    print(f"Quality gate: unique (gameId, personId) rows: {len(output)}")
    print(f"Quality gate: warning count: {warning_count}")
    print(f"Quality gate: quarantined error rows: {len(quarantine_rows)}")

    dq_metrics = {
        "input_rows": len(rows),
        "output_rows": len(output),
        "quarantine_rows": len(quarantine_rows),
        "warning_count": warning_count,
        "error_count": len(quarantine_rows),
        "dropped_missing_game_id": dropped_missing_game_id,
        "dropped_missing_person_id": dropped_missing_person_id,
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
    """Write final player-game parquet to S3 (rewrites same destination key)."""
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
    """Run the boxscore player-game silver transform."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"boxscore_player_game_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    rows, source_metrics = build_latest_player_rows(s3_client)
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
        "dropped_missing_person_id": dq_metrics["dropped_missing_person_id"],
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
