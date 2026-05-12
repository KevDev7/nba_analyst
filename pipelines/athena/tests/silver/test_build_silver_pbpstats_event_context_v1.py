from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import pytest


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_pbpstats_event_context_v1 as event_context


REPO_ROOT = Path(__file__).resolve().parents[4]


def first_existing_path(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


PBP_FIXTURE = first_existing_path(
    REPO_ROOT / "pipelines" / "athena" / "tests" / "fixtures" / "event_projection_v2_inputs" / "playbyplay" / "game_id=0022000001.json",
    REPO_ROOT / "references" / "pbpstats" / "tests" / "data" / "pbp" / "live_0022000001.json",
    REPO_ROOT / "reference" / "pbpstats" / "tests" / "data" / "pbp" / "live_0022000001.json",
)

BOXSCORE_FIXTURE = first_existing_path(
    REPO_ROOT / "pipelines" / "athena" / "tests" / "fixtures" / "event_projection_v2_inputs" / "boxscore" / "game_id=0022000001.json",
    REPO_ROOT / "references" / "pbpstats" / "tests" / "data" / "game_details" / "live_0022000001.json",
    REPO_ROOT / "reference" / "pbpstats" / "tests" / "data" / "game_details" / "live_0022000001.json",
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
    pbp_payload = json.loads(PBP_FIXTURE.read_text())
    boxscore_payload = json.loads(BOXSCORE_FIXTURE.read_text())
    return event_context.project_payload_to_rows(
        pbp_payload,
        home_team_id=boxscore_payload["game"]["homeTeam"]["teamId"],
        away_team_id=boxscore_payload["game"]["awayTeam"]["teamId"],
        source_file=str(PBP_FIXTURE),
        source_last_modified_utc=None,
        fallback_game_id="0022000001",
    )[:2]


def test_target_schema_keeps_context_column_order_and_meta_tail():
    assert event_context.TARGET_SCHEMA.names[: len(event_context.PROJECTION_COLUMNS)] == event_context.PROJECTION_COLUMNS
    assert event_context.TARGET_SCHEMA.names[-len(META_COLUMNS) :] == META_COLUMNS


def test_project_payload_to_rows_uses_boxscore_home_away_orientation_and_sorted_arrays():
    game_id, rows = load_real_projection_rows()
    first_row = rows[0]

    assert game_id == "0022000001"
    assert first_row["home_team_id"] == 1610612751
    assert first_row["away_team_id"] == 1610612744
    assert first_row["home_current_player_ids"] == sorted(first_row["home_current_player_ids"], key=str)
    assert first_row["away_current_player_ids"] == sorted(first_row["away_current_player_ids"], key=str)


def test_project_payload_to_rows_keeps_period_starters_only_on_period_start_rows():
    _, rows = load_real_projection_rows()

    start_row = next(row for row in rows if row["event_num"] == 2)
    jumpball_row = next(row for row in rows if row["event_num"] == 4)

    assert start_row["home_period_starter_ids"] is not None
    assert start_row["away_period_starter_ids"] is not None
    assert jumpball_row["home_period_starter_ids"] is None
    assert jumpball_row["away_period_starter_ids"] is None


def test_project_payload_to_rows_preserves_lineup_ids_from_sorted_player_arrays():
    _, rows = load_real_projection_rows()
    start_row = next(row for row in rows if row["event_num"] == 2)

    assert start_row["home_lineup_id"] == event_context.lineup_id_from_player_ids(start_row["home_current_player_ids"])
    assert start_row["away_lineup_id"] == event_context.lineup_id_from_player_ids(start_row["away_current_player_ids"])


def test_project_payload_to_rows_fails_without_boxscore_orientation():
    pbp_payload = json.loads(PBP_FIXTURE.read_text())

    with pytest.raises(event_context.ProjectionFailure, match="Missing usable home/away team orientation"):
        event_context.project_payload_to_rows(
            pbp_payload,
            home_team_id=None,
            away_team_id=None,
            source_file=str(PBP_FIXTURE),
            source_last_modified_utc=None,
            fallback_game_id="0022000001",
        )


class FakeEvent:
    game_id = "0022409999"
    event_num = 10
    current_players = {
        1610612737: [5, 4, 3, 2, 1],
        1610612738: [10, 9, 8, 7, 6],
    }
    lineup_ids = {
        1610612737: "1-2-3-4-99",
        1610612738: "6-7-8-9-10",
    }
    fouls_to_give = {
        1610612737: 4,
        1610612738: 3,
    }


def test_build_event_context_row_raises_on_lineup_mismatch():
    with pytest.raises(event_context.ProjectionFailure, match="Lineup id mismatch"):
        event_context.build_event_context_row(
            FakeEvent(),
            home_team_id=1610612737,
            away_team_id=1610612738,
            starter_warning_event_nums=set(),
            source_file="s3://bucket/raw/cdn/playbyplay/game_id=0022409999.json",
            source_last_modified_utc=None,
        )


def test_project_payload_to_rows_nulls_starter_arrays_when_warning_event_is_present(monkeypatch):
    pbp_payload = json.loads(PBP_FIXTURE.read_text())
    boxscore_payload = json.loads(BOXSCORE_FIXTURE.read_text())
    game_id, items, _ = event_context.load_live_enhanced_pbp_items_with_period_starter_warnings(
        pbp_payload,
        fallback_game_id="0022000001",
    )

    def fake_loader(*args, **kwargs):
        return game_id, items, [{"game_id": game_id, "event_num": 2, "period": 1}]

    monkeypatch.setattr(event_context, "load_live_enhanced_pbp_items_with_period_starter_warnings", fake_loader)

    _, rows, warnings = event_context.project_payload_to_rows(
        pbp_payload,
        home_team_id=boxscore_payload["game"]["homeTeam"]["teamId"],
        away_team_id=boxscore_payload["game"]["awayTeam"]["teamId"],
        source_file=str(PBP_FIXTURE),
        source_last_modified_utc=None,
        fallback_game_id="0022000001",
    )
    start_row = next(row for row in rows if row["event_num"] == 2)

    assert len(warnings) == 1
    assert start_row["home_period_starter_ids"] is None
    assert start_row["away_period_starter_ids"] is None


def test_project_payload_to_rows_fails_on_duplicate_projected_event_keys(monkeypatch):
    pbp_payload = json.loads(PBP_FIXTURE.read_text())

    def fake_loader(*args, **kwargs):
        return "0022000001", [object(), object()], []

    def fake_build_row(*args, **kwargs):
        return {
            "game_id": "0022000001",
            "event_num": 2,
        }

    monkeypatch.setattr(event_context, "load_live_enhanced_pbp_items_with_period_starter_warnings", fake_loader)
    monkeypatch.setattr(event_context, "build_event_context_row", fake_build_row)

    with pytest.raises(event_context.ProjectionFailure, match="Duplicate projected event keys"):
        event_context.project_payload_to_rows(
            pbp_payload,
            home_team_id=1610612751,
            away_team_id=1610612744,
            source_file=str(PBP_FIXTURE),
            source_last_modified_utc=None,
            fallback_game_id="0022000001",
        )


def test_context_rows_accept_standard_silver_metadata():
    _, rows = load_real_projection_rows()
    enriched = event_context.add_silver_metadata(
        rows[:1],
        pipeline_run_id="run_123",
        ingested_at_utc=__import__("datetime").datetime(2026, 3, 27, tzinfo=__import__("datetime").timezone.utc),
        source_system=event_context.SOURCE_SYSTEM,
        source_key="raw/cdn/playbyplay/game_id=0022000001.json",
        source_last_modified_utc=None,
        schema_version=event_context.META_SCHEMA_VERSION,
    )

    assert enriched[0]["_meta_pipeline_run_id"] == "run_123"
    assert enriched[0]["_meta_source_system"] == event_context.SOURCE_SYSTEM
    assert enriched[0]["_meta_source_key"] == "raw/cdn/playbyplay/game_id=0022000001.json"
    assert enriched[0]["_meta_schema_version"] == 1
