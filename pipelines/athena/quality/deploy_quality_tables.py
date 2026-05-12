from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, replace
from pathlib import Path

import boto3

try:
    from pipelines.athena.quality.quality_manifest import DEFAULT_BUCKET
    from pipelines.athena.transform.gold.athena_view_helpers import (
        AthenaClient,
        load_settings,
    )
except ModuleNotFoundError:
    import sys

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.athena.quality.quality_manifest import DEFAULT_BUCKET
    from pipelines.athena.transform.gold.athena_view_helpers import (
        AthenaClient,
        load_settings,
    )


QUALITY_DATABASE = "quality"
PARTITION_COLUMN = "run_date"


@dataclass(frozen=True)
class QualityField:
    name: str
    athena_type: str


@dataclass(frozen=True)
class QualityTableSpec:
    table_name: str
    s3_prefix: str
    fields: tuple[QualityField, ...]


BASE_PROFILE_FIELDS = (
    QualityField("run_id", "string"),
    QualityField("artifact_id", "string"),
    QualityField("layer", "string"),
    QualityField("artifact_type", "string"),
    QualityField("source_key", "string"),
    QualityField("source_prefix", "string"),
    QualityField("is_exact_key", "boolean"),
    QualityField("object_count", "bigint"),
    QualityField("total_size_bytes", "bigint"),
    QualityField("latest_last_modified_utc", "string"),
    QualityField("sample_key", "string"),
    QualityField("sample_row_count", "bigint"),
    QualityField("profile_status", "string"),
    QualityField("error_message", "string"),
)

