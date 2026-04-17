from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_pbpstats_event_projection_v1 as pbpstats_proj


REAL_LIVE_FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "reference"
    / "pbpstats"
    / "tests"
    / "data"
    / "pbp"
    / "live_0022000001.json"
)

META_COLUMNS = [
    "_meta_pipeline_run_id",
    "_meta_ingested_at_utc",
    "_meta_source_system",
    "_meta_source_key",
    "_meta_source_last_modified_utc",
    "_meta_schema_version",
]


@lru_cache(maxsize=1)
def load_real_projection_rows() -> tuple[str, list[dict]]:
    payload = json.loads(REAL_LIVE_FIXTURE.read_text())
    return pbpstats_proj.project_payload_to_rows(
        payload,
        source_file=str(REAL_LIVE_FIXTURE),
        source_last_modified_utc=None,
        fallback_game_id="0022000001",
    )


class FakeReplayEvent(pbpstats_proj.Replay):
    game_id = "0022409999"
    event_num = 999
    order = 999000
    period = 4
    clock = "PT00M10.00S"
    description = ""
    action_type = "replay"
    seconds_remaining = 10.0
    seconds_since_previous_event = 1.0
    score_margin = 2
    is_possession_ending_event = False
    count_as_possession = False
    previous_event = None
    next_event = None

    def is_second_chance_event(self):
        return False

    def is_penalty_event(self):
        return False

    @property
    def support_ruling(self):
        return False

    @property
    def overturn_ruling(self):
        return False

    @property
    def ruling_stands(self):
        return False


def test_target_schema_keeps_projection_column_order_and_meta_tail():
    assert pbpstats_proj.TARGET_SCHEMA.names[: len(pbpstats_proj.PROJECTION_COLUMNS)] == pbpstats_proj.PROJECTION_COLUMNS
    assert pbpstats_proj.TARGET_SCHEMA.names[-len(META_COLUMNS) :] == META_COLUMNS


def test_project_payload_to_rows_keeps_action_number_and_order_alignment():
    game_id, rows = load_real_projection_rows()

    assert game_id == "0022000001"
    assert rows[0]["event_num"] == 2
    assert rows[0]["event_order"] == 20000
    assert rows[1]["event_num"] == 4
    assert rows[1]["event_order"] == 40000


def test_project_payload_to_rows_uses_one_hot_event_class_flags():
    _, rows = load_real_projection_rows()

    for row in rows:
        assert sum(bool(row[column]) for column in pbpstats_proj.EVENT_CLASS_FLAG_COLUMNS) == 1


def test_project_payload_to_rows_preserves_empty_description_and_generic_event_flag():
    _, rows = load_real_projection_rows()

    empty_desc_row = next(row for row in rows if row["event_num"] == 49)
    assert empty_desc_row["description"] == ""
    assert empty_desc_row["action_type"] == "stoppage"
    assert empty_desc_row["is_other_event"] is True


def test_build_event_projection_row_keeps_replay_fields_null():
    row = pbpstats_proj.build_event_projection_row(
        FakeReplayEvent(),
        source_file="s3://bucket/raw/cdn/playbyplay/game_id=0022409999.json",
        source_last_modified_utc=None,
    )

    assert row["is_replay_event"] is True
    assert row["support_ruling"] is None
    assert row["overturn_ruling"] is None
    assert row["ruling_stands"] is None


def test_project_payload_to_rows_keeps_substitution_incoming_outgoing_nullability():
    _, rows = load_real_projection_rows()

    sub_row = next(row for row in rows if row["event_num"] == 66)
    assert sub_row["is_substitution_event"] is True
    assert sub_row["incoming_player_id"] is None
    assert sub_row["outgoing_player_id"] == 1630164


def test_project_payload_to_rows_flattens_linked_references():
    _, rows = load_real_projection_rows()

    rebound_row = next(row for row in rows if row["event_num"] == 19)
    free_throw_row = next(row for row in rows if row["event_num"] == 10)

    assert rebound_row["missed_shot_event_num"] == 18
    assert free_throw_row["foul_that_led_to_ft_event_num"] == 8
    assert free_throw_row["free_throw_trip_sequence_num"] == 1
    assert free_throw_row["free_throw_trip_size"] == 2


def test_projection_rows_accept_standard_silver_metadata():
    _, rows = load_real_projection_rows()
    enriched = pbpstats_proj.add_silver_metadata(
        rows[:1],
        pipeline_run_id="run_123",
        ingested_at_utc=pd.Timestamp("2026-03-27T00:00:00Z").to_pydatetime(),
        source_system=pbpstats_proj.SOURCE_SYSTEM,
        source_key="raw/cdn/playbyplay/game_id=0022000001.json",
        source_last_modified_utc=None,
        schema_version=pbpstats_proj.META_SCHEMA_VERSION,
    )

    assert enriched[0]["_meta_pipeline_run_id"] == "run_123"
    assert enriched[0]["_meta_source_system"] == pbpstats_proj.SOURCE_SYSTEM
    assert enriched[0]["_meta_source_key"] == "raw/cdn/playbyplay/game_id=0022000001.json"
    assert enriched[0]["_meta_schema_version"] == 1


def test_transform_failure_shape_is_capturable_from_projection_exception(monkeypatch):
    def raise_projection_failure(*args, **kwargs):
        raise pbpstats_proj.ProjectionFailure("Linked rebound.missed_shot resolution failed: boom")

    monkeypatch.setattr(pbpstats_proj, "project_payload_to_rows", raise_projection_failure)

    input_pdf = pd.DataFrame(
        [
            {
                "_source_file": "s3://bucket/raw/cdn/playbyplay/game_id=0022409000.json",
                "_source_last_modified_utc": None,
                "_fallback_game_id": "0022409000",
                "content": json.dumps({"game": {"gameId": "0022409000", "actions": []}}).encode("utf-8"),
            }
        ]
    )

    try:
        for row in input_pdf.to_dict(orient="records"):
            payload = json.loads(row["content"].decode("utf-8"))
            pbpstats_proj.project_payload_to_rows(
                payload,
                source_file=row["_source_file"],
                source_last_modified_utc=row["_source_last_modified_utc"],
                fallback_game_id=row["_fallback_game_id"],
            )
    except pbpstats_proj.ProjectionFailure as exc:
        assert "Linked rebound.missed_shot" in str(exc)
