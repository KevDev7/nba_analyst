"""
One-time transform from raw scheduleLeagueV2_1 JSON to a silver parquet file.

Reads:
  s3://nba-analytics-lakehouse-dev/raw/cdn/scheduleLeagueV2_1.json

Writes:
  s3://nba-analytics-lakehouse-dev/silver/scheduleLeagueV2_1.parquet
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
SOURCE_KEY = "raw/cdn/scheduleLeagueV2_1.json"
DESTINATION_KEY = "silver/scheduleLeagueV2_1.parquet"
TABLE_NAME = "scheduleLeagueV2_1"
META_SOURCE_SYSTEM = "nba_cdn_schedule"
META_SCHEMA_VERSION = 1

TARGET_SCHEMA = pa.schema(
    [
        pa.field("seasonYear", pa.string()),
        pa.field("leagueId", pa.string()),
        pa.field("gameId", pa.string()),
        pa.field("gameCode", pa.string()),
        pa.field("gameSequence", pa.int64()),
        pa.field("gameDate", pa.date32()),
        pa.field("gameDateTimeUTC", pa.timestamp("us", tz="UTC")),
        pa.field("day", pa.string()),
        pa.field("monthNum", pa.int64()),
        pa.field("weekNumber", pa.int64()),
        pa.field("weekName", pa.string()),
        pa.field("gameStatus", pa.int64()),
        pa.field("gameStatusText", pa.string()),
        pa.field("postponedStatus", pa.string()),
        pa.field("ifNecessary", pa.bool_()),
        pa.field("gameLabel", pa.string()),
        pa.field("gameSubLabel", pa.string()),
        pa.field("gameSubtype", pa.string()),
        pa.field("seriesGameNumber", pa.string()),
        pa.field("seriesText", pa.string()),
        pa.field("isNeutral", pa.bool_()),
        pa.field("arenaName", pa.string()),
        pa.field("arenaCity", pa.string()),
        pa.field("arenaState", pa.string()),
        pa.field("homeTeamId", pa.int64()),
        pa.field("homeTeamName", pa.string()),
        pa.field("homeTeamCity", pa.string()),
        pa.field("homeTeamTricode", pa.string()),
        pa.field("homeTeamSlug", pa.string()),
        pa.field("awayTeamId", pa.int64()),
        pa.field("awayTeamName", pa.string()),
        pa.field("awayTeamCity", pa.string()),
        pa.field("awayTeamTricode", pa.string()),
        pa.field("awayTeamSlug", pa.string()),
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
    """Convert input to int when present; return None for empty-like values."""
    value = null_if_empty(value)
    if value is None:
        return None
    return int(value)


def to_bool_or_none(value: Any) -> bool | None:
    """Convert input to bool when present; supports bool and string flags."""
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    raise ValueError(f"Cannot convert value to bool: {value!r}")


def parse_game_date(value: Any):
    """Parse parent gameDate ('MM/DD/YYYY HH:MM:SS') into date."""
    value = null_if_empty(value)
    if value is None:
        return None
    return datetime.strptime(str(value), "%m/%d/%Y %H:%M:%S").date()


def parse_utc_timestamp(value: Any) -> datetime | None:
    """Parse UTC timestamp and return timezone-aware datetime in UTC."""
    value = null_if_empty(value)
    if value is None:
        return None

    text = str(value)
    if text.endswith("Z"):
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
        return parsed.replace(tzinfo=timezone.utc)

    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_source_payload(s3_client) -> tuple[dict[str, Any], datetime | None]:
    """Load source JSON from S3 and return payload + source last-modified timestamp."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=SOURCE_KEY)
    payload_bytes = response["Body"].read()
    last_modified = response.get("LastModified")
    if isinstance(last_modified, datetime) and last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=timezone.utc)
    return json.loads(payload_bytes), last_modified


