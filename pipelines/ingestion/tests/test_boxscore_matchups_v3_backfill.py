from __future__ import annotations

from datetime import date, datetime, timezone

from pipelines.ingestion.cdn.backfill_manifest import ManifestGame
from pipelines.ingestion.nba_stats import backfill_boxscore_matchups_v3 as matchups_backfill


def manifest_game(game_id: str, season_year: str = "2025-26") -> ManifestGame:
    return ManifestGame(
        game_id=game_id,
        season_year=season_year,
        game_date=date(2026, 1, 1),
        game_datetime_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        game_status_text="Final",
        manifest_source="test",
    )


def test_destination_key_for_game_normalizes_to_ten_digit_json_key():
    assert (
        matchups_backfill.destination_key_for_game("22400001")
        == "raw/boxscorematchupsv3/game_id=0022400001.json"
    )


def test_default_season_strings_cover_first_slice_window():
    assert matchups_backfill.season_strings_from_start_years(
        matchups_backfill.DEFAULT_SEASON_START_YEARS
    ) == {
        "2020-21",
        "2021-22",
        "2022-23",
        "2023-24",
        "2024-25",
        "2025-26",
    }


def test_filter_to_game_id_prefixes_keeps_regular_playoff_and_play_in():
    games = [
        manifest_game("0012500001"),
        manifest_game("0022500001"),
        manifest_game("0032500001"),
        manifest_game("0042500001"),
        manifest_game("0052500001"),
        manifest_game("0062500001"),
    ]

    selected = matchups_backfill.filter_to_game_id_prefixes(
        games,
        matchups_backfill.DEFAULT_GAME_ID_PREFIXES,
    )

    assert [game.game_id for game in selected] == [
        "0022500001",
        "0042500001",
        "0052500001",
    ]
