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
- `source_manifest.py` renders the raw/bronze source map from
  `pipelines/athena/metadata/pipeline_registry.json` so source ownership can be
  inspected without reading every backfill script.
- Game- and season-scoped raw sources share the current refactor backfill window
  declared in `source_manifest.py`: `2020-21` through `2025-26`. Quality source
  completeness reads this same convention instead of keeping its own copy.
- Reference repository clones live under `/references` and are not operational
  ingestion code. Promote logic from a reference clone into `pipelines/ingestion`
  only through a reviewed source-faithful backfill script and a registry/source
  manifest update.

```bash
python3 pipelines/ingestion/source_manifest.py
```

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

## BoxScoreMatchupsV3 Raw Backfill

`pipelines/ingestion/nba_stats/backfill_boxscore_matchups_v3.py` ingests source-faithful
NBA Stats matchup JSON from `boxscorematchupsv3`.

Default slice:
- seasons `2020-21` through `2025-26`
- completed games only unless `--include-future` is passed
- game id prefixes `002`, `004`, `005` for regular season, playoffs, and play-in
- raw output: `raw/boxscorematchupsv3/game_id=<GAME_ID>.json`

Dry-run first:

```bash
python3 pipelines/ingestion/nba_stats/backfill_boxscore_matchups_v3.py --dry-run
```

Run a small paced batch:

```bash
python3 pipelines/ingestion/nba_stats/backfill_boxscore_matchups_v3.py --max-games-per-run 50
```

If `stats.nba.com` is unavailable from the runtime, use the packaged archives from
`shufinskiy/nba_data` and preserve the source `.tar.xz` files in raw:

```bash
python3 pipelines/ingestion/nba_stats/backfill_nba_data_matchups_archives.py --dry-run
python3 pipelines/ingestion/nba_stats/backfill_nba_data_matchups_archives.py
```

Archive output lands under `raw/nba_data/matchups/season=<start_year>/season_type=<regular|playoffs>/`.

## BoxScoreTraditionalV3 Period-Range Raw Backfill

`pipelines/ingestion/nba_stats/backfill_boxscoretraditionalv3_period_ranges.py`
fetches source-faithful NBA Stats JSON for period-range player presence. This raw
input powers the silver `on_court_period_starter_qa` sidecar.

Target a small set of games first:

```bash
python3 pipelines/ingestion/nba_stats/backfill_boxscoretraditionalv3_period_ranges.py \
  --game-ids 0022500001 \
  --periods 1,2,3,4,5 \
  --dry-run
```

Raw output lands under:

```text
raw/boxscoretraditionalv3/period_player_stats/game_id=<GAME_ID>/period=<PERIOD>.json
```
