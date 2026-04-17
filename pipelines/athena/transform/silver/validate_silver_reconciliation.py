"""
Cross-table Wave 2 reconciliation checks for Silver tables.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_player_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/scheduleLeagueV2_1.parquet

Writes:
  s3://nba-analytics-lakehouse-dev/silver/_audit/silver_reconciliation/... (json + parquet)
  s3://nba-analytics-lakehouse-dev/silver/_audit/silver_reconciliation/..._details.json
"""

from __future__ import annotations

import io
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow.parquet as pq
from silver_pipeline_helpers import run_date, write_audit_artifacts

S3_BUCKET = "nba-analytics-lakehouse-dev"
TABLE_NAME = "silver_reconciliation"

BOXSCORE_GAME_KEY = "silver/boxscore_game.parquet"
BOXSCORE_PLAYER_GAME_KEY = "silver/boxscore_player_game.parquet"
BOXSCORE_TEAM_GAME_KEY = "silver/boxscore_team_game.parquet"
SCHEDULE_KEY = "silver/scheduleLeagueV2_1.parquet"


def read_table(s3_client, key: str, columns: list[str]):
    """Read selected columns from an S3 parquet object."""
    obj = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    return pq.read_table(io.BytesIO(obj["Body"].read()), columns=columns)


def write_details_json(
    s3_client,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    details: dict[str, Any],
) -> str:
    """Write detailed reconciliation payload (samples + counters)."""
    key = (
        f"silver/_audit/{TABLE_NAME}/"
        f"run_date={run_date(ingested_at_utc)}/{pipeline_run_id}_details.json"
    )
    body = json.dumps(details, default=str, sort_keys=True).encode("utf-8")
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
    return key


