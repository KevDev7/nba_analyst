from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.ingestion.cdn import backfill_cdn_boxscore as boxscore
from pipelines.ingestion.cdn import backfill_cdn_playbyplay as playbyplay
from pipelines.ingestion.cdn.backfill_manifest import (
    HISTORICAL_MANIFEST_SOURCE,
    LIVE_MANIFEST_SOURCE,
    ManifestGame,
    apply_existing_skip_and_cap,
    build_historical_manifest_games,
    build_live_manifest_games,
    filter_manifest_games,
    merge_manifest_games,
    parse_cli_game_ids,
)
from pipelines.ingestion.nba_stats.backfill_schedule_league_v2_season_games import (
    current_nba_season_start_year,
)


def sample_live_payload() -> dict:
    return {
        "leagueSchedule": {
            "seasonYear": "2025-26",
            "gameDates": [
                {
                    "gameDate": "02/20/2026 00:00:00",
                    "games": [
                        {
                            "gameId": "0022500802",
                            "gameDateTimeUTC": "2026-02-20T00:30:00Z",
                            "gameStatusText": "Final",
                        }
                    ],
                },
                {
                    "gameDate": "03/31/2026 00:00:00",
                    "games": [
                        {
                            "gameId": "0022501099",
                            "gameDateTimeUTC": "2026-03-31T23:00:00Z",
                            "gameStatusText": "7:00 pm ET",
                        }
                    ],
                },
                {
                    "gameDate": "06/19/2026 00:00:00",
                    "games": [
                        {
                            "gameId": "0042500407",
                            "gameDateTimeUTC": "2026-06-20T00:30:00Z",
                            "gameStatusText": "8:30 pm ET",
                        }
                    ],
                },
            ],
        }
    }


def test_build_live_manifest_games_discovers_current_season_ids() -> None:
    games = build_live_manifest_games(sample_live_payload())
    game_ids = {game.game_id for game in games}
    assert "0022500802" in game_ids
    assert "0022501099" in game_ids
    assert all(game.season_year == "2025-26" for game in games)


def test_filter_manifest_games_excludes_future_by_default() -> None:
    games = build_live_manifest_games(sample_live_payload())
    filtered = filter_manifest_games(
        games,
        season="2025-26",
        include_future=False,
        today=date(2026, 3, 31),
    )
    assert [game.game_id for game in filtered] == ["0022501099", "0022500802"]


def test_filter_manifest_games_includes_future_when_requested() -> None:
    games = build_live_manifest_games(sample_live_payload())
    filtered = filter_manifest_games(
        games,
        season="2025-26",
        include_future=True,
        today=date(2026, 3, 31),
    )
    assert [game.game_id for game in filtered] == ["0042500407", "0022501099", "0022500802"]


def test_explicit_game_ids_override_other_filters_and_preserve_order() -> None:
    games = build_live_manifest_games(sample_live_payload())
    filtered = filter_manifest_games(
        games,
        explicit_game_ids=["0022500802", "0022509999", "0022501099"],
        season="2024-25",
        date_from=date(2025, 1, 1),
        date_to=date(2025, 1, 31),
        include_future=False,
        today=date(2026, 1, 1),
    )
    assert [game.game_id for game in filtered] == ["0022500802", "0022509999", "0022501099"]
    assert filtered[1].manifest_source == "explicit"


def test_merge_manifest_games_prefers_live_manifest_rows() -> None:
    live_games = build_live_manifest_games(sample_live_payload())
    historical_games = build_historical_manifest_games(
        [
            {"gameId": "0022500802", "gameDateTimeUTC": "2026-02-19T00:30:00Z"},
            {"gameId": "0022500700", "gameDateTimeUTC": "2026-02-10T00:30:00Z"},
        ],
        season_start_year=2025,
    )
    merged = merge_manifest_games(live_games, historical_games)
    merged_by_id = {game.game_id: game for game in merged}
    assert merged_by_id["0022500802"].manifest_source == LIVE_MANIFEST_SOURCE
    assert merged_by_id["0022500700"].manifest_source == HISTORICAL_MANIFEST_SOURCE


def test_apply_existing_skip_and_cap_is_deterministic() -> None:
    games = [
        ManifestGame(
            game_id="0022500804",
            season_year="2025-26",
            game_date=date(2026, 2, 20),
            game_datetime_utc=datetime(2026, 2, 20, 3, 0, tzinfo=timezone.utc),
            game_status_text="Final",
            manifest_source=LIVE_MANIFEST_SOURCE,
        ),
        ManifestGame(
            game_id="0022500803",
            season_year="2025-26",
            game_date=date(2026, 2, 20),
            game_datetime_utc=datetime(2026, 2, 20, 2, 0, tzinfo=timezone.utc),
            game_status_text="Final",
            manifest_source=LIVE_MANIFEST_SOURCE,
        ),
        ManifestGame(
            game_id="0022500802",
            season_year="2025-26",
            game_date=date(2026, 2, 20),
            game_datetime_utc=datetime(2026, 2, 20, 1, 0, tzinfo=timezone.utc),
            game_status_text="Final",
            manifest_source=LIVE_MANIFEST_SOURCE,
        ),
    ]
    selected, skipped_existing = apply_existing_skip_and_cap(
        games,
        object_exists_for_game_id=lambda game_id: game_id == "0022500803",
        max_games_per_run=2,
    )
    assert skipped_existing == 1
    assert [game.game_id for game in selected] == ["0022500804", "0022500802"]


def test_parse_cli_game_ids_normalizes_and_dedupes() -> None:
    assert parse_cli_game_ids("22500802,0022500802, 0022501099 ") == [
        "0022500802",
        "0022501099",
    ]


def test_boxscore_key_candidates_cover_padded_and_legacy_formats() -> None:
    assert boxscore.destination_key_candidates_for_game("0022500802") == [
        "raw/cdn/boxscore/game_id=0022500802.json",
        "raw/cdn/boxscore/game_id=22500802.json",
    ]


def test_boxscore_parse_args_supports_targeted_cli(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_cdn_boxscore.py",
            "--manifest-source",
            "hybrid",
            "--season",
            "2025-26",
            "--date-from",
            "2026-02-20",
            "--date-to",
            "2026-03-31",
            "--game-ids",
            "0022500802,0022501099",
            "--max-games-per-run",
            "25",
            "--dry-run",
            "--include-future",
        ],
    )
    args = boxscore.parse_args()
    assert args.manifest_source == "hybrid"
    assert args.season == "2025-26"
    assert args.date_from == date(2026, 2, 20)
    assert args.date_to == date(2026, 3, 31)
    assert args.game_ids == "0022500802,0022501099"
    assert args.max_games_per_run == 25
    assert args.dry_run is True
    assert args.include_future is True


def test_playbyplay_parse_args_supports_targeted_cli(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "backfill_cdn_playbyplay.py",
            "--manifest-source",
            "live",
            "--season",
            "2025-26",
            "--date-from",
            "2026-02-20",
            "--max-games-per-run",
            "10",
        ],
    )
    args = playbyplay.parse_args()
    assert args.manifest_source == "live"
    assert args.season == "2025-26"
    assert args.date_from == date(2026, 2, 20)
    assert args.max_games_per_run == 10


def test_current_nba_season_start_year_rolls_with_calendar() -> None:
    assert current_nba_season_start_year(date(2026, 3, 31)) == 2025
    assert current_nba_season_start_year(date(2026, 10, 1)) == 2026
