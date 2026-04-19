#!/usr/bin/env python3
"""
Run Phase 0 silver/playbyplay parity checks between Athena-side S3 parquet files
and Databricks SQL.

This intentionally uses the S3-backed Athena silver parquet objects directly
because the live Athena catalog does not currently register `silver/playbyplay`
as an external table.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path
import sys
from typing import Any

import boto3
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from reference.databricks.jobs.sql_warehouse_utils import DEFAULT_WAREHOUSE_ID, rows_query

DEFAULT_GAME_SET_CSV = (
    REPO_ROOT / "pipelines" / "athena" / "metadata" / "playbyplay_phase0_validation_games.csv"
)

BUCKET = "nba-analytics-lakehouse-dev"
S3_PREFIX = "silver/playbyplay/"
DATABRICKS_TABLE = "legacy_gold.silver.playbyplay_events"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game-set-csv",
        type=Path,
        default=DEFAULT_GAME_SET_CSV,
        help="CSV of validation game_ids.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only validate the first N games from the CSV.",
    )
    parser.add_argument(
        "--game-id",
        dest="game_ids",
        action="append",
        default=[],
        help="Optional explicit game_id to validate. Repeatable.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional path for JSON summary output.",
    )
    return parser.parse_args()


def load_validation_games(csv_path: Path, explicit_game_ids: list[str], limit: int | None) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as infile:
        rows = list(csv.DictReader(infile))

    if explicit_game_ids:
        explicit_set = set(explicit_game_ids)
        rows = [row for row in rows if row["game_id"] in explicit_set]
        found_ids = {row["game_id"] for row in rows}
        missing_ids = [game_id for game_id in explicit_game_ids if game_id not in found_ids]
        if missing_ids:
            raise SystemExit(f"Game ids not found in {csv_path}: {', '.join(missing_ids)}")

    if limit is not None:
        rows = rows[:limit]

    return rows


def s3_rows_for_game(s3_client: Any, game_id: str) -> list[dict[str, Any]]:
    key = f"{S3_PREFIX}game_id={game_id}.parquet"
    payload = s3_client.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    table = pq.read_table(BytesIO(payload), columns=["gameId", "actionNumber", "actionType"])
    return table.to_pylist()


def s3_schema_columns(game_id: str) -> list[str]:
    s3_client = boto3.client("s3")
    key = f"{S3_PREFIX}game_id={game_id}.parquet"
    payload = s3_client.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    table = pq.read_table(BytesIO(payload))
    return list(table.column_names)


def s3_metrics(games: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    s3_client = boto3.client("s3")
    metrics: dict[str, dict[str, Any]] = {}
    for game in games:
        game_id = game["game_id"]
        rows = s3_rows_for_game(s3_client, game_id)
        action_numbers = [row.get("actionNumber") for row in rows]
        action_types = Counter((row.get("actionType") or "__NULL__") for row in rows)
        metrics[game_id] = {
            "row_count": len(rows),
            "distinct_action_numbers": len(set(action_numbers)),
            "duplicate_action_numbers": len(rows) - len(set(action_numbers)),
            "action_type_counts": dict(sorted(action_types.items())),
        }
    return metrics


def databricks_metrics(game_ids: list[str]) -> dict[str, dict[str, Any]]:
    in_list = ",".join(f"'{game_id}'" for game_id in game_ids)

    base_rows = rows_query(
        DEFAULT_WAREHOUSE_ID,
        f"""
        SELECT
          gameId,
          COUNT(*) AS row_count,
          COUNT(DISTINCT actionNumber) AS distinct_action_numbers
        FROM {DATABRICKS_TABLE}
        WHERE gameId IN ({in_list})
        GROUP BY gameId
        ORDER BY gameId
        """,
    )
    action_rows = rows_query(
        DEFAULT_WAREHOUSE_ID,
        f"""
        SELECT
          gameId,
          COALESCE(actionType, '__NULL__') AS action_type,
          COUNT(*) AS row_count
        FROM {DATABRICKS_TABLE}
        WHERE gameId IN ({in_list})
        GROUP BY gameId, COALESCE(actionType, '__NULL__')
        ORDER BY gameId, action_type
        """,
    )

    metrics: dict[str, dict[str, Any]] = {}
    for game_id, row_count, distinct_action_numbers in base_rows:
        row_count_int = int(row_count)
        distinct_int = int(distinct_action_numbers)
        metrics[game_id] = {
            "row_count": row_count_int,
            "distinct_action_numbers": distinct_int,
            "duplicate_action_numbers": row_count_int - distinct_int,
            "action_type_counts": {},
        }

    for game_id, action_type, row_count in action_rows:
        metrics.setdefault(
            game_id,
            {
                "row_count": 0,
                "distinct_action_numbers": 0,
                "duplicate_action_numbers": 0,
                "action_type_counts": {},
            },
        )["action_type_counts"][action_type] = int(row_count)

    for metric in metrics.values():
        metric["action_type_counts"] = dict(sorted(metric["action_type_counts"].items()))
    return metrics


def databricks_schema_columns() -> list[str]:
    rows = rows_query(
        DEFAULT_WAREHOUSE_ID,
        """
        SELECT column_name
        FROM legacy_gold.information_schema.columns
        WHERE table_schema = 'silver' AND table_name = 'playbyplay_events'
        ORDER BY ordinal_position
        """,
    )
    return [row[0] for row in rows]


def compare_metrics(
    games: list[dict[str, str]],
    s3_by_game: dict[str, dict[str, Any]],
    dbx_by_game: dict[str, dict[str, Any]],
    athena_schema_columns: list[str],
    databricks_schema: list[str],
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    summary = defaultdict(int)
    per_game: list[dict[str, Any]] = []

    if athena_schema_columns != databricks_schema:
        summary["schema_columns"] += 1
        mismatches.append(
            {
                "field": "schema_columns",
                "athena_only": sorted(set(athena_schema_columns) - set(databricks_schema)),
                "databricks_only": sorted(set(databricks_schema) - set(athena_schema_columns)),
            }
        )

    for game in games:
        game_id = game["game_id"]
        s3_metric = s3_by_game.get(game_id)
        dbx_metric = dbx_by_game.get(game_id)
        game_result = {
            **game,
            "athena_s3_present": s3_metric is not None,
            "databricks_present": dbx_metric is not None,
            "mismatches": [],
        }

        if s3_metric is None or dbx_metric is None:
            summary["missing_side"] += 1
            mismatches.append(
                {
                    "game_id": game_id,
                    "field": "__missing_game__",
                    "athena_s3": None if s3_metric is None else "present",
                    "databricks": None if dbx_metric is None else "present",
                }
            )
            per_game.append(game_result)
            continue

        for field in ("row_count", "distinct_action_numbers", "duplicate_action_numbers"):
            if s3_metric[field] != dbx_metric[field]:
                summary[field] += 1
                detail = {
                    "game_id": game_id,
                    "field": field,
                    "athena_s3": s3_metric[field],
                    "databricks": dbx_metric[field],
                }
                mismatches.append(detail)
                game_result["mismatches"].append(detail)

        if s3_metric["action_type_counts"] != dbx_metric["action_type_counts"]:
            summary["action_type_counts"] += 1
            differing_types = sorted(
                set(s3_metric["action_type_counts"]) | set(dbx_metric["action_type_counts"])
            )
            diff_preview = []
            for action_type in differing_types:
                athena_count = s3_metric["action_type_counts"].get(action_type, 0)
                dbx_count = dbx_metric["action_type_counts"].get(action_type, 0)
                if athena_count != dbx_count:
                    diff_preview.append(
                        {
                            "action_type": action_type,
                            "athena_s3": athena_count,
                            "databricks": dbx_count,
                        }
                    )
            detail = {
                "game_id": game_id,
                "field": "action_type_counts",
                "differences": diff_preview,
            }
            mismatches.append(detail)
            game_result["mismatches"].append(detail)

        per_game.append(game_result)

    return {
        "games_checked": len(games),
        "mismatch_summary": dict(summary),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "per_game": per_game,
        "athena_schema_columns": athena_schema_columns,
        "databricks_schema_columns": databricks_schema,
        "athena_s3_metrics": s3_by_game,
        "databricks_metrics": dbx_by_game,
    }


def main() -> None:
    args = parse_args()
    games = load_validation_games(args.game_set_csv, args.game_ids, args.limit)
    if not games:
        raise SystemExit("No validation games selected.")

    s3_by_game = s3_metrics(games)
    dbx_by_game = databricks_metrics([game["game_id"] for game in games])
    athena_schema = s3_schema_columns(games[0]["game_id"])
    databricks_schema = databricks_schema_columns()
    summary = compare_metrics(games, s3_by_game, dbx_by_game, athena_schema, databricks_schema)

    print(
        json.dumps(
            {
                "games_checked": summary["games_checked"],
                "mismatch_count": summary["mismatch_count"],
                "mismatch_summary": summary["mismatch_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )

    if summary["mismatches"]:
        print("\nMismatches:")
        for mismatch in summary["mismatches"]:
            print(json.dumps(mismatch, sort_keys=True))
    else:
        print("\nAll Phase 0 parity checks matched.")

    if args.json_output is not None:
        args.json_output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"\nWrote JSON summary to {args.json_output}")


if __name__ == "__main__":
    main()
