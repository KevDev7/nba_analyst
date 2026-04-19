from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timezone
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


BUCKET = "nba-analytics-lakehouse-dev"

ROOT_TABLE_KEYS: dict[str, str] = {
    "bbr_player_index": "silver/bbr_player_index.parquet",
    "bbr_player_awards": "silver/bbr_player_awards.parquet",
    "bbr_player_profile": "silver/bbr_player_profile.parquet",
    "bbr_player_profile_label_inventory": "silver/bbr_player_profile_label_inventory.parquet",
    "boxscore_game": "silver/boxscore_game.parquet",
    "boxscore_game_official": "silver/boxscore_game_official.parquet",
    "boxscore_player_game": "silver/boxscore_player_game.parquet",
    "boxscore_team_game": "silver/boxscore_team_game.parquet",
    "boxscore_team_period": "silver/boxscore_team_period.parquet",
    "player_identity_bridge_bbr_nba": "silver/player_identity_bridge_bbr_nba.parquet",
    "player_identity_bridge_bbr_nba_ambiguous": "silver/player_identity_bridge_bbr_nba_ambiguous.parquet",
    "player_identity_bridge_bbr_nba_unmatched_bbr": "silver/player_identity_bridge_bbr_nba_unmatched_bbr.parquet",
    "player_identity_bridge_bbr_nba_unmatched_nba": "silver/player_identity_bridge_bbr_nba_unmatched_nba.parquet",
    "player_movement": "silver/player_movement.parquet",
    "players": "silver/players.parquet",
    "schedule": "silver/scheduleLeagueV2_1.parquet",
    "team_histories": "silver/team_histories.parquet",
}

PARTITIONED_PREFIXES: dict[str, str] = {
    "playbyplay_events": "silver/playbyplay/",
    "on_court_state": "silver/on_court_state/",
    "possessions": "silver/possessions/",
    "pbpstats_event_projection_v1": "silver/pbpstats_event_projection_v1/",
    "pbpstats_event_context_v1": "silver/pbpstats_event_context_v1/",
}

ORDER_BY: dict[str, list[str]] = {
    "bbr_player_index": ["basketball_reference_player_id"],
    "bbr_player_awards": ["basketball_reference_player_id", "season_label", "award_family", "team_tier"],
    "bbr_player_profile": ["basketball_reference_player_id"],
    "bbr_player_profile_label_inventory": ["basketball_reference_player_id", "paragraph_index", "label_name_normalized"],
    "boxscore_game": ["gameId"],
    "boxscore_game_official": ["gameId", "personId"],
    "boxscore_player_game": ["gameId", "teamId", "personId"],
    "boxscore_team_game": ["gameId", "teamId"],
    "boxscore_team_period": ["gameId", "teamId", "team_side", "period_number"],
    "player_identity_bridge_bbr_nba": ["nba_person_id", "basketball_reference_player_id"],
    "player_identity_bridge_bbr_nba_ambiguous": ["nba_person_id"],
    "player_identity_bridge_bbr_nba_unmatched_bbr": ["basketball_reference_player_id"],
    "player_identity_bridge_bbr_nba_unmatched_nba": ["nba_person_id"],
    "player_movement": ["TRANSACTION_DATE", "PLAYER_ID", "TEAM_ID", "Additional_Sort"],
    "players": ["personId"],
    "schedule": ["gameId"],
    "team_histories": ["teamId", "seasonFounded"],
    "playbyplay_events": ["gameId", "actionNumber"],
    "on_court_state": ["gameId", "period", "stint_id"],
    "possessions": ["gameId", "possessionNumber"],
    "pbpstats_event_projection_v1": ["game_id", "event_num"],
    "pbpstats_event_context_v1": ["game_id", "event_num"],
}

METADATA_COLUMNS = {
    "record_source",
    "created_at_utc",
    "updated_at_utc",
    "meta_version",
    "meta_code",
    "meta_request",
    "meta_time",
    "_meta_pipeline_run_id",
    "_meta_ingested_at_utc",
    "_meta_source_system",
    "_meta_source_key",
    "_meta_source_last_modified_utc",
    "_meta_schema_version",
}


def _normalize_decimal(value: str) -> str:
    normalized = Decimal(value)
    return format(normalized.normalize(), "f") if normalized != normalized.to_integral() else format(
        normalized.quantize(Decimal("1")), "f"
    )


def _try_normalize_decimal(value: str) -> str | None:
    if not value:
        return None
    try:
        return _normalize_decimal(value)
    except InvalidOperation:
        return None


def _normalize_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return _normalize_decimal(str(value))

    text = str(value).strip()
    if text == "":
        return None
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered
    if _timestampish(text):
        candidate = text
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None
        if parsed is not None:
            normalized = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            return normalized.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    decimal_value = _try_normalize_decimal(text)
    if decimal_value is not None:
        return decimal_value
    return text


