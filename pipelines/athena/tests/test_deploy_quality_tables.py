from __future__ import annotations

from pipelines.athena.quality.deploy_quality_tables import (
    PARTITION_COLUMN,
    QUALITY_DATABASE,
    QUALITY_TABLE_SPECS,
    deploy_quality_tables,
    build_add_partition_ddl,
    build_create_database_ddl,
    build_create_table_ddl,
    discover_run_date_partitions,
)
from pipelines.athena.transform.gold.athena_view_helpers import AthenaSettings


class FakePaginator:
    def paginate(self, **_kwargs):
        return [
            {
                "CommonPrefixes": [
                    {"Prefix": "quality/table_profiles/all_artifacts/run_date=2026-05-11/"},
                    {"Prefix": "quality/table_profiles/all_artifacts/run_date=2026-05-12/"},
                    {"Prefix": "quality/table_profiles/all_artifacts/not_a_partition/"},
                ]
            }
        ]


class FakeS3Client:
    def get_paginator(self, _name):
        return FakePaginator()


class RecordingAthenaClient:
    queries: list[str] = []

    def __init__(self, _settings):
        self.queries = RecordingAthenaClient.queries

    def execute(self, query: str):
        self.queries.append(query)
        return [], []


def spec_by_name(name: str):
    return next(spec for spec in QUALITY_TABLE_SPECS if spec.table_name == name)


def test_quality_table_specs_cover_current_parquet_outputs():
    table_names = {spec.table_name for spec in QUALITY_TABLE_SPECS}

    assert table_names == {
        "table_profiles_all_artifacts",
        "schema_snapshots_all_artifacts",
        "source_completeness_all_sources",
        "quarantine_summaries_all_silver",
        "anomaly_summaries_all_layers",
        "row_count_trends_all_artifacts",
        "schema_drift_all_artifacts",
        "grain_checks_all_artifacts",
        "serving_snapshot_quality_duckdb_snapshot",
        "reconciliation_gold_parity_lock",
        "reconciliation_silver_gold",
        "schema_snapshots_gold_parity_lock",
    }
    for spec in QUALITY_TABLE_SPECS:
        assert PARTITION_COLUMN not in {field.name for field in spec.fields}
        assert spec.s3_prefix.startswith("quality/")


def test_build_create_database_ddl_uses_quality_database():
    assert build_create_database_ddl() == f"CREATE DATABASE IF NOT EXISTS `{QUALITY_DATABASE}`"


def test_build_create_table_ddl_partitions_by_run_date():
    spec = spec_by_name("table_profiles_all_artifacts")

    ddl = build_create_table_ddl(spec, bucket="test-bucket", database="quality")

    assert "CREATE EXTERNAL TABLE IF NOT EXISTS `quality`.`table_profiles_all_artifacts`" in ddl
    assert "`run_id` string" in ddl
    assert "`object_count` bigint" in ddl
    assert "`run_date`" not in ddl.split("PARTITIONED BY", 1)[0]
    assert "PARTITIONED BY (`run_date` string)" in ddl
    assert "LOCATION 's3://test-bucket/quality/table_profiles/all_artifacts/'" in ddl


def test_source_completeness_table_includes_family_and_season_fields():
    spec = spec_by_name("source_completeness_all_sources")
    field_names = {field.name for field in spec.fields}

    assert {
        "source_family",
        "completeness_grain",
        "season_year",
        "expected_object_count",
        "observed_object_count",
        "missing_object_count",
        "source_completeness_status",
    } <= field_names


def test_build_add_partition_ddl_targets_run_date_folder():
    spec = spec_by_name("schema_snapshots_gold_parity_lock")

    ddl = build_add_partition_ddl(
        spec,
        run_date="2026-05-11",
        bucket="test-bucket",
        database="quality",
    )

    assert "ALTER TABLE `quality`.`schema_snapshots_gold_parity_lock`" in ddl
    assert "PARTITION (`run_date`='2026-05-11')" in ddl
    assert (
        "LOCATION 's3://test-bucket/quality/schema_snapshots/gold_parity_lock/"
        "run_date=2026-05-11/'"
    ) in ddl


def test_discover_run_date_partitions_reads_immediate_children():
    assert discover_run_date_partitions(
        FakeS3Client(),
        bucket="test-bucket",
        prefix="quality/table_profiles/all_artifacts/",
    ) == ["2026-05-11", "2026-05-12"]


def test_deploy_quality_tables_can_refresh_without_dropping(monkeypatch):
    from pipelines.athena.quality import deploy_quality_tables as deploy_module

    RecordingAthenaClient.queries = []
    monkeypatch.setattr(
        deploy_module,
        "load_settings",
        lambda: AthenaSettings(
            database="default",
            output_location="s3://athena-results/",
            region="us-east-1",
            workgroup="primary",
            catalog="AwsDataCatalog",
            timeout_seconds=30,
            poll_interval_seconds=0.5,
        ),
    )
    monkeypatch.setattr(deploy_module, "AthenaClient", RecordingAthenaClient)
    monkeypatch.setattr(deploy_module.boto3, "client", lambda _name: FakeS3Client())

    summary = deploy_quality_tables(
        bucket="test-bucket",
        database="quality",
        drop_existing=False,
    )

    assert summary["drop_existing"] is False
    assert not any(query.startswith("DROP TABLE") for query in RecordingAthenaClient.queries)
    assert any("CREATE EXTERNAL TABLE IF NOT EXISTS" in query for query in RecordingAthenaClient.queries)
    assert any("ADD IF NOT EXISTS PARTITION" in query for query in RecordingAthenaClient.queries)
