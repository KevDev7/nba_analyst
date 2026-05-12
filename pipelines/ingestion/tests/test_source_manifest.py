from __future__ import annotations

from pipelines.ingestion.source_manifest import (
    DEFAULT_BACKFILL_SEASONS,
    build_source_manifest,
    expected_backfill_seasons,
    infer_source_family,
    load_registry,
)


def test_infer_source_family_from_raw_prefix():
    assert infer_source_family("raw/cdn/playbyplay/game_id=<GAME_ID>.json") == "cdn"
    assert infer_source_family("raw/bball-reference/player_profile/player_id=<ID>/*.html") == "bbr"
    assert infer_source_family("raw/hoopR/nba_pbp/game_id=<GAME_ID>.*") == "hoopr"
    assert infer_source_family("raw/nba_data/matchups/season=<YYYY>/*.tar.xz") == "nba_data"


def test_source_manifest_lists_raw_sources_from_registry():
    manifest = build_source_manifest(load_registry())
    sources = {source["id"]: source for source in manifest["sources"]}

    assert manifest["source_count"] == 12
    assert sources["raw.cdn_playbyplay"]["source_family"] == "cdn"
    assert sources["raw.boxscorematchupsv3"]["source_family"] == "nba_stats"
    assert sources["raw.nba_data_matchups_archive"]["raw_file_type"] == "xz"
    assert sources["raw.hoopr_nba_pbp"]["source_family"] == "hoopr"
    assert sources["raw.cdn_playbyplay"]["expected_backfill_seasons"] == list(
        DEFAULT_BACKFILL_SEASONS
    )
    assert sources["raw.bbr_players_index"]["expected_backfill_seasons"] == []


def test_expected_backfill_seasons_only_for_game_or_season_scoped_sources():
    assert expected_backfill_seasons("raw/cdn/playbyplay/game_id=<GAME_ID>.json") == list(
        DEFAULT_BACKFILL_SEASONS
    )
    assert expected_backfill_seasons("raw/scheduleleaguev2/seasongames/season=*/season_games.parquet") == list(
        DEFAULT_BACKFILL_SEASONS
    )
    assert expected_backfill_seasons("raw/bball-reference/players_index/letter=<LETTER>/*.html") == []
