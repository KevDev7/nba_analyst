#!/usr/bin/env python3
"""Validate Athena silver pbpstats_event_projection_v1 against direct reprojection."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError


REPO_ROOT = Path(__file__).resolve().parents[4]
SILVER_TRANSFORM_DIR = REPO_ROOT / "pipelines" / "athena" / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_pbpstats_event_projection_v1 as projection
import build_silver_playbyplay_events as pbp_silver
from pbpstats_projection_common import InvalidNumberOfStartersException


S3_BUCKET = "nba-analytics-lakehouse-dev"
DEFAULT_GAME_SET_CSV = REPO_ROOT / "pipelines" / "athena" / "metadata" / "pbpstats_phase3_validation_games.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-set-csv", type=Path, default=DEFAULT_GAME_SET_CSV)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--game-id", dest="game_ids", action="append", default=[])
    parser.add_argument("--max-examples", type=int, default=20)
    parser.add_argument("--json-output", type=Path, default=None)
    return parser.parse_args()


def load_validation_games(csv_path: Path, explicit_game_ids: list[str], limit: int | None) -> list[str]:
    with csv_path.open(newline="", encoding="utf-8") as infile:
        rows = list(csv.DictReader(infile))
    game_ids = [row["game_id"] for row in rows]
    if explicit_game_ids:
        explicit_set = set(explicit_game_ids)
        game_ids = [game_id for game_id in game_ids if game_id in explicit_set]
    if limit is not None:
        game_ids = game_ids[:limit]
    return game_ids


def read_actual_rows(s3_client, game_id: str) -> list[dict[str, Any]]:
    key = f"silver/pbpstats_event_projection_v1/game_id={game_id}.parquet"
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload = response["Body"].read()
    table = pq.read_table(pa.BufferReader(payload))
    return table.to_pylist()


def normalize_value(value: Any) -> Any:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def compare_game(s3_client, game_id: str, max_examples: int) -> dict[str, Any]:
    payload = pbp_silver.read_json_payload(s3_client, f"raw/cdn/playbyplay/game_id={game_id}.json")
    try:
        _, expected_rows = projection.project_payload_to_rows(
            payload,
            source_file=f"raw/cdn/playbyplay/game_id={game_id}.json",
            source_last_modified_utc=None,
            fallback_game_id=game_id,
        )
    except (projection.ProjectionFailure, InvalidNumberOfStartersException, RuntimeError, ValueError, AttributeError) as exc:
        try:
            actual_rows = read_actual_rows(s3_client, game_id)
            actual_row_count = len(actual_rows)
        except ClientError:
            actual_row_count = 0
        return {
            "game_id": game_id,
            "status": "projection_failure",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "actual_row_count": actual_row_count,
            "expected_row_count": 0,
            "mismatch_count": 0,
            "mismatch_examples": [],
        }
    actual_rows = read_actual_rows(s3_client, game_id)
    actual_index = {row["event_num"]: row for row in actual_rows}
    expected_index = {row["event_num"]: row for row in expected_rows}
    mismatches: list[dict[str, Any]] = []
    for event_num in sorted(set(actual_index) | set(expected_index)):
        actual_row = actual_index.get(event_num)
        expected_row = expected_index.get(event_num)
        if actual_row is None or expected_row is None:
            mismatches.append(
                {
                    "event_num": event_num,
                    "field": "__row_presence__",
                    "actual": None if actual_row is None else "present",
                    "expected": None if expected_row is None else "present",
                }
            )
            continue
        for column in projection.PROJECTION_COLUMNS:
            actual_value = normalize_value(actual_row.get(column))
            expected_value = normalize_value(expected_row.get(column))
            if actual_value != expected_value:
                mismatches.append(
                    {
                        "event_num": event_num,
                        "field": column,
                        "actual": actual_value,
                        "expected": expected_value,
                    }
                )
                if len(mismatches) >= max_examples:
                    break
        if len(mismatches) >= max_examples:
            break
    return {
        "game_id": game_id,
        "status": "compared",
        "actual_row_count": len(actual_rows),
        "expected_row_count": len(expected_rows),
        "mismatch_count": len(mismatches),
        "mismatch_examples": mismatches,
    }


def main() -> None:
    args = parse_args()
    game_ids = load_validation_games(args.game_set_csv, args.game_ids, args.limit)
    s3_client = boto3.client("s3")
    sample_results = [compare_game(s3_client, game_id, args.max_examples) for game_id in game_ids]
    duplicate_key_count = 0
    missing_event_num_count = 0
    for result in sample_results:
        if result.get("status") != "compared":
            continue
        actual_rows = read_actual_rows(s3_client, result["game_id"])
        event_nums = [row.get("event_num") for row in actual_rows]
        duplicate_key_count += sum(count - 1 for count in Counter(event_nums).values() if count > 1)
        missing_event_num_count += sum(1 for event_num in event_nums if event_num is None)

    failures: list[str] = []
    if duplicate_key_count > 0:
        failures.append(f"duplicate_key_count={duplicate_key_count}")
    if missing_event_num_count > 0:
        failures.append(f"missing_event_num_count={missing_event_num_count}")
    mismatch_games = [
        result["game_id"]
        for result in sample_results
        if result.get("status") == "compared" and result["mismatch_count"] > 0
    ]
    if mismatch_games:
        failures.append(f"sample_parity_mismatch_games={','.join(mismatch_games)}")

    summary = {
        "table_name": projection.TABLE_NAME,
        "validated_game_count": len(game_ids),
        "duplicate_key_count": duplicate_key_count,
        "missing_event_num_count": missing_event_num_count,
        "sample_results": sample_results,
        "failures": failures,
    }
    if args.json_output is not None:
        args.json_output.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
