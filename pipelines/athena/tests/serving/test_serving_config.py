from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pipelines.athena.serving.duckdb import serving_config as serving_config_module


def _write_env(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _clear_env(monkeypatch) -> None:  # noqa: ANN001
    for name in serving_config_module._DUCKDB_BUILDER_ENV_NAMES:  # pyright: ignore[reportPrivateUsage]
        monkeypatch.delenv(name, raising=False)


def test_builder_settings_prefer_builder_local_env(monkeypatch, tmp_path: Path):
    _clear_env(monkeypatch)
    serving_config_module._EMITTED_DEPRECATION_WARNINGS.clear()  # pyright: ignore[reportPrivateUsage]
    repo_root = tmp_path / "repo"
    builder_dir = repo_root / "pipelines" / "athena" / "serving" / "duckdb"
    _write_env(
        builder_dir / ".env",
        """
        ATHENA_DATABASE=builder_db
        ATHENA_OUTPUT_LOCATION=s3://builder-results/
        AWS_DEFAULT_REGION=us-east-1
        DUCKDB_SERVING_DB_PATH=/tmp/builder.duckdb
        DUCKDB_ATHENA_UNLOAD_PREFIX=s3://builder-results/duckdb-serving-unload
        """,
    )
    _write_env(
        repo_root / ".env",
        """
        ATHENA_DATABASE=root_db
        ATHENA_OUTPUT_LOCATION=s3://root-results/
        AWS_DEFAULT_REGION=us-west-2
        DUCKDB_SERVING_DB_PATH=/tmp/root.duckdb
        DUCKDB_ATHENA_UNLOAD_PREFIX=s3://root-results/duckdb-serving-unload
        """,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        settings = serving_config_module.DuckDBServingSnapshotSettings.from_env(
            builder_dir=builder_dir,
            repo_root=repo_root,
        )

    assert settings.athena_database == "builder_db"
    assert settings.athena_output_location == "s3://builder-results/"
    assert settings.aws_region == "us-east-1"
    assert str(settings.output_path) == "/tmp/builder.duckdb"
    assert settings.athena_unload_prefix == "s3://builder-results/duckdb-serving-unload"
    assert caught == []


def test_builder_settings_use_deprecated_root_fallback(monkeypatch, tmp_path: Path):
    _clear_env(monkeypatch)
    serving_config_module._EMITTED_DEPRECATION_WARNINGS.clear()  # pyright: ignore[reportPrivateUsage]
    repo_root = tmp_path / "repo"
    builder_dir = repo_root / "pipelines" / "athena" / "serving" / "duckdb"
    _write_env(builder_dir / ".env", "")
    _write_env(
        repo_root / ".env",
        """
        ATHENA_DATABASE=root_db
        ATHENA_OUTPUT_LOCATION=s3://root-results/
        AWS_DEFAULT_REGION=us-east-1
        DUCKDB_SERVING_DB_PATH=/tmp/root.duckdb
        DUCKDB_ATHENA_UNLOAD_PREFIX=s3://root-results/duckdb-serving-unload
        """,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        settings = serving_config_module.DuckDBServingSnapshotSettings.from_env(
            builder_dir=builder_dir,
            repo_root=repo_root,
        )

    assert settings.athena_database == "root_db"
    assert str(settings.output_path) == "/tmp/root.duckdb"
    assert len(caught) == 1
    assert "deprecated repo root .env fallback" in str(caught[0].message)


def test_builder_settings_emit_root_fallback_warning_only_once(monkeypatch, tmp_path: Path):
    _clear_env(monkeypatch)
    serving_config_module._EMITTED_DEPRECATION_WARNINGS.clear()  # pyright: ignore[reportPrivateUsage]
    repo_root = tmp_path / "repo"
    builder_dir = repo_root / "pipelines" / "athena" / "serving" / "duckdb"
    _write_env(
        repo_root / ".env",
        """
        ATHENA_DATABASE=root_db
        ATHENA_OUTPUT_LOCATION=s3://root-results/
        AWS_DEFAULT_REGION=us-east-1
        DUCKDB_SERVING_DB_PATH=/tmp/root.duckdb
        DUCKDB_ATHENA_UNLOAD_PREFIX=s3://root-results/duckdb-serving-unload
        """,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        serving_config_module.DuckDBServingSnapshotSettings.from_env(
            builder_dir=builder_dir,
            repo_root=repo_root,
        )
        serving_config_module.DuckDBServingSnapshotSettings.from_env(
            builder_dir=builder_dir,
            repo_root=repo_root,
        )

    assert len(caught) == 1


def test_builder_settings_normalize_stale_repo_output_path(monkeypatch, tmp_path: Path):
    _clear_env(monkeypatch)
    serving_config_module._EMITTED_DEPRECATION_WARNINGS.clear()  # pyright: ignore[reportPrivateUsage]
    repo_root = tmp_path / "nba_analyst"
    stale_root = tmp_path / "nba-analytics-lakehouse"
    builder_dir = repo_root / "pipelines" / "athena" / "serving" / "duckdb"
    stale_output_path = stale_root / "data" / "serving" / "nba_serving.duckdb"
    _write_env(
        builder_dir / ".env",
        f"""
        ATHENA_DATABASE=builder_db
        ATHENA_OUTPUT_LOCATION=s3://builder-results/
        AWS_DEFAULT_REGION=us-east-1
        DUCKDB_SERVING_DB_PATH={stale_output_path}
        DUCKDB_ATHENA_UNLOAD_PREFIX=s3://builder-results/duckdb-serving-unload
        """,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        settings = serving_config_module.DuckDBServingSnapshotSettings.from_env(
            builder_dir=builder_dir,
            repo_root=repo_root,
        )

    assert settings.output_path == repo_root / "data" / "serving" / "nba_serving.duckdb"
    assert len(caught) == 1
    assert "ignored stale output path" in str(caught[0].message)
