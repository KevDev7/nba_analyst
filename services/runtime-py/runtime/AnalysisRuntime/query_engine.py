# Purpose:
# Execute SQL against the gold-first DuckDB snapshot.
#
# Uses:
# - execution plans produced by grounded planning
# - scripts/load_gold_snapshot.py to ensure the local DB exists
#
# Produces:
# - tabular query results for the runtime
#
# Next:
# - runner.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import duckdb

from scripts.load_gold_snapshot import DB_PATH, load_database


def ensure_database() -> Path:
    if not DB_PATH.exists():
        load_database()
    return DB_PATH


def run_sql(sql: str) -> List[Dict[str, object]]:
    db_path = ensure_database()
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()
