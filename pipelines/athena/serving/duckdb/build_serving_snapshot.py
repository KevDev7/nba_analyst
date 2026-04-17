from __future__ import annotations

import argparse
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import boto3
import duckdb
from botocore.exceptions import BotoCoreError, ClientError

try:
    from .serving_config import DuckDBServingSnapshotSettings
except ImportError:  # pragma: no cover - direct script execution fallback
    from serving_config import DuckDBServingSnapshotSettings


REQUIRED_SERVING_SOURCES: tuple[str, ...] = (
    "agg_player_season",
    "player_season_percentiles",
    "dim_player",
    "dim_team",
    "dim_game",
    "dim_date",
    "fct_player_game",
    "fct_player_game_shot_type_source",
    "fct_team_game",
    "agg_team_season",
    "team_season_percentiles",
    "extended_player_dim",
    "player_award_history",
    "vw_player_game_shot_type_source",
    "vw_player_season_boxscore_advanced",
    "vw_team_season_boxscore_advanced",
)
SNAPSHOT_SCOPE_VERSION = "duckdb_serving_contract_v3"
SOURCE_BACKEND = "athena"


class SnapshotBuildError(RuntimeError):
    pass


class SourceParquetExporter(Protocol):
    def export_source(self, source_name: str, destination_dir: Path) -> list[Path]: ...


@dataclass(frozen=True)
class SourceSnapshotResult:
    source_name: str
    row_count: int


@dataclass(frozen=True)
class SnapshotInspectionResult:
    path: Path
    built_at_utc: str | None
    latest_regular_season: str
    size_bytes: int
    row_counts: dict[str, int]