def build_rows(
    payload: dict[str, Any],
    source_key: str,
    source_last_modified_utc: datetime | None,
) -> list[dict[str, Any]]:
    """Flatten leagueSchedule.gameDates[].games[] into one row per game."""
    schedule = payload.get("leagueSchedule") or {}
    season_year = null_if_empty(schedule.get("seasonYear"))
    league_id = null_if_empty(schedule.get("leagueId"))

    rows: list[dict[str, Any]] = []
    for game_date_entry in schedule.get("gameDates") or []:
        game_date = parse_game_date(game_date_entry.get("gameDate"))
        for game in game_date_entry.get("games") or []:
            home_team = game.get("homeTeam") or {}
            away_team = game.get("awayTeam") or {}

            rows.append(
                {
                    "seasonYear": season_year,
                    "leagueId": league_id,
                    "gameId": null_if_empty(game.get("gameId")),
                    "gameCode": null_if_empty(game.get("gameCode")),
                    "gameSequence": to_int_or_none(game.get("gameSequence")),
                    "gameDate": game_date,
                    "gameDateTimeUTC": parse_utc_timestamp(game.get("gameDateTimeUTC")),
                    "day": null_if_empty(game.get("day")),
                    "monthNum": to_int_or_none(game.get("monthNum")),
                    "weekNumber": to_int_or_none(game.get("weekNumber")),
                    "weekName": null_if_empty(game.get("weekName")),
                    "gameStatus": to_int_or_none(game.get("gameStatus")),
                    "gameStatusText": null_if_empty(game.get("gameStatusText")),
                    "postponedStatus": null_if_empty(game.get("postponedStatus")),
                    "ifNecessary": to_bool_or_none(game.get("ifNecessary")),
                    "gameLabel": null_if_empty(game.get("gameLabel")),
                    "gameSubLabel": null_if_empty(game.get("gameSubLabel")),
                    "gameSubtype": null_if_empty(game.get("gameSubtype")),
                    "seriesGameNumber": null_if_empty(game.get("seriesGameNumber")),
                    "seriesText": null_if_empty(game.get("seriesText")),
                    "isNeutral": to_bool_or_none(game.get("isNeutral")),
                    "arenaName": null_if_empty(game.get("arenaName")),
                    "arenaCity": null_if_empty(game.get("arenaCity")),
                    "arenaState": null_if_empty(game.get("arenaState")),
                    "homeTeamId": to_int_or_none(home_team.get("teamId")),
                    "homeTeamName": null_if_empty(home_team.get("teamName")),
                    "homeTeamCity": null_if_empty(home_team.get("teamCity")),
                    "homeTeamTricode": null_if_empty(home_team.get("teamTricode")),
                    "homeTeamSlug": null_if_empty(home_team.get("teamSlug")),
                    "awayTeamId": to_int_or_none(away_team.get("teamId")),
                    "awayTeamName": null_if_empty(away_team.get("teamName")),
                    "awayTeamCity": null_if_empty(away_team.get("teamCity")),
                    "awayTeamTricode": null_if_empty(away_team.get("teamTricode")),
                    "awayTeamSlug": null_if_empty(away_team.get("teamSlug")),
                    "_meta_source_key": source_key,
                    "_meta_source_last_modified_utc": source_last_modified_utc,
                }
            )

    return rows


def quality_score(row: dict[str, Any]) -> int:
    """Score row completeness for deterministic duplicate resolution."""
    score_columns = [
        "gameId",
        "gameCode",
        "gameDate",
        "gameDateTimeUTC",
        "gameStatus",
        "gameStatusText",
        "homeTeamId",
        "awayTeamId",
    ]
    return sum(1 for col in score_columns if row.get(col) is not None)


