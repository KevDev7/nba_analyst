from __future__ import annotations

import argparse
import io
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

try:
    from pipelines.athena.quality.quality_manifest import (
        DEFAULT_BUCKET,
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
        new_run_id,
        quality_result_key,
        today_run_date,
    )
    from pipelines.athena.quality.registration import refresh_quality_athena_tables
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings


RECONCILIATION_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("check_id", pa.string()),
        ("check_group", pa.string()),
        ("source_artifact_id", pa.string()),
        ("target_artifact_id", pa.string()),
        ("source_row_count", pa.int64()),
        ("target_row_count", pa.int64()),
        ("mismatch_count", pa.int64()),
        ("reconciliation_status", pa.string()),
        ("error_message", pa.string()),
    ]
)


@dataclass(frozen=True)
class ReconciliationCheck:
    check_id: str
    check_group: str
    source_artifact_id: str
    target_artifact_id: str
    sql: str


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def table_name(schema_name: str, name: str) -> str:
    return f"{quote_ident(schema_name)}.{quote_ident(name)}"


def count_sql(schema_name: str, name: str, where: str | None = None) -> str:
    predicate = f" WHERE {where}" if where else ""
    return f"SELECT COUNT(*) FROM {table_name(schema_name, name)}{predicate}"


def row_count_check_sql(
    *,
    source_schema: str,
    source_table: str,
    target_schema: str,
    target_table: str,
    source_where: str | None = None,
    target_where: str | None = None,
) -> str:
    source_count = count_sql(source_schema, source_table, source_where)
    target_count = count_sql(target_schema, target_table, target_where)
    return f"""
WITH counts AS (
  SELECT
    ({source_count}) AS source_row_count,
    ({target_count}) AS target_row_count
)
SELECT
  source_row_count,
  target_row_count,
  ABS(source_row_count - target_row_count) AS mismatch_count
FROM counts
"""


def key_set_check_sql(
    *,
    source_schema: str,
    source_table: str,
    target_schema: str,
    target_table: str,
    key_columns: tuple[str, ...],
    source_where: str | None = None,
    target_where: str | None = None,
) -> str:
    source_cols = ", ".join(quote_ident(column) for column in key_columns)
    target_cols = ", ".join(quote_ident(column) for column in key_columns)
    join_condition = " AND ".join(
        f"source.{quote_ident(column)} = target.{quote_ident(column)}"
        for column in key_columns
    )
    missing_condition = " AND ".join(
        f"target.{quote_ident(column)} IS NULL" for column in key_columns
    )
    source_predicate = f"WHERE {source_where}" if source_where else ""
    target_predicate = f"WHERE {target_where}" if target_where else ""
    return f"""
WITH source_keys AS (
  SELECT DISTINCT {source_cols}
  FROM {table_name(source_schema, source_table)}
  {source_predicate}
),
target_keys AS (
  SELECT DISTINCT {target_cols}
  FROM {table_name(target_schema, target_table)}
  {target_predicate}
)
SELECT
  (SELECT COUNT(*) FROM source_keys) AS source_row_count,
  (SELECT COUNT(*) FROM target_keys) AS target_row_count,
  COUNT(*) AS mismatch_count
FROM source_keys AS source
LEFT JOIN target_keys AS target
  ON {join_condition}
WHERE {missing_condition}
"""


def key_set_mapping_check_sql(
    *,
    source_schema: str,
    source_table: str,
    target_schema: str,
    target_table: str,
    key_columns: tuple[tuple[str, str], ...],
    source_where: str | None = None,
    target_where: str | None = None,
) -> str:
    source_cols = ", ".join(
        f"{quote_ident(source_column)} AS {quote_ident(source_column)}"
        for source_column, _target_column in key_columns
    )
    target_cols = ", ".join(
        f"{quote_ident(target_column)} AS {quote_ident(source_column)}"
        for source_column, target_column in key_columns
    )
    join_condition = " AND ".join(
        f"source.{quote_ident(source_column)} = target.{quote_ident(source_column)}"
        for source_column, _target_column in key_columns
    )
    missing_condition = " AND ".join(
        f"target.{quote_ident(source_column)} IS NULL"
        for source_column, _target_column in key_columns
    )
    source_predicate = f"WHERE {source_where}" if source_where else ""
    target_predicate = f"WHERE {target_where}" if target_where else ""
    return f"""
WITH source_keys AS (
  SELECT DISTINCT {source_cols}
  FROM {table_name(source_schema, source_table)}
  {source_predicate}
),
target_keys AS (
  SELECT DISTINCT {target_cols}
  FROM {table_name(target_schema, target_table)}
  {target_predicate}
)
SELECT
  (SELECT COUNT(*) FROM source_keys) AS source_row_count,
  (SELECT COUNT(*) FROM target_keys) AS target_row_count,
  COUNT(*) AS mismatch_count
FROM source_keys AS source
LEFT JOIN target_keys AS target
  ON {join_condition}
WHERE {missing_condition}
"""


