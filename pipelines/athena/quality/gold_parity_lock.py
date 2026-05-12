from __future__ import annotations

import argparse
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

try:
    from pipelines.athena.quality.quality_manifest import (
        DEFAULT_BUCKET,
        KNOWN_GRAIN_COLUMNS,
        load_registry,
        new_run_id,
        quality_result_key,
        today_run_date,
    )
    from pipelines.athena.quality.registration import refresh_quality_athena_tables
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings
except ModuleNotFoundError:
    import sys

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.athena.quality.quality_manifest import (
        DEFAULT_BUCKET,
        KNOWN_GRAIN_COLUMNS,
        load_registry,
        new_run_id,
        quality_result_key,
        today_run_date,
    )
    from pipelines.athena.quality.registration import refresh_quality_athena_tables
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings


GOLD_LAYERS = {"legacy_gold", "semantic_gold"}


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def schema_for_layer(layer: str) -> str:
    if layer not in GOLD_LAYERS:
        raise ValueError(f"Unsupported gold parity layer: {layer}")
    return layer


def grain_distinct_expression(columns: list[str]) -> str:
    if len(columns) == 1:
        return f"CAST({quote_ident(columns[0])} AS VARCHAR)"
    parts = [f"COALESCE(CAST({quote_ident(column)} AS VARCHAR), '<NULL>')" for column in columns]
    return " || '|' || ".join(parts)


def build_grain_query(*, schema_name: str, table_name: str, grain_columns: list[str]) -> str:
    distinct_expr = grain_distinct_expression(grain_columns)
    return f"""
SELECT
  COUNT(*) AS total_rows,
  COUNT(DISTINCT {distinct_expr}) AS distinct_rows
FROM {quote_ident(schema_name)}.{quote_ident(table_name)}
"""


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def gold_registry_artifacts(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        artifact
        for artifact in registry["artifacts"]
        if artifact["layer"] in GOLD_LAYERS and artifact["artifact_type"] in {"table", "view"}
    ]


def fetch_columns(client: AthenaClient, *, schema_name: str, table_name: str) -> list[dict[str, Any]]:
    _, rows = client.execute(
        f"""
        SELECT column_name, data_type, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = '{schema_name}'
          AND table_name = '{table_name}'
        ORDER BY ordinal_position
        """
    )
    return rows


def run_gold_parity_lock(
    *,
    bucket: str = DEFAULT_BUCKET,
    run_id: str | None = None,
    run_date: str | None = None,
    write_s3: bool = True,
    register_athena: bool = True,
    quality_database: str = "quality",
) -> dict[str, Any]:
    os.environ.pop("AWS_PROFILE", None)
    resolved_run_id = run_id or new_run_id()
    resolved_run_date = run_date or today_run_date()
    registry = load_registry()
    settings = load_settings()
    client = AthenaClient(settings)

    result_rows: list[dict[str, Any]] = []
    schema_rows: list[dict[str, Any]] = []

    for artifact in gold_registry_artifacts(registry):
        schema_name = schema_for_layer(artifact["layer"])
        table_name = artifact["name"]
        artifact_id = artifact["id"]
        status = "ok"
        error_message = None
        row_count = None
        distinct_rows = None
        duplicate_rows = None
        columns: list[dict[str, Any]] = []

        try:
            columns = fetch_columns(client, schema_name=schema_name, table_name=table_name)
            if not columns:
                status = "missing_schema"
            else:
                _, count_rows = client.execute(
                    f"SELECT COUNT(*) AS row_count FROM {quote_ident(schema_name)}.{quote_ident(table_name)}"
                )
                row_count = to_int(count_rows[0]["row_count"]) if count_rows else None
                grain_columns = KNOWN_GRAIN_COLUMNS.get(artifact_id)
                column_names = {row["column_name"] for row in columns}
                if grain_columns and set(grain_columns) <= column_names:
                    _, grain_rows = client.execute(
                        build_grain_query(
                            schema_name=schema_name,
                            table_name=table_name,
                            grain_columns=grain_columns,
                        )
                    )
                    if grain_rows:
                        distinct_rows = to_int(grain_rows[0]["distinct_rows"])
                        total_rows = to_int(grain_rows[0]["total_rows"])
                        duplicate_rows = (total_rows or 0) - (distinct_rows or 0)
                        if duplicate_rows:
                            status = "grain_duplicates"
                if row_count == 0 and status == "ok":
                    status = "empty"
        except Exception as exc:
            status = "query_error"
            error_message = f"{type(exc).__name__}: {exc}"

        result_rows.append(
            {
                "run_id": resolved_run_id,
                "run_date": resolved_run_date,
                "artifact_id": artifact_id,
                "layer": artifact["layer"],
                "schema_name": schema_name,
                "table_name": table_name,
                "artifact_type": artifact["artifact_type"],
                "row_count": row_count,
                "distinct_grain_rows": distinct_rows,
                "duplicate_grain_rows": duplicate_rows,
                "column_count": len(columns),
                "parity_status": status,
                "error_message": error_message,
            }
        )
        for column in columns:
            schema_rows.append(
                {
                    "run_id": resolved_run_id,
                    "run_date": resolved_run_date,
                    "artifact_id": artifact_id,
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "column_name": column["column_name"],
                    "data_type": column["data_type"],
                    "ordinal_position": column["ordinal_position"],
                }
            )

    summary = {
        "run_id": resolved_run_id,
        "run_date": resolved_run_date,
        "bucket": bucket,
        "checked_artifact_count": len(result_rows),
        "schema_row_count": len(schema_rows),
        "status_counts": {
            status: sum(1 for row in result_rows if row["parity_status"] == status)
            for status in sorted({row["parity_status"] for row in result_rows})
        },
        "failed_artifacts": [
            {
                "artifact_id": row["artifact_id"],
                "schema_name": row["schema_name"],
                "table_name": row["table_name"],
                "parity_status": row["parity_status"],
                "error_message": row["error_message"],
            }
            for row in result_rows
            if row["parity_status"] not in {"ok"}
        ],
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    if write_s3:
        s3_client = boto3.client("s3")
        for dataset, rows in {
            "reconciliation": result_rows,
            "schema_snapshots": schema_rows,
        }.items():
            key = quality_result_key(dataset, "gold_parity_lock", resolved_run_date, resolved_run_id)
            table = pa.Table.from_pylist(rows or [{"_empty": True}])
            buffer = io.BytesIO()
            pq.write_table(table, buffer, compression="snappy")
            buffer.seek(0)
            s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=buffer.getvalue(),
                ContentType="application/octet-stream",
            )
        s3_client.put_object(
            Bucket=bucket,
            Key=(
                "quality/_summaries/reconciliation/gold_parity_lock/"
                f"run_date={resolved_run_date}/{resolved_run_id}.json"
            ),
            Body=json.dumps(summary, indent=2, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )
        if register_athena:
            summary["athena_registration"] = refresh_quality_athena_tables(
                bucket=bucket,
                database=quality_database,
            )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run gold/semantic-gold parity lock checks.")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-date", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quality-database", default="quality")
    parser.add_argument("--skip-athena-registration", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_gold_parity_lock(
        bucket=args.bucket,
        run_id=args.run_id or None,
        run_date=args.run_date or None,
        write_s3=not args.dry_run,
        register_athena=not args.skip_athena_registration,
        quality_database=args.quality_database,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
