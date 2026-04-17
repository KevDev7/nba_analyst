from __future__ import annotations

import io
import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pipelines.athena.serving.duckdb.build_serving_snapshot import (
    REQUIRED_SERVING_SOURCES,
    AthenaSourceParquetExporter,
    DuckDBServingSnapshotBuilder,
    SnapshotBuildError,
)
from pipelines.athena.serving.duckdb.serving_config import DuckDBServingSnapshotSettings


class FakeParquetExporter:
    def __init__(self, parquet_sources: dict[str, list[Path]]):
        self._parquet_sources = parquet_sources

    def export_source(self, source_name: str, destination_dir: Path) -> list[Path]:
        destination_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for source_path in self._parquet_sources.get(source_name, []):
            target_path = destination_dir / source_path.name
            target_path.write_bytes(source_path.read_bytes())
            copied.append(target_path)
        return copied


def _write_parquet(path: Path, table: pa.Table) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return path


def _parquet_bytes(table: pa.Table) -> bytes:
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    return buffer.getvalue()


def _non_empty_sources(tmp_path: Path) -> dict[str, list[Path]]:
    datasets: dict[str, list[Path]] = {}
    for source in REQUIRED_SERVING_SOURCES:
        if source == "agg_player_season":
            table = pa.table(
                {
                    "season_year": ["2024-25"],
                    "season_type": ["regular_season"],
                    "person_id": [1628973],
                }
            )
        elif source == "fct_player_game_shot_type_source":
            table = pa.table(
                {
                    "game_id": ["0022300001"],
                    "person_id": [201939],
                    "source_shot_type_label": ["3PT Pullup Jump Shot"],
                    "field_goals_attempted": [5],
                }
            )
        elif source == "vw_player_game_shot_type_source":
            table = pa.table(
                {
                    "player_id": [201939],
                    "player_name": ["Stephen Curry"],
                    "game_id": ["0022300001"],
                    "shot_type": ["3PT Pullup Jump Shot"],
                }
            )
        elif source == "vw_player_season_boxscore_advanced":
            table = pa.table({"player_name": ["Jalen Brunson"], "team": ["NYK"], "games_played": [77]})
        elif source == "vw_team_season_boxscore_advanced":
            table = pa.table({"team": ["OKC"], "games_played": [82], "net_rating": [8.7]})
        else:
            table = pa.table({"id": [1]})
        datasets[source] = [_write_parquet(tmp_path / source / f"{source}.parquet", table)]
    return datasets


def test_builder_creates_required_tables_and_metadata(tmp_path: Path):
    output_path = tmp_path / "serving" / "nba_serving.duckdb"
    builder = DuckDBServingSnapshotBuilder(
        FakeParquetExporter(_non_empty_sources(tmp_path)),
        output_path=output_path,
    )

    built_path = builder.build_snapshot()

    assert built_path == output_path
    with duckdb.connect(str(output_path), read_only=True) as conn:
        table_names = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert set(REQUIRED_SERVING_SOURCES).issubset(table_names)
        meta_rows = conn.execute(
            """
            SELECT source_name, row_count
            FROM "serving_snapshot_meta"
            ORDER BY source_name
            """
        ).fetchall()
        assert len(meta_rows) == len(REQUIRED_SERVING_SOURCES)
        assert meta_rows[0][1] > 0


def test_builder_atomically_replaces_existing_snapshot(tmp_path: Path):
    output_path = tmp_path / "serving" / "nba_serving.duckdb"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(output_path)) as conn:
        conn.execute('CREATE TABLE "old_snapshot_marker" AS SELECT 1 AS value')

    builder = DuckDBServingSnapshotBuilder(
        FakeParquetExporter(_non_empty_sources(tmp_path)),
        output_path=output_path,
    )
    builder.build_snapshot()

    with duckdb.connect(str(output_path), read_only=True) as conn:
        table_names = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert "old_snapshot_marker" not in table_names
        assert "agg_player_season" in table_names


