from __future__ import annotations

import json
import subprocess
import urllib.request
from decimal import Decimal, InvalidOperation

from pipelines.athena.transform.gold.athena_view_helpers import (
    AthenaClient,
    CROSS_BACKEND_SUPPORTED_VIEW_NAMES,
    SUPPORTED_VIEW_NAMES,
    load_settings,
)


GOLD_TABLE_ORDER_BY: dict[str, str] = {
    "dim_date": "date_sk",
    "dim_game": "game_id",
    "dim_team": "team_sk",
    "dim_player": "player_sk",
    "fct_player_game": "fct_player_game_sk",
    "fct_team_game": "fct_team_game_sk",
    "fct_player_game_shot_type_source": "fct_player_game_shot_type_source_sk",
    "agg_player_season": "agg_player_season_sk",
    "agg_team_season": "agg_team_season_sk",
    "player_season_percentiles": "player_season_percentiles_sk",
    "team_season_percentiles": "team_season_percentiles_sk",
    "player_award_history": "player_award_history_sk",
}

GOLD_VIEW_ORDER_BY: dict[str, str] = {
    "vw_player_season_boxscore_advanced": "player_id, season_year, season_type",
    "vw_player_game_shot_type_source": "player_id, game_date, shot_type",
    "vw_team_season_boxscore_advanced": "team_id, season_year, season_type",
}


def _run_command(args: list[str]) -> dict[str, object] | list[dict[str, object]]:
    return json.loads(subprocess.check_output(args, text=True))


def _get_databricks_host(profile: str) -> str:
    payload = _run_command(["databricks", "auth", "env", "--profile", profile, "-o", "json"])
    return str(payload["env"]["DATABRICKS_HOST"])


def _get_databricks_token(profile: str) -> str:
    payload = _run_command(["databricks", "auth", "token", "--profile", profile, "-o", "json"])
    return str(payload["access_token"])


def _get_warehouse_id(profile: str) -> str:
    warehouses = _run_command(["databricks", "warehouses", "list", "--profile", profile, "-o", "json"])
    if not warehouses:
        raise RuntimeError("No Databricks SQL warehouse is available for gold spot checks.")
    first = warehouses[0]
    return str(first["id"])


def _dbx_query(host: str, token: str, warehouse_id: str, sql: str) -> tuple[list[str], list[list[object]]]:
    payload = json.dumps(
        {
            "statement": sql,
            "warehouse_id": warehouse_id,
            "catalog": "legacy_gold",
            "schema": "gold",
            "wait_timeout": "50s",
        }
    ).encode()
    request = urllib.request.Request(
        host + "/api/2.0/sql/statements/",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request) as response:
        body = json.loads(response.read().decode())
    columns = [column["name"] for column in body.get("manifest", {}).get("schema", {}).get("columns", [])]
    rows = body.get("result", {}).get("data_array", [])
    return columns, rows


def _athena_query(athena: AthenaClient, sql: str) -> tuple[list[str], list[list[str | None]]]:
    headers, rows = athena.execute(sql)
    values = [[row.get(header) for header in headers] for row in rows]
    return headers, values


def _normalize_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return _normalize_decimal(str(value))

    text = str(value).strip()
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered
    decimal_value = _try_normalize_decimal(text)
    if decimal_value is not None:
        return decimal_value
    return text


def _try_normalize_decimal(value: str) -> str | None:
    if not value:
        return None
    try:
        return _normalize_decimal(value)
    except InvalidOperation:
        return None


def _normalize_decimal(value: str) -> str:
    normalized = Decimal(value)
    return format(normalized.normalize(), "f") if normalized != normalized.to_integral() else format(normalized.quantize(Decimal("1")), "f")


def _normalize_rows(rows: list[list[object]]) -> list[tuple[object, ...]]:
    return [tuple(_normalize_value(value) for value in row) for row in rows]


