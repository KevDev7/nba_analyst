from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

try:
    from pipelines.athena.quality.quality_manifest import (
        DEFAULT_BUCKET,
        KNOWN_GRAIN_COLUMNS,
        build_quality_manifest,
        load_registry,
        manifest_key,
        quality_result_key,
    )
    from pipelines.athena.quality.registration import refresh_quality_athena_tables
    from pipelines.ingestion.source_manifest import DEFAULT_BACKFILL_SEASONS, infer_source_family
except ModuleNotFoundError:
    import sys

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.athena.quality.quality_manifest import (
        DEFAULT_BUCKET,
        KNOWN_GRAIN_COLUMNS,
        build_quality_manifest,
        load_registry,
        manifest_key,
        quality_result_key,
    )
    from pipelines.athena.quality.registration import refresh_quality_athena_tables
    from pipelines.ingestion.source_manifest import DEFAULT_BACKFILL_SEASONS, infer_source_family


@dataclass(frozen=True)
class SourceLocation:
    source_key: str | None
    source_prefix: str | None
    is_exact_key: bool


PROFILE_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("artifact_id", pa.string()),
        ("layer", pa.string()),
        ("artifact_type", pa.string()),
        ("source_key", pa.string()),
        ("source_prefix", pa.string()),
        ("is_exact_key", pa.bool_()),
        ("object_count", pa.int64()),
        ("total_size_bytes", pa.int64()),
        ("latest_last_modified_utc", pa.string()),
        ("sample_key", pa.string()),
        ("sample_row_count", pa.int64()),
        ("profile_status", pa.string()),
        ("error_message", pa.string()),
    ]
)

SCHEMA_SNAPSHOT_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("artifact_id", pa.string()),
        ("layer", pa.string()),
        ("sample_key", pa.string()),
        ("field_index", pa.int64()),
        ("column_name", pa.string()),
        ("data_type", pa.string()),
        ("nullable", pa.bool_()),
        ("schema_status", pa.string()),
    ]
)

SOURCE_COMPLETENESS_SCHEMA = pa.schema(
    list(PROFILE_SCHEMA)
    + [
        pa.field("dataset", pa.string()),
        pa.field("source_family", pa.string()),
        pa.field("completeness_grain", pa.string()),
        pa.field("season_year", pa.string()),
        pa.field("expected_object_count", pa.int64()),
        pa.field("observed_object_count", pa.int64()),
        pa.field("missing_object_count", pa.int64()),
        pa.field("source_completeness_status", pa.string()),
    ]
)
QUARANTINE_SUMMARY_SCHEMA = PROFILE_SCHEMA.append(pa.field("dataset", pa.string()))
DEFAULT_EXPECTED_SEASONS = DEFAULT_BACKFILL_SEASONS
SEASON_PARTITION_RE = re.compile(r"/season=([^/]+)/")
GAME_ID_RE = re.compile(r"/game_id=([0-9]{10})")
SNAPSHOT_DATE_RE = re.compile(r"/snapshot_date=([0-9]{4})-([0-9]{2})-[0-9]{2}/")

ANOMALY_SUMMARY_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("layer", pa.string()),
        ("profile_status", pa.string()),
        ("artifact_count", pa.int64()),
    ]
)

ROW_COUNT_TREND_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("artifact_id", pa.string()),
        ("layer", pa.string()),
        ("current_sample_row_count", pa.int64()),
        ("previous_run_id", pa.string()),
        ("previous_run_date", pa.string()),
        ("previous_sample_row_count", pa.int64()),
        ("row_count_delta", pa.int64()),
        ("row_count_delta_pct", pa.float64()),
        ("current_profile_status", pa.string()),
        ("previous_profile_status", pa.string()),
        ("trend_status", pa.string()),
    ]
)

SCHEMA_DRIFT_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("artifact_id", pa.string()),
        ("layer", pa.string()),
        ("column_name", pa.string()),
        ("current_data_type", pa.string()),
        ("previous_data_type", pa.string()),
        ("current_nullable", pa.bool_()),
        ("previous_nullable", pa.bool_()),
        ("drift_type", pa.string()),
        ("drift_status", pa.string()),
        ("previous_run_id", pa.string()),
        ("previous_run_date", pa.string()),
    ]
)