def main() -> None:
    """Run cross-table reconciliation checks and emit audit artifacts."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"silver_recon_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    game_table = read_table(s3_client, BOXSCORE_GAME_KEY, ["gameId"])
    player_table = read_table(s3_client, BOXSCORE_PLAYER_GAME_KEY, ["gameId", "personId"])
    team_table = read_table(s3_client, BOXSCORE_TEAM_GAME_KEY, ["gameId", "team_side", "teamId"])
    schedule_table = read_table(s3_client, SCHEDULE_KEY, ["gameId"])

    boxscore_game_ids = {x for x in game_table["gameId"].to_pylist() if x is not None and str(x).strip() != ""}
    player_game_ids = {x for x in player_table["gameId"].to_pylist() if x is not None and str(x).strip() != ""}
    team_game_ids = {x for x in team_table["gameId"].to_pylist() if x is not None and str(x).strip() != ""}
    schedule_game_ids = {x for x in schedule_table["gameId"].to_pylist() if x is not None and str(x).strip() != ""}

    missing_player_refs = sorted(player_game_ids - boxscore_game_ids)
    missing_team_refs = sorted(team_game_ids - boxscore_game_ids)

    team_row_count_by_game: Counter[str] = Counter()
    team_side_set_by_game: dict[str, set[str]] = {}
    for game_id, team_side in zip(team_table["gameId"].to_pylist(), team_table["team_side"].to_pylist()):
        if game_id is None or str(game_id).strip() == "":
            continue
        game_id = str(game_id)
        side = None if team_side is None else str(team_side)
        team_row_count_by_game[game_id] += 1
        side_set = team_side_set_by_game.get(game_id)
        if side_set is None:
            side_set = set()
            team_side_set_by_game[game_id] = side_set
        if side is not None:
            side_set.add(side)

    invalid_team_grain_games = []
    for game_id, row_count in team_row_count_by_game.items():
        sides = team_side_set_by_game.get(game_id) or set()
        if row_count != 2 or sides != {"home", "away"}:
            invalid_team_grain_games.append(game_id)
    invalid_team_grain_games.sort()

    overlap_count = len(schedule_game_ids & boxscore_game_ids)
    schedule_only_count = len(schedule_game_ids - boxscore_game_ids)
    boxscore_only_count = len(boxscore_game_ids - schedule_game_ids)
    schedule_overlap_ratio = (
        (overlap_count / len(schedule_game_ids)) if schedule_game_ids else None
    )

    warning_reason_counts: Counter[str] = Counter()
    warning_count = 0
    if schedule_overlap_ratio is not None and schedule_overlap_ratio < 0.5:
        warning_reason_counts["low_schedule_overlap_ratio"] += 1
        warning_count += 1
    if schedule_only_count > 0:
        warning_reason_counts["schedule_only_games_present"] += 1
        warning_count += 1
    if boxscore_only_count > 0:
        warning_reason_counts["boxscore_only_games_present"] += 1
        warning_count += 1

    error_reason_counts: Counter[str] = Counter()
    error_reason_counts["player_missing_boxscore_game_ref"] += len(missing_player_refs)
    error_reason_counts["team_missing_boxscore_game_ref"] += len(missing_team_refs)
    error_reason_counts["invalid_team_game_grain"] += len(invalid_team_grain_games)
    error_count = (
        len(missing_player_refs)
        + len(missing_team_refs)
        + len(invalid_team_grain_games)
    )

    run_status = "success"
    if error_count > 0:
        run_status = "failed"
    elif warning_count > 0:
        run_status = "success_with_warnings"

    details_payload = {
        "pipeline_run_id": pipeline_run_id,
        "ingested_at_utc": ingested_at_utc.isoformat().replace("+00:00", "Z"),
        "missing_player_ref_game_ids_sample": missing_player_refs[:100],
        "missing_team_ref_game_ids_sample": missing_team_refs[:100],
        "invalid_team_grain_game_ids_sample": invalid_team_grain_games[:100],
        "schedule_only_game_ids_sample": sorted(list(schedule_game_ids - boxscore_game_ids))[:100],
        "boxscore_only_game_ids_sample": sorted(list(boxscore_game_ids - schedule_game_ids))[:100],
    }
    details_key = write_details_json(
        s3_client,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        details=details_payload,
    )

    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": run_status,
        "ingested_at_utc": ingested_at_utc,
        "boxscore_game_key": BOXSCORE_GAME_KEY,
        "boxscore_player_game_key": BOXSCORE_PLAYER_GAME_KEY,
        "boxscore_team_game_key": BOXSCORE_TEAM_GAME_KEY,
        "schedule_key": SCHEDULE_KEY,
        "boxscore_game_count": len(boxscore_game_ids),
        "player_distinct_game_count": len(player_game_ids),
        "team_distinct_game_count": len(team_game_ids),
        "schedule_game_count": len(schedule_game_ids),
        "missing_player_ref_game_count": len(missing_player_refs),
        "missing_team_ref_game_count": len(missing_team_refs),
        "invalid_team_grain_game_count": len(invalid_team_grain_games),
        "schedule_overlap_count": overlap_count,
        "schedule_only_count": schedule_only_count,
        "boxscore_only_count": boxscore_only_count,
        "schedule_overlap_ratio": schedule_overlap_ratio,
        "warning_count": warning_count,
        "error_count": error_count,
        "details_key": details_key,
        "error_reason_counts": json.dumps(dict(error_reason_counts), sort_keys=True),
        "warning_reason_counts": json.dumps(dict(warning_reason_counts), sort_keys=True),
    }
    audit_json_key, audit_parquet_key = write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )
    print(f"Wrote reconciliation details JSON: s3://{S3_BUCKET}/{details_key}")
    print(f"Wrote reconciliation audit JSON: s3://{S3_BUCKET}/{audit_json_key}")
    print(f"Wrote reconciliation audit parquet: s3://{S3_BUCKET}/{audit_parquet_key}")

    if error_count > 0:
        raise RuntimeError(
            "Reconciliation failed: "
            f"missing_player_refs={len(missing_player_refs)}, "
            f"missing_team_refs={len(missing_team_refs)}, "
            f"invalid_team_grain_games={len(invalid_team_grain_games)}"
        )


if __name__ == "__main__":
    main()
