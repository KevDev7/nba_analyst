from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.athena.transform.gold.transform_to_dim_date_parquet import build_dim_date_rows


def test_dim_date_sentinel_row_matches_databricks_year_end_contract() -> None:
    rows = build_dim_date_rows({date.min}, {})

    assert len(rows) == 1
    row = rows[0]
    assert row["calendar_date"] == date.min
    assert row["is_year_start"] is True
    assert row["is_year_end"] is None
