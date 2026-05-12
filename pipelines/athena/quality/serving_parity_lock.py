from __future__ import annotations

import argparse
import io
import json
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

try:
    from pipelines.athena.quality.quality_manifest import (
        DEFAULT_BUCKET,
        new_run_id,
        quality_result_key,
        today_run_date,
    )
    from pipelines.athena.quality.registration import refresh_quality_athena_tables
    from pipelines.athena.serving.duckdb.build_serving_snapshot import (
        REQUIRED_SERVING_SOURCES,
        SNAPSHOT_SCOPE_VERSION,
    )
    from pipelines.athena.serving.duckdb.serving_config import DuckDBServingSnapshotSettings
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
    from pipelines.athena.serving.duckdb.build_serving_snapshot import (
        REQUIRED_SERVING_SOURCES,
        SNAPSHOT_SCOPE_VERSION,
    )
    from pipelines.athena.serving.duckdb.serving_config import DuckDBServingSnapshotSettings
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings


SERVING_SNAPSHOT_QUALITY_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("source_name", pa.string()),
        ("snapshot_path", pa.string()),
        ("built_at_utc", pa.string()),
        ("snapshot_scope_version", pa.string()),
        ("athena_database", pa.string()),
        ("local_row_count", pa.int64()),
        ("athena_row_count", pa.int64()),
        ("row_count_delta", pa.int64()),
        ("local_column_count", pa.int64()),
        ("athena_column_count", pa.int64()),
        ("local_only_columns", pa.string()),
        ("athena_only_columns", pa.string()),
        ("quality_status", pa.string()),
        ("error_message", pa.string()),
    ]
)


@dataclass(frozen=True)
class SourceState:
    row_count: int | None
    columns: tuple[str, ...]
    status: str
    error_message: str | None = None


@dataclass(frozen=True)
class LocalSnapshotState:
    path: Path
    exists: bool
    built_at_utc: str | None
    snapshot_scope_version: str | None
    sources: dict[str, SourceState]


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_serving_settings() -> DuckDBServingSnapshotSettings:
    repo_root = Path(__file__).resolve().parents[3]
    builder_dir = repo_root / "pipelines" / "athena" / "serving" / "duckdb"
    load_dotenv(builder_dir / ".env", override=True)
    return DuckDBServingSnapshotSettings.from_env(builder_dir=builder_dir, repo_root=repo_root)


def inspect_local_snapshot(path: Path, required_sources: tuple[str, ...]) -> LocalSnapshotState:
    if not path.exists():
        return LocalSnapshotState(
            path=path,
            exists=False,
            built_at_utc=None,
            snapshot_scope_version=None,
            sources={
                source: SourceState(None, (), "missing_snapshot", f"Snapshot does not exist: {path}")
                for source in required_sources
            },
        )

    sources: dict[str, SourceState] = {}
    built_at_utc = None
    scope_version = None
    try:
        with duckdb.connect(str(path), read_only=True) as conn:
            table_names = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
            if "serving_snapshot_meta" in table_names:
                meta = conn.execute(
                    """
                    SELECT MAX("built_at_utc"), MAX("snapshot_scope_version")
                    FROM "serving_snapshot_meta"
                    """
                ).fetchone()
                if meta:
                    built_at_utc = str(meta[0]) if meta[0] not in (None, "") else None
                    scope_version = str(meta[1]) if meta[1] not in (None, "") else None

            for source in required_sources:
                if source not in table_names:
                    sources[source] = SourceState(None, (), "missing_local_table", None)
                    continue
                row_count = int(
                    conn.execute(f"SELECT COUNT(*) FROM {quote_ident(source)}").fetchone()[0] or 0
                )
                columns = tuple(row[0] for row in conn.execute(f"DESCRIBE {quote_ident(source)}").fetchall())
                sources[source] = SourceState(row_count, columns, "ok", None)
    except Exception as exc:
        return LocalSnapshotState(
            path=path,
            exists=True,
            built_at_utc=built_at_utc,
            snapshot_scope_version=scope_version,
            sources={
                source: SourceState(None, (), "local_query_error", f"{type(exc).__name__}: {exc}")
                for source in required_sources
            },
        )

    return LocalSnapshotState(path, True, built_at_utc, scope_version, sources)


