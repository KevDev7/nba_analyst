from __future__ import annotations

import gzip
import io
import re
from datetime import datetime, timezone
from typing import Any, Callable

import pyarrow.parquet as pq

from .types import RawHtmlSnapshot


def normalize_last_modified(value: datetime | None) -> datetime | None:
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_newer_source(
    current_fetched_at_utc: datetime,
    current_last_modified_utc: datetime | None,
    candidate_fetched_at_utc: datetime,
    candidate_last_modified_utc: datetime | None,
) -> bool:
    if candidate_fetched_at_utc > current_fetched_at_utc:
        return True
    if candidate_fetched_at_utc < current_fetched_at_utc:
        return False
    min_utc = datetime.min.replace(tzinfo=timezone.utc)
    return (candidate_last_modified_utc or min_utc) > (current_last_modified_utc or min_utc)


def list_source_objects(s3_client, *, bucket: str, prefix: str) -> list[dict[str, Any]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".html.gz"):
                objects.append(obj)
    return objects


def get_latest_sources(
    s3_client,
    *,
    bucket: str,
    prefix: str,
    key_parser: Callable[[str], tuple[str, datetime] | None],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    source_objects = list_source_objects(s3_client, bucket=bucket, prefix=prefix)
    latest_sources = select_latest_source_objects(source_objects, key_parser=key_parser)
    return source_objects, latest_sources


def select_latest_source_objects(
    source_objects: list[dict[str, Any]],
    *,
    key_parser: Callable[[str], tuple[str, datetime] | None],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for obj in source_objects:
        key = obj.get("Key", "")
        parsed = key_parser(key)
        if parsed is None:
            continue
        entity_id, fetched_at_utc = parsed
        candidate_last_modified_utc = normalize_last_modified(obj.get("LastModified"))
        current = latest.get(entity_id)
        if current is None or is_newer_source(
            current_fetched_at_utc=current["fetched_at_utc"],
            current_last_modified_utc=current["last_modified_utc"],
            candidate_fetched_at_utc=fetched_at_utc,
            candidate_last_modified_utc=candidate_last_modified_utc,
        ):
            latest[entity_id] = {
                "entity_id": entity_id,
                "key": key,
                "fetched_at_utc": fetched_at_utc,
                "last_modified_utc": candidate_last_modified_utc,
            }
    return latest


def read_gzipped_html(s3_client, *, bucket: str, key: str) -> tuple[str, dict[str, str]]:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    payload = response["Body"].read()
    metadata = response.get("Metadata") or {}
    return gzip.decompress(payload).decode("utf-8", errors="replace"), metadata


def load_latest_raw_snapshots(
    s3_client,
    *,
    bucket: str,
    prefix: str,
    key_parser: Callable[[str], tuple[str, datetime] | None],
) -> list[RawHtmlSnapshot]:
    latest_sources = select_latest_source_objects(
        list_source_objects(s3_client, bucket=bucket, prefix=prefix),
        key_parser=key_parser,
    )
    snapshots: list[RawHtmlSnapshot] = []
    for entity_id in sorted(latest_sources):
        source = latest_sources[entity_id]
        html, s3_metadata = read_gzipped_html(s3_client, bucket=bucket, key=source["key"])
        snapshots.append(
            RawHtmlSnapshot(
                entity_id=entity_id,
                key=source["key"],
                fetched_at_utc=source["fetched_at_utc"],
                last_modified_utc=source["last_modified_utc"],
                html=html,
                s3_metadata=s3_metadata,
            )
        )
    return snapshots


def iter_latest_raw_snapshots(
    s3_client,
    *,
    bucket: str,
    latest_sources: dict[str, dict[str, Any]],
):
    for entity_id in sorted(latest_sources):
        source = latest_sources[entity_id]
        html, s3_metadata = read_gzipped_html(s3_client, bucket=bucket, key=source["key"])
        yield RawHtmlSnapshot(
            entity_id=entity_id,
            key=source["key"],
            fetched_at_utc=source["fetched_at_utc"],
            last_modified_utc=source["last_modified_utc"],
            html=html,
            s3_metadata=s3_metadata,
        )


def read_parquet_rows(s3_client, *, bucket: str, key: str) -> list[dict[str, Any]]:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return pq.read_table(io.BytesIO(response["Body"].read())).to_pylist()


def parse_timestamped_source_key(key: str, *, pattern: re.Pattern[str], entity_group: int | str) -> tuple[str, datetime] | None:
    match = pattern.match(key)
    if match is None:
        return None
    entity_id = match.group(entity_group)
    fetched_at_utc = datetime.strptime(match.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    return entity_id, fetched_at_utc
