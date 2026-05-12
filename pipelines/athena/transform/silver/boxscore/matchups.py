"""
Transform raw NBA Stats BoxScoreMatchupsV3 JSON files into silver parquet.

Reads all objects under:
  s3://nba-analytics-lakehouse-dev/raw/boxscorematchupsv3/

Writes:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_matchups.parquet

Grain:
  One row per (game_id, team_id, person_id, matchups_person_id).
"""

from __future__ import annotations

import io
import json
import os
import re
import tarfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from boxscore.contracts import META_SCHEMA_VERSION, S3_BUCKET
from silver_pipeline_helpers import make_quarantine_row, write_audit_artifacts, write_quarantine_rows

load_dotenv(override=True)  # Ensure .env credentials override any system variables
if os.environ.get("AWS_PROFILE") == "":
    os.environ.pop("AWS_PROFILE")

ENDPOINT_SOURCE_PREFIX = "raw/boxscorematchupsv3/"
ARCHIVE_SOURCE_PREFIX = "raw/nba_data/matchups/"
SOURCE_PREFIX = ENDPOINT_SOURCE_PREFIX
DESTINATION_KEY = "silver/boxscore_matchups.parquet"
TABLE_NAME = "boxscore_matchups"
META_SOURCE_SYSTEM = "nba_stats_boxscorematchupsv3"
ARCHIVE_META_SOURCE_SYSTEM = "github_nba_data_matchups_archive"

TARGET_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("away_team_id", pa.int64()),
        pa.field("home_team_id", pa.int64()),
        pa.field("team_side", pa.string()),
        pa.field("team_id", pa.int64()),
        pa.field("team_name", pa.string()),
        pa.field("team_city", pa.string()),
        pa.field("team_tricode", pa.string()),
        pa.field("team_slug", pa.string()),
        pa.field("person_id", pa.int64()),
        pa.field("first_name", pa.string()),
        pa.field("family_name", pa.string()),
        pa.field("name_i", pa.string()),
        pa.field("player_slug", pa.string()),
        pa.field("position", pa.string()),
        pa.field("comment", pa.string()),
        pa.field("jersey_num", pa.string()),
        pa.field("matchups_person_id", pa.int64()),
        pa.field("matchups_first_name", pa.string()),
        pa.field("matchups_family_name", pa.string()),
        pa.field("matchups_name_i", pa.string()),
        pa.field("matchups_player_slug", pa.string()),
        pa.field("matchups_jersey_num", pa.string()),
        pa.field("matchup_minutes", pa.string()),
        pa.field("matchup_minutes_sort", pa.float64()),
        pa.field("partial_possessions", pa.float64()),
        pa.field("percentage_defender_total_time", pa.float64()),
        pa.field("percentage_offensive_total_time", pa.float64()),
        pa.field("percentage_total_time_both_on", pa.float64()),
        pa.field("switches_on", pa.int64()),
        pa.field("player_points", pa.int64()),
        pa.field("team_points", pa.int64()),
        pa.field("matchup_assists", pa.int64()),
        pa.field("matchup_potential_assists", pa.int64()),
        pa.field("matchup_turnovers", pa.int64()),
        pa.field("matchup_blocks", pa.int64()),
        pa.field("matchup_field_goals_made", pa.int64()),
        pa.field("matchup_field_goals_attempted", pa.int64()),
        pa.field("matchup_field_goals_percentage", pa.float64()),
        pa.field("matchup_three_pointers_made", pa.int64()),
        pa.field("matchup_three_pointers_attempted", pa.int64()),
        pa.field("matchup_three_pointers_percentage", pa.float64()),
        pa.field("help_blocks", pa.int64()),
        pa.field("help_field_goals_made", pa.int64()),
        pa.field("help_field_goals_attempted", pa.int64()),
        pa.field("help_field_goals_percentage", pa.float64()),
        pa.field("matchup_free_throws_made", pa.int64()),
        pa.field("matchup_free_throws_attempted", pa.int64()),
        pa.field("shooting_fouls", pa.int64()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)

