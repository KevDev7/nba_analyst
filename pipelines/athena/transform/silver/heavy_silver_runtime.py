from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any, Callable

import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError


CHECKPOINT_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("source_fingerprint", pa.string()),
        pa.field("processed_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("pipeline_run_id", pa.string()),
    ]
)


SourceIndex = dict[str, list[dict[str, Any]]]
LegacyFallbackSelector = Callable[[SourceIndex, dict[str, Any]], tuple[set[str], dict[str, Any]]]


def parse_target_game_ids(value: str | None) -> set[str]:
    """Parse comma-separated target game ids from env vars."""
    if value is None:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def normalize_utc_datetime(value: Any) -> datetime | None:
    """Normalize datetime-like values to timezone-aware UTC."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def datetime_to_iso(value: datetime | None) -> str | None:
    """Serialize datetime to canonical ISO Z form."""
    normalized = normalize_utc_datetime(value)
    if normalized is None:
        return None
    return normalized.isoformat().replace("+00:00", "Z")


def checkpoint_key(table_name: str) -> str:
    """Return the shared checkpoint key for a heavy silver table."""
    return f"silver/_state/{table_name}_checkpoint.parquet"


def read_json_state(
    *,
    s3_client,
    bucket: str,
    key: str,
) -> dict[str, Any]:
    """Load JSON state from S3, returning empty state when absent."""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = (exc.response or {}).get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404"}:
            return {}
        raise
    return json.loads(response["Body"].read())


def write_json_state(
    *,
    s3_client,
    bucket: str,
    key: str,
    state: dict[str, Any],
) -> None:
    """Persist JSON state to S3."""
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(state, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
    )


def read_checkpoint_index(
    *,
    s3_client,
    bucket: str,
    table_name: str,
) -> tuple[bool, dict[str, dict[str, Any]]]:
    """Load checkpoint parquet into an index keyed by game_id."""
    key = checkpoint_key(table_name)
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = (exc.response or {}).get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404"}:
            return False, {}
        raise

    payload = response["Body"].read()
    table = pq.read_table(pa.BufferReader(payload))
    rows = table.to_pylist()
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        game_id = row.get("game_id")
        if game_id is None or str(game_id).strip() == "":
            continue
        index[str(game_id)] = {
            "game_id": str(game_id),
            "source_fingerprint": row.get("source_fingerprint"),
            "processed_at_utc": normalize_utc_datetime(row.get("processed_at_utc")),
            "pipeline_run_id": row.get("pipeline_run_id"),
        }
    return True, index


def write_checkpoint_index(
    *,
    s3_client,
    bucket: str,
    table_name: str,
    checkpoint_rows: list[dict[str, Any]],
) -> str:
    """Write checkpoint parquet for one heavy silver table."""
    key = checkpoint_key(table_name)
    table = pa.Table.from_pylist(checkpoint_rows, schema=CHECKPOINT_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )
    return key


def build_source_artifact(key: str, last_modified: Any) -> dict[str, Any]:
    """Build a normalized source-artifact descriptor."""
    return {
        "key": key,
        "last_modified_utc": datetime_to_iso(normalize_utc_datetime(last_modified)),
    }


def build_source_fingerprint(artifacts: list[dict[str, Any]]) -> str:
    """Build deterministic fingerprint for a game's source artifacts."""
    normalized_artifacts = sorted(
        [
            {
                "key": str(artifact.get("key") or ""),
                "last_modified_utc": artifact.get("last_modified_utc"),
            }
            for artifact in artifacts
        ],
        key=lambda artifact: (artifact["key"], artifact["last_modified_utc"] or ""),
    )
    payload = json.dumps(normalized_artifacts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_source_index_from_objects(
    objects: list[dict[str, Any]],
    *,
    game_id_from_key: Callable[[str], str | None],
) -> SourceIndex:
    """Build game_id -> source artifact list from S3 list_objects rows."""
    source_index: SourceIndex = {}
    for obj in objects:
        key = str(obj.get("Key") or "")
        game_id = game_id_from_key(key)
        if game_id is None:
            continue
        source_index.setdefault(game_id, []).append(
            build_source_artifact(key, obj.get("LastModified"))
        )
    return source_index


def add_source_artifact(
    source_index: SourceIndex,
    *,
    game_id: str,
    key: str,
    last_modified: Any,
) -> None:
    """Append one normalized source artifact to a game's source index entry."""
    source_index.setdefault(game_id, []).append(build_source_artifact(key, last_modified))


def checkpoint_rows_with_updates(
    *,
    existing_rows: dict[str, dict[str, Any]],
    source_index: SourceIndex,
    written_game_ids: set[str],
    processed_at_utc: datetime,
    pipeline_run_id: str,
) -> list[dict[str, Any]]:
    """Merge successful game writes into checkpoint rows."""
    merged = dict(existing_rows)
    processed_at = normalize_utc_datetime(processed_at_utc)
    for game_id in sorted(written_game_ids):
        artifacts = source_index.get(game_id) or []
        merged[game_id] = {
            "game_id": game_id,
            "source_fingerprint": build_source_fingerprint(artifacts),
            "processed_at_utc": processed_at,
            "pipeline_run_id": pipeline_run_id,
        }
    return [merged[game_id] for game_id in sorted(merged)]


def select_game_ids_for_processing(
    *,
    source_index: SourceIndex,
    target_game_ids: set[str],
    force_full_refresh: bool,
    checkpoint_exists: bool,
    checkpoint_rows: dict[str, dict[str, Any]],
    legacy_state: dict[str, Any] | None = None,
    legacy_fallback_selector: LegacyFallbackSelector | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Select game_ids using target, full refresh, checkpoint, then legacy fallback."""
    all_game_ids = sorted(source_index)

    if target_game_ids:
        available_game_ids = sorted(game_id for game_id in target_game_ids if game_id in source_index)
        missing_game_ids = sorted(game_id for game_id in target_game_ids if game_id not in source_index)
        return available_game_ids, {
            "selection_mode": "target_game_ids",
            "target_game_ids": sorted(target_game_ids),
            "missing_target_game_ids": missing_game_ids,
            "checkpoint_enabled": checkpoint_exists,
            "legacy_state_fallback_used": False,
        }

    if force_full_refresh:
        return all_game_ids, {
            "selection_mode": "full_refresh",
            "target_game_ids": [],
            "checkpoint_enabled": checkpoint_exists,
            "legacy_state_fallback_used": False,
        }

    if checkpoint_exists:
        changed_game_ids: list[str] = []
        for game_id in all_game_ids:
            current_fingerprint = build_source_fingerprint(source_index.get(game_id) or [])
            previous_row = checkpoint_rows.get(game_id)
            if previous_row is None or previous_row.get("source_fingerprint") != current_fingerprint:
                changed_game_ids.append(game_id)
        return changed_game_ids, {
            "selection_mode": "checkpoint_incremental",
            "target_game_ids": [],
            "checkpoint_enabled": True,
            "legacy_state_fallback_used": False,
        }

    if legacy_state and legacy_fallback_selector is not None:
        selected_game_ids, legacy_meta = legacy_fallback_selector(source_index, legacy_state)
        selection_meta = dict(legacy_meta)
        selection_meta.setdefault("selection_mode", selection_meta.get("mode", "legacy_state_fallback"))
        selection_meta["checkpoint_enabled"] = False
        selection_meta["legacy_state_fallback_used"] = True
        selection_meta.setdefault("target_game_ids", [])
        return sorted(selected_game_ids), selection_meta

    return all_game_ids, {
        "selection_mode": "checkpoint_initial",
        "target_game_ids": [],
        "checkpoint_enabled": checkpoint_exists,
        "legacy_state_fallback_used": False,
    }


def selection_audit_fields(
    selection_meta: dict[str, Any],
    *,
    checkpoint_key_written: str | None,
) -> dict[str, Any]:
    """Return the shared audit fields for heavy silver selection metadata."""
    return {
        "selection_mode": selection_meta.get("selection_mode"),
        "target_game_ids": json.dumps(selection_meta.get("target_game_ids") or []),
        "missing_target_game_ids": json.dumps(
            selection_meta.get("missing_target_game_ids") or []
        ),
        "checkpoint_enabled": int(bool(selection_meta.get("checkpoint_enabled"))),
        "legacy_state_fallback_used": int(
            bool(selection_meta.get("legacy_state_fallback_used"))
        ),
        "checkpoint_key": checkpoint_key_written,
    }
