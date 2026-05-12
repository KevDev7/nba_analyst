from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

from boxscore.sources import build_latest_cdn_boxscore_candidates


class FakeBody:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakePaginator:
    def __init__(self, objects: list[dict]):
        self.objects = objects

    def paginate(self, *, Bucket: str, Prefix: str):
        return [{"Contents": self.objects}]


class FakeS3Client:
    def __init__(self, objects: list[dict], payloads: dict[str, dict]):
        self.objects = objects
        self.payloads = payloads

    def get_paginator(self, name: str) -> FakePaginator:
        assert name == "list_objects_v2"
        return FakePaginator(self.objects)

    def get_object(self, *, Bucket: str, Key: str):
        return {"Body": FakeBody(self.payloads[Key])}


def payload(game_id: str, meta_time: str) -> dict:
    return {
        "meta": {"time": meta_time},
        "game": {"gameId": game_id, "homeTeam": {}, "awayTeam": {}, "officials": []},
    }


def test_build_latest_cdn_boxscore_candidates_keeps_latest_meta_time():
    older_key = "raw/cdn/boxscore/game_id=0022500001_older.json"
    newer_key = "raw/cdn/boxscore/game_id=0022500001_newer.json"
    s3_client = FakeS3Client(
        objects=[
            {"Key": older_key, "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            {"Key": newer_key, "LastModified": datetime(2026, 1, 2, tzinfo=timezone.utc)},
        ],
        payloads={
            older_key: payload("0022500001", "2026-01-01 00:00:00"),
            newer_key: payload("0022500001", "2026-01-01 00:05:00"),
        },
    )

    latest, metrics = build_latest_cdn_boxscore_candidates(
        s3_client,
        bucket="test-bucket",
        source_prefix="raw/cdn/boxscore/",
    )

    assert list(latest) == ["0022500001"]
    assert latest["0022500001"].source_key == newer_key
    assert metrics["source_json_object_count"] == 2
    assert metrics["source_replaced_by_recency"] == 1
    assert metrics["source_deduped_game_count"] == 1


def test_build_latest_cdn_boxscore_candidates_falls_back_to_key_game_id():
    key = "raw/cdn/boxscore/game_id=0022500002.json"
    s3_client = FakeS3Client(
        objects=[{"Key": key, "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)}],
        payloads={key: {"meta": {"time": "2026-01-01 00:00:00"}, "game": {}}},
    )

    latest, metrics = build_latest_cdn_boxscore_candidates(
        s3_client,
        bucket="test-bucket",
        source_prefix="raw/cdn/boxscore/",
    )

    assert list(latest) == ["0022500002"]
    assert latest["0022500002"].source_key == key
    assert metrics["source_skipped_without_game_id"] == 0