def _fetch_athena_columns(athena: AthenaClient, database: str, object_name: str) -> list[str]:
    _, rows = _athena_query(
        athena,
        f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = '{database}'
          AND table_name = '{object_name}'
        ORDER BY ordinal_position
        """,
    )
    return [str(row[0]) for row in rows]


def _fetch_dbx_columns(host: str, token: str, warehouse_id: str, object_name: str) -> list[str]:
    _, rows = _dbx_query(
        host,
        token,
        warehouse_id,
        f"""
        SELECT column_name
        FROM legacy_gold.information_schema.columns
        WHERE table_schema = 'gold'
          AND table_name = '{object_name}'
        ORDER BY ordinal_position
        """,
    )
    return [str(row[0]) for row in rows]


def _quote_athena_columns(columns: list[str]) -> str:
    return ", ".join(f'"{column}"' for column in columns)


def _quote_dbx_columns(columns: list[str]) -> str:
    return ", ".join(f"`{column}`" for column in columns)


def _check_object(
    athena: AthenaClient,
    database: str,
    host: str,
    token: str,
    warehouse_id: str,
    object_name: str,
    order_by: str,
) -> tuple[str, object | None]:
    athena_columns = _fetch_athena_columns(athena, database, object_name)
    dbx_columns = _fetch_dbx_columns(host, token, warehouse_id, object_name)
    if [column.lower() for column in athena_columns] != [column.lower() for column in dbx_columns]:
        return (
            "SCHEMA_MISMATCH",
            {
                "athena": athena_columns,
                "databricks": dbx_columns,
            },
        )

    athena_headers, athena_rows = _athena_query(
        athena,
        f'SELECT {_quote_athena_columns(athena_columns)} FROM "{object_name}" ORDER BY {order_by} LIMIT 10',
    )
    dbx_headers, dbx_rows = _dbx_query(
        host,
        token,
        warehouse_id,
        f"SELECT {_quote_dbx_columns(dbx_columns)} FROM legacy_gold.gold.`{object_name}` ORDER BY {order_by} LIMIT 10",
    )

    if [header.lower() for header in athena_headers] != [header.lower() for header in dbx_headers]:
        return (
            "HEADER_MISMATCH",
            {
                "athena": athena_headers,
                "databricks": dbx_headers,
            },
        )

    athena_normalized = _normalize_rows(athena_rows)
    dbx_normalized = _normalize_rows(dbx_rows)
    if athena_normalized != dbx_normalized:
        return (
            "ROW_MISMATCH",
            {
                "athena": athena_normalized,
                "databricks": dbx_normalized,
            },
        )

    return ("MATCH", len(athena_normalized))


def main() -> None:
    settings = load_settings()
    athena = AthenaClient(settings)

    profile = "workspace-oauth"
    host = _get_databricks_host(profile)
    token = _get_databricks_token(profile)
    warehouse_id = _get_warehouse_id(profile)

    mismatches: list[tuple[str, object]] = []

    for object_name, order_by in GOLD_TABLE_ORDER_BY.items():
        status, payload = _check_object(
            athena,
            settings.database,
            host,
            token,
            warehouse_id,
            object_name,
            order_by,
        )
        print(status, object_name, payload)
        if status != "MATCH":
            mismatches.append((object_name, payload))

    for object_name in CROSS_BACKEND_SUPPORTED_VIEW_NAMES:
        status, payload = _check_object(
            athena,
            settings.database,
            host,
            token,
            warehouse_id,
            object_name,
            GOLD_VIEW_ORDER_BY[object_name],
        )
        print(status, object_name, payload)
        if status != "MATCH":
            mismatches.append((object_name, payload))

    for object_name in set(SUPPORTED_VIEW_NAMES) - set(CROSS_BACKEND_SUPPORTED_VIEW_NAMES):
        athena_headers, athena_rows = _athena_query(
            athena,
            f'SELECT * FROM "{object_name}" ORDER BY {GOLD_VIEW_ORDER_BY[object_name]} LIMIT 10',
        )
        print("ATHENA_ONLY", object_name, len(athena_headers), len(athena_rows))

    print("MISMATCH_COUNT", len(mismatches))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