INT_COLUMNS = {
    "away_team_id",
    "home_team_id",
    "team_id",
    "person_id",
    "matchups_person_id",
    "switches_on",
    "player_points",
    "team_points",
    "matchup_assists",
    "matchup_potential_assists",
    "matchup_turnovers",
    "matchup_blocks",
    "matchup_field_goals_made",
    "matchup_field_goals_attempted",
    "matchup_three_pointers_made",
    "matchup_three_pointers_attempted",
    "help_blocks",
    "help_field_goals_made",
    "help_field_goals_attempted",
    "matchup_free_throws_made",
    "matchup_free_throws_attempted",
    "shooting_fouls",
}

FLOAT_COLUMNS = {
    "matchup_minutes_sort",
    "partial_possessions",
    "percentage_defender_total_time",
    "percentage_offensive_total_time",
    "percentage_total_time_both_on",
    "matchup_field_goals_percentage",
    "matchup_three_pointers_percentage",
    "help_field_goals_percentage",
}

SOURCE_VALUE_COLUMNS = [name for name in TARGET_SCHEMA.names if not name.startswith("_meta_")]


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
    return int(float(value))


def to_float_or_none(value: Any) -> float | None:
    """Convert numeric-like input into float; return None for empty-like values."""
    value = null_if_empty(value)
    if value is None:
        return None
    return float(value)


def clean_name(value: str) -> str:
    """Convert NBA Stats camelCase/PascalCase keys into snake_case."""
    text = re.sub(r"[^0-9A-Za-z]+", "_", str(value)).strip("_")
    text = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return re.sub(r"_+", "_", text).lower()


def normalize_game_id(value: Any) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return text.zfill(10)
    return text


def extract_game_id_from_key(key: str) -> str | None:
    """Fallback parser for keys like raw/boxscorematchupsv3/game_id=0022500001.json."""
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id=") or not filename.endswith(".json"):
        return None
    return normalize_game_id(filename[len("game_id=") : -len(".json")])


def list_source_json_objects(s3_client) -> list[dict[str, Any]]:
    """List all source JSON objects under the matchup raw prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=ENDPOINT_SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".json"):
                objects.append(obj)

    return objects


def list_source_archive_objects(s3_client) -> list[dict[str, Any]]:
    """List all source archive objects under the nba_data matchup raw prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=ARCHIVE_SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".tar.xz"):
                objects.append(obj)

    return objects


def read_json_object(s3_client, key: str) -> dict[str, Any]:
    """Read and decode one JSON object from S3."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    return json.loads(response["Body"].read())


def read_bytes_object(s3_client, key: str) -> bytes:
    """Read one object from S3 as bytes."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    return response["Body"].read()


def normalize_source_row(row: dict[str, Any]) -> dict[str, Any]:
    """Keep target columns only and coerce source values into the explicit schema."""
    output: dict[str, Any] = {}
    for name in SOURCE_VALUE_COLUMNS:
        value = null_if_empty(row.get(name))
        if name == "game_id":
            output[name] = normalize_game_id(value)
        elif name in INT_COLUMNS:
            output[name] = to_int_or_none(value)
        elif name in FLOAT_COLUMNS:
            output[name] = to_float_or_none(value)
        else:
            output[name] = str(value).strip() if value is not None else None
    return output


