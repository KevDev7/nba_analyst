from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import pyarrow.parquet as pq


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_event_projection_v2 as projection_v2
import build_silver_playbyplay_events as pbp_silver


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
GOLDEN_ROOT = FIXTURE_ROOT / "pbpstats_event_projection_v1_golden"
INPUT_ROOT = FIXTURE_ROOT / "event_projection_v2_inputs"

META_COLUMNS = [
    "_meta_pipeline_run_id",
    "_meta_ingested_at_utc",
    "_meta_source_system",
    "_meta_source_key",
    "_meta_source_last_modified_utc",
    "_meta_schema_version",
]

GOLDEN_GAME_IDS = [
    "0012000001",
    "0012000002",
    "0022000001",
    "0022000002",
    "0022100001",
    "0022100732",
    "0022200001",
    "0022300001",
    "0022400001",
    "0022500001",
]


def _sorted_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: (row["event_order"], row["event_num"]))


@lru_cache(maxsize=None)
def load_fixture_projection_rows(game_id: str) -> list[dict]:
    playbyplay_payload = json.loads(
        (INPUT_ROOT / "playbyplay" / f"game_id={game_id}.json").read_text()
    )
    boxscore_payload = json.loads(
        (INPUT_ROOT / "boxscore" / f"game_id={game_id}.json").read_text()
    )
    boxscore_context = pbp_silver.build_boxscore_context(boxscore_payload)
    _, rows = projection_v2.project_payload_to_rows(
        playbyplay_payload,
        source_file=str(INPUT_ROOT / "playbyplay" / f"game_id={game_id}.json"),
        source_last_modified_utc=None,
        fallback_game_id=game_id,
        boxscore_context=boxscore_context,
    )
    return _sorted_rows(rows)


@lru_cache(maxsize=None)
def load_golden_rows(game_id: str) -> list[dict]:
    table = pq.read_table(GOLDEN_ROOT / f"game_id={game_id}.parquet")
    return _sorted_rows(table.to_pylist())


def test_target_schema_keeps_projection_column_order_and_meta_tail():
    assert projection_v2.TARGET_SCHEMA.names[: len(projection_v2.PROJECTION_COLUMNS)] == projection_v2.PROJECTION_COLUMNS
    assert projection_v2.TARGET_SCHEMA.names[-len(META_COLUMNS) :] == META_COLUMNS


def test_project_payload_to_rows_uses_one_hot_event_class_flags():
    rows = load_fixture_projection_rows("0022000001")

    for row in rows:
        assert sum(bool(row[column]) for column in projection_v2.EVENT_CLASS_FLAG_COLUMNS) == 1


def test_project_payload_to_rows_keeps_replay_fields_null():
    rows = load_fixture_projection_rows("0022100732")
    replay_like_row = next(row for row in rows if row["action_type"] == "instantreplay")

    assert replay_like_row["is_other_event"] is True
    assert replay_like_row["is_replay_event"] is False
    assert replay_like_row["support_ruling"] is None
    assert replay_like_row["overturn_ruling"] is None
    assert replay_like_row["ruling_stands"] is None


def test_project_payload_to_rows_keeps_substitution_incoming_outgoing_nullability():
    rows = load_fixture_projection_rows("0022000001")

    sub_row = next(row for row in rows if row["event_num"] == 66)
    assert sub_row["is_substitution_event"] is True
    assert sub_row["incoming_player_id"] is None
    assert sub_row["outgoing_player_id"] == 1630164


def test_project_payload_to_rows_flattens_linked_references():
    rows = load_fixture_projection_rows("0022000001")

    rebound_row = next(row for row in rows if row["event_num"] == 19)
    free_throw_row = next(row for row in rows if row["event_num"] == 10)

    assert rebound_row["missed_shot_event_num"] == 18
    assert free_throw_row["foul_that_led_to_ft_event_num"] == 8
    assert free_throw_row["free_throw_trip_sequence_num"] == 1
    assert free_throw_row["free_throw_trip_size"] == 2


def test_project_payload_to_rows_backfills_missing_sub_type_attributes():
    playbyplay_payload = json.loads(
        (INPUT_ROOT / "playbyplay" / "game_id=0022200001.json").read_text()
    )
    boxscore_payload = json.loads(
        (INPUT_ROOT / "boxscore" / "game_id=0022200001.json").read_text()
    )
    boxscore_context = pbp_silver.build_boxscore_context(boxscore_payload)

    foul_row = next(
        action
        for action in playbyplay_payload["game"]["actions"]
        if action.get("actionType") == "foul" and action.get("subType")
    )
    foul_row.pop("subType", None)

    _, rows = projection_v2.project_payload_to_rows(
        playbyplay_payload,
        source_file=str(INPUT_ROOT / "playbyplay" / "game_id=0022200001.json"),
        source_last_modified_utc=None,
        fallback_game_id="0022200001",
        boxscore_context=boxscore_context,
    )

    matched = next(row for row in rows if row["event_num"] == foul_row["actionNumber"])
    assert matched["sub_type"] is None
    assert matched["is_foul_event"] is True


def test_project_payload_to_rows_collapses_duplicate_raw_actions_using_richer_row():
    playbyplay_payload = json.loads(
        (INPUT_ROOT / "playbyplay" / "game_id=0022200001.json").read_text()
    )
    boxscore_payload = json.loads(
        (INPUT_ROOT / "boxscore" / "game_id=0022200001.json").read_text()
    )
    boxscore_context = pbp_silver.build_boxscore_context(boxscore_payload)

    source_action = next(
        action
        for action in playbyplay_payload["game"]["actions"]
        if action.get("actionType") == "foul" and action.get("foulDrawnPersonId")
    )
    duplicate = dict(source_action)
    duplicate["foulDrawnPersonId"] = None
    duplicate["foulDrawnPlayerName"] = None
    duplicate["personIdsFilter"] = [source_action["personId"]]
    insert_at = playbyplay_payload["game"]["actions"].index(source_action)
    playbyplay_payload["game"]["actions"].insert(insert_at, duplicate)

    _, rows = projection_v2.project_payload_to_rows(
        playbyplay_payload,
        source_file=str(INPUT_ROOT / "playbyplay" / "game_id=0022200001.json"),
        source_last_modified_utc=None,
        fallback_game_id="0022200001",
        boxscore_context=boxscore_context,
    )

    matching_rows = [row for row in rows if row["event_num"] == source_action["actionNumber"]]
    assert len(matching_rows) == 1
    assert matching_rows[0]["player3_id"] == source_action["foulDrawnPersonId"]


def test_golden_fixture_parity_for_all_games():
    for game_id in GOLDEN_GAME_IDS:
        actual_rows = load_fixture_projection_rows(game_id)
        expected_rows = load_golden_rows(game_id)

        assert len(actual_rows) == len(expected_rows), game_id
        assert list(actual_rows[0].keys()) == projection_v2.PROJECTION_COLUMNS, game_id
        assert actual_rows == expected_rows, game_id
