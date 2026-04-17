from __future__ import annotations

import io
from datetime import date, datetime, timezone
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.athena.transform.gold.gold_transform_helpers import (
    canonical_season_start_year_from_date,
    canonical_season_year_from_date,
    choose_primary_team,
    games_played_from_values,
    normalize_game_id,
    normalize_position_group,
    parse_game_code_date,
    parse_iso_duration_seconds,
    read_parquet_table_from_s3,
    safe_ratio,
    season_type_code_from_game_id,
    season_type_label_from_code,
)
from pipelines.athena.transform.gold.scd2_utils import build_scd2_versions, resolve_scd2_sk


def test_normalize_game_id_zero_pads_short_values() -> None:
    assert normalize_game_id("22400151") == "0022400151"


def test_read_parquet_table_from_s3_matches_columns_case_insensitively() -> None:
    source_table = pa.Table.from_pylist(
        [
            {"gameId": "0022400151", "teamId": 1610612737, "turnoversTotal": 12},
            {"gameId": "0022400152", "teamId": 1610612738, "turnoversTotal": 9},
        ]
    )
    buffer = io.BytesIO()
    pq.write_table(source_table, buffer)
    payload = buffer.getvalue()

    class _FakeS3Client:
        def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
            return {"Body": io.BytesIO(payload)}

    table = read_parquet_table_from_s3(
        _FakeS3Client(),
        "unused-key",
        ["gameid", "teamid", "turnoverstotal", "missing_column"],
    )

    assert table.column_names == ["gameid", "teamid", "turnoverstotal", "missing_column"]
    assert table.to_pylist() == [
        {"gameid": "0022400151", "teamid": 1610612737, "turnoverstotal": 12, "missing_column": None},
        {"gameid": "0022400152", "teamid": 1610612738, "turnoverstotal": 9, "missing_column": None},
    ]


def test_season_derivation_from_date_matches_nba_calendar() -> None:
    assert canonical_season_start_year_from_date(date(2025, 1, 10)) == 2024
    assert canonical_season_year_from_date(date(2025, 1, 10)) == "2024-25"


def test_game_code_date_parsing() -> None:
    assert parse_game_code_date("20250411/BKNMIN") == date(2025, 4, 11)


def test_iso_duration_seconds_parser() -> None:
    assert parse_iso_duration_seconds("PT34M21.50S") == pytest.approx(2061.5)


def test_position_group_normalization() -> None:
    assert normalize_position_group("G-F") == "wing"
    assert normalize_position_group("C") == "center"


def test_safe_ratio_handles_zero_denominator() -> None:
    assert safe_ratio(3, 0) is None
    assert safe_ratio(9, 3) == pytest.approx(3.0)


def test_games_played_rule_matches_databricks_contract() -> None:
    assert games_played_from_values(1, None) == 1
    assert games_played_from_values(0, 12.0) == 1
    assert games_played_from_values(0, 0.0) == 0


def test_season_type_label_lookup() -> None:
    assert season_type_code_from_game_id("0022400151") == "002"
    assert season_type_label_from_code("002") == "regular_season"


def test_choose_primary_team_prefers_games_played_then_games_on_roster_then_lowest_team_id() -> None:
    selected = choose_primary_team(
        [
            {"team_id": 1610612751, "games_played": 4, "games_on_roster": 5},
            {"team_id": 1610612737, "games_played": 4, "games_on_roster": 5},
            {"team_id": 1610612744, "games_played": 3, "games_on_roster": 6},
        ]
    )
    assert selected is not None
    assert selected["team_id"] == 1610612737


def test_build_scd2_versions_carries_forward_tracked_values() -> None:
    events = [
        {
            "person_id": 1,
            "game_id": "0022400001",
            "game_time_utc": datetime(2024, 10, 20, 0, 0, tzinfo=timezone.utc),
            "game_date": date(2024, 10, 20),
            "primary_position": "G",
            "latest_team_id": 1610612744,
        },
        {
            "person_id": 1,
            "game_id": "0022400002",
            "game_time_utc": datetime(2024, 10, 22, 0, 0, tzinfo=timezone.utc),
            "game_date": date(2024, 10, 22),
            "primary_position": None,
            "latest_team_id": 1610612744,
        },
    ]
    versions = build_scd2_versions(
        events=events,
        entity_id_col="person_id",
        tracked_cols=["primary_position", "latest_team_id"],
        carry_forward_cols=["primary_position", "latest_team_id"],
        event_time_col="game_time_utc",
        event_date_col="game_date",
        event_order_cols=["game_time_utc", "game_id"],
        record_source="test",
    )
    assert len(versions) == 1
    assert versions[0]["primary_position"] == "G"


def test_resolve_scd2_sk_uses_point_in_time_window() -> None:
    dim_rows = [
        {
            "person_id": 7,
            "player_sk": 10,
            "valid_from_utc": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "valid_to_utc": datetime(2024, 6, 30, 23, 59, tzinfo=timezone.utc),
            "is_current": 0,
        },
        {
            "person_id": 7,
            "player_sk": 11,
            "valid_from_utc": datetime(2024, 7, 1, tzinfo=timezone.utc),
            "valid_to_utc": None,
            "is_current": 1,
        },
    ]
    fact_rows = [
        {
            "person_id": 7,
            "game_datetime_utc": datetime(2024, 3, 1, tzinfo=timezone.utc),
        },
        {
            "person_id": 7,
            "game_datetime_utc": datetime(2024, 12, 1, tzinfo=timezone.utc),
        },
    ]
    resolved = resolve_scd2_sk(
        fact_rows=fact_rows,
        dim_rows=dim_rows,
        natural_id_col="person_id",
        fact_event_time_col="game_datetime_utc",
        sk_col="player_sk",
        output_sk_col="player_sk",
    )
    assert [row["player_sk"] for row in resolved] == [10, 11]


def test_resolve_scd2_sk_uses_past_future_and_current_fallbacks() -> None:
    dim_rows = [
        {
            "team_id": 3,
            "team_sk": 100,
            "valid_from_utc": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "valid_to_utc": datetime(2024, 6, 30, 23, 59, tzinfo=timezone.utc),
            "is_current": 0,
        },
        {
            "team_id": 3,
            "team_sk": 101,
            "valid_from_utc": datetime(2024, 7, 1, tzinfo=timezone.utc),
            "valid_to_utc": None,
            "is_current": 1,
        },
    ]
    fact_rows = [
        {"opponent_team_id": 3, "game_datetime_utc": datetime(2024, 8, 1, tzinfo=timezone.utc)},
        {"opponent_team_id": 3, "game_datetime_utc": datetime(2023, 12, 1, tzinfo=timezone.utc)},
        {"opponent_team_id": 3, "game_datetime_utc": None},
    ]
    resolved = resolve_scd2_sk(
        fact_rows=fact_rows,
        dim_rows=dim_rows,
        natural_id_col="team_id",
        fact_natural_id_col="opponent_team_id",
        fact_event_time_col="game_datetime_utc",
        sk_col="team_sk",
        output_sk_col="resolved_team_sk",
    )
    assert [row["resolved_team_sk"] for row in resolved] == [101, 100, 101]
