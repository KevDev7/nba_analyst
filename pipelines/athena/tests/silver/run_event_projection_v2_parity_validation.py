#!/usr/bin/env python3
"""Validate raw-first event_projection_v2 against live pbpstats_event_projection_v1."""

from __future__ import annotations

import argparse
import json
import re
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

import build_silver_event_projection_v2 as projection_v2
import build_silver_playbyplay_events as pbp_silver


S3_BUCKET = "nba-analytics-lakehouse-dev"
RAW_PREFIX = "raw/cdn/playbyplay/"
V1_PREFIX = "silver/pbpstats_event_projection_v1/"
GAME_ID_RE = re.compile(r"game_id=([0-9]+)\.(?:json|parquet)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Cap compared success-set games.")
    parser.add_argument("--failure-limit", type=int, default=None, help="Cap v1-failure coverage attempts.")
    parser.add_argument("--game-id", dest="game_ids", action="append", default=[], help="Restrict to specific game ids.")
    parser.add_argument("--max-examples", type=int, default=20)
    parser.add_argument("--json-output", type=Path, default=None)
    return parser.parse_args()


def list_game_ids(s3_client, prefix: str) -> set[str]:
    paginator = s3_client.get_paginator("list_objects_v2")
    game_ids: set[str] = set()
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            match = GAME_ID_RE.search(key)
            game_id = match.group(1).zfill(10) if match is not None else None
            if game_id is not None:
                game_ids.add(game_id)
    return game_ids


def read_actual_rows(s3_client, game_id: str) -> list[dict[str, Any]]:
    key = f"{V1_PREFIX}game_id={game_id}.parquet"
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload = response["Body"].read()
    table = pq.read_table(pa.BufferReader(payload))
    rows = table.to_pylist()
    return sorted(rows, key=lambda row: (row["event_order"], row["event_num"]))


def normalize_value(value: Any) -> Any:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def compare_success_game(s3_client, game_id: str, max_examples: int) -> dict[str, Any]:
    payload = pbp_silver.read_json_payload(s3_client, f"{RAW_PREFIX}game_id={game_id}.json")
    boxscore_context = pbp_silver.load_boxscore_context_for_game(s3_client, game_id)
    try:
        _, expected_rows = projection_v2.project_payload_to_rows(
            payload,
            source_file=f"{RAW_PREFIX}game_id={game_id}.json",
            source_last_modified_utc=None,
            fallback_game_id=game_id,
            boxscore_context=boxscore_context,
        )
    except (projection_v2.ProjectionFailure, RuntimeError, ValueError, AttributeError) as exc:
        return {
            "game_id": game_id,
            "status": "projection_failure",
            "actual_row_count": None,
            "expected_row_count": None,
            "mismatch_count": None,
            "top_differing_columns": [],
            "mismatch_examples": [],
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    expected_rows = sorted(expected_rows, key=lambda row: (row["event_order"], row["event_num"]))
    actual_rows = read_actual_rows(s3_client, game_id)

    mismatches: list[dict[str, Any]] = []
    differing_columns: Counter[str] = Counter()
    for actual_row, expected_row in zip(actual_rows, expected_rows):
        for column in projection_v2.PROJECTION_COLUMNS:
            actual_value = normalize_value(actual_row.get(column))
            expected_value = normalize_value(expected_row.get(column))
            if actual_value != expected_value:
                differing_columns[column] += 1
                if len(mismatches) < max_examples:
                    mismatches.append(
                        {
                            "event_num": actual_row.get("event_num"),
                            "field": column,
                            "actual": actual_value,
                            "expected": expected_value,
                        }
                    )
    if len(actual_rows) != len(expected_rows) and len(mismatches) < max_examples:
        mismatches.append(
            {
                "event_num": None,
                "field": "__row_count__",
                "actual": len(actual_rows),
                "expected": len(expected_rows),
            }
        )

    return {
        "game_id": game_id,
        "status": "compared",
        "actual_row_count": len(actual_rows),
        "expected_row_count": len(expected_rows),
        "mismatch_count": sum(differing_columns.values()),
        "top_differing_columns": differing_columns.most_common(10),
        "mismatch_examples": mismatches,
    }


def assess_v1_failure_game(s3_client, game_id: str) -> dict[str, Any]:
    payload = pbp_silver.read_json_payload(s3_client, f"{RAW_PREFIX}game_id={game_id}.json")
    boxscore_context = pbp_silver.load_boxscore_context_for_game(s3_client, game_id)
    try:
        _, rows = projection_v2.project_payload_to_rows(
            payload,
            source_file=f"{RAW_PREFIX}game_id={game_id}.json",
            source_last_modified_utc=None,
            fallback_game_id=game_id,
            boxscore_context=boxscore_context,
        )
    except (projection_v2.ProjectionFailure, RuntimeError, ValueError, AttributeError) as exc:
        return {
            "game_id": game_id,
            "status": "projection_failure",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    return {
        "game_id": game_id,
        "status": "built",
        "row_count": len(rows),
    }


def main() -> None:
    args = parse_args()
    selected_game_ids = {game_id.zfill(10) for game_id in args.game_ids}
    s3_client = boto3.client("s3")

    raw_game_ids = list_game_ids(s3_client, RAW_PREFIX)
    v1_game_ids = list_game_ids(s3_client, V1_PREFIX)

    success_game_ids = sorted(raw_game_ids & v1_game_ids)
    v1_failure_game_ids = sorted(raw_game_ids - v1_game_ids)

    if selected_game_ids:
        success_game_ids = [game_id for game_id in success_game_ids if game_id in selected_game_ids]
        v1_failure_game_ids = [game_id for game_id in v1_failure_game_ids if game_id in selected_game_ids]

    if args.limit is not None:
        success_game_ids = success_game_ids[: args.limit]
    if args.failure_limit is not None:
        v1_failure_game_ids = v1_failure_game_ids[: args.failure_limit]

    success_results = [compare_success_game(s3_client, game_id, args.max_examples) for game_id in success_game_ids]
    failure_results = [assess_v1_failure_game(s3_client, game_id) for game_id in v1_failure_game_ids]

    mismatch_games = [
        result
        for result in success_results
        if result.get("status") != "compared" or (result.get("mismatch_count") or 0) > 0
    ]
    success_column_counts: Counter[str] = Counter()
    for result in success_results:
        for column, count in result.get("top_differing_columns", []):
            success_column_counts[column] += count

    failure_status_counts = Counter(result["status"] for result in failure_results)
    failure_error_counts = Counter(
        result.get("error_type")
        for result in failure_results
        if result.get("status") == "projection_failure"
    )

    summary = {
        "table_name": projection_v2.TABLE_NAME,
        "raw_game_count": len(raw_game_ids),
        "v1_success_game_count": len(raw_game_ids & v1_game_ids),
        "v1_failure_game_count": len(raw_game_ids - v1_game_ids),
        "compared_success_game_count": len(success_game_ids),
        "compared_success_games_with_mismatches": len(mismatch_games),
        "top_differing_columns": success_column_counts.most_common(20),
        "coverage_checked_failure_game_count": len(v1_failure_game_ids),
        "failure_status_counts": dict(failure_status_counts),
        "failure_error_counts": dict(failure_error_counts),
        "success_results": success_results,
        "failure_results": failure_results,
    }
    if args.json_output is not None:
        args.json_output.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    if mismatch_games:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