def boxscore_matchups_root(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the root boxScoreMatchups object from known endpoint response shapes."""
    root = payload.get("boxScoreMatchups")
    if isinstance(root, list):
        return root[0] if root and isinstance(root[0], dict) else {}
    if isinstance(root, dict):
        return root
    return {}


def build_rows_from_payload(payload: dict[str, Any], fallback_game_id: str | None = None) -> list[dict[str, Any]]:
    """Flatten one BoxScoreMatchupsV3 raw JSON payload into source-shaped rows."""
    root = boxscore_matchups_root(payload)
    if not root:
        return []

    game_id = normalize_game_id(root.get("gameId") or fallback_game_id)
    common = {
        "game_id": game_id,
        "away_team_id": root.get("awayTeamId"),
        "home_team_id": root.get("homeTeamId"),
    }

    rows: list[dict[str, Any]] = []
    for source_key, team_side in (("homeTeam", "home"), ("awayTeam", "away")):
        team = root.get(source_key) or {}
        if not isinstance(team, dict):
            continue
        team_info = {
            "team_side": team_side,
            "team_id": team.get("teamId"),
            "team_name": team.get("teamName"),
            "team_city": team.get("teamCity"),
            "team_tricode": team.get("teamTricode"),
            "team_slug": team.get("teamSlug"),
        }

        for player in team.get("players") or []:
            if not isinstance(player, dict):
                continue
            player_fields = {
                clean_name(key): value
                for key, value in player.items()
                if key != "matchups"
            }
            for matchup in player.get("matchups") or []:
                if not isinstance(matchup, dict):
                    continue
                matchup_fields = {
                    f"matchups_{clean_name(key)}": value
                    for key, value in matchup.items()
                    if key != "statistics"
                }
                statistics = matchup.get("statistics") or {}
                if not isinstance(statistics, dict):
                    statistics = {}
                stat_fields = {clean_name(key): value for key, value in statistics.items()}
                rows.append(
                    normalize_source_row(
                        {
                            **common,
                            **team_info,
                            **player_fields,
                            **matchup_fields,
                            **stat_fields,
                        }
                    )
                )

    return rows


def build_rows_from_archive(payload: bytes) -> list[dict[str, Any]]:
    """Extract CSV rows from one source tar.xz archive."""
    rows: list[dict[str, Any]] = []
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as archive:
        csv_members = [member for member in archive.getmembers() if member.isfile() and member.name.endswith(".csv")]
        for member in csv_members:
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            text = io.TextIOWrapper(extracted, encoding="utf-8", newline="")
            import csv

            reader = csv.DictReader(text)
            for row in reader:
                rows.append(normalize_source_row(row))
    return rows


def build_all_source_rows(s3_client) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load all source files and flatten matchup rows."""
    json_objects = list_source_json_objects(s3_client)
    archive_objects = list_source_archive_objects(s3_client)
    print(f"Discovered {len(json_objects)} source JSON objects under {ENDPOINT_SOURCE_PREFIX}")
    print(f"Discovered {len(archive_objects)} source archive objects under {ARCHIVE_SOURCE_PREFIX}")

    rows: list[dict[str, Any]] = []
    failed_reads = 0
    source_empty_payloads = 0
    min_last_modified_utc: datetime | None = None
    max_last_modified_utc: datetime | None = None

    for obj in json_objects:
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
            source_rows = build_rows_from_payload(payload, fallback_game_id=extract_game_id_from_key(key))
        except Exception as exc:
            failed_reads += 1
            print(f"Failed to parse {key}: {type(exc).__name__}: {exc}")
            continue

        if not source_rows:
            source_empty_payloads += 1
            continue

        for row in source_rows:
            row["_meta_source_key"] = key
            row["_meta_source_last_modified_utc"] = last_modified
            row["_meta_source_system"] = META_SOURCE_SYSTEM
            rows.append(row)

    for obj in archive_objects:
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
            source_rows = build_rows_from_archive(read_bytes_object(s3_client, key))
        except Exception as exc:
            failed_reads += 1
            print(f"Failed to parse {key}: {type(exc).__name__}: {exc}")
            continue

        if not source_rows:
            source_empty_payloads += 1
            continue

        for row in source_rows:
            row["_meta_source_key"] = key
            row["_meta_source_last_modified_utc"] = last_modified
            row["_meta_source_system"] = ARCHIVE_META_SOURCE_SYSTEM
            rows.append(row)

    print(f"Built {len(rows)} source matchup rows")
    print(f"Empty/no-matchup source payloads: {source_empty_payloads}")
    print(f"Failed source reads/parses: {failed_reads}")
    return rows, {
        "source_json_object_count": len(json_objects),
        "source_archive_object_count": len(archive_objects),
        "source_total_object_count": len(json_objects) + len(archive_objects),
        "source_min_last_modified_utc": min_last_modified_utc,
        "source_max_last_modified_utc": max_last_modified_utc,
        "source_empty_payloads": source_empty_payloads,
        "source_failed_reads": failed_reads,
    }


def quality_score(row: dict[str, Any]) -> int:
    """Score row completeness for deterministic uniqueness enforcement."""
    score_columns = [
        "game_id",
        "team_id",
        "person_id",
        "matchups_person_id",
        "matchup_minutes_sort",
        "partial_possessions",
        "player_points",
        "_meta_source_key",
        "_meta_source_last_modified_utc",
    ]
    return sum(1 for col in score_columns if row.get(col) is not None)


def grain_key(row: dict[str, Any]) -> tuple[str | None, int | None, int | None, int | None]:
    return (
        row.get("game_id"),
        row.get("team_id"),
        row.get("person_id"),
        row.get("matchups_person_id"),
    )


def validate_and_dedupe_rows(
    rows: list[dict[str, Any]],
    detected_at_utc: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Validate rows, quarantine hard failures, and enforce the matchup grain."""
    deduped: dict[tuple[str | None, int | None, int | None, int | None], dict[str, Any]] = {}
    quarantine_rows: list[dict[str, Any]] = []
    warning_count = 0
    replaced_for_quality = 0
    error_reason_counts: Counter[str] = Counter()
    warning_reason_counts: Counter[str] = Counter()

    required_columns = ("game_id", "team_id", "person_id", "matchups_person_id")
    nonnegative_columns = INT_COLUMNS | FLOAT_COLUMNS
    percentage_columns = {name for name in FLOAT_COLUMNS if name.startswith("percentage_") or name.endswith("_percentage")}

    for row in rows:
        missing_required = [name for name in required_columns if row.get(name) is None]
        if missing_required:
            reason = "missing_required_grain_column"
            error_reason_counts[reason] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code=reason,
                    reason_level="error",
                    reason_detail=f"Missing required columns: {','.join(missing_required)}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        invalid_negative = [name for name in nonnegative_columns if row.get(name) is not None and row[name] < 0]
        if invalid_negative:
            reason = "negative_numeric_value"
            error_reason_counts[reason] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code=reason,
                    reason_level="error",
                    reason_detail=f"Negative values in: {','.join(invalid_negative)}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        if any(row.get(name) is not None and row[name] > 1.0 for name in percentage_columns):
            warning_count += 1
            warning_reason_counts["percentage_outside_unit_interval"] += 1

        key = grain_key(row)
        current = deduped.get(key)
        if current is None:
            deduped[key] = row
            continue
        warning_count += 1
        warning_reason_counts["duplicate_matchup_grain"] += 1
        if quality_score(row) > quality_score(current):
            deduped[key] = row
            replaced_for_quality += 1

    output = sorted(
        deduped.values(),
        key=lambda x: (
            x.get("game_id") or "",
            x.get("team_side") or "",
            x.get("team_id") or 0,
            x.get("person_id") or 0,
            x.get("matchups_person_id") or 0,
        ),
    )

    print(f"Quality gate: unique matchup rows: {len(output)}")
    print(f"Quality gate: replacements by higher-quality duplicate grain: {replaced_for_quality}")
    print(f"Quality gate: warning count: {warning_count}")
    print(f"Quality gate: quarantined error rows: {len(quarantine_rows)}")

    return output, quarantine_rows, {
        "input_rows": len(rows),
        "output_rows": len(output),
        "quarantine_rows": len(quarantine_rows),
        "warning_count": warning_count,
        "error_count": len(quarantine_rows),
        "replaced_for_quality": replaced_for_quality,
        "error_reason_counts": dict(error_reason_counts),
        "warning_reason_counts": dict(warning_reason_counts),
    }


def add_metadata_columns(rows: list[dict[str, Any]], pipeline_run_id: str, ingested_at_utc: datetime) -> None:
    """Attach standardized metadata contract columns to each row."""
    for row in rows:
        source_last_modified = row.get("_meta_source_last_modified_utc")
        if isinstance(source_last_modified, datetime) and source_last_modified.tzinfo is None:
            source_last_modified = source_last_modified.replace(tzinfo=timezone.utc)

        row["_meta_pipeline_run_id"] = pipeline_run_id
        row["_meta_ingested_at_utc"] = ingested_at_utc
        row["_meta_source_system"] = null_if_empty(row.get("_meta_source_system")) or META_SOURCE_SYSTEM
        row["_meta_source_key"] = null_if_empty(row.get("_meta_source_key"))
        row["_meta_source_last_modified_utc"] = source_last_modified
        row["_meta_schema_version"] = META_SCHEMA_VERSION


def write_parquet_to_s3(rows: list[dict[str, Any]], s3_client) -> None:
    """Write final matchup parquet to S3."""
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
    """Run the boxscore matchup silver transform."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"boxscore_matchups_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    rows, source_metrics = build_all_source_rows(s3_client)
    if source_metrics["source_total_object_count"] == 0:
        audit_row = {
            "table_name": TABLE_NAME,
            "pipeline_run_id": pipeline_run_id,
            "run_status": "skipped_no_source",
            "ingested_at_utc": ingested_at_utc,
            "source_bucket": S3_BUCKET,
            "source_prefix": f"{ENDPOINT_SOURCE_PREFIX},{ARCHIVE_SOURCE_PREFIX}",
            "source_json_object_count": 0,
            "source_archive_object_count": 0,
            "source_total_object_count": 0,
            "source_min_last_modified_utc": None,
            "source_max_last_modified_utc": None,
            "source_empty_payloads": 0,
            "source_failed_reads": 0,
            "destination_key": DESTINATION_KEY,
            "quarantine_key": None,
            "input_row_count": 0,
            "output_row_count": 0,
            "quarantine_row_count": 0,
            "warning_count": 0,
            "error_count": 0,
            "replaced_for_quality": 0,
            "error_reason_counts": json.dumps({}, sort_keys=True),
            "warning_reason_counts": json.dumps({}, sort_keys=True),
            "meta_source_system": META_SOURCE_SYSTEM,
            "meta_schema_version": META_SCHEMA_VERSION,
        }
        audit_json_key, audit_parquet_key = write_audit_artifacts(
            s3_client=s3_client,
            bucket=S3_BUCKET,
            table_name=TABLE_NAME,
            pipeline_run_id=pipeline_run_id,
            ingested_at_utc=ingested_at_utc,
            audit_row=audit_row,
        )
        print(
            "No source objects found under "
            f"s3://{S3_BUCKET}/{ENDPOINT_SOURCE_PREFIX} or s3://{S3_BUCKET}/{ARCHIVE_SOURCE_PREFIX}; "
            "skipped main silver write."
        )
        print(f"Wrote audit JSON: s3://{S3_BUCKET}/{audit_json_key}")
        print(f"Wrote audit parquet: s3://{S3_BUCKET}/{audit_parquet_key}")
        return

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
        "source_prefix": f"{ENDPOINT_SOURCE_PREFIX},{ARCHIVE_SOURCE_PREFIX}",
        "source_json_object_count": source_metrics["source_json_object_count"],
        "source_archive_object_count": source_metrics["source_archive_object_count"],
        "source_total_object_count": source_metrics["source_total_object_count"],
        "source_min_last_modified_utc": source_metrics["source_min_last_modified_utc"],
        "source_max_last_modified_utc": source_metrics["source_max_last_modified_utc"],
        "source_empty_payloads": source_metrics["source_empty_payloads"],
        "source_failed_reads": source_metrics["source_failed_reads"],
        "destination_key": DESTINATION_KEY,
        "quarantine_key": quarantine_output_key,
        "input_row_count": input_row_count,
        "output_row_count": len(rows),
        "quarantine_row_count": dq_metrics["quarantine_rows"],
        "warning_count": dq_metrics["warning_count"],
        "error_count": dq_metrics["error_count"],
        "replaced_for_quality": dq_metrics["replaced_for_quality"],
        "error_reason_counts": json.dumps(dq_metrics["error_reason_counts"], sort_keys=True),
        "warning_reason_counts": json.dumps(dq_metrics["warning_reason_counts"], sort_keys=True),
        "meta_source_system": META_SOURCE_SYSTEM,
        "meta_schema_version": META_SCHEMA_VERSION,
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
        raise SystemExit(f"{TABLE_NAME} run failed: quarantined error rows={dq_metrics['error_count']}")


if __name__ == "__main__":
    main()