SILVER_GOLD_RECONCILIATION_CHECKS = (
    ReconciliationCheck(
        check_id="silver_player_game_to_legacy_fact_row_count",
        check_group="silver_to_legacy_gold",
        source_artifact_id="silver.boxscore_player_game",
        target_artifact_id="legacy_gold.fct_player_game",
        sql=row_count_check_sql(
            source_schema="silver",
            source_table="boxscore_player_game",
            target_schema="legacy_gold",
            target_table="fct_player_game",
        ),
    ),
    ReconciliationCheck(
        check_id="silver_player_game_to_legacy_fact_key_coverage",
        check_group="silver_to_legacy_gold",
        source_artifact_id="silver.boxscore_player_game",
        target_artifact_id="legacy_gold.fct_player_game",
        sql=key_set_mapping_check_sql(
            source_schema="silver",
            source_table="boxscore_player_game",
            target_schema="legacy_gold",
            target_table="fct_player_game",
            key_columns=(("gameId", "game_id"), ("personId", "person_id")),
        ),
    ),
    ReconciliationCheck(
        check_id="silver_team_game_to_legacy_fact_row_count",
        check_group="silver_to_legacy_gold",
        source_artifact_id="silver.boxscore_team_game",
        target_artifact_id="legacy_gold.fct_team_game",
        sql=row_count_check_sql(
            source_schema="silver",
            source_table="boxscore_team_game",
            target_schema="legacy_gold",
            target_table="fct_team_game",
            source_where='"teamId" IS NOT NULL',
            target_where='"team_id" IS NOT NULL',
        ),
    ),
    ReconciliationCheck(
        check_id="silver_team_game_to_legacy_fact_key_coverage",
        check_group="silver_to_legacy_gold",
        source_artifact_id="silver.boxscore_team_game",
        target_artifact_id="legacy_gold.fct_team_game",
        sql=key_set_mapping_check_sql(
            source_schema="silver",
            source_table="boxscore_team_game",
            target_schema="legacy_gold",
            target_table="fct_team_game",
            key_columns=(("gameId", "game_id"), ("teamId", "team_id")),
            source_where='"teamId" IS NOT NULL',
            target_where='"team_id" IS NOT NULL',
        ),
    ),
    ReconciliationCheck(
        check_id="legacy_player_fact_to_player_season_key_coverage",
        check_group="legacy_gold_fact_to_aggregate",
        source_artifact_id="legacy_gold.fct_player_game",
        target_artifact_id="legacy_gold.agg_player_season",
        sql=key_set_check_sql(
            source_schema="legacy_gold",
            source_table="fct_player_game",
            target_schema="legacy_gold",
            target_table="agg_player_season",
            key_columns=("person_id", "season_year", "raw_season_type_code"),
            source_where='"person_id" IS NOT NULL',
        ),
    ),
    ReconciliationCheck(
        check_id="legacy_team_fact_to_team_season_key_coverage",
        check_group="legacy_gold_fact_to_aggregate",
        source_artifact_id="legacy_gold.fct_team_game",
        target_artifact_id="legacy_gold.agg_team_season",
        sql=key_set_check_sql(
            source_schema="legacy_gold",
            source_table="fct_team_game",
            target_schema="legacy_gold",
            target_table="agg_team_season",
            key_columns=("team_id", "season_year", "raw_season_type_code"),
            source_where='"team_id" IS NOT NULL',
        ),
    ),
    ReconciliationCheck(
        check_id="legacy_player_fact_to_semantic_player_game_key_coverage",
        check_group="legacy_gold_to_semantic_gold",
        source_artifact_id="legacy_gold.fct_player_game",
        target_artifact_id="semantic_gold.player_game",
        sql=key_set_check_sql(
            source_schema="legacy_gold",
            source_table="fct_player_game",
            target_schema="semantic_gold",
            target_table="player_game",
            key_columns=("game_id", "person_id"),
            source_where='"person_id" IS NOT NULL',
        ),
    ),
    ReconciliationCheck(
        check_id="legacy_team_fact_to_semantic_team_game_key_coverage",
        check_group="legacy_gold_to_semantic_gold",
        source_artifact_id="legacy_gold.fct_team_game",
        target_artifact_id="semantic_gold.team_game",
        sql=key_set_check_sql(
            source_schema="legacy_gold",
            source_table="fct_team_game",
            target_schema="semantic_gold",
            target_table="team_game",
            key_columns=("game_id", "team_id"),
            source_where='"team_id" IS NOT NULL',
        ),
    ),
)


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def build_reconciliation_row(
    *,
    run_id: str,
    run_date: str,
    check: ReconciliationCheck,
    result: dict[str, Any] | None,
    error_message: str | None = None,
) -> dict[str, Any]:
    source_row_count = to_int(result.get("source_row_count")) if result else None
    target_row_count = to_int(result.get("target_row_count")) if result else None
    mismatch_count = to_int(result.get("mismatch_count")) if result else None
    status = "query_error" if error_message else "ok"
    if not error_message and mismatch_count:
        status = "mismatch"
    return {
        "run_id": run_id,
        "run_date": run_date,
        "check_id": check.check_id,
        "check_group": check.check_group,
        "source_artifact_id": check.source_artifact_id,
        "target_artifact_id": check.target_artifact_id,
        "source_row_count": source_row_count,
        "target_row_count": target_row_count,
        "mismatch_count": mismatch_count,
        "reconciliation_status": status,
        "error_message": error_message,
    }


