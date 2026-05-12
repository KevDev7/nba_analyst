from __future__ import annotations

from datetime import datetime
from typing import Any

from .contracts import META_SCHEMA_VERSION, META_SOURCE_SYSTEM, SOURCE_KEY


def null_if_empty(value: Any) -> Any:
    """Convert empty/blank strings to None; keep other values unchanged."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def to_int_or_none(value: Any) -> int | None:
    """Convert value to int when present."""
    value = null_if_empty(value)
    if value is None:
        return None
    return int(value)


def parse_transaction_datetime(value: Any) -> datetime | None:
    """Parse TRANSACTION_DATE in ISO-like format, e.g. 2026-02-28T00:00:00."""
    value = null_if_empty(value)
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def build_rows(
    payload: dict[str, Any],
    source_last_modified_utc: datetime | None,
) -> list[dict[str, Any]]:
    """Build row list with the exact required columns."""
    movement = payload.get("NBA_Player_Movement") or {}
    source_rows = movement.get("rows") or []

    rows: list[dict[str, Any]] = []
    for item in source_rows:
        rows.append(
            {
                "Transaction_Type": null_if_empty(item.get("Transaction_Type")),
                "TRANSACTION_DATE": parse_transaction_datetime(item.get("TRANSACTION_DATE")),
                "TRANSACTION_DESCRIPTION": null_if_empty(item.get("TRANSACTION_DESCRIPTION")),
                "TEAM_ID": to_int_or_none(item.get("TEAM_ID")),
                "TEAM_SLUG": null_if_empty(item.get("TEAM_SLUG")),
                "PLAYER_ID": to_int_or_none(item.get("PLAYER_ID")),
                "PLAYER_SLUG": null_if_empty(item.get("PLAYER_SLUG")),
                "Additional_Sort": to_int_or_none(item.get("Additional_Sort")),
                "GroupSort": null_if_empty(item.get("GroupSort")),
                "_meta_source_key": SOURCE_KEY,
                "_meta_source_last_modified_utc": source_last_modified_utc,
            }
        )
    return rows


def add_metadata_columns(
    rows: list[dict[str, Any]],
    pipeline_run_id: str,
    ingested_at_utc: datetime,
) -> None:
    """Attach standardized metadata contract columns to each row."""
    for row in rows:
        row["_meta_pipeline_run_id"] = pipeline_run_id
        row["_meta_ingested_at_utc"] = ingested_at_utc
        row["_meta_source_system"] = META_SOURCE_SYSTEM
        row["_meta_schema_version"] = META_SCHEMA_VERSION