def fetch_athena_source_state(
    client: AthenaClient,
    *,
    database: str,
    source_name: str,
) -> SourceState:
    try:
        _, count_rows = client.execute(
            f"SELECT COUNT(*) AS row_count FROM {quote_ident(database)}.{quote_ident(source_name)}"
        )
        _, column_rows = client.execute(
            f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = '{database}'
              AND table_name = '{source_name}'
            ORDER BY ordinal_position
            """
        )
        return SourceState(
            row_count=int(count_rows[0]["row_count"]) if count_rows else None,
            columns=tuple(str(row["column_name"]) for row in column_rows),
            status="ok",
            error_message=None,
        )
    except Exception as exc:
        return SourceState(None, (), "athena_query_error", f"{type(exc).__name__}: {exc}")


def build_serving_quality_rows(
    *,
    run_id: str,
    run_date: str,
    local_snapshot: LocalSnapshotState,
    athena_states: dict[str, SourceState],
    required_sources: tuple[str, ...],
    athena_database: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in required_sources:
        local_state = local_snapshot.sources[source]
        athena_state = athena_states[source]
        local_columns = set(local_state.columns)
        athena_columns = set(athena_state.columns)
        row_count_delta = (
            local_state.row_count - athena_state.row_count
            if local_state.row_count is not None and athena_state.row_count is not None
            else None
        )

        if local_state.status != "ok":
            quality_status = local_state.status
            error_message = local_state.error_message
        elif athena_state.status != "ok":
            quality_status = athena_state.status
            error_message = athena_state.error_message
        elif row_count_delta != 0:
            quality_status = "row_count_mismatch"
            error_message = None
        elif local_columns != athena_columns:
            quality_status = "schema_mismatch"
            error_message = None
        else:
            quality_status = "ok"
            error_message = None

        rows.append(
            {
                "run_id": run_id,
                "run_date": run_date,
                "source_name": source,
                "snapshot_path": str(local_snapshot.path),
                "built_at_utc": local_snapshot.built_at_utc,
                "snapshot_scope_version": local_snapshot.snapshot_scope_version,
                "athena_database": athena_database,
                "local_row_count": local_state.row_count,
                "athena_row_count": athena_state.row_count,
                "row_count_delta": row_count_delta,
                "local_column_count": len(local_state.columns),
                "athena_column_count": len(athena_state.columns),
                "local_only_columns": ",".join(sorted(local_columns - athena_columns)) or None,
                "athena_only_columns": ",".join(sorted(athena_columns - local_columns)) or None,
                "quality_status": quality_status,
                "error_message": error_message,
            }
        )
    return rows


def write_parquet_rows(
    s3_client,
    *,
    bucket: str,
    key: str,
    rows: list[dict[str, Any]],
) -> None:
    table = pa.Table.from_pylist(rows, schema=SERVING_SNAPSHOT_QUALITY_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )


def run_serving_parity_lock(
    *,
    bucket: str = DEFAULT_BUCKET,
    run_id: str | None = None,
    run_date: str | None = None,
    write_s3: bool = True,
    register_athena: bool = True,
    quality_database: str = "quality",
) -> dict[str, Any]:
    settings = load_serving_settings()
    os.environ.pop("AWS_PROFILE", None)
    resolved_run_id = run_id or new_run_id()
    resolved_run_date = run_date or today_run_date()
    athena_settings = replace(load_settings(), database=settings.athena_database)
    athena_client = AthenaClient(athena_settings)

    local_snapshot = inspect_local_snapshot(settings.output_path, REQUIRED_SERVING_SOURCES)
    athena_states = {
        source: fetch_athena_source_state(
            athena_client,
            database=settings.athena_database,
            source_name=source,
        )
        for source in REQUIRED_SERVING_SOURCES
    }
    rows = build_serving_quality_rows(
        run_id=resolved_run_id,
        run_date=resolved_run_date,
        local_snapshot=local_snapshot,
        athena_states=athena_states,
        required_sources=REQUIRED_SERVING_SOURCES,
        athena_database=settings.athena_database,
    )
    status_counts = {
        status: sum(1 for row in rows if row["quality_status"] == status)
        for status in sorted({row["quality_status"] for row in rows})
    }
    summary = {
        "run_id": resolved_run_id,
        "run_date": resolved_run_date,
        "bucket": bucket,
        "snapshot_path": str(settings.output_path),
        "snapshot_exists": local_snapshot.exists,
        "athena_database": settings.athena_database,
        "source_count": len(rows),
        "status_counts": status_counts,
        "generated_at_utc": iso_utc_now(),
    }

    if write_s3:
        s3_client = boto3.client("s3")
        key = quality_result_key(
            "serving_snapshot_quality",
            "duckdb_snapshot",
            resolved_run_date,
            resolved_run_id,
        )
        write_parquet_rows(s3_client, bucket=bucket, key=key, rows=rows)
        s3_client.put_object(
            Bucket=bucket,
            Key=(
                "quality/_summaries/serving_snapshot_quality/duckdb_snapshot/"
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
    parser = argparse.ArgumentParser(description="Run DuckDB serving snapshot parity checks.")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-date", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quality-database", default="quality")
    parser.add_argument("--skip-athena-registration", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_serving_parity_lock(
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
