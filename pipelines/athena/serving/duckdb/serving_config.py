from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_NBA_ANALYTICS_DUCKDB_BUILDER_ENV_NAMES: tuple[str, ...] = (
    "ATHENA_DATABASE",
    "ATHENA_OUTPUT_LOCATION",
    "ATHENA_WORKGROUP",
    "ATHENA_CATALOG",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
    "NBA_ANALYTICS_API_DUCKDB_SERVING_DB_PATH",
    "OPENUI_API_DUCKDB_SERVING_DB_PATH",
    "DUCKDB_SERVING_DB_PATH",
    "NBA_ANALYTICS_API_DUCKDB_ATHENA_UNLOAD_PREFIX",
    "OPENUI_API_DUCKDB_ATHENA_UNLOAD_PREFIX",
    "DUCKDB_ATHENA_UNLOAD_PREFIX",
    "ATHENA_TIMEOUT_SECONDS",
    "ATHENA_POLL_INTERVAL_SECONDS",
)
_EMITTED_DEPRECATION_WARNINGS: set[str] = set()


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _has_value(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def _warn_once(key: str, message: str) -> None:
    if key in _EMITTED_DEPRECATION_WARNINGS:
        return
    _EMITTED_DEPRECATION_WARNINGS.add(key)
    warnings.warn(message, UserWarning, stacklevel=2)


def _load_primary_then_root_fallback(
    *,
    primary_env_path: Path,
    root_env_path: Path,
    relevant_names: tuple[str, ...],
    warning_key: str,
    warning_owner: str,
) -> None:
    load_dotenv(primary_env_path, override=False)
    if not root_env_path.exists():
        return
    before_root = {name: os.getenv(name) for name in relevant_names}
    load_dotenv(root_env_path, override=False)
    fallback_names = sorted(name for name in relevant_names if not _has_value(before_root[name]) and _has_value(os.getenv(name)))
    if fallback_names:
        joined = ", ".join(fallback_names)
        _warn_once(
            warning_key,
            (
                f"{warning_owner} is using the deprecated repo root .env fallback for: {joined}. "
                f"Move these values into {primary_env_path}."
            ),
        )


@dataclass(frozen=True)
class DuckDBServingSnapshotSettings:
    athena_database: str
    athena_output_location: str
    athena_workgroup: str
    athena_catalog: str
    aws_region: str
    output_path: Path
    athena_unload_prefix: str
    athena_timeout_seconds: float = 300.0
    athena_poll_interval_seconds: float = 1.0

    @property
    def athena_configured(self) -> bool:
        return bool(self.athena_database and self.athena_output_location and self.aws_region and self.athena_unload_prefix)

    @classmethod
    def from_env(
        cls,
        *,
        builder_dir: Path | None = None,
        repo_root: Path | None = None,
    ) -> DuckDBServingSnapshotSettings:
        resolved_builder_dir = builder_dir or Path(__file__).resolve().parent
        resolved_repo_root = repo_root or Path(__file__).resolve().parents[4]
        _load_primary_then_root_fallback(
            primary_env_path=resolved_builder_dir / ".env",
            root_env_path=resolved_repo_root / ".env",
            relevant_names=_NBA_ANALYTICS_DUCKDB_BUILDER_ENV_NAMES,
            warning_key="duckdb_builder_root_env_fallback",
            warning_owner="duckdb snapshot builder",
        )
        athena_output_location = os.getenv("ATHENA_OUTPUT_LOCATION", "").strip()
        default_output_path = resolved_repo_root / "data" / "serving" / "nba_serving.duckdb"
        default_unload_prefix = f"{athena_output_location.rstrip('/')}/duckdb-serving-unload" if athena_output_location else ""
        return cls(
            athena_database=os.getenv("ATHENA_DATABASE", "legacy_gold").strip() or "legacy_gold",
            athena_output_location=athena_output_location,
            athena_workgroup=os.getenv("ATHENA_WORKGROUP", "primary").strip() or "primary",
            athena_catalog=os.getenv("ATHENA_CATALOG", "AwsDataCatalog").strip() or "AwsDataCatalog",
            aws_region=_first_env("AWS_DEFAULT_REGION", "AWS_REGION", default=""),
            output_path=Path(
                _first_env(
                    "NBA_ANALYTICS_API_DUCKDB_SERVING_DB_PATH",
                    "OPENUI_API_DUCKDB_SERVING_DB_PATH",
                    "DUCKDB_SERVING_DB_PATH",
                    default=str(default_output_path),
                )
            ),
            athena_unload_prefix=_first_env(
                "NBA_ANALYTICS_API_DUCKDB_ATHENA_UNLOAD_PREFIX",
                "OPENUI_API_DUCKDB_ATHENA_UNLOAD_PREFIX",
                "DUCKDB_ATHENA_UNLOAD_PREFIX",
                default=default_unload_prefix,
            ),
            athena_timeout_seconds=float(os.getenv("ATHENA_TIMEOUT_SECONDS", "300")),
            athena_poll_interval_seconds=float(os.getenv("ATHENA_POLL_INTERVAL_SECONDS", "1")),
        )
