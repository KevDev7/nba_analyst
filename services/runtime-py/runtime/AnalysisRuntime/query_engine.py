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

from dataclasses import dataclass
import hashlib
from pathlib import Path
import time
from typing import Dict, List, Optional

import duckdb

from scripts.load_gold_snapshot import DB_PATH, load_database


def ensure_database() -> Path:
    # Make sure the local DuckDB snapshot exists before trying to query it.
    if not DB_PATH.exists():
        load_database()
    return DB_PATH


@dataclass(frozen=True)
class QueryExecutionResult:
    rows: List[Dict[str, object]]
    sql_hash: str
    returned_row_count: int
    row_limit_requested: Optional[int]
    row_limit_enforced: bool
    truncated: bool
    execution_ms: int


def run_sql_result(sql: str, *, row_limit: Optional[int] = None) -> QueryExecutionResult:
    _validate_single_statement(sql)
    db_path = ensure_database()
    started = time.perf_counter()
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        raw_rows = cursor.fetchmany(row_limit + 1) if row_limit is not None else cursor.fetchall()
        truncated = bool(row_limit is not None and len(raw_rows) > row_limit)
        if truncated:
            raw_rows = raw_rows[:row_limit]
        rows = [dict(zip(columns, row)) for row in raw_rows]
        execution_ms = int((time.perf_counter() - started) * 1000)
        return QueryExecutionResult(
            rows=rows,
            sql_hash=_sql_hash(sql),
            returned_row_count=len(rows),
            row_limit_requested=row_limit,
            row_limit_enforced=row_limit is not None,
            truncated=truncated,
            execution_ms=execution_ms,
        )
    finally:
        conn.close()


def run_sql(sql: str) -> List[Dict[str, object]]:
    # Backward-compatible helper for direct tests and debug utilities.
    return run_sql_result(sql).rows


def _sql_hash(sql: str) -> str:
    return "sha256:" + hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _validate_single_statement(sql: str) -> None:
    if _has_non_trailing_statement_separator(sql):
        raise ValueError("SQL execution accepts exactly one statement.")


def _has_non_trailing_statement_separator(sql: str) -> bool:
    in_single = False
    in_double = False
    index = 0
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if char == "'" and not in_double:
            if in_single and next_char == "'":
                index += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ";" and not in_single and not in_double:
            remainder = sql[index + 1 :].strip()
            return bool(remainder)
        index += 1
    return False
