from __future__ import annotations

from pipelines.ingestion.nba_stats import backfill_nba_data_matchups_archives as archive_backfill


def test_archive_for_regular_season_builds_raw_destination_key():
    archive = archive_backfill.archive_for(2024, "regular")

    assert archive.archive_name == "matchups_2024.tar.xz"
    assert archive.url.endswith("/matchups_2024.tar.xz")
    assert (
        archive.destination_key
        == "raw/nba_data/matchups/season=2024/season_type=regular/matchups_2024.tar.xz"
    )


def test_archive_for_playoffs_builds_raw_destination_key():
    archive = archive_backfill.archive_for(2024, "playoffs")

    assert archive.archive_name == "matchups_po_2024.tar.xz"
    assert archive.url.endswith("/matchups_po_2024.tar.xz")
    assert (
        archive.destination_key
        == "raw/nba_data/matchups/season=2024/season_type=playoffs/matchups_po_2024.tar.xz"
    )
