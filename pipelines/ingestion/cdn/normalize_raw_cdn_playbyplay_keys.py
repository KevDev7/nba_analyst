"""
Canonicalize raw CDN play-by-play S3 object keys to 10-digit game_id filenames.

Current problem:
- older raw files were stored like game_id=12000001.json
- silver and gold expect canonical 10-digit ids like game_id=0012000001

This script:
1. lists raw/cdn/playbyplay JSON files
2. copies any legacy/unpadded key to the canonical padded key
3. optionally deletes the legacy key after the copy succeeds

It does not re-fetch from the CDN.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError


S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "raw/cdn/playbyplay/"
DRY_RUN = os.getenv("PLAYBYPLAY_KEY_MIGRATION_DRY_RUN", "false").strip().lower() == "true"
DELETE_LEGACY = os.getenv("PLAYBYPLAY_KEY_MIGRATION_DELETE_LEGACY", "true").strip().lower() != "false"
MIGRATION_LIMIT = int(os.getenv("PLAYBYPLAY_KEY_MIGRATION_LIMIT", "0").strip() or "0")


@dataclass(frozen=True)
class PlayByPlayObject:
    key: str
    game_id: str
    canonical_game_id: str
    canonical_key: str
    already_canonical: bool


def extract_raw_game_id(key: str) -> str | None:
    """Extract raw game_id text from keys like raw/cdn/playbyplay/game_id=12000001.json."""
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id=") or not filename.endswith(".json"):
        return None
    return filename[len("game_id=") : -len(".json")] or None


def canonical_game_id(game_id: str | None) -> str | None:
    """Normalize to 10-digit game_id."""
    if game_id is None:
        return None
    text = str(game_id).strip()
    if not text:
        return None
    return text.zfill(10)


def canonical_key_for_game_id(game_id: str) -> str:
    """Return canonical raw S3 key."""
    return f"{SOURCE_PREFIX}game_id={game_id}.json"


def list_playbyplay_objects(s3_client) -> list[PlayByPlayObject]:
    """List all raw play-by-play objects and normalize their metadata."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[PlayByPlayObject] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SOURCE_PREFIX):
        for item in page.get("Contents", []):
            key = item.get("Key", "")
            raw_game_id = extract_raw_game_id(key)
            normalized_game_id = canonical_game_id(raw_game_id)
            if normalized_game_id is None:
                continue
            canonical_key = canonical_key_for_game_id(normalized_game_id)
            objects.append(
                PlayByPlayObject(
                    key=key,
                    game_id=str(raw_game_id),
                    canonical_game_id=normalized_game_id,
                    canonical_key=canonical_key,
                    already_canonical=(key == canonical_key),
                )
            )
    return objects


def s3_object_exists(s3_client, key: str) -> bool:
    """Return True if the object exists."""
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def copy_object_if_needed(s3_client, source_key: str, destination_key: str) -> str:
    """Copy legacy key to canonical key when needed."""
    if source_key == destination_key:
        return "already_canonical"
    if s3_object_exists(s3_client, destination_key):
        return "destination_exists"
    if not s3_object_exists(s3_client, source_key):
        return "source_missing"
    if DRY_RUN:
        return "dry_run_copy"
    try:
        s3_client.copy_object(
            Bucket=S3_BUCKET,
            CopySource={"Bucket": S3_BUCKET, "Key": source_key},
            Key=destination_key,
            ContentType="application/json",
            MetadataDirective="COPY",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return "source_missing"
        raise
    return "copied"


def delete_legacy_object_if_needed(s3_client, source_key: str, destination_key: str) -> str:
    """Delete legacy key once canonical key exists."""
    if source_key == destination_key:
        return "not_legacy"
    if not DELETE_LEGACY:
        return "kept_legacy"
    if not s3_object_exists(s3_client, destination_key):
        return "destination_missing"
    if DRY_RUN:
        return "dry_run_delete"
    s3_client.delete_object(Bucket=S3_BUCKET, Key=source_key)
    return "deleted_legacy"


def main() -> None:
    """Canonicalize raw play-by-play object keys."""
    s3_client = boto3.client("s3")
    objects = list_playbyplay_objects(s3_client)

    total = len(objects)
    already_canonical = 0
    legacy = 0
    copied = 0
    destination_exists = 0
    deleted_legacy = 0
    kept_legacy = 0
    processed_legacy = 0

    print(
        {
            "bucket": S3_BUCKET,
            "prefix": SOURCE_PREFIX,
            "dry_run": DRY_RUN,
            "delete_legacy": DELETE_LEGACY,
            "migration_limit": MIGRATION_LIMIT,
            "objects_discovered": total,
        }
    )

    for index, obj in enumerate(objects, start=1):
        if obj.already_canonical:
            already_canonical += 1
            continue

        if MIGRATION_LIMIT > 0 and processed_legacy >= MIGRATION_LIMIT:
            break

        legacy += 1
        processed_legacy += 1
        copy_status = copy_object_if_needed(s3_client, obj.key, obj.canonical_key)
        if copy_status in {"copied", "dry_run_copy"}:
            copied += 1
        elif copy_status == "destination_exists":
            destination_exists += 1

        delete_status = delete_legacy_object_if_needed(s3_client, obj.key, obj.canonical_key)
        if delete_status in {"deleted_legacy", "dry_run_delete"}:
            deleted_legacy += 1
        elif delete_status == "kept_legacy":
            kept_legacy += 1

        if index <= 5 or index % 500 == 0:
            print(
                {
                    "index": index,
                    "legacy_key": obj.key,
                    "canonical_key": obj.canonical_key,
                    "copy_status": copy_status,
                    "delete_status": delete_status,
                }
            )

    print(
        {
            "already_canonical": already_canonical,
            "legacy_objects": legacy,
            "processed_legacy": processed_legacy,
            "copied_or_would_copy": copied,
            "destination_exists": destination_exists,
            "deleted_or_would_delete_legacy": deleted_legacy,
            "kept_legacy": kept_legacy,
        }
    )


if __name__ == "__main__":
    main()