def test_builder_rejects_incomplete_snapshot_with_empty_required_source(tmp_path: Path):
    parquet_sources = _non_empty_sources(tmp_path)
    parquet_sources["vw_team_season_boxscore_advanced"] = [
        _write_parquet(
            tmp_path / "empty" / "vw_team_season_boxscore_advanced.parquet",
            pa.table(
                {
                    "team": pa.array([], type=pa.string()),
                    "games_played": pa.array([], type=pa.int64()),
                    "net_rating": pa.array([], type=pa.float64()),
                }
            ),
        )
    ]
    builder = DuckDBServingSnapshotBuilder(
        FakeParquetExporter(parquet_sources),
        output_path=tmp_path / "serving" / "nba_serving.duckdb",
    )

    with pytest.raises(SnapshotBuildError, match="empty required sources"):
        builder.build_snapshot()


class _FakePaginator:
    def __init__(self, objects: list[dict[str, object]]):
        self._objects = objects

    def paginate(self, Bucket: str, Prefix: str):  # noqa: N803
        matching = [item for item in self._objects if str(item["Key"]).startswith(Prefix)]
        yield {"Contents": matching}


class _FakeS3Client:
    def __init__(self, bucket: str, objects: dict[str, bytes]):
        self._bucket = bucket
        self._objects = objects

    def get_paginator(self, name: str) -> _FakePaginator:
        assert name == "list_objects_v2"
        object_rows = [{"Key": key, "Size": len(payload)} for key, payload in self._objects.items()]
        return _FakePaginator(object_rows)

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        assert bucket == self._bucket
        Path(destination).write_bytes(self._objects[key])


def _make_exporter(objects: dict[str, bytes]) -> AthenaSourceParquetExporter:
    settings = DuckDBServingSnapshotSettings(
        athena_database="nba_analytics",
        athena_output_location="s3://example/athena-results/",
        athena_workgroup="primary",
        athena_catalog="AwsDataCatalog",
        aws_region="us-east-1",
        output_path=Path("/tmp/nba_serving.duckdb"),
        athena_unload_prefix="s3://example/athena-results/duckdb-serving-unload",
    )
    exporter = AthenaSourceParquetExporter(settings)
    exporter._s3 = _FakeS3Client("example", objects)  # pyright: ignore[reportAttributeAccessIssue]
    return exporter


def test_exporter_accepts_extensionless_athena_unload_parquet(tmp_path: Path):
    prefix = "athena-results/duckdb-serving-unload/run-1/agg_player_season/"
    data_key = prefix + "20260401_204818_00205_srt9m_file"
    exporter = _make_exporter(
        {
            data_key: _parquet_bytes(pa.table({"season_year": ["2024-25"], "season_type": ["regular_season"]})),
        }
    )

    downloaded = exporter._download_parquet_objects("s3://example/" + prefix, tmp_path)  # pyright: ignore[reportPrivateUsage]

    assert len(downloaded) == 1
    assert downloaded[0].name.endswith(".parquet")
    assert downloaded[0].read_bytes()[:4] == b"PAR1"


def test_exporter_skips_manifest_metadata_zero_byte_and_invalid_candidates(tmp_path: Path):
    prefix = "athena-results/duckdb-serving-unload/run-2/agg_player_season/"
    objects = {
        prefix + "data-file.parquet": _parquet_bytes(pa.table({"season_year": ["2024-25"]})),
        prefix + "manifest.manifest": b'{"entries":[]}',
        prefix + "metadata.metadata": b"metadata",
        prefix + "folder/": b"",
        prefix + "zero-byte-file": b"",
        prefix + "not-parquet": b"plain-text",
    }
    exporter = _make_exporter(objects)

    downloaded = exporter._download_parquet_objects("s3://example/" + prefix, tmp_path)  # pyright: ignore[reportPrivateUsage]

    assert [path.name for path in downloaded] == ["data-file.parquet"]
    assert not (tmp_path / "not-parquet.parquet").exists()


def test_exporter_raises_when_no_valid_parquet_objects_exist(tmp_path: Path):
    prefix = "athena-results/duckdb-serving-unload/run-3/agg_player_season/"
    exporter = _make_exporter(
        {
            prefix + "manifest.manifest": b'{"entries":[]}',
            prefix + "metadata.metadata": b"metadata",
            prefix + "not-parquet": b"plain-text",
        }
    )

    with pytest.raises(SnapshotBuildError, match="No parquet exports found"):
        exporter._download_parquet_objects("s3://example/" + prefix, tmp_path)  # pyright: ignore[reportPrivateUsage]
