# Athena Quality Layer

The quality layer is a sidecar to the pipeline:

```text
raw / bronze -> silver -> legacy_gold -> semantic_gold / serving
                    \
                     quality/
```

It should record pipeline health, schema shape, table profiles, grain checks,
source completeness, reconciliation summaries, and quarantine summaries without
becoming a serving or business-facing data layer.

The first slice is intentionally manifest-driven. `quality_manifest.py` reads
`pipelines/athena/metadata/pipeline_registry.json` and produces a baseline check
plan with S3 result keys rooted under:

```text
s3://nba-analytics-lakehouse-dev/quality/
```

Existing silver audit and quarantine artifacts stay where they are for now. The
quality layer references and summarizes them rather than moving raw audit output
during the initial baseline slice.

Run the real S3-backed baseline with:

```bash
python3 pipelines/athena/quality/run_quality_baseline.py
```

This writes the manifest plus aggregate parquet artifacts under `quality/`,
including row-count trends, schema drift, and S3-backed grain checks for
artifacts with known grains. After a non-dry run, it also refreshes the Athena
`quality` tables and discovered `run_date` partitions without dropping existing
tables.

`source_completeness_all_sources` is source-family aware. It includes
`source_family`, `completeness_grain`, `season_year`, expected/observed object
counts, missing object counts, and a `source_completeness_status`. Game- and
season-partitioned raw sources are checked against the current refactor
backfill window (`2020-21` through `2025-26`) so missing seasons show up before
silver or gold drift.

Run the gold/semantic-gold parity lock with:

```bash
python3 pipelines/athena/quality/gold_parity_lock.py
```

Run the silver-to-gold reconciliation checks with:

```bash
python3 pipelines/athena/quality/silver_gold_reconciliation.py
```

Run the DuckDB serving snapshot parity lock with:

```bash
python3 pipelines/athena/quality/serving_parity_lock.py
```

The parity and reconciliation scripts write quality parquet outputs and refresh
the same Athena quality tables after successful S3 writes. Use
`--skip-athena-registration` only when intentionally avoiding Athena calls, such
as local smoke tests.

Register the current parquet outputs in Athena with:

```bash
python3 pipelines/athena/quality/deploy_quality_tables.py
```

This creates a separate `quality` Athena database and registers or refreshes the
aggregate parquet outputs as `run_date`-partitioned external tables. The JSON
`pipeline_runs` manifests remain S3-only for now; the queryable tables are the
parquet artifacts used for profiles, schema snapshots, source completeness,
quarantine summaries, anomaly summaries, row-count trends, schema drift, grain
checks, parity reconciliation, silver-to-gold reconciliation, and serving
snapshot quality.

By default the deploy command drops and recreates the quality tables, which is
useful after schema changes. Normal quality runs call the same deploy logic with
`drop_existing=False`, so partition refresh does not require a separate manual
step.

Current planned datasets:

- `pipeline_runs`
- `table_profiles`
- `schema_snapshots`
- `grain_checks`
- `reconciliation`
- `source_completeness`
- `quarantine_summaries`
- `row_count_trends`
- `schema_drift`
- `anomaly_summaries`
- `serving_snapshot_quality`