class AthenaSourceParquetExporter:
    def __init__(self, settings: DuckDBServingSnapshotSettings):
        self._settings = settings
        self._athena = boto3.client("athena", region_name=settings.aws_region) if settings.aws_region else None
        self._s3 = boto3.client("s3", region_name=settings.aws_region) if settings.aws_region else None

    def export_source(self, source_name: str, destination_dir: Path) -> list[Path]:
        if not self._settings.athena_configured or self._athena is None or self._s3 is None:
            raise SnapshotBuildError("Athena UNLOAD is not configured for DuckDB serving snapshot builds.")
        destination_dir.mkdir(parents=True, exist_ok=True)
        unload_prefix = (
            f"{self._settings.athena_unload_prefix.rstrip('/')}/"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex}/{source_name}/"
        )
        unload_sql = (
            f'UNLOAD (SELECT * FROM "{self._settings.athena_database}"."{source_name}") '
            f"TO '{unload_prefix}' "
            "WITH (format = 'PARQUET', compression = 'SNAPPY')"
        )
        print(f"[duckdb snapshot export] source={source_name} s3_prefix={unload_prefix}")
        self._run_athena_statement(unload_sql)
        downloaded = self._download_parquet_objects(unload_prefix, destination_dir)
        print(f"[duckdb snapshot export] source={source_name} parquet_files={len(downloaded)}")
        return downloaded

    def _run_athena_statement(self, sql: str) -> None:
        try:
            start = self._athena.start_query_execution(
                QueryString=sql,
                QueryExecutionContext={
                    "Database": self._settings.athena_database,
                    "Catalog": self._settings.athena_catalog,
                },
                ResultConfiguration={"OutputLocation": self._settings.athena_output_location},
                WorkGroup=self._settings.athena_workgroup,
            )
        except (BotoCoreError, ClientError) as exc:
            raise SnapshotBuildError(f"Athena UNLOAD start failed: {exc}") from exc

        query_execution_id = start["QueryExecutionId"]
        deadline = time.time() + self._settings.athena_timeout_seconds
        while time.time() < deadline:
            execution = self._athena.get_query_execution(QueryExecutionId=query_execution_id)
            status = execution["QueryExecution"]["Status"]["State"]
            if status == "SUCCEEDED":
                return
            if status in {"FAILED", "CANCELLED"}:
                reason = execution["QueryExecution"]["Status"].get("StateChangeReason", "Athena UNLOAD failed.")
                raise SnapshotBuildError(reason)
            time.sleep(self._settings.athena_poll_interval_seconds)
        try:
            self._athena.stop_query_execution(QueryExecutionId=query_execution_id)
        except Exception:
            pass
        raise SnapshotBuildError("Athena UNLOAD timed out.")

    def _download_parquet_objects(self, s3_prefix: str, destination_dir: Path) -> list[Path]:
        bucket, prefix = _parse_s3_uri(s3_prefix)
        paginator = self._s3.get_paginator("list_objects_v2")
        downloaded: list[Path] = []
        total_objects = 0
        skipped_non_data = 0
        skipped_zero_byte = 0
        skipped_non_parquet = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = str(item.get("Key", ""))
                total_objects += 1
                if self._is_non_data_artifact(key):
                    skipped_non_data += 1
                    continue
                if int(item.get("Size", 0) or 0) <= 0:
                    skipped_zero_byte += 1
                    continue
                local_path = destination_dir / self._local_parquet_filename(key)
                self._s3.download_file(bucket, key, str(local_path))
                if not self._is_parquet_file(local_path):
                    skipped_non_parquet += 1
                    local_path.unlink(missing_ok=True)
                    continue
                downloaded.append(local_path)
        print(
            "[duckdb snapshot export] "
            f"s3_prefix={s3_prefix} total_objects={total_objects} "
            f"skipped_non_data={skipped_non_data} skipped_zero_byte={skipped_zero_byte} "
            f"skipped_non_parquet={skipped_non_parquet} accepted_parquet={len(downloaded)}"
        )
        if not downloaded:
            raise SnapshotBuildError(f"No parquet exports found under {s3_prefix}")
        return downloaded

    def _is_non_data_artifact(self, key: str) -> bool:
        lowered = key.lower()
        return lowered.endswith("/") or lowered.endswith(".metadata") or lowered.endswith(".manifest")

    def _local_parquet_filename(self, key: str) -> str:
        filename = Path(key).name
        if filename.lower().endswith(".parquet"):
            return filename
        return f"{filename}.parquet"

    def _is_parquet_file(self, path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                header = handle.read(4)
                if header != b"PAR1":
                    return False
                handle.seek(-4, 2)
                footer = handle.read(4)
        except OSError:
            return False
        return footer == b"PAR1"


class DuckDBServingSnapshotBuilder:
    def __init__(
        self,
        exporter: SourceParquetExporter,
        *,
        output_path: Path,
        required_sources: tuple[str, ...] = REQUIRED_SERVING_SOURCES,
    ):
        self._exporter = exporter
        self._output_path = output_path
        self._required_sources = required_sources

    def build_snapshot(self) -> Path:
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        started_at = time.perf_counter()
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_db_path = self._output_path.parent / f".{self._output_path.name}.{run_id}.tmp"
        temp_dir = Path(tempfile.mkdtemp(prefix="duckdb-serving-", dir=str(self._output_path.parent)))
        built_at_utc = datetime.now(timezone.utc).isoformat()
        try:
            source_results = self._populate_snapshot(temp_db_path, temp_dir, built_at_utc)
            inspection = self._validate_snapshot(temp_db_path, source_results)
            temp_db_path.replace(self._output_path)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
            print(
                "[duckdb snapshot build] "
                f"status=ok path={self._output_path} duration_ms={duration_ms} "
                f"size_bytes={inspection.size_bytes} latest_regular_season={inspection.latest_regular_season} "
                f"required_sources={len(source_results)}"
            )
            return self._output_path
        except Exception:
            if temp_db_path.exists():
                temp_db_path.unlink()
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _populate_snapshot(self, temp_db_path: Path, temp_dir: Path, built_at_utc: str) -> list[SourceSnapshotResult]:
        source_results: list[SourceSnapshotResult] = []
        with duckdb.connect(str(temp_db_path)) as conn:
            for source_name in self._required_sources:
                source_dir = temp_dir / source_name
                parquet_files = self._exporter.export_source(source_name, source_dir)
                if not parquet_files:
                    raise SnapshotBuildError(f"Exporter returned no parquet files for {source_name}")
                parquet_glob = str(source_dir / "*.parquet")
                conn.execute(f'CREATE TABLE "{source_name}" AS SELECT * FROM read_parquet(?)', [parquet_glob])
                row_count = int(conn.execute(f'SELECT COUNT(*) FROM "{source_name}"').fetchone()[0] or 0)
                source_results.append(SourceSnapshotResult(source_name=source_name, row_count=row_count))
            self._write_metadata(conn, built_at_utc, source_results)
        return source_results

    def _write_metadata(
        self,
        conn: duckdb.DuckDBPyConnection,
        built_at_utc: str,
        source_results: list[SourceSnapshotResult],
    ) -> None:
        conn.execute(
            """
            CREATE TABLE "serving_snapshot_meta" (
                built_at_utc VARCHAR,
                source_backend VARCHAR,
                snapshot_scope_version VARCHAR,
                source_name VARCHAR,
                row_count BIGINT
            )
            """
        )
        rows = [
            (
                built_at_utc,
                SOURCE_BACKEND,
                SNAPSHOT_SCOPE_VERSION,
                result.source_name,
                result.row_count,
            )
            for result in source_results
        ]
        conn.executemany(
            'INSERT INTO "serving_snapshot_meta" VALUES (?, ?, ?, ?, ?)',
            rows,
        )

    def _validate_snapshot(self, db_path: Path, source_results: list[SourceSnapshotResult]) -> SnapshotInspectionResult:
        row_counts = {result.source_name: result.row_count for result in source_results}
        with duckdb.connect(str(db_path), read_only=True) as conn:
            table_names = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
            missing = sorted(set(self._required_sources) - table_names)
            if missing:
                raise SnapshotBuildError(f"Snapshot missing required sources: {', '.join(missing)}")
            empty_sources = sorted(source for source in self._required_sources if row_counts.get(source, 0) <= 0)
            if empty_sources:
                raise SnapshotBuildError(f"Snapshot contains empty required sources: {', '.join(empty_sources)}")
            latest_regular_season = conn.execute(
                """
                SELECT MAX("season_year") AS "season_year"
                FROM "agg_player_season"
                WHERE "season_type" = 'regular_season'
                """
            ).fetchone()[0]
            if latest_regular_season in (None, ""):
                raise SnapshotBuildError("Snapshot could not resolve latest regular season.")
            for advanced_source in ("vw_player_season_boxscore_advanced", "vw_team_season_boxscore_advanced"):
                advanced_count = conn.execute(f'SELECT COUNT(*) FROM "{advanced_source}"').fetchone()[0]
                if int(advanced_count or 0) <= 0:
                    raise SnapshotBuildError(f"Advanced serving source is empty: {advanced_source}")
            built_at_row = conn.execute(
                """
                SELECT MAX("built_at_utc") AS "built_at_utc"
                FROM "serving_snapshot_meta"
                """
            ).fetchone()
        return SnapshotInspectionResult(
            path=db_path,
            built_at_utc=str(built_at_row[0]) if built_at_row and built_at_row[0] not in (None, "") else None,
            latest_regular_season=str(latest_regular_season),
            size_bytes=db_path.stat().st_size,
            row_counts=row_counts,
        )


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise SnapshotBuildError(f"Invalid S3 URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a DuckDB serving snapshot from Athena contract sources.")
    parser.add_argument("--output-path", default="", help="Optional override for the DuckDB output path.")
    args = parser.parse_args()

    settings = DuckDBServingSnapshotSettings.from_env()
    output_path = Path(args.output_path) if args.output_path else settings.output_path
    print(
        "[duckdb snapshot build] "
        f"status=starting output_path={output_path} "
        f"athena_database={settings.athena_database} "
        f"athena_unload_prefix={settings.athena_unload_prefix}"
    )
    builder = DuckDBServingSnapshotBuilder(
        AthenaSourceParquetExporter(settings),
        output_path=output_path,
    )
    built_path = builder.build_snapshot()
    print(f"Built DuckDB serving snapshot at {built_path}")


if __name__ == "__main__":
    main()
