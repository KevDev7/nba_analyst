#!/usr/bin/env python3
# Purpose:
# Ensure the live gold-derived DuckDB snapshot exists and matches the current semantic_gold contract.
#
# Uses:
# - fixtures/duckdb/gold_slice.duckdb
# - build_gold_slice_snapshot.py when the snapshot is missing or stale
#
# Produces:
# - a ready-to-query local DuckDB snapshot for the CLI and runtime
#
# Next:
# - apps/cli/main.py

from __future__ import annotations

from pathlib import Path

import duckdb

try:
    from .build_gold_slice_snapshot import DUCKDB_DIR, DUCKDB_PATH, build_snapshot
except ImportError:  # pragma: no cover - direct script execution
    from build_gold_slice_snapshot import DUCKDB_DIR, DUCKDB_PATH, build_snapshot
from pipelines.athena.transform.semantic_gold.contracts import SEMANTIC_GOLD_TABLE_SPECS


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_COLUMNS_BY_TABLE = {
    spec.table_name: {field.name for field in spec.schema}
    for spec in SEMANTIC_GOLD_TABLE_SPECS
}
REQUIRED_TABLES = set(REQUIRED_COLUMNS_BY_TABLE) | {"snapshot_meta"}


def _snapshot_is_current(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
            if not REQUIRED_TABLES.issubset(tables):
                return False
            for table_name, required_columns in REQUIRED_COLUMNS_BY_TABLE.items():
                current_columns = {
                    row[0] for row in conn.execute(f'DESCRIBE "{table_name}"').fetchall()
                }
                if current_columns != required_columns:
                    return False
            return True
        finally:
            conn.close()
    except duckdb.Error:
        return False


def load_database(force: bool = False) -> Path:
    DUCKDB_DIR.mkdir(parents=True, exist_ok=True)
    if force or not _snapshot_is_current(DUCKDB_PATH):
        build_snapshot(
            region="us-east-1",
            database="semantic_gold",
            output_location="s3://nba-analytics-lakehouse-dev/athena-results/",
            workgroup="primary",
            catalog="AwsDataCatalog",
            force=True,
        )
    return DUCKDB_PATH


DB_PATH = DUCKDB_PATH


if __name__ == "__main__":
    print(load_database())