def _normalize_rows(rows: list[list[object]]) -> list[tuple[object, ...]]:
    return [tuple(_normalize_value(value) for value in row) for row in rows]


def _sort_scalar(value: object) -> tuple[int, object]:
    if value is None:
        return (3, "")
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (int, float)):
        return (0, Decimal(str(value)))
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return (1, normalized.astimezone(timezone.utc).isoformat(timespec="milliseconds"))
    if isinstance(value, date):
        return (1, value.isoformat())

    text = str(value).strip()
    if text == "":
        return (3, "")

    decimal_value = _try_normalize_decimal(text)
    if decimal_value is not None:
        return (0, Decimal(decimal_value))

    if _timestampish(text):
        candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None
        if parsed is not None:
            normalized = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            return (1, normalized.astimezone(timezone.utc).isoformat(timespec="milliseconds"))

    return (2, text)


def _sort_key_for_row(row: dict[str, Any], order_columns: list[str]) -> tuple[object, ...]:
    values: list[object] = []
    for column in order_columns:
        values.append(_sort_scalar(row.get(column)))
    return tuple(values)


def _s3_rows_from_root(s3_client: Any, key: str) -> tuple[list[str], list[list[object]]]:
    payload = s3_client.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    table = pq.read_table(BytesIO(payload))
    rows = table.to_pylist()
    return list(table.column_names), [list(row.values()) for row in rows]