def validate_and_dedupe_rows(
    rows: list[dict[str, Any]],
    detected_at_utc: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Validate rows, quarantine hard failures, and enforce one row per gameId."""
    deduped: dict[str, dict[str, Any]] = {}
    quarantine_rows: list[dict[str, Any]] = []
    dropped_missing_game_id = 0
    replaced_for_quality = 0
    warning_count = 0
    error_reason_counts: Counter[str] = Counter()
    warning_reason_counts: Counter[str] = Counter()

    for row in rows:
        game_id = null_if_empty(row.get("gameId"))
        if game_id is None:
            dropped_missing_game_id += 1
            error_reason_counts["missing_game_id"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="missing_game_id",
                    reason_level="error",
                    reason_detail="gameId is null/blank for schedule row",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue
        row["gameId"] = str(game_id)

        home_team_id = to_int_or_none(row.get("homeTeamId"))
        away_team_id = to_int_or_none(row.get("awayTeamId"))
        if home_team_id is None or away_team_id is None:
            error_reason_counts["missing_team_id"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="missing_team_id",
                    reason_level="error",
                    reason_detail="homeTeamId or awayTeamId is null",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue
        row["homeTeamId"] = home_team_id
        row["awayTeamId"] = away_team_id

        if home_team_id == away_team_id:
            if home_team_id == 0:
                warning_count += 1
                warning_reason_counts["placeholder_unassigned_teams"] += 1
            else:
                error_reason_counts["home_away_same_team"] += 1
                quarantine_rows.append(
                    make_quarantine_row(
                        row,
                        table_name=TABLE_NAME,
                        reason_code="home_away_same_team",
                        reason_level="error",
                        reason_detail="homeTeamId equals awayTeamId",
                        detected_at_utc=detected_at_utc,
                    )
                )
                continue

        game_sequence = to_int_or_none(row.get("gameSequence"))
        if game_sequence is not None and game_sequence < 0:
            error_reason_counts["negative_game_sequence"] += 1
            quarantine_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="negative_game_sequence",
                    reason_level="error",
                    reason_detail="gameSequence is negative",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue

        game_status = to_int_or_none(row.get("gameStatus"))
        if game_status is not None and game_status not in {1, 2, 3, 4}:
            warning_count += 1
            warning_reason_counts["unexpected_game_status"] += 1
        if (home_team_id == 0) ^ (away_team_id == 0):
            warning_count += 1
            warning_reason_counts["placeholder_team_id_zero"] += 1

        current = deduped.get(row["gameId"])
        if current is None:
            deduped[row["gameId"]] = row
            continue

        if quality_score(row) > quality_score(current):
            deduped[row["gameId"]] = row
            replaced_for_quality += 1

    output = sorted(
        deduped.values(),
        key=lambda x: (
            x.get("gameDateTimeUTC") or datetime.min.replace(tzinfo=timezone.utc),
            x.get("gameId") or "",
        ),
    )

    print(f"Quality gate: dropped rows missing gameId: {dropped_missing_game_id}")
    print(f"Quality gate: replacements by higher-quality duplicate gameId: {replaced_for_quality}")
    print(f"Quality gate: unique gameId rows: {len(output)}")
    print(f"Quality gate: warning count: {warning_count}")
    print(f"Quality gate: quarantined error rows: {len(quarantine_rows)}")

    dq_metrics = {
        "input_rows": len(rows),
        "output_rows": len(output),
        "quarantine_rows": len(quarantine_rows),
        "warning_count": warning_count,
        "error_count": len(quarantine_rows),
        "dropped_missing_game_id": dropped_missing_game_id,
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
    """Write flattened rows as one parquet file to S3 silver."""
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
    """Run the one-time transform job."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"schedule_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    print(f"Reading s3://{S3_BUCKET}/{SOURCE_KEY}")
    payload, source_last_modified_utc = read_source_payload(s3_client)

    rows = build_rows(
        payload,
        source_key=SOURCE_KEY,
        source_last_modified_utc=source_last_modified_utc,
    )
    print(f"Flattened {len(rows)} rows")
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
        "source_key": SOURCE_KEY,
        "source_last_modified_utc": source_last_modified_utc,
        "destination_key": DESTINATION_KEY,
        "quarantine_key": quarantine_output_key,
        "input_row_count": input_row_count,
        "output_row_count": len(rows),
        "quarantine_row_count": dq_metrics["quarantine_rows"],
        "warning_count": dq_metrics["warning_count"],
        "error_count": dq_metrics["error_count"],
        "dropped_missing_game_id": dq_metrics["dropped_missing_game_id"],
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
