from __future__ import annotations

import io
import sys
from datetime import datetime, timezone
from pathlib import Path


SILVER_TRANSFORM_DIR = (
    Path(__file__).resolve().parents[2] / "transform" / "silver"
)
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import heavy_silver_runtime as runtime


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str):
        body = self.objects.get((Bucket, Key))
        if body is None:
            raise runtime.ClientError(  # type: ignore[attr-defined]
                {"Error": {"Code": "NoSuchKey"}},
                "GetObject",
            )
        return {"Body": io.BytesIO(body)}


def test_build_source_fingerprint_is_deterministic_for_multi_input_artifacts():
    artifacts_a = [
        runtime.build_source_artifact(
            "silver/playbyplay/game_id=0022400001.parquet",
            datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc),
        ),
        runtime.build_source_artifact(
            "silver/on_court_state/game_id=0022400001.parquet",
            datetime(2026, 3, 27, 12, 5, tzinfo=timezone.utc),
        ),
    ]
    artifacts_b = list(reversed(artifacts_a))

    assert runtime.build_source_fingerprint(artifacts_a) == runtime.build_source_fingerprint(artifacts_b)


def test_select_game_ids_prioritizes_target_game_ids_over_checkpoint_state():
    source_index = {
        "0022400001": [runtime.build_source_artifact("a", None)],
        "0022400002": [runtime.build_source_artifact("b", None)],
    }

    selected_game_ids, selection_meta = runtime.select_game_ids_for_processing(
        source_index=source_index,
        target_game_ids={"0022400002", "0099999999"},
        force_full_refresh=False,
        checkpoint_exists=True,
        checkpoint_rows={"0022400001": {"source_fingerprint": "same"}},
    )

    assert selected_game_ids == ["0022400002"]
    assert selection_meta["selection_mode"] == "target_game_ids"
    assert selection_meta["missing_target_game_ids"] == ["0099999999"]


def test_select_game_ids_uses_full_refresh_when_requested():
    source_index = {
        "0022400001": [runtime.build_source_artifact("a", None)],
        "0022400002": [runtime.build_source_artifact("b", None)],
    }

    selected_game_ids, selection_meta = runtime.select_game_ids_for_processing(
        source_index=source_index,
        target_game_ids=set(),
        force_full_refresh=True,
        checkpoint_exists=True,
        checkpoint_rows={},
    )

    assert selected_game_ids == ["0022400001", "0022400002"]
    assert selection_meta["selection_mode"] == "full_refresh"


def test_select_game_ids_uses_checkpoint_delta_when_checkpoint_exists():
    source_index = {
        "0022400001": [runtime.build_source_artifact("a", datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc))],
        "0022400002": [runtime.build_source_artifact("b", datetime(2026, 3, 27, 12, 5, tzinfo=timezone.utc))],
    }
    checkpoint_rows = {
        "0022400001": {
            "source_fingerprint": runtime.build_source_fingerprint(source_index["0022400001"]),
        }
    }

    selected_game_ids, selection_meta = runtime.select_game_ids_for_processing(
        source_index=source_index,
        target_game_ids=set(),
        force_full_refresh=False,
        checkpoint_exists=True,
        checkpoint_rows=checkpoint_rows,
    )

    assert selected_game_ids == ["0022400002"]
    assert selection_meta["selection_mode"] == "checkpoint_incremental"


def test_select_game_ids_falls_back_to_legacy_selector_without_checkpoint():
    source_index = {
        "0022400001": [runtime.build_source_artifact("a", None)],
        "0022400002": [runtime.build_source_artifact("b", None)],
    }

    def legacy_selector(current_source_index, state):
        assert current_source_index == source_index
        assert state == {"legacy": True}
        return {"0022400002"}, {"selection_mode": "legacy_state_incremental"}

    selected_game_ids, selection_meta = runtime.select_game_ids_for_processing(
        source_index=source_index,
        target_game_ids=set(),
        force_full_refresh=False,
        checkpoint_exists=False,
        checkpoint_rows={},
        legacy_state={"legacy": True},
        legacy_fallback_selector=legacy_selector,
    )

    assert selected_game_ids == ["0022400002"]
    assert selection_meta["selection_mode"] == "legacy_state_incremental"
    assert selection_meta["legacy_state_fallback_used"] is True


def test_checkpoint_round_trip_persists_rows():
    s3_client = FakeS3Client()
    checkpoint_rows = [
        {
            "game_id": "0022400001",
            "source_fingerprint": "abc",
            "processed_at_utc": datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc),
            "pipeline_run_id": "run_1",
        }
    ]

    key = runtime.write_checkpoint_index(
        s3_client=s3_client,
        bucket="bucket",
        table_name="playbyplay_events",
        checkpoint_rows=checkpoint_rows,
    )
    exists, loaded_index = runtime.read_checkpoint_index(
        s3_client=s3_client,
        bucket="bucket",
        table_name="playbyplay_events",
    )

    assert key == "silver/_state/playbyplay_events_checkpoint.parquet"
    assert exists is True
    assert loaded_index["0022400001"]["source_fingerprint"] == "abc"
    assert loaded_index["0022400001"]["pipeline_run_id"] == "run_1"