def _s3_rows_from_partitioned_prefix(
    s3_client: Any,
    prefix: str,
    order_columns: list[str],
) -> tuple[list[str], list[list[object]]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    candidate_rows: list[dict[str, Any]] = []
    headers: list[str] | None = None

    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in sorted(page.get("Contents", []), key=lambda item: item["Key"]):
            key = obj["Key"]
            if not key.endswith(".parquet"):
                continue
            payload = s3_client.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            table = pq.read_table(BytesIO(payload))
            headers = headers or list(table.column_names)
            candidate_rows.extend(table.to_pylist())
            if len(candidate_rows) >= 200:
                break
        if len(candidate_rows) >= 200:
            break

    if headers is None:
        return [], []

    candidate_rows.sort(key=lambda row: _sort_key_for_row(row, order_columns))
    top_rows = candidate_rows[:10]
    return headers, [[row.get(column) for column in headers] for row in top_rows]


def _s3_table(name: str, s3_client: Any) -> tuple[list[str], list[list[object]]]:
    if name in ROOT_TABLE_KEYS:
        headers, rows = _s3_rows_from_root(s3_client, ROOT_TABLE_KEYS[name])
        row_dicts = [dict(zip(headers, row)) for row in rows]
        row_dicts.sort(key=lambda row: _sort_key_for_row(row, ORDER_BY[name]))
        top_rows = row_dicts[:10]
        return headers, [[row.get(column) for column in headers] for row in top_rows]
    if name in PARTITIONED_PREFIXES:
        return _s3_rows_from_partitioned_prefix(s3_client, PARTITIONED_PREFIXES[name], ORDER_BY[name])
    raise KeyError(name)


def _dbx_schema(name: str) -> list[str]:
    rows = rows_query(
        DEFAULT_WAREHOUSE_ID,
        f"""
        SELECT column_name
        FROM legacy_gold.information_schema.columns
        WHERE table_schema = 'silver' AND table_name = '{name}'
        ORDER BY ordinal_position
        """,
    )
    return [str(row[0]) for row in rows]


def _shared_order_columns(name: str, athena_columns: list[str], dbx_columns: list[str]) -> list[str]:
    athena_set = {column.lower(): column for column in athena_columns}
    dbx_set = {column.lower(): column for column in dbx_columns}
    shared: list[str] = []
    for column in ORDER_BY[name]:
        if column.lower() in athena_set and column.lower() in dbx_set:
            shared.append(dbx_set[column.lower()])
    if shared:
        return shared
    for candidate in dbx_columns[:3]:
        if candidate.lower() in athena_set:
            shared.append(candidate)
    return shared


def _dbx_top10(name: str, columns: list[str], order_columns: list[str]) -> list[list[object]]:
    order_by = ", ".join(order_columns)
    select_columns = ", ".join(f"`{column}`" for column in columns)
    return rows_query(
        DEFAULT_WAREHOUSE_ID,
        f"SELECT {select_columns} FROM legacy_gold.silver.`{name}` ORDER BY {order_by} LIMIT 10",
    )


def _timestampish(value: object) -> bool:
    if value is None:
        return False
    text = str(value)
    return ("-" in text and ":" in text) or text.endswith("Z")


def _row_diff_columns(
    columns: list[str],
    athena_rows: list[tuple[object, ...]],
    dbx_rows: list[tuple[object, ...]],
) -> list[str]:
    differing: list[str] = []
    row_count = min(len(athena_rows), len(dbx_rows))
    for row_index in range(row_count):
        for col_index, column in enumerate(columns):
            if athena_rows[row_index][col_index] != dbx_rows[row_index][col_index]:
                differing.append(column)
    seen: list[str] = []
    for column in differing:
        if column not in seen:
            seen.append(column)
    return seen


def _classify_schema_mismatch(athena_columns: list[str], dbx_columns: list[str]) -> str:
    if {column.lower() for column in athena_columns} == {column.lower() for column in dbx_columns}:
        return "schema_or_order"
    return "business_value"


def _classify_row_mismatch(
    columns: list[str],
    athena_rows: list[tuple[object, ...]],
    dbx_rows: list[tuple[object, ...]],
) -> tuple[str, list[str]]:
    differing_columns = _row_diff_columns(columns, athena_rows, dbx_rows)
    if differing_columns and all(column in METADATA_COLUMNS for column in differing_columns):
        return "metadata_only", differing_columns

    timestamp_only = True
    for row_index in range(min(len(athena_rows), len(dbx_rows))):
        for col_index, column in enumerate(columns):
            if athena_rows[row_index][col_index] == dbx_rows[row_index][col_index]:
                continue
            if column not in METADATA_COLUMNS:
                timestamp_only = False
                break
            if not (_timestampish(athena_rows[row_index][col_index]) and _timestampish(dbx_rows[row_index][col_index])):
                timestamp_only = False
                break
        if not timestamp_only:
            break
    if differing_columns and timestamp_only:
        return "metadata_only", differing_columns
    return "business_value", differing_columns


def main() -> None:
    s3_client = boto3.client("s3")
    inventory = list(ROOT_TABLE_KEYS) + list(PARTITIONED_PREFIXES)
    mismatches: list[dict[str, object]] = []
    category_counts = {
        "metadata_only": 0,
        "schema_or_order": 0,
        "business_value": 0,
        "error": 0,
    }
    category_tables = {
        "metadata_only": [],
        "schema_or_order": [],
        "business_value": [],
        "error": [],
    }

    for name in inventory:
        try:
            athena_columns, athena_rows = _s3_table(name, s3_client)
            dbx_columns = _dbx_schema(name)
        except Exception as exc:  # noqa: BLE001
            print("ERROR", name, exc)
            mismatches.append({"table": name, "kind": "error", "category": "error", "detail": str(exc)})
            category_counts["error"] += 1
            category_tables["error"].append(name)
            continue
        if [column.lower() for column in athena_columns] != [column.lower() for column in dbx_columns]:
            print("SCHEMA_MISMATCH", name)
            category = _classify_schema_mismatch(athena_columns, dbx_columns)
            mismatches.append(
                {
                    "table": name,
                    "kind": "schema",
                    "category": category,
                    "detail": {"athena": athena_columns, "databricks": dbx_columns},
                }
            )
            category_counts[category] += 1
            category_tables[category].append(name)
            continue

        try:
            order_columns = _shared_order_columns(name, athena_columns, dbx_columns)
            athena_headers = [column for column in athena_columns]
            athena_dict_rows = [dict(zip(athena_headers, row)) for row in athena_rows]
            athena_dict_rows.sort(key=lambda row: _sort_key_for_row(row, order_columns))
            athena_projected = [[row.get(column) for column in athena_headers] for row in athena_dict_rows[:10]]
            dbx_rows = _dbx_top10(name, dbx_columns, order_columns)
            athena_normalized = _normalize_rows(athena_projected)
            dbx_normalized = _normalize_rows(dbx_rows)
        except Exception as exc:  # noqa: BLE001
            print("ERROR", name, exc)
            mismatches.append({"table": name, "kind": "error", "category": "error", "detail": str(exc)})
            category_counts["error"] += 1
            category_tables["error"].append(name)
            continue

        if athena_normalized != dbx_normalized:
            print("ROW_MISMATCH", name)
            category, differing_columns = _classify_row_mismatch(dbx_columns, athena_normalized, dbx_normalized)
            mismatches.append(
                {
                    "table": name,
                    "kind": "rows",
                    "category": category,
                    "differing_columns": differing_columns,
                    "detail": {"athena": athena_normalized, "databricks": dbx_normalized},
                }
            )
            category_counts[category] += 1
            category_tables[category].append(name)
        else:
            print("MATCH", name, len(athena_normalized))

    print("CATEGORY_COUNTS", json.dumps(category_counts, sort_keys=True))
    print("CATEGORY_TABLES", json.dumps(category_tables, sort_keys=True))
    print("MISMATCH_COUNT", len(mismatches))
    if mismatches:
        print("MISMATCH_DETAILS", json.dumps(mismatches, default=str))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