def write_parquet_rows(s3_client, *, bucket: str, key: str, rows: list[dict[str, Any]]) -> None:
    table = pa.Table.from_pylist(rows, schema=RECONCILIATION_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )


def run_silver_gold_reconciliation(
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
    client = AthenaClient(load_settings())

    rows: list[dict[str, Any]] = []
    for check in SILVER_GOLD_RECONCILIATION_CHECKS:
        try:
            _, result_rows = client.execute(check.sql)
            rows.append(
                build_reconciliation_row(
                    run_id=resolved_run_id,
                    run_date=resolved_run_date,
                    check=check,
                    result=result_rows[0] if result_rows else {},
                )
            )
        except Exception as exc:
            rows.append(
                build_reconciliation_row(
                    run_id=resolved_run_id,
                    run_date=resolved_run_date,
                    check=check,
                    result=None,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            )

    summary = {
        "run_id": resolved_run_id,
        "run_date": resolved_run_date,
        "bucket": bucket,
        "check_count": len(rows),
        "status_counts": {
            status: sum(1 for row in rows if row["reconciliation_status"] == status)
            for status in sorted({row["reconciliation_status"] for row in rows})
        },
        "failed_checks": [
            {
                "check_id": row["check_id"],
                "reconciliation_status": row["reconciliation_status"],
                "mismatch_count": row["mismatch_count"],
                "error_message": row["error_message"],
            }
            for row in rows
            if row["reconciliation_status"] != "ok"
        ],
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    if write_s3:
        s3_client = boto3.client("s3")
        write_parquet_rows(
            s3_client,
            bucket=bucket,
            key=quality_result_key("reconciliation", "silver_gold", resolved_run_date, resolved_run_id),
            rows=rows,
        )
        s3_client.put_object(
            Bucket=bucket,
            Key=(
                "quality/_summaries/reconciliation/silver_gold/"
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
    parser = argparse.ArgumentParser(description="Run silver-to-gold reconciliation checks.")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-date", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quality-database", default="quality")
    parser.add_argument("--skip-athena-registration", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_silver_gold_reconciliation(
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
