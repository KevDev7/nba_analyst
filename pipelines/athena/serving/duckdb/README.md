# DuckDB Serving Snapshot

Build the local DuckDB serving snapshot from the Athena gold contract sources:

```bash
python3 -m pipelines.athena.serving.duckdb.build_serving_snapshot
```

The builder keeps Athena as the source of truth, materializes the serving contract into a temporary local `.duckdb` file, validates it, and atomically swaps it into the configured active path.

## Local Env Ownership

The preferred local env file for the snapshot job is:

```bash
cp pipelines/athena/serving/duckdb/.env.example pipelines/athena/serving/duckdb/.env
```

The repo root `.env` is only a deprecated fallback for missing values during migration.

## Required Environment

- `ATHENA_DATABASE`
- `ATHENA_OUTPUT_LOCATION`
- `ATHENA_WORKGROUP`
- `ATHENA_CATALOG`
- `AWS_DEFAULT_REGION` or `AWS_REGION`
- `NBA_ANALYTICS_API_DUCKDB_SERVING_DB_PATH` or the legacy aliases `OPENUI_API_DUCKDB_SERVING_DB_PATH` / `DUCKDB_SERVING_DB_PATH`
- `NBA_ANALYTICS_API_DUCKDB_ATHENA_UNLOAD_PREFIX` or the legacy aliases `OPENUI_API_DUCKDB_ATHENA_UNLOAD_PREFIX` / `DUCKDB_ATHENA_UNLOAD_PREFIX`

## Build Behavior

The builder:

- UNLOADs the required serving sources from Athena to Parquet in S3
- imports those Parquet files into a temporary local `.duckdb` file
- writes `serving_snapshot_meta`
- validates the snapshot
- atomically swaps the validated file into the configured output path

During a real run it prints:

- the configured output path
- the base Athena UNLOAD prefix
- the per-source S3 UNLOAD prefix used for each export
- the final build duration in milliseconds
- the final snapshot size in bytes
- the latest regular season resolved from the built snapshot

This is the contract to capture during the first operator-run validation.

## S3 Staging Layout

Each export is written under:

```text
<DUCKDB_ATHENA_UNLOAD_PREFIX>/<UTC timestamp>-<random id>/<source_name>/
```

Example shape:

```text
s3://my-athena-results/duckdb-serving-unload/20260401T100501Z-ab12cd34/agg_player_season/
```

## Manual Validation Runbook

1. Build the snapshot:

```bash
python3 -m pipelines.athena.serving.duckdb.build_serving_snapshot
```

2. Inspect metadata and row counts:

```bash
python3 - <<'PY'
import duckdb

path = "data/serving/nba_serving.duckdb"
with duckdb.connect(path, read_only=True) as conn:
    rows = conn.execute(
        '''
        SELECT source_name, row_count, built_at_utc
        FROM "serving_snapshot_meta"
        ORDER BY source_name
        '''
    ).fetchall()
    for row in rows:
        print(row)
PY
```

3. Confirm the latest regular season resolves:

```bash
python3 - <<'PY'
import duckdb

path = "data/serving/nba_serving.duckdb"
with duckdb.connect(path, read_only=True) as conn:
    season = conn.execute(
        '''
        SELECT MAX("season_year")
        FROM "agg_player_season"
        WHERE "season_type" = 'regular_season'
        '''
    ).fetchone()[0]
    print({"latest_regular_season": season})
PY
```

4. Detect stale or partial snapshots:

- stale: the file mtime is older than your configured `DUCKDB_SNAPSHOT_MAX_AGE_HOURS`
- partial: any required contract source is missing or has `row_count <= 0` in `serving_snapshot_meta`
- invalid: the snapshot exists but the latest regular season query returns null or the file cannot be opened

## Runtime Rollout

- The runtime now serves from DuckDB first by default.
- Configure the serving snapshot with:
  - `NBA_ANALYTICS_API_DUCKDB_SERVING_DB_PATH`
  - `NBA_ANALYTICS_API_DUCKDB_SNAPSHOT_MAX_AGE_HOURS`
- Keep Athena configured as the fallback warehouse contract with:
  - `ATHENA_DATABASE`
  - `ATHENA_OUTPUT_LOCATION`
  - `AWS_DEFAULT_REGION` or `AWS_REGION`
- Verify readiness with:

```bash
curl http://127.0.0.1:8000/health/ready
```
