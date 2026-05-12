"""Source helpers shared by silver boxscore transforms."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CdnBoxscoreCandidate:
    """Latest-source candidate for one CDN boxscore game payload."""

    game_id: str
    payload: dict[str, Any]
    meta_time: datetime | None
    source_key: str
    source_last_modified_utc: datetime | None


def null_if_empty(value: Any) -> Any:
    """Convert empty/blank strings to None; keep all other values unchanged."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def to_int_or_none(value: Any) -> int | None:
    """Convert numeric-like input into int; return None for empty-like values."""
    value = null_if_empty(value)
    if value is None:
        return None
    return int(value)


def to_float_or_none(value: Any) -> float | None:
    """Convert numeric-like input into float; return None for empty-like values."""
    value = null_if_empty(value)
    if value is None:
        return None
    return float(value)


def to_str_or_none(value: Any) -> str | None:
    """Convert text-like input into stripped string; return None for empty-like values."""
    value = null_if_empty(value)
    if value is None:
        return None
    return str(value).strip()


def parse_iso_to_utc(value: Any) -> datetime | None:
    """Parse ISO-like datetime strings to timezone-aware UTC datetime."""
    value = null_if_empty(value)
    if value is None:
        return None

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_meta_time_to_utc(value: Any) -> datetime | None:
    """Parse CDN boxscore meta time into timezone-aware UTC datetime."""
    value = null_if_empty(value)
    if value is None:
        return None

    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return parse_iso_to_utc(text)


def normalize_s3_last_modified(value: Any) -> datetime | None:
    """Return a timezone-aware UTC S3 LastModified value when available."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def extract_game_id_from_cdn_boxscore_key(key: str) -> str | None:
    """Fallback parser for keys like raw/cdn/boxscore/game_id=0022500857.json."""
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id=") or not filename.endswith(".json"):
        return None
    return filename[len("game_id=") : -len(".json")] or None


def list_json_objects(s3_client, *, bucket: str, prefix: str) -> list[dict[str, Any]]:
    """List all JSON objects under a source prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".json"):
                objects.append(obj)

    return objects


def read_json_object(s3_client, *, bucket: str, key: str) -> dict[str, Any]:
    """Read and decode one JSON object from S3."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return json.loads(response["Body"].read())


def is_newer_candidate(
    current_meta_time: datetime | None,
    current_last_modified: datetime | None,
    candidate_meta_time: datetime | None,
    candidate_last_modified: datetime | None,
) -> bool:
    """Return True if candidate should replace current using defined precedence."""
    min_utc = datetime.min.replace(tzinfo=timezone.utc)

    current_meta_key = current_meta_time or min_utc
    candidate_meta_key = candidate_meta_time or min_utc
    if candidate_meta_key > current_meta_key:
        return True
    if candidate_meta_key < current_meta_key:
        return False

    current_lm_key = current_last_modified or min_utc
    candidate_lm_key = candidate_last_modified or min_utc
    return candidate_lm_key > current_lm_key


def build_cdn_boxscore_candidate(
    payload: dict[str, Any],
    *,
    key: str,
    last_modified: datetime | None,
) -> CdnBoxscoreCandidate | None:
    """Build one dedupe candidate at CDN boxscore game grain."""
    meta = payload.get("meta") or {}
    game = payload.get("game") or {}
    game_id = null_if_empty(game.get("gameId")) or extract_game_id_from_cdn_boxscore_key(key)
    if game_id is None:
        return None
    return CdnBoxscoreCandidate(
        game_id=str(game_id),
        payload=payload,
        meta_time=parse_meta_time_to_utc(meta.get("time")),
        source_key=key,
        source_last_modified_utc=last_modified,
    )


def build_latest_cdn_boxscore_candidates(
    s3_client,
    *,
    bucket: str,
    source_prefix: str,
) -> tuple[dict[str, CdnBoxscoreCandidate], dict[str, Any]]:
    """Load CDN boxscore source files and keep the latest payload for each game."""
    objects = list_json_objects(s3_client, bucket=bucket, prefix=source_prefix)
    print(f"Discovered {len(objects)} source JSON objects under {source_prefix}")

    latest_by_game_id: dict[str, CdnBoxscoreCandidate] = {}
    skipped_without_game_id = 0
    failed_reads = 0
    replaced_count = 0
    min_last_modified_utc: datetime | None = None
    max_last_modified_utc: datetime | None = None

    for obj in objects:
        key = obj.get("Key", "")
        last_modified = normalize_s3_last_modified(obj.get("LastModified"))
        if last_modified is not None:
            if min_last_modified_utc is None or last_modified < min_last_modified_utc:
                min_last_modified_utc = last_modified
            if max_last_modified_utc is None or last_modified > max_last_modified_utc:
                max_last_modified_utc = last_modified

        try:
            payload = read_json_object(s3_client, bucket=bucket, key=key)
            candidate = build_cdn_boxscore_candidate(payload, key=key, last_modified=last_modified)
        except Exception as exc:
            failed_reads += 1
            print(f"Failed to parse {key}: {type(exc).__name__}: {exc}")
            continue

        if candidate is None:
            skipped_without_game_id += 1
            continue

        current = latest_by_game_id.get(candidate.game_id)
        if current is None:
            latest_by_game_id[candidate.game_id] = candidate
            continue

        if is_newer_candidate(
            current_meta_time=current.meta_time,
            current_last_modified=current.source_last_modified_utc,
            candidate_meta_time=candidate.meta_time,
            candidate_last_modified=candidate.source_last_modified_utc,
        ):
            latest_by_game_id[candidate.game_id] = candidate
            replaced_count += 1

    source_metrics = {
        "source_json_object_count": len(objects),
        "source_min_last_modified_utc": min_last_modified_utc,
        "source_max_last_modified_utc": max_last_modified_utc,
        "source_skipped_without_game_id": skipped_without_game_id,
        "source_failed_reads": failed_reads,
        "source_replaced_by_recency": replaced_count,
        "source_deduped_game_count": len(latest_by_game_id),
    }
    return latest_by_game_id, source_metrics

