from __future__ import annotations

import json
import subprocess
import urllib.request

from pipelines.athena.transform.gold.athena_view_helpers import (
    AthenaClient,
    CROSS_BACKEND_SUPPORTED_VIEW_NAMES,
    DEFERRED_VIEW_NAMES,
    RETIRED_VIEW_NAMES,
    load_settings,
)


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
        raise RuntimeError("No Databricks SQL warehouse is available for Phase 5 parity checks.")
    first = warehouses[0]
    return str(first["id"])


def _dbx_query(host: str, token: str, warehouse_id: str, sql: str) -> tuple[list[str], list[list[str]]]:
    payload = json.dumps(
        {
            "statement": sql,
            "warehouse_id": warehouse_id,
            "catalog": "nba_analytics",
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


def main() -> None:
    settings = load_settings()
    athena = AthenaClient(settings)

    profile = "workspace-oauth"
    host = _get_databricks_host(profile)
    token = _get_databricks_token(profile)
    warehouse_id = _get_warehouse_id(profile)

    mismatches: list[tuple[str, object, object]] = []

    _, athena_view_rows = _athena_query(
        athena,
        f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = '{settings.database}'
          AND table_type = 'VIEW'
          AND table_name LIKE 'vw_%'
        ORDER BY table_name
        """,
    )
    athena_views = [row[0] for row in athena_view_rows]
    _, dbx_view_rows = _dbx_query(
        host,
        token,
        warehouse_id,
        """
        SELECT table_name
        FROM nba_analytics.information_schema.tables
        WHERE table_schema = 'gold'
          AND table_type = 'VIEW'
          AND table_name LIKE 'vw_%'
        ORDER BY table_name
        """,
    )
    dbx_views = [row[0] for row in dbx_view_rows]
    if athena_views != dbx_views:
        mismatches.append(("inventory", athena_views, dbx_views))

    print("ATHENA_VIEWS", athena_views)
    print("DBX_VIEWS", dbx_views)

    for view_name in CROSS_BACKEND_SUPPORTED_VIEW_NAMES:
        _, athena_schema_rows = _athena_query(
            athena,
            f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = '{settings.database}'
              AND table_name = '{view_name}'
            ORDER BY ordinal_position
            """,
        )
        athena_columns = [row[0] for row in athena_schema_rows]
        _, dbx_schema_rows = _dbx_query(
            host,
            token,
            warehouse_id,
            f"""
            SELECT column_name
            FROM nba_analytics.information_schema.columns
            WHERE table_schema = 'gold'
              AND table_name = '{view_name}'
            ORDER BY ordinal_position
            """,
        )
        dbx_columns = [row[0] for row in dbx_schema_rows]
        if [column.lower() for column in athena_columns] != [column.lower() for column in dbx_columns]:
            mismatches.append((f"{view_name}.schema", athena_columns, dbx_columns))

        _, athena_count_rows = _athena_query(athena, f'SELECT COUNT(*) AS row_count FROM "{view_name}"')
        _, dbx_count_rows = _dbx_query(
            host,
            token,
            warehouse_id,
            f'SELECT COUNT(*) AS row_count FROM nba_analytics.gold.`{view_name}`',
        )
        athena_count = int(athena_count_rows[0][0])
        dbx_count = int(dbx_count_rows[0][0])
        if athena_count != dbx_count:
            mismatches.append((f"{view_name}.count", athena_count, dbx_count))
        print("VIEW", view_name, "cols", len(athena_columns), "rows", athena_count)

    sample_queries = {
        "vw_player_season_boxscore_advanced": """
            SELECT player_id, season_year, season_type, ROUND(pie, 6) AS pie
            FROM {view_ref}
            WHERE season_year = '2024-25' AND season_type = 'regular_season' AND games_played > 0
            ORDER BY pie DESC, player_id
            LIMIT 3
        """,
        "vw_team_season_boxscore_advanced": """
            SELECT team_id, season_year, season_type, ROUND(offensive_rating, 4) AS offensive_rating, ROUND(defensive_rating, 4) AS defensive_rating
            FROM {view_ref}
            WHERE season_year = '2024-25' AND season_type = 'regular_season'
            ORDER BY wins DESC, team
            LIMIT 3
        """,
    }

    for view_name, template in sample_queries.items():
        athena_headers, athena_rows = _athena_query(athena, template.format(view_ref=f'"{view_name}"'))
        dbx_headers, dbx_rows = _dbx_query(
            host,
            token,
            warehouse_id,
            template.format(view_ref=f'nba_analytics.gold.`{view_name}`'),
        )
        athena_tuples = [tuple(row) for row in athena_rows]
        dbx_tuples = [tuple(row) for row in dbx_rows]
        if athena_headers != dbx_headers or athena_tuples != dbx_tuples:
            mismatches.append(
                (
                    f"{view_name}.sample",
                    {"headers": athena_headers, "rows": athena_tuples},
                    {"headers": dbx_headers, "rows": dbx_tuples},
                )
            )
        print("SAMPLE", view_name, athena_tuples)

    for view_name in DEFERRED_VIEW_NAMES + RETIRED_VIEW_NAMES:
        present = view_name in athena_views
        print("DEFERRED_PRESENT", view_name, present)
        if present:
            mismatches.append((f"{view_name}.deferred", False, True))

    print("MISMATCH_COUNT", len(mismatches))
    if mismatches:
        for mismatch in mismatches[:10]:
            print("MISMATCH", mismatch[0])
            print(mismatch[1])
            print(mismatch[2])
            print("---")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