QUALITY_TABLE_SPECS = (
    QualityTableSpec(
        table_name="table_profiles_all_artifacts",
        s3_prefix="quality/table_profiles/all_artifacts/",
        fields=BASE_PROFILE_FIELDS,
    ),
    QualityTableSpec(
        table_name="schema_snapshots_all_artifacts",
        s3_prefix="quality/schema_snapshots/all_artifacts/",
        fields=(
            QualityField("run_id", "string"),
            QualityField("artifact_id", "string"),
            QualityField("layer", "string"),
            QualityField("sample_key", "string"),
            QualityField("field_index", "bigint"),
            QualityField("column_name", "string"),
            QualityField("data_type", "string"),
            QualityField("nullable", "boolean"),
            QualityField("schema_status", "string"),
        ),
    ),
    QualityTableSpec(
        table_name="source_completeness_all_sources",
        s3_prefix="quality/source_completeness/all_sources/",
        fields=BASE_PROFILE_FIELDS
        + (
            QualityField("dataset", "string"),
            QualityField("source_family", "string"),
            QualityField("completeness_grain", "string"),
            QualityField("season_year", "string"),
            QualityField("expected_object_count", "bigint"),
            QualityField("observed_object_count", "bigint"),
            QualityField("missing_object_count", "bigint"),
            QualityField("source_completeness_status", "string"),
        ),
    ),
    QualityTableSpec(
        table_name="quarantine_summaries_all_silver",
        s3_prefix="quality/quarantine_summaries/all_silver/",
        fields=BASE_PROFILE_FIELDS + (QualityField("dataset", "string"),),
    ),
    QualityTableSpec(
        table_name="anomaly_summaries_all_layers",
        s3_prefix="quality/anomaly_summaries/all_layers/",
        fields=(
            QualityField("run_id", "string"),
            QualityField("layer", "string"),
            QualityField("profile_status", "string"),
            QualityField("artifact_count", "bigint"),
        ),
    ),
    QualityTableSpec(
        table_name="row_count_trends_all_artifacts",
        s3_prefix="quality/row_count_trends/all_artifacts/",
        fields=(
            QualityField("run_id", "string"),
            QualityField("artifact_id", "string"),
            QualityField("layer", "string"),
            QualityField("current_sample_row_count", "bigint"),
            QualityField("previous_run_id", "string"),
            QualityField("previous_run_date", "string"),
            QualityField("previous_sample_row_count", "bigint"),
            QualityField("row_count_delta", "bigint"),
            QualityField("row_count_delta_pct", "double"),
            QualityField("current_profile_status", "string"),
            QualityField("previous_profile_status", "string"),
            QualityField("trend_status", "string"),
        ),
    ),
    QualityTableSpec(
        table_name="schema_drift_all_artifacts",
        s3_prefix="quality/schema_drift/all_artifacts/",
        fields=(
            QualityField("run_id", "string"),
            QualityField("artifact_id", "string"),
            QualityField("layer", "string"),
            QualityField("column_name", "string"),
            QualityField("current_data_type", "string"),
            QualityField("previous_data_type", "string"),
            QualityField("current_nullable", "boolean"),
            QualityField("previous_nullable", "boolean"),
            QualityField("drift_type", "string"),
            QualityField("drift_status", "string"),
            QualityField("previous_run_id", "string"),
            QualityField("previous_run_date", "string"),
        ),
    ),
    QualityTableSpec(
        table_name="grain_checks_all_artifacts",
        s3_prefix="quality/grain_checks/all_artifacts/",
        fields=(
            QualityField("run_id", "string"),
            QualityField("artifact_id", "string"),
            QualityField("layer", "string"),
            QualityField("sample_key", "string"),
            QualityField("grain_columns", "string"),
            QualityField("total_rows", "bigint"),
            QualityField("distinct_grain_rows", "bigint"),
            QualityField("duplicate_grain_rows", "bigint"),
            QualityField("null_grain_rows", "bigint"),
            QualityField("grain_status", "string"),
            QualityField("error_message", "string"),
        ),
    ),
    QualityTableSpec(
        table_name="serving_snapshot_quality_duckdb_snapshot",
        s3_prefix="quality/serving_snapshot_quality/duckdb_snapshot/",
        fields=(
            QualityField("run_id", "string"),
            QualityField("source_name", "string"),
            QualityField("snapshot_path", "string"),
            QualityField("built_at_utc", "string"),
            QualityField("snapshot_scope_version", "string"),
            QualityField("athena_database", "string"),
            QualityField("local_row_count", "bigint"),
            QualityField("athena_row_count", "bigint"),
            QualityField("row_count_delta", "bigint"),
            QualityField("local_column_count", "bigint"),
            QualityField("athena_column_count", "bigint"),
            QualityField("local_only_columns", "string"),
            QualityField("athena_only_columns", "string"),
            QualityField("quality_status", "string"),
            QualityField("error_message", "string"),
        ),
    ),
    QualityTableSpec(
        table_name="reconciliation_gold_parity_lock",
        s3_prefix="quality/reconciliation/gold_parity_lock/",
        fields=(
            QualityField("run_id", "string"),
            QualityField("artifact_id", "string"),
            QualityField("layer", "string"),
            QualityField("schema_name", "string"),
            QualityField("table_name", "string"),
            QualityField("artifact_type", "string"),
            QualityField("row_count", "bigint"),
            QualityField("distinct_grain_rows", "bigint"),
            QualityField("duplicate_grain_rows", "bigint"),
            QualityField("column_count", "bigint"),
            QualityField("parity_status", "string"),
            QualityField("error_message", "string"),
        ),
    ),
    QualityTableSpec(
        table_name="reconciliation_silver_gold",
        s3_prefix="quality/reconciliation/silver_gold/",
        fields=(
            QualityField("run_id", "string"),
            QualityField("check_id", "string"),
            QualityField("check_group", "string"),
            QualityField("source_artifact_id", "string"),
            QualityField("target_artifact_id", "string"),
            QualityField("source_row_count", "bigint"),
            QualityField("target_row_count", "bigint"),
            QualityField("mismatch_count", "bigint"),
            QualityField("reconciliation_status", "string"),
            QualityField("error_message", "string"),
        ),
    ),
    QualityTableSpec(
        table_name="schema_snapshots_gold_parity_lock",
        s3_prefix="quality/schema_snapshots/gold_parity_lock/",
        fields=(
            QualityField("run_id", "string"),
            QualityField("artifact_id", "string"),
            QualityField("schema_name", "string"),
            QualityField("table_name", "string"),
            QualityField("column_name", "string"),
            QualityField("data_type", "string"),
            QualityField("ordinal_position", "string"),
        ),
    ),
)


def quote_ident(identifier: str) -> str:
    return "`" + identifier.replace("`", "``") + "`"


