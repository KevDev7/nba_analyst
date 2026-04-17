# Ingestion Layout

This folder groups ingestion scripts by source family so new raw-data work does
not keep accumulating in a single flat directory.

## Subfolders

- `bbr/`
  - Basketball Reference fetch/backfill scripts
- `cdn/`
  - NBA live/CDN raw payload ingestion and normalization scripts
- `hoopr/`
  - third-party hoopR / SportsDataverse ingestion scripts
  - ESPN-based backfill lands both `.rds` and `.parquet` per `game_id`
    under `raw/hoopR/espn_nba_pbp/`
  - NBA-native backfill lands both `.rds` and `.parquet` per `game_id`
    under `raw/hoopR/nba_pbp/`
- `nba_stats/`
  - NBA Stats API and related one-off backfill scripts
- `audit/`
  - ingestion audits and completeness checks

## Notes

- This reorganization is source-based only. Script behavior is unchanged.
- Some file names still reflect older naming conventions; normalize them only as
  a follow-up if we decide the scripts are still worth keeping long-term.

## Current-Season Raw Backfills

For current-season CDN raw recovery, the canonical game-id manifest is:

- `raw/cdn/scheduleLeagueV2_1.json`

Refresh it with:

```bash
python3 pipelines/ingestion/nba_stats/backfill_schedule_league_v2.py
```

Then run targeted raw fills from the CDN scripts under `pipelines/ingestion/cdn/`.

Historical `raw/scheduleleaguev2/seasongames/season=*/season_games.parquet`
remains useful for archived season recovery, but it is not the default current-season
driver anymore.