GRAIN_CHECK_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("artifact_id", pa.string()),
        ("layer", pa.string()),
        ("sample_key", pa.string()),
        ("grain_columns", pa.string()),
        ("total_rows", pa.int64()),
        ("distinct_grain_rows", pa.int64()),
        ("duplicate_grain_rows", pa.int64()),
        ("null_grain_rows", pa.int64()),
        ("grain_status", pa.string()),
        ("error_message", pa.string()),
    ]
)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def source_location(destination_key: str | None) -> SourceLocation:
    if not destination_key:
        return SourceLocation(None, None, False)

    wildcard_indexes = [
        index
        for marker in ("*", "<")
        if (index := destination_key.find(marker)) >= 0
    ]
    if not wildcard_indexes:
        return SourceLocation(destination_key, destination_key.rsplit("/", 1)[0] + "/", True)

    marker_index = min(wildcard_indexes)
    prefix = destination_key[:marker_index].rsplit("/", 1)[0] + "/"
    return SourceLocation(destination_key, prefix, False)


def list_objects(s3_client, *, bucket: str, prefix: str) -> list[dict[str, Any]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects.extend(page.get("Contents", []))
    return sorted(objects, key=lambda obj: obj.get("Key", ""))


def expected_quality_seasons() -> tuple[str, ...]:
    return DEFAULT_EXPECTED_SEASONS


def season_label_from_start_year(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def season_year_from_game_id(game_id: str) -> str | None:
    if len(game_id) != 10 or not game_id.isdigit():
        return None
    start_year_suffix = int(game_id[3:5])
    start_year = 1900 + start_year_suffix if start_year_suffix >= 70 else 2000 + start_year_suffix
    return season_label_from_start_year(start_year)


def season_year_from_key(key: str) -> str | None:
    season_match = SEASON_PARTITION_RE.search(f"/{key}")
    if season_match:
        value = season_match.group(1)
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}", value):
            return value
        if re.fullmatch(r"[0-9]{4}", value):
            return season_label_from_start_year(int(value))

    game_match = GAME_ID_RE.search(f"/{key}")
    if game_match:
        return season_year_from_game_id(game_match.group(1))

    snapshot_match = SNAPSHOT_DATE_RE.search(f"/{key}")
    if snapshot_match:
        year = int(snapshot_match.group(1))
        month = int(snapshot_match.group(2))
        start_year = year if month >= 10 else year - 1
        return season_label_from_start_year(start_year)

    return None


def completeness_grain_for_destination(destination_key: str | None) -> str:
    if not destination_key:
        return "unknown"
    if "season=" in destination_key:
        return "source_season"
    if "game_id=" in destination_key or "<GAME_ID>" in destination_key:
        return "source_season"
    if "snapshot_date=" in destination_key or "<YYYY-MM-DD>" in destination_key:
        return "source_snapshot_date"
    return "source"


def source_completeness_status(
    *,
    profile_status: str,
    expected_object_count: int | None,
    observed_object_count: int,
) -> str:
    if profile_status == "error":
        return "error"
    if expected_object_count is not None and observed_object_count < expected_object_count:
        return "missing_expected_objects"
    if observed_object_count == 0:
        return "missing"
    return "ok"


def head_object(s3_client, *, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return s3_client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def read_parquet_schema_and_count(
    s3_client,
    *,
    bucket: str,
    key: str,
    max_schema_object_bytes: int,
) -> tuple[pa.Schema | None, int | None, str | None]:
    metadata = head_object(s3_client, bucket=bucket, key=key)
    if metadata is None:
        return None, None, "missing_sample_object"
    size = int(metadata.get("ContentLength") or 0)
    if size > max_schema_object_bytes:
        return None, None, f"sample_object_too_large:{size}"

    response = s3_client.get_object(Bucket=bucket, Key=key)
    payload = response["Body"].read()
    parquet_file = pq.ParquetFile(io.BytesIO(payload))
    row_count = sum(parquet_file.metadata.row_group(index).num_rows for index in range(parquet_file.metadata.num_row_groups))
    return parquet_file.schema_arrow, row_count, None


def read_parquet_table(
    s3_client,
    *,
    bucket: str,
    key: str,
    max_object_bytes: int,
) -> tuple[pa.Table | None, str | None]:
    metadata = head_object(s3_client, bucket=bucket, key=key)
    if metadata is None:
        return None, "missing_sample_object"
    size = int(metadata.get("ContentLength") or 0)
    if size > max_object_bytes:
        return None, f"sample_object_too_large:{size}"

    response = s3_client.get_object(Bucket=bucket, Key=key)
    payload = response["Body"].read()
    return pq.read_table(io.BytesIO(payload)), None


def latest_object(objects: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [obj for obj in objects if not str(obj.get("Key", "")).endswith("/")]
    if not candidates:
        return None
    return max(candidates, key=lambda obj: obj.get("LastModified") or datetime.min.replace(tzinfo=timezone.utc))


def write_parquet_rows(
    s3_client,
    *,
    bucket: str,
    key: str,
    rows: list[dict[str, Any]],
    schema: pa.Schema | None = None,
) -> None:
    table = pa.Table.from_pylist(rows, schema=schema) if schema else pa.Table.from_pylist(rows)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )


def read_parquet_rows(s3_client, *, bucket: str, key: str) -> list[dict[str, Any]]:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    payload = response["Body"].read()
    return pq.read_table(io.BytesIO(payload)).to_pylist()


def list_quality_result_keys(
    s3_client,
    *,
    bucket: str,
    dataset: str,
    artifact_id: str,
) -> list[str]:
    prefix = quality_result_key(dataset, artifact_id, "", "").split("run_date=", 1)[0]
    objects = list_objects(s3_client, bucket=bucket, prefix=prefix)
    return [
        str(obj["Key"])
        for obj in objects
        if str(obj.get("Key", "")).endswith(".parquet")
    ]


def historical_quality_rows(
    s3_client,
    *,
    bucket: str,
    dataset: str,
    artifact_id: str,
    current_run_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in list_quality_result_keys(
        s3_client,
        bucket=bucket,
        dataset=dataset,
        artifact_id=artifact_id,
    ):
        for row in read_parquet_rows(s3_client, bucket=bucket, key=key):
            if row.get("run_id") != current_run_id:
                rows.append(row)
    return rows


def write_json(
    s3_client,
    *,
    bucket: str,
    key: str,
    payload: dict[str, Any],
) -> None:
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
    )


def profile_artifact(
    s3_client,
    *,
    bucket: str,
    artifact: dict[str, Any],
    run_id: str,
    run_date: str,
    max_schema_object_bytes: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    location = source_location(artifact.get("destination_key"))
    objects: list[dict[str, Any]] = []
    error_message = None

    try:
        if location.is_exact_key and location.source_key:
            head = head_object(s3_client, bucket=bucket, key=location.source_key)
            if head:
                objects = [{"Key": location.source_key, **head}]
        elif location.source_prefix:
            objects = list_objects(s3_client, bucket=bucket, prefix=location.source_prefix)
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"

    real_objects = [obj for obj in objects if not str(obj.get("Key", "")).endswith("/")]
    newest = latest_object(real_objects)
    sample_key = str(newest.get("Key")) if newest else None
    row_count: int | None = None
    schema: pa.Schema | None = None
    schema_error: str | None = None

    if sample_key and sample_key.endswith(".parquet"):
        schema, row_count, schema_error = read_parquet_schema_and_count(
            s3_client,
            bucket=bucket,
            key=sample_key,
            max_schema_object_bytes=max_schema_object_bytes,
        )

    profile_status = "ok"
    if error_message:
        profile_status = "error"
    elif not real_objects and artifact.get("destination_key"):
        profile_status = "missing"
    elif schema_error:
        profile_status = "partial"

    profile = {
        "run_id": run_id,
        "run_date": run_date,
        "artifact_id": artifact["id"],
        "layer": artifact["layer"],
        "artifact_type": artifact["artifact_type"],
        "source_key": location.source_key,
        "source_prefix": location.source_prefix,
        "is_exact_key": location.is_exact_key,
        "object_count": len(real_objects),
        "total_size_bytes": sum(int(obj.get("Size") or obj.get("ContentLength") or 0) for obj in real_objects),
        "latest_last_modified_utc": iso_utc(newest.get("LastModified")) if newest else None,
        "sample_key": sample_key,
        "sample_row_count": row_count,
        "profile_status": profile_status,
        "error_message": error_message or schema_error,
    }

    schema_rows: list[dict[str, Any]] = []
    if schema is not None:
        for index, field in enumerate(schema):
            schema_rows.append(
                {
                    "run_id": run_id,
                    "run_date": run_date,
                    "artifact_id": artifact["id"],
                    "layer": artifact["layer"],
                    "sample_key": sample_key,
                    "field_index": index,
                    "column_name": field.name,
                    "data_type": str(field.type),
                    "nullable": bool(field.nullable),
                    "schema_status": "ok",
                }
            )
    else:
        schema_rows.append(
            {
                "run_id": run_id,
                "run_date": run_date,
                "artifact_id": artifact["id"],
                "layer": artifact["layer"],
                "sample_key": sample_key,
                "field_index": None,
                "column_name": None,
                "data_type": None,
                "nullable": None,
                "schema_status": profile_status if sample_key else "missing",
            }
        )

    return profile, schema_rows


def source_object_keys_for_artifact(
    s3_client,
    *,
    bucket: str,
    artifact: dict[str, Any],
) -> list[str]:
    location = source_location(artifact.get("destination_key"))
    if location.is_exact_key and location.source_key:
        return [location.source_key] if head_object(s3_client, bucket=bucket, key=location.source_key) else []
    if location.source_prefix:
        return [
            str(obj.get("Key"))
            for obj in list_objects(s3_client, bucket=bucket, prefix=location.source_prefix)
            if obj.get("Key") and not str(obj.get("Key")).endswith("/")
        ]
    return []


def build_source_completeness_rows(
    *,
    artifact: dict[str, Any],
    profile: dict[str, Any],
    object_keys: list[str],
    expected_seasons: tuple[str, ...] = DEFAULT_EXPECTED_SEASONS,
) -> list[dict[str, Any]]:
    destination_key = artifact.get("destination_key")
    source_family = infer_source_family(destination_key or "")
    completeness_grain = completeness_grain_for_destination(destination_key)
    profile_status = str(profile.get("profile_status") or "unknown")

    def row_for_scope(
        *,
        season_year: str | None,
        observed_count: int,
        expected_count: int | None,
    ) -> dict[str, Any]:
        missing_count = (
            max(expected_count - observed_count, 0)
            if expected_count is not None
            else None
        )
        return {
            **profile,
            "dataset": "source_completeness",
            "source_family": source_family,
            "completeness_grain": completeness_grain,
            "season_year": season_year,
            "expected_object_count": expected_count,
            "observed_object_count": observed_count,
            "missing_object_count": missing_count,
            "source_completeness_status": source_completeness_status(
                profile_status=profile_status,
                expected_object_count=expected_count,
                observed_object_count=observed_count,
            ),
        }

    if completeness_grain != "source_season":
        expected_count = 1 if profile.get("is_exact_key") else None
        return [
            row_for_scope(
                season_year=None,
                observed_count=int(profile.get("object_count") or 0),
                expected_count=expected_count,
            )
        ]

    observed_by_season = Counter(
        season_year
        for key in object_keys
        if (season_year := season_year_from_key(key)) is not None
    )
    rows = [
        row_for_scope(
            season_year=season_year,
            observed_count=int(observed_by_season.get(season_year, 0)),
            expected_count=1,
        )
        for season_year in expected_seasons
    ]

    extra_seasons = sorted(set(observed_by_season) - set(expected_seasons))
    rows.extend(
        row_for_scope(
            season_year=season_year,
            observed_count=int(observed_by_season[season_year]),
            expected_count=None,
        )
        for season_year in extra_seasons
    )
    if not rows:
        rows.append(row_for_scope(season_year=None, observed_count=0, expected_count=None))
    return rows


def _latest_row_by_artifact(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        artifact_id = str(row.get("artifact_id") or "")
        if not artifact_id:
            continue
        current_key = (str(row.get("run_date") or ""), str(row.get("run_id") or ""))
        previous = latest.get(artifact_id)
        previous_key = (
            str(previous.get("run_date") or ""),
            str(previous.get("run_id") or ""),
        ) if previous else ("", "")
        if previous is None or current_key > previous_key:
            latest[artifact_id] = row
    return latest


def build_row_count_trends(
    profiles: list[dict[str, Any]],
    historical_profiles: list[dict[str, Any]],
    *,
    run_id: str,
    run_date: str,
) -> list[dict[str, Any]]:
    previous_by_artifact = _latest_row_by_artifact(historical_profiles)
    rows: list[dict[str, Any]] = []

    for profile in profiles:
        previous = previous_by_artifact.get(profile["artifact_id"])
        current_count = profile.get("sample_row_count")
        previous_count = previous.get("sample_row_count") if previous else None
        delta = (
            int(current_count) - int(previous_count)
            if current_count is not None and previous_count is not None
            else None
        )
        delta_pct = (
            float(delta) / float(previous_count)
            if delta is not None and previous_count not in {None, 0}
            else None
        )

        if previous is None:
            trend_status = "no_history"
        elif current_count is None:
            trend_status = "current_missing_row_count"
        elif previous_count is None:
            trend_status = "previous_missing_row_count"
        elif delta == 0:
            trend_status = "stable"
        else:
            trend_status = "changed"

        rows.append(
            {
                "run_id": run_id,
                "run_date": run_date,
                "artifact_id": profile["artifact_id"],
                "layer": profile["layer"],
                "current_sample_row_count": current_count,
                "previous_run_id": previous.get("run_id") if previous else None,
                "previous_run_date": previous.get("run_date") if previous else None,
                "previous_sample_row_count": previous_count,
                "row_count_delta": delta,
                "row_count_delta_pct": delta_pct,
                "current_profile_status": profile["profile_status"],
                "previous_profile_status": previous.get("profile_status") if previous else None,
                "trend_status": trend_status,
            }
        )

    return rows


def _schema_rows_by_latest_run(
    rows: list[dict[str, Any]],
) -> dict[str, tuple[dict[str, Any], dict[str, dict[str, Any]]]]:
    grouped: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = {}
    for row in rows:
        artifact_id = str(row.get("artifact_id") or "")
        column_name = row.get("column_name")
        if not artifact_id or column_name is None:
            continue
        run_key = (str(row.get("run_date") or ""), str(row.get("run_id") or ""))
        grouped.setdefault(artifact_id, {}).setdefault(run_key, []).append(row)

    latest: dict[str, tuple[dict[str, Any], dict[str, dict[str, Any]]]] = {}
    for artifact_id, rows_by_run in grouped.items():
        latest_key = max(rows_by_run)
        run_rows = rows_by_run[latest_key]
        run_info = {
            "run_date": latest_key[0],
            "run_id": latest_key[1],
        }
        latest[artifact_id] = (
            run_info,
            {str(row["column_name"]): row for row in run_rows},
        )
    return latest


def build_schema_drift_rows(
    schema_rows: list[dict[str, Any]],
    historical_schema_rows: list[dict[str, Any]],
    *,
    run_id: str,
    run_date: str,
) -> list[dict[str, Any]]:
    previous_by_artifact = _schema_rows_by_latest_run(historical_schema_rows)
    current_by_artifact = _schema_rows_by_latest_run(schema_rows)
    rows: list[dict[str, Any]] = []

    for artifact_id, (_current_run, current_columns) in sorted(current_by_artifact.items()):
        previous_run, previous_columns = previous_by_artifact.get(
            artifact_id,
            ({"run_id": None, "run_date": None}, {}),
        )
        column_names = sorted(set(current_columns) | set(previous_columns))
        for column_name in column_names:
            current = current_columns.get(column_name)
            previous = previous_columns.get(column_name)
            if previous is None:
                drift_type = "no_history" if not previous_columns else "added_column"
            elif current is None:
                drift_type = "removed_column"
            elif current.get("data_type") != previous.get("data_type"):
                drift_type = "type_changed"
            elif current.get("nullable") != previous.get("nullable"):
                drift_type = "nullable_changed"
            else:
                drift_type = "unchanged"

            rows.append(
                {
                    "run_id": run_id,
                    "run_date": run_date,
                    "artifact_id": artifact_id,
                    "layer": (current or previous or {}).get("layer"),
                    "column_name": column_name,
                    "current_data_type": current.get("data_type") if current else None,
                    "previous_data_type": previous.get("data_type") if previous else None,
                    "current_nullable": current.get("nullable") if current else None,
                    "previous_nullable": previous.get("nullable") if previous else None,
                    "drift_type": drift_type,
                    "drift_status": "ok" if drift_type == "unchanged" else drift_type,
                    "previous_run_id": previous_run.get("run_id"),
                    "previous_run_date": previous_run.get("run_date"),
                }
            )

    return rows


def grain_check_for_artifact(
    s3_client,
    *,
    bucket: str,
    artifact: dict[str, Any],
    profile: dict[str, Any],
    run_id: str,
    run_date: str,
    max_schema_object_bytes: int,
) -> dict[str, Any]:
    grain_columns = KNOWN_GRAIN_COLUMNS[artifact["id"]]
    sample_key = profile.get("sample_key")
    base_row = {
        "run_id": run_id,
        "run_date": run_date,
        "artifact_id": artifact["id"],
        "layer": artifact["layer"],
        "sample_key": sample_key,
        "grain_columns": ",".join(grain_columns),
        "total_rows": None,
        "distinct_grain_rows": None,
        "duplicate_grain_rows": None,
        "null_grain_rows": None,
        "grain_status": "unknown",
        "error_message": None,
    }

    if not sample_key:
        return {**base_row, "grain_status": "missing_sample"}
    if not str(sample_key).endswith(".parquet"):
        return {**base_row, "grain_status": "non_parquet_sample"}

    try:
        table, error_message = read_parquet_table(
            s3_client,
            bucket=bucket,
            key=str(sample_key),
            max_object_bytes=max_schema_object_bytes,
        )
        if error_message or table is None:
            return {
                **base_row,
                "grain_status": "partial",
                "error_message": error_message,
            }
        missing_columns = [column for column in grain_columns if column not in table.column_names]
        if missing_columns:
            return {
                **base_row,
                "grain_status": "missing_columns",
                "error_message": ",".join(missing_columns),
            }

        projected = table.select(grain_columns).to_pylist()
        grain_values = [
            tuple(row.get(column) for column in grain_columns)
            for row in projected
        ]
        null_rows = sum(1 for values in grain_values if any(value is None for value in values))
        distinct_rows = len(set(grain_values))
        total_rows = len(grain_values)
        duplicate_rows = total_rows - distinct_rows
        status = "duplicates" if duplicate_rows else "ok"
        if null_rows and status == "ok":
            status = "null_grain_values"

        return {
            **base_row,
            "total_rows": total_rows,
            "distinct_grain_rows": distinct_rows,
            "duplicate_grain_rows": duplicate_rows,
            "null_grain_rows": null_rows,
            "grain_status": status,
        }
    except Exception as exc:
        return {
            **base_row,
            "grain_status": "error",
            "error_message": f"{type(exc).__name__}: {exc}",
        }


def build_grain_checks(
    s3_client,
    *,
    bucket: str,
    registry: dict[str, Any],
    profiles: list[dict[str, Any]],
    run_id: str,
    run_date: str,
    max_schema_object_bytes: int,
) -> list[dict[str, Any]]:
    profiles_by_artifact = {profile["artifact_id"]: profile for profile in profiles}
    rows: list[dict[str, Any]] = []
    for artifact in registry["artifacts"]:
        if artifact["id"] not in KNOWN_GRAIN_COLUMNS:
            continue
        profile = profiles_by_artifact.get(artifact["id"])
        if profile is None:
            continue
        rows.append(
            grain_check_for_artifact(
                s3_client,
                bucket=bucket,
                artifact=artifact,
                profile=profile,
                run_id=run_id,
                run_date=run_date,
                max_schema_object_bytes=max_schema_object_bytes,
            )
        )
    return rows


def run_quality_baseline(
    *,
    bucket: str = DEFAULT_BUCKET,
    run_id: str | None = None,
    run_date: str | None = None,
    max_schema_object_bytes: int = 64_000_000,
    write_s3: bool = True,
    register_athena: bool = True,
    quality_database: str = "quality",
) -> dict[str, Any]:
    registry = load_registry()
    manifest = build_quality_manifest(registry, run_id=run_id, run_date=run_date)
    resolved_run_id = manifest["run_id"]
    resolved_run_date = manifest["run_date"]
    s3_client = boto3.client("s3")

    profiles: list[dict[str, Any]] = []
    schema_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    quarantine_rows: list[dict[str, Any]] = []

    for artifact in registry["artifacts"]:
        if artifact["artifact_type"] not in {"source", "table", "artifact"}:
            continue
        profile, artifact_schema_rows = profile_artifact(
            s3_client,
            bucket=bucket,
            artifact=artifact,
            run_id=resolved_run_id,
            run_date=resolved_run_date,
            max_schema_object_bytes=max_schema_object_bytes,
        )
        profiles.append(profile)
        schema_rows.extend(artifact_schema_rows)
        if artifact["layer"] == "raw":
            try:
                raw_object_keys = source_object_keys_for_artifact(
                    s3_client,
                    bucket=bucket,
                    artifact=artifact,
                )
                source_rows.extend(
                    build_source_completeness_rows(
                        artifact=artifact,
                        profile=profile,
                        object_keys=raw_object_keys,
                    )
                )
            except Exception as exc:
                source_rows.append(
                    {
                        **profile,
                        "dataset": "source_completeness",
                        "source_family": infer_source_family(artifact.get("destination_key") or ""),
                        "completeness_grain": completeness_grain_for_destination(artifact.get("destination_key")),
                        "season_year": None,
                        "expected_object_count": None,
                        "observed_object_count": None,
                        "missing_object_count": None,
                        "source_completeness_status": "error",
                        "error_message": f"{type(exc).__name__}: {exc}",
                    }
                )
        if artifact["layer"] == "silver":
            quarantine_artifact = {
                **artifact,
                "destination_key": f"silver/_quarantine/{artifact['name']}/",
            }
            quarantine_profile, _ = profile_artifact(
                s3_client,
                bucket=bucket,
                artifact=quarantine_artifact,
                run_id=resolved_run_id,
                run_date=resolved_run_date,
                max_schema_object_bytes=max_schema_object_bytes,
            )
            quarantine_rows.append(
                {
                    **quarantine_profile,
                    "dataset": "quarantine_summaries",
                    "source_key": f"silver/_quarantine/{artifact['name']}/",
                }
            )

    historical_profiles = historical_quality_rows(
        s3_client,
        bucket=bucket,
        dataset="table_profiles",
        artifact_id="all_artifacts",
        current_run_id=resolved_run_id,
    )
    historical_schema_rows = historical_quality_rows(
        s3_client,
        bucket=bucket,
        dataset="schema_snapshots",
        artifact_id="all_artifacts",
        current_run_id=resolved_run_id,
    )
    row_count_trend_rows = build_row_count_trends(
        profiles,
        historical_profiles,
        run_id=resolved_run_id,
        run_date=resolved_run_date,
    )
    schema_drift_rows = build_schema_drift_rows(
        schema_rows,
        historical_schema_rows,
        run_id=resolved_run_id,
        run_date=resolved_run_date,
    )
    grain_check_rows = build_grain_checks(
        s3_client,
        bucket=bucket,
        registry=registry,
        profiles=profiles,
        run_id=resolved_run_id,
        run_date=resolved_run_date,
        max_schema_object_bytes=max_schema_object_bytes,
    )

    status_counts = Counter(row["profile_status"] for row in profiles)
    anomaly_rows = [
        {
            "run_id": resolved_run_id,
            "run_date": resolved_run_date,
            "layer": layer,
            "profile_status": status,
            "artifact_count": count,
        }
        for (layer, status), count in sorted(
            Counter((row["layer"], row["profile_status"]) for row in profiles).items()
        )
    ]

    summary = {
        "run_id": resolved_run_id,
        "run_date": resolved_run_date,
        "bucket": bucket,
        "manifest_key": manifest_key(resolved_run_date, resolved_run_id),
        "artifact_count": len(registry["artifacts"]),
        "profile_count": len(profiles),
        "schema_row_count": len(schema_rows),
        "source_completeness_count": len(source_rows),
        "quarantine_summary_count": len(quarantine_rows),
        "row_count_trend_count": len(row_count_trend_rows),
        "schema_drift_count": len(schema_drift_rows),
        "grain_check_count": len(grain_check_rows),
        "profile_status_counts": dict(status_counts),
        "grain_status_counts": dict(Counter(row["grain_status"] for row in grain_check_rows)),
        "schema_drift_status_counts": dict(
            Counter(row["drift_status"] for row in schema_drift_rows)
        ),
        "generated_at_utc": iso_utc(datetime.now(timezone.utc)),
    }
    manifest["baseline_summary"] = summary

    if write_s3:
        write_json(
            s3_client,
            bucket=bucket,
            key=manifest_key(resolved_run_date, resolved_run_id),
            payload=manifest,
        )
        write_parquet_rows(
            s3_client,
            bucket=bucket,
            key=quality_result_key("table_profiles", "all_artifacts", resolved_run_date, resolved_run_id),
            rows=profiles,
            schema=PROFILE_SCHEMA,
        )
        write_parquet_rows(
            s3_client,
            bucket=bucket,
            key=quality_result_key("schema_snapshots", "all_artifacts", resolved_run_date, resolved_run_id),
            rows=schema_rows,
            schema=SCHEMA_SNAPSHOT_SCHEMA,
        )
        write_parquet_rows(
            s3_client,
            bucket=bucket,
            key=quality_result_key("source_completeness", "all_sources", resolved_run_date, resolved_run_id),
            rows=source_rows,
            schema=SOURCE_COMPLETENESS_SCHEMA,
        )
        write_parquet_rows(
            s3_client,
            bucket=bucket,
            key=quality_result_key("quarantine_summaries", "all_silver", resolved_run_date, resolved_run_id),
            rows=quarantine_rows,
            schema=QUARANTINE_SUMMARY_SCHEMA,
        )
        write_parquet_rows(
            s3_client,
            bucket=bucket,
            key=quality_result_key("anomaly_summaries", "all_layers", resolved_run_date, resolved_run_id),
            rows=anomaly_rows,
            schema=ANOMALY_SUMMARY_SCHEMA,
        )
        write_parquet_rows(
            s3_client,
            bucket=bucket,
            key=quality_result_key("row_count_trends", "all_artifacts", resolved_run_date, resolved_run_id),
            rows=row_count_trend_rows,
            schema=ROW_COUNT_TREND_SCHEMA,
        )
        write_parquet_rows(
            s3_client,
            bucket=bucket,
            key=quality_result_key("schema_drift", "all_artifacts", resolved_run_date, resolved_run_id),
            rows=schema_drift_rows,
            schema=SCHEMA_DRIFT_SCHEMA,
        )
        write_parquet_rows(
            s3_client,
            bucket=bucket,
            key=quality_result_key("grain_checks", "all_artifacts", resolved_run_date, resolved_run_id),
            rows=grain_check_rows,
            schema=GRAIN_CHECK_SCHEMA,
        )
        if register_athena:
            summary["athena_registration"] = refresh_quality_athena_tables(
                bucket=bucket,
                database=quality_database,
            )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run and persist the real S3-backed quality baseline.")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-date", default="")
    parser.add_argument("--max-schema-object-bytes", type=int, default=64_000_000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quality-database", default="quality")
    parser.add_argument("--skip-athena-registration", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_quality_baseline(
        bucket=args.bucket,
        run_id=args.run_id or None,
        run_date=args.run_date or None,
        max_schema_object_bytes=args.max_schema_object_bytes,
        write_s3=not args.dry_run,
        register_athena=not args.skip_athena_registration,
        quality_database=args.quality_database,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