def qualified_table(database: str, table_name: str) -> str:
    return f"{quote_ident(database)}.{quote_ident(table_name)}"


def s3_location(bucket: str, prefix: str) -> str:
    return f"s3://{bucket}/{prefix.strip('/')}/"


def build_create_database_ddl(database: str = QUALITY_DATABASE) -> str:
    return f"CREATE DATABASE IF NOT EXISTS {quote_ident(database)}"


def build_drop_table_ddl(spec: QualityTableSpec, *, database: str = QUALITY_DATABASE) -> str:
    return f"DROP TABLE IF EXISTS {qualified_table(database, spec.table_name)}"


def build_create_table_ddl(
    spec: QualityTableSpec,
    *,
    bucket: str = DEFAULT_BUCKET,
    database: str = QUALITY_DATABASE,
) -> str:
    columns = ",\n".join(
        f"  {quote_ident(field.name)} {field.athena_type}" for field in spec.fields
    )
    return f"""CREATE EXTERNAL TABLE IF NOT EXISTS {qualified_table(database, spec.table_name)} (
{columns}
)
PARTITIONED BY ({quote_ident(PARTITION_COLUMN)} string)
STORED AS PARQUET
LOCATION '{s3_location(bucket, spec.s3_prefix)}'"""


def discover_run_date_partitions(
    s3_client,
    *,
    bucket: str = DEFAULT_BUCKET,
    prefix: str,
) -> list[str]:
    normalized_prefix = prefix.strip("/") + "/"
    paginator = s3_client.get_paginator("list_objects_v2")
    run_dates: set[str] = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=normalized_prefix, Delimiter="/"):
        for common_prefix in page.get("CommonPrefixes", []):
            child_prefix = str(common_prefix.get("Prefix", ""))
            partition_name = child_prefix.removeprefix(normalized_prefix).strip("/")
            if partition_name.startswith(f"{PARTITION_COLUMN}="):
                run_dates.add(partition_name.split("=", 1)[1])
    return sorted(run_dates)


def build_add_partition_ddl(
    spec: QualityTableSpec,
    *,
    run_date: str,
    bucket: str = DEFAULT_BUCKET,
    database: str = QUALITY_DATABASE,
) -> str:
    location = s3_location(bucket, f"{spec.s3_prefix.rstrip('/')}/{PARTITION_COLUMN}={run_date}/")
    return (
        f"ALTER TABLE {qualified_table(database, spec.table_name)} "
        f"ADD IF NOT EXISTS PARTITION ({quote_ident(PARTITION_COLUMN)}='{run_date}') "
        f"LOCATION '{location}'"
    )


def deploy_quality_tables(
    *,
    bucket: str = DEFAULT_BUCKET,
    database: str = QUALITY_DATABASE,
    drop_existing: bool = True,
) -> dict[str, object]:
    os.environ.pop("AWS_PROFILE", None)
    settings = replace(load_settings(), database=database)
    athena_client = AthenaClient(settings)
    s3_client = boto3.client("s3")

    athena_client.execute(build_create_database_ddl(database))

    table_count = 0
    partition_count = 0
    for spec in QUALITY_TABLE_SPECS:
        if drop_existing:
            athena_client.execute(build_drop_table_ddl(spec, database=database))
        athena_client.execute(build_create_table_ddl(spec, bucket=bucket, database=database))
        table_count += 1

        for run_date in discover_run_date_partitions(
            s3_client,
            bucket=bucket,
            prefix=spec.s3_prefix,
        ):
            athena_client.execute(
                build_add_partition_ddl(
                    spec,
                    run_date=run_date,
                    bucket=bucket,
                    database=database,
                )
            )
            partition_count += 1

    return {
        "bucket": bucket,
        "database": database,
        "drop_existing": drop_existing,
        "table_count": table_count,
        "partition_count": partition_count,
        "tables": [spec.table_name for spec in QUALITY_TABLE_SPECS],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register quality-layer parquet outputs in Athena.")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--database", default=QUALITY_DATABASE)
    parser.add_argument("--skip-drop", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = deploy_quality_tables(
        bucket=args.bucket,
        database=args.database,
        drop_existing=not args.skip_drop,
    )
    print(summary)


if __name__ == "__main__":
    main()
