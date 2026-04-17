"""
Transform raw CDN boxscore JSON files into a silver team-game parquet table.

Reads all objects under:
  s3://nba-analytics-lakehouse-dev/raw/cdn/boxscore/

Writes (single object, rewritten on each run):
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game.parquet

Deduplication / upsert semantics:
  - Final grain is one row per (gameId, team_side).
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
DESTINATION_KEY = "silver/boxscore_team_game.parquet"
ATHENA_DESTINATION_KEY = "silver/boxscore_team_game/data.parquet"
TABLE_NAME = "boxscore_team_game"
META_SOURCE_SYSTEM = "nba_cdn_boxscore"
META_SCHEMA_VERSION = 1

TEAM_STAT_INT_FIELDS = [
    "assists",
    "benchPoints",
    "biggestLead",
    "biggestScoringRun",
    "blocks",
    "blocksReceived",
    "fastBreakPointsAttempted",
    "fastBreakPointsMade",
    "fieldGoalsAttempted",
    "fieldGoalsMade",
    "foulsDrawn",
    "foulsOffensive",
    "foulsPersonal",
    "foulsTeam",
    "foulsTeamTechnical",
    "foulsTechnical",
    "freeThrowsAttempted",
    "freeThrowsMade",
    "leadChanges",
    "points",
    "pointsAgainst",
    "pointsFastBreak",
    "pointsFromTurnovers",
    "pointsInThePaint",
    "pointsInThePaintAttempted",
    "pointsInThePaintMade",
    "pointsSecondChance",
    "reboundsDefensive",
    "reboundsOffensive",
    "reboundsPersonal",
    "reboundsTeam",
    "reboundsTeamDefensive",
    "reboundsTeamOffensive",
    "reboundsTotal",
    "secondChancePointsAttempted",
    "secondChancePointsMade",
    "steals",
    "teamFieldGoalAttempts",
    "threePointersAttempted",
    "threePointersMade",
    "timesTied",
    "turnovers",
    "turnoversTeam",
    "turnoversTotal",
    "twoPointersAttempted",
    "twoPointersMade",
]

TEAM_STAT_FLOAT_FIELDS = [
    "assistsTurnoverRatio",
    "fastBreakPointsPercentage",
    "fieldGoalsEffectiveAdjusted",
    "fieldGoalsPercentage",
    "freeThrowsPercentage",
    "pointsInThePaintPercentage",
    "secondChancePointsPercentage",
    "threePointersPercentage",
    "trueShootingAttempts",
    "trueShootingPercentage",
    "twoPointersPercentage",
]

TEAM_STAT_STRING_FIELDS = [
    "biggestLeadScore",
    "biggestScoringRunScore",
    "minutes",
    "minutesCalculated",
    "timeLeading",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("gameId", pa.string()),
        pa.field("team_side", pa.string()),
        pa.field("teamId", pa.int64()),
        pa.field("teamName", pa.string()),
        pa.field("teamCity", pa.string()),
        pa.field("teamTricode", pa.string()),
        pa.field("score", pa.int64()),
        pa.field("inBonus", pa.int64()),
        pa.field("timeoutsRemaining", pa.int64()),
        pa.field("assists", pa.int64()),
        pa.field("benchPoints", pa.int64()),
        pa.field("biggestLead", pa.int64()),
        pa.field("biggestScoringRun", pa.int64()),
        pa.field("blocks", pa.int64()),
        pa.field("blocksReceived", pa.int64()),
        pa.field("fastBreakPointsAttempted", pa.int64()),
        pa.field("fastBreakPointsMade", pa.int64()),
        pa.field("fieldGoalsAttempted", pa.int64()),
        pa.field("fieldGoalsMade", pa.int64()),
        pa.field("foulsDrawn", pa.int64()),
        pa.field("foulsOffensive", pa.int64()),
        pa.field("foulsPersonal", pa.int64()),
        pa.field("foulsTeam", pa.int64()),
        pa.field("foulsTeamTechnical", pa.int64()),
        pa.field("foulsTechnical", pa.int64()),
        pa.field("freeThrowsAttempted", pa.int64()),
        pa.field("freeThrowsMade", pa.int64()),
        pa.field("leadChanges", pa.int64()),
        pa.field("points", pa.int64()),
        pa.field("pointsAgainst", pa.int64()),
        pa.field("pointsFastBreak", pa.int64()),
        pa.field("pointsFromTurnovers", pa.int64()),
        pa.field("pointsInThePaint", pa.int64()),
        pa.field("pointsInThePaintAttempted", pa.int64()),
        pa.field("pointsInThePaintMade", pa.int64()),
        pa.field("pointsSecondChance", pa.int64()),
        pa.field("reboundsDefensive", pa.int64()),
        pa.field("reboundsOffensive", pa.int64()),
        pa.field("reboundsPersonal", pa.int64()),
        pa.field("reboundsTeam", pa.int64()),
        pa.field("reboundsTeamDefensive", pa.int64()),
        pa.field("reboundsTeamOffensive", pa.int64()),
        pa.field("reboundsTotal", pa.int64()),
        pa.field("secondChancePointsAttempted", pa.int64()),
        pa.field("secondChancePointsMade", pa.int64()),
        pa.field("steals", pa.int64()),
        pa.field("teamFieldGoalAttempts", pa.int64()),
        pa.field("threePointersAttempted", pa.int64()),
        pa.field("threePointersMade", pa.int64()),
        pa.field("timesTied", pa.int64()),
        pa.field("turnovers", pa.int64()),
        pa.field("turnoversTeam", pa.int64()),
        pa.field("turnoversTotal", pa.int64()),
        pa.field("twoPointersAttempted", pa.int64()),
        pa.field("twoPointersMade", pa.int64()),
        pa.field("assistsTurnoverRatio", pa.float64()),
        pa.field("fastBreakPointsPercentage", pa.float64()),
        pa.field("fieldGoalsEffectiveAdjusted", pa.float64()),
        pa.field("fieldGoalsPercentage", pa.float64()),
        pa.field("freeThrowsPercentage", pa.float64()),
        pa.field("pointsInThePaintPercentage", pa.float64()),
        pa.field("secondChancePointsPercentage", pa.float64()),
        pa.field("threePointersPercentage", pa.float64()),
        pa.field("trueShootingAttempts", pa.float64()),
        pa.field("trueShootingPercentage", pa.float64()),
        pa.field("twoPointersPercentage", pa.float64()),
        pa.field("biggestLeadScore", pa.string()),
        pa.field("biggestScoringRunScore", pa.string()),
        pa.field("minutes", pa.string()),
        pa.field("minutesCalculated", pa.string()),
        pa.field("timeLeading", pa.string()),
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


def to_str_or_none(value: Any) -> str | None:
    """Convert text-like input into stripped string; return None for empty-like values."""
    value = null_if_empty(value)
    if value is None:
        return None
    return str(value).strip()


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


def to_team_row(
    game_id: str,
    team_side: str,
    team_obj: dict[str, Any],
    source_key: str | None,
    source_last_modified_utc: datetime | None,
) -> dict[str, Any]:
    """Build one team-game row for home or away side."""
    statistics = team_obj.get("statistics") or {}
    row = {
        "gameId": game_id,
        "team_side": team_side,
        "teamId": to_int_or_none(team_obj.get("teamId")),
        "teamName": null_if_empty(team_obj.get("teamName")),
        "teamCity": null_if_empty(team_obj.get("teamCity")),
        "teamTricode": null_if_empty(team_obj.get("teamTricode")),
        "score": to_int_or_none(team_obj.get("score")),
        "inBonus": to_int_or_none(team_obj.get("inBonus")),
        "timeoutsRemaining": to_int_or_none(team_obj.get("timeoutsRemaining")),
        "_meta_source_key": source_key,
        "_meta_source_last_modified_utc": source_last_modified_utc,
    }
    for field in TEAM_STAT_INT_FIELDS:
        row[field] = to_int_or_none(statistics.get(field))
    for field in TEAM_STAT_FLOAT_FIELDS:
        row[field] = to_float_or_none(statistics.get(field))
    for field in TEAM_STAT_STRING_FIELDS:
        row[field] = to_str_or_none(statistics.get(field))
    return row


def build_latest_team_rows(s3_client) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load source files, dedupe by gameId recency, then emit home/away team rows."""
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
        rows.append(
            to_team_row(
                game_id,
                "home",
                candidate.get("homeTeam") or {},
                source_key=source_key,
                source_last_modified_utc=source_last_modified,
            )
        )
        rows.append(
            to_team_row(
                game_id,
                "away",
                candidate.get("awayTeam") or {},
                source_key=source_key,
                source_last_modified_utc=source_last_modified,
            )
        )

    print(f"Built {len(rows)} team-game rows")
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
        "team_side",
        "teamId",
        "teamName",
        "teamTricode",
        "score",
        "_meta_source_key",
        "_meta_source_last_modified_utc",
    ]
    return sum(1 for col in score_columns if row.get(col) is not None)


