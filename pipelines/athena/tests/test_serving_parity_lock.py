from __future__ import annotations

from pathlib import Path

import duckdb

from pipelines.athena.quality.serving_parity_lock import (
    LocalSnapshotState,
    SourceState,
    build_serving_quality_rows,
    inspect_local_snapshot,
)


def test_build_serving_quality_rows_marks_matching_source_ok():
    local_snapshot = LocalSnapshotState(
        path=Path("/tmp/nba_serving.duckdb"),
        exists=True,
        built_at_utc="2026-05-11T00:00:00Z",
        snapshot_scope_version="duckdb_serving_contract_v3",
        sources={"player": SourceState(10, ("player_id", "name"), "ok")},
    )
    athena_states = {"player": SourceState(10, ("player_id", "name"), "ok")}

    rows = build_serving_quality_rows(
        run_id="run_1",
        run_date="2026-05-11",
        local_snapshot=local_snapshot,
        athena_states=athena_states,
        required_sources=("player",),
        athena_database="semantic_gold",
    )

    assert rows[0]["quality_status"] == "ok"
    assert rows[0]["row_count_delta"] == 0
    assert rows[0]["local_only_columns"] is None
    assert rows[0]["athena_only_columns"] is None


def test_build_serving_quality_rows_detects_row_count_mismatch():
    local_snapshot = LocalSnapshotState(
        path=Path("/tmp/nba_serving.duckdb"),
        exists=True,
        built_at_utc=None,
        snapshot_scope_version=None,
        sources={"player": SourceState(9, ("player_id",), "ok")},
    )
    athena_states = {"player": SourceState(10, ("player_id",), "ok")}

    rows = build_serving_quality_rows(
        run_id="run_1",
        run_date="2026-05-11",
        local_snapshot=local_snapshot,
        athena_states=athena_states,
        required_sources=("player",),
        athena_database="semantic_gold",
    )

    assert rows[0]["quality_status"] == "row_count_mismatch"
    assert rows[0]["row_count_delta"] == -1


def test_build_serving_quality_rows_detects_schema_mismatch():
    local_snapshot = LocalSnapshotState(
        path=Path("/tmp/nba_serving.duckdb"),
        exists=True,
        built_at_utc=None,
        snapshot_scope_version=None,
        sources={"player": SourceState(10, ("player_id", "local_extra"), "ok")},
    )
    athena_states = {"player": SourceState(10, ("player_id", "athena_extra"), "ok")}

    rows = build_serving_quality_rows(
        run_id="run_1",
        run_date="2026-05-11",
        local_snapshot=local_snapshot,
        athena_states=athena_states,
        required_sources=("player",),
        athena_database="semantic_gold",
    )

    assert rows[0]["quality_status"] == "schema_mismatch"
    assert rows[0]["local_only_columns"] == "local_extra"
    assert rows[0]["athena_only_columns"] == "athena_extra"


def test_build_serving_quality_rows_prefers_local_error_status():
    local_snapshot = LocalSnapshotState(
        path=Path("/tmp/missing.duckdb"),
        exists=False,
        built_at_utc=None,
        snapshot_scope_version=None,
        sources={"player": SourceState(None, (), "missing_snapshot", "missing")},
    )
    athena_states = {"player": SourceState(10, ("player_id",), "ok")}

    rows = build_serving_quality_rows(
        run_id="run_1",
        run_date="2026-05-11",
        local_snapshot=local_snapshot,
        athena_states=athena_states,
        required_sources=("player",),
        athena_database="semantic_gold",
    )

    assert rows[0]["quality_status"] == "missing_snapshot"
    assert rows[0]["error_message"] == "missing"


def test_inspect_local_snapshot_reads_column_names_not_types(tmp_path: Path):
    snapshot_path = tmp_path / "snapshot.duckdb"
    with duckdb.connect(str(snapshot_path)) as conn:
        conn.execute('CREATE TABLE "player" ("player_id" BIGINT, "name" VARCHAR)')

    snapshot = inspect_local_snapshot(snapshot_path, ("player",))

    assert snapshot.sources["player"].columns == ("player_id", "name")
