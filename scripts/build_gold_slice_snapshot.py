#!/usr/bin/env python3
# Purpose:
# Build the semantic_gold DuckDB snapshot used by the live semantic-layer slices.
#
# Uses:
# - Athena semantic_gold tables
# - local DuckDB as the development snapshot target
#
# Produces:
# - fixtures/duckdb/gold_slice.duckdb with the live semantic_gold snapshot
#
# Next:
# - load_gold_snapshot.py

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import boto3
import duckdb
import pyarrow.types as patypes

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines.athena.transform.semantic_gold.contracts import SEMANTIC_GOLD_TABLE_SPECS

DUCKDB_DIR = ROOT / "fixtures" / "duckdb"
DUCKDB_PATH = DUCKDB_DIR / "gold_slice.duckdb"

DEFAULT_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
DEFAULT_DATABASE = os.getenv("ATHENA_DATABASE", "semantic_gold")
DEFAULT_OUTPUT = os.getenv("ATHENA_OUTPUT_LOCATION", "s3://nba-analytics-lakehouse-dev/athena-results/")
DEFAULT_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
DEFAULT_CATALOG = os.getenv("ATHENA_CATALOG", "AwsDataCatalog")

SOURCE_QUERIES = {
    "player": "SELECT * FROM player ORDER BY player_name ASC",
    "team": "SELECT * FROM team ORDER BY team_name ASC",
    "game": "SELECT * FROM game ORDER BY game_date DESC, game_id ASC",
    "player_game": "SELECT * FROM player_game ORDER BY game_date DESC, person_id ASC",
    "team_game": "SELECT * FROM team_game ORDER BY game_date DESC, team_id ASC",
}

TABLE_SCHEMAS = {spec.table_name: spec.schema for spec in SEMANTIC_GOLD_TABLE_SPECS}


def run_athena_query(
    *,
    sql: str,
    region: str,
    database: str,
    output_location: str,
    workgroup: str,
    catalog: str,
) -> str:
    athena = boto3.client("athena", region_name=region)
    s3 = boto3.client("s3", region_name=region)
    query_execution_id = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database, "Catalog": catalog},
        ResultConfiguration={"OutputLocation": output_location},
        WorkGroup=workgroup,
    )["QueryExecutionId"]

    for _ in range(240):
        execution = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = execution["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            result_location = execution["QueryExecution"]["ResultConfiguration"]["OutputLocation"]
            parsed = urlparse(result_location)
            body = s3.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))["Body"].read()
            return body.decode("utf-8")
        if state in {"FAILED", "CANCELLED"}:
            reason = execution["QueryExecution"]["Status"].get("StateChangeReason", state)
            raise RuntimeError(f"Athena query failed: {reason}")
        time.sleep(0.5)
    raise TimeoutError("Athena query timed out.")


def write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def count_csv_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def build_snapshot(
    *,
    region: str,
    database: str,
    output_location: str,
    workgroup: str,
    catalog: str,
    force: bool,
) -> Path:
    DUCKDB_DIR.mkdir(parents=True, exist_ok=True)
    if DUCKDB_PATH.exists() and not force:
        return DUCKDB_PATH

    with tempfile.TemporaryDirectory(prefix="semantic-gold-slice-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        csv_paths: dict[str, Path] = {}
        row_counts: dict[str, int] = {}

        for table_name, sql in SOURCE_QUERIES.items():
            csv_text = run_athena_query(
                sql=sql,
                region=region,
                database=database,
                output_location=output_location,
                workgroup=workgroup,
                catalog=catalog,
            )
            csv_path = temp_dir / f"{table_name}.csv"
            write_csv(csv_path, csv_text)
            csv_paths[table_name] = csv_path
            row_counts[table_name] = count_csv_rows(csv_path)

        db_path = DUCKDB_PATH
        if db_path.exists():
            db_path.unlink()
        conn = duckdb.connect(str(db_path))
        try:
            for table_name, csv_path in csv_paths.items():
                conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                raw_table_name = f"_raw_{table_name}"
                conn.execute(f'DROP TABLE IF EXISTS "{raw_table_name}"')
                conn.execute(
                    f'CREATE TEMP TABLE "{raw_table_name}" AS SELECT * FROM read_csv_auto(?, HEADER=TRUE, ALL_VARCHAR=TRUE)',
                    [str(csv_path)],
                )
                conn.execute(
                    f'CREATE TABLE "{table_name}" AS SELECT {typed_projection(table_name)} FROM "{raw_table_name}"'
                )
            conn.execute("DROP TABLE IF EXISTS snapshot_meta")
            conn.execute(
                """
                CREATE TABLE snapshot_meta AS
                SELECT
                  ? AS snapshot_id,
                  ? AS source_database,
                  ? AS source_backend,
                  CURRENT_TIMESTAMP AS built_at_utc
                """,
                [uuid.uuid4().hex, database, "athena"],
            )
        finally:
            conn.close()

        print(f"Built snapshot at {db_path}")
        for table_name, row_count in row_counts.items():
            print(f"{table_name}: {row_count} rows")
        return db_path


def typed_projection(table_name: str) -> str:
    schema = TABLE_SCHEMAS[table_name]
    projection = []
    for field in schema:
        quoted_name = f'"{field.name}"'
        duckdb_type = duckdb_type_for_field(field)
        if duckdb_type == "VARCHAR":
            projection.append(f"{quoted_name} AS {quoted_name}")
        else:
            projection.append(
                f"TRY_CAST({quoted_name} AS {duckdb_type}) AS {quoted_name}"
            )
    return ", ".join(projection)


def duckdb_type_for_field(field) -> str:
    field_type = field.type
    if patypes.is_int64(field_type):
        return "BIGINT"
    if patypes.is_float64(field_type):
        return "DOUBLE"
    if patypes.is_date32(field_type):
        return "DATE"
    if patypes.is_timestamp(field_type):
        return "TIMESTAMP"
    if patypes.is_boolean(field_type):
        return "BOOLEAN"
    return "VARCHAR"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a semantic_gold DuckDB snapshot from Athena.")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--output-location", default=DEFAULT_OUTPUT)
    parser.add_argument("--workgroup", default=DEFAULT_WORKGROUP)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    build_snapshot(
        region=args.region,
        database=args.database,
        output_location=args.output_location,
        workgroup=args.workgroup,
        catalog=args.catalog,
        force=args.force,
    )


if __name__ == "__main__":
    main()