def validate_and_dedupe_rows(
    rows: list[dict[str, Any]],
    detected_at_utc: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Validate rows, quarantine hard failures, and enforce one row per (gameId, team_side)."""
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    quarantine_rows: list[dict[str, Any]] = []
    dropped_missing_game_id = 0
    dropped_missing_team_side = 0
    replaced_for_quality = 0
    duplicate_game_team_id_pairs = 0
    warning_count = 0
    error_reason_counts: Counter[str] = Counter()
    warning_reason_counts: Counter[str] = Counter()

    seen_game_team_id: set[tuple[str, int]] = set()

    for row in rows:
        game_id = null_if_empty(row.get("gameId"))
        team_side = null_if_empty(row.get("team_side"))
        team_id = to_int_or_none(row.get("teamId"))
        score = to_int_or_none(row.get("score"))
        in_bonus = to_int_or_none(row.get("inBonus"))
        timeouts_remaining = to_int_or_none(row.get("timeoutsRemaining"))

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

        game_id = str(game_id)
        team_side = str(team_side)
        row["gameId"] = game_id
        row["team_side"] = team_side

        if team_side not in {"home", "away"}:
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

        if score is not None and score < 0:
            error_reason_counts["negative_score"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="negative_score",
                    reason_level="error",
                    reason_detail=f"score has negative value={score}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        if in_bonus is not None and in_bonus not in {0, 1}:
            error_reason_counts["invalid_in_bonus_flag"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="invalid_in_bonus_flag",
                    reason_level="error",
                    reason_detail=f"inBonus has invalid value={in_bonus}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        if team_id is None:
            warning_count += 1
            warning_reason_counts["missing_team_id"] += 1

        if timeouts_remaining is not None and (timeouts_remaining < -1 or timeouts_remaining > 7):
            warning_count += 1
            warning_reason_counts["timeouts_remaining_out_of_range"] += 1

        dedupe_key = (game_id, team_side)
        current = deduped.get(dedupe_key)
        if current is None:
            deduped[dedupe_key] = row
        elif quality_score(row) > quality_score(current):
            deduped[dedupe_key] = row
            replaced_for_quality += 1

        if team_id is not None:
            game_team_id_key = (game_id, team_id)
            if game_team_id_key in seen_game_team_id:
                duplicate_game_team_id_pairs += 1
            else:
                seen_game_team_id.add(game_team_id_key)

    if duplicate_game_team_id_pairs > 0:
        warning_count += duplicate_game_team_id_pairs
        warning_reason_counts["duplicate_game_team_id_pairs"] += duplicate_game_team_id_pairs

    output_pre_grain_check = sorted(
        deduped.values(),
        key=lambda x: (
            x.get("gameId") or "",
            x.get("team_side") or "",
            x.get("teamId") or -1,
        ),
    )
    invalid_grain_game_ids: set[str] = set()
    row_count_by_game: dict[str, int] = {}
    side_set_by_game: dict[str, set[str]] = {}

    for row in output_pre_grain_check:
        game_id = row["gameId"]
        row_count_by_game[game_id] = row_count_by_game.get(game_id, 0) + 1
        sides = side_set_by_game.get(game_id)
        if sides is None:
            sides = set()
            side_set_by_game[game_id] = sides
        sides.add(row["team_side"])

    for game_id, row_count in row_count_by_game.items():
        side_set = side_set_by_game.get(game_id) or set()
        if row_count != 2 or side_set != {"home", "away"}:
            invalid_grain_game_ids.add(game_id)

    output: list[dict[str, Any]] = []
    if invalid_grain_game_ids:
        for row in output_pre_grain_check:
            if row["gameId"] in invalid_grain_game_ids:
                error_reason_counts["invalid_game_team_grain"] += 1
                quarantine_rows.append(
                    make_quarantine_row(
                        row,
                        table_name=TABLE_NAME,
                        reason_code="invalid_game_team_grain",
                        reason_level="error",
                        reason_detail=(
                            "Expected exactly one home and one away row per game after dedupe"
                        ),
                        detected_at_utc=detected_at_utc,
                    )
                )
            else:
                output.append(row)
    else:
        output = output_pre_grain_check

    print(f"Quality gate: dropped rows missing gameId: {dropped_missing_game_id}")
    print(f"Quality gate: dropped rows missing team_side: {dropped_missing_team_side}")
    print(f"Quality gate: replacements by higher-quality duplicate (gameId, team_side): {replaced_for_quality}")
    print(f"Quality gate: duplicate (gameId, teamId) pairs observed: {duplicate_game_team_id_pairs}")
    print(f"Quality gate: unique (gameId, team_side) rows: {len(output)}")
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
        "replaced_for_quality": replaced_for_quality,
        "duplicate_game_team_id_pairs": duplicate_game_team_id_pairs,
        "invalid_grain_game_count": len(invalid_grain_game_ids),
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
    """Write final team-game parquet to both the legacy single-file key and Athena-friendly prefix."""
    table = pa.Table.from_pylist(rows, schema=TARGET_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    payload = buffer.getvalue()

    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=DESTINATION_KEY,
        Body=payload,
        ContentType="application/octet-stream",
    )
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=ATHENA_DESTINATION_KEY,
        Body=payload,
        ContentType="application/octet-stream",
    )


def main() -> None:
    """Run the boxscore team-game silver transform."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"boxscore_team_game_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    rows, source_metrics = build_latest_team_rows(s3_client)
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
        print(f"Wrote s3://{S3_BUCKET}/{ATHENA_DESTINATION_KEY}")
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
        "replaced_for_quality": dq_metrics["replaced_for_quality"],
        "duplicate_game_team_id_pairs": dq_metrics["duplicate_game_team_id_pairs"],
        "invalid_grain_game_count": dq_metrics["invalid_grain_game_count"],
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
