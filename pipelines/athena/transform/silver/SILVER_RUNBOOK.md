# Silver Runbook

## Purpose

Current operational guide for the Athena silver pipeline after the Databricks-alignment refactor.

Use this file for:
- how to run the silver pipeline today
- how heavy-table incremental selection works
- where checkpoints and audits land
- how to do targeted backfills safely

If this file conflicts with the scripts under `pipelines/athena/transform/silver/`, treat the scripts as the implementation source of truth and update this runbook.

## Current Runner Model

Primary orchestrator:
- `pipelines/athena/transform/silver/run_silver_pipeline.py`

Current default runner behavior:
- runs the standard silver reference/build tables first
- optionally includes heavy per-game tables with `--include-heavy`
- appends `validate_silver_reconciliation.py` unless `--skip-reconciliation` is passed
- remains a thin subprocess sequencer, not a workflow engine

Heavy tables currently in the active runner:
- `build_silver_playbyplay_events.py`
- `build_silver_pbpstats_event_projection_v1.py`
- `build_silver_pbpstats_event_context_v1.py`
- `build_silver_on_court_state.py`

Important note:
- `build_silver_possessions.py` is a heavy table with the same checkpoint/runtime model, but it is not currently included in `run_silver_pipeline.py --include-heavy`
- run it directly when possession refreshes are needed

## Standard Commands

Recommended upstream raw refresh before targeted catch-up:

```bash
python3 pipelines/ingestion/nba_stats/backfill_schedule_league_v2.py
python3 pipelines/ingestion/cdn/backfill_cdn_boxscore.py --season 2025-26 --date-from 2026-02-20 --date-to 2026-03-31 --dry-run
python3 pipelines/ingestion/cdn/backfill_cdn_playbyplay.py --season 2025-26 --date-from 2026-02-20 --date-to 2026-03-31 --dry-run
```

Non-heavy run:

```bash
python3 pipelines/athena/transform/silver/run_silver_pipeline.py
```

Runner including heavy tables:

```bash
python3 pipelines/athena/transform/silver/run_silver_pipeline.py --include-heavy
```

Targeted script subset:

```bash
python3 pipelines/athena/transform/silver/run_silver_pipeline.py --only build_silver_boxscore_game.py,build_silver_boxscore_player_game.py
```

Targeted heavy rerun:

```bash
python3 pipelines/athena/transform/silver/run_silver_pipeline.py --include-heavy --only build_silver_playbyplay_events.py,build_silver_on_court_state.py --skip-reconciliation
```

Retry / timeout guarded run:

```bash
python3 pipelines/athena/transform/silver/run_silver_pipeline.py --include-heavy --retries 1 --retry-backoff-seconds 15 --timeout-seconds 10800
```

## Heavy-Table Selection Rules

Heavy tables now use the shared runtime in `heavy_silver_runtime.py`.

Selection precedence is:

1. explicit target game ids
2. force full refresh
3. checkpoint incremental selection
4. legacy JSON state fallback only when a checkpoint parquet does not exist yet

Shared behavior:
- one checkpoint parquet per heavy table under `silver/_state/`
- deterministic source fingerprints per `game_id`
- audit/detail metadata records `selection_mode`, `target_game_ids`, `checkpoint_enabled`, and `legacy_state_fallback_used`

Checkpoint keys follow:
- `silver/_state/<table_name>_checkpoint.parquet`

Examples:
- `silver/_state/playbyplay_events_checkpoint.parquet`
- `silver/_state/pbpstats_event_projection_v1_checkpoint.parquet`
- `silver/_state/pbpstats_event_context_v1_checkpoint.parquet`
- `silver/_state/on_court_state_checkpoint.parquet`
- `silver/_state/possessions_checkpoint.parquet`

Legacy JSON state files may still exist for rollback compatibility, but they are no longer the primary incremental mechanism.

## Heavy-Table Environment Controls

Play-by-play:
- `PLAYBYPLAY_TARGET_GAME_IDS`
- `PLAYBYPLAY_FORCE_FULL_REFRESH`

PBPStats projection:
- `PBPSTATS_EVENT_PROJECTION_TARGET_GAME_IDS`
- `PBPSTATS_EVENT_PROJECTION_FORCE_FULL_REFRESH`

PBPStats context:
- `PBPSTATS_EVENT_CONTEXT_TARGET_GAME_IDS`
- `PBPSTATS_EVENT_CONTEXT_FORCE_FULL_REFRESH`

On-court state:
- `ON_COURT_STATE_TARGET_GAME_IDS`
- `ON_COURT_STATE_FORCE_FULL_REFRESH`

Possessions:
- `POSSESSIONS_TARGET_GAME_IDS`
- `POSSESSIONS_FORCE_FULL_REFRESH`

Example direct targeted rerun:

```bash
PLAYBYPLAY_TARGET_GAME_IDS=0022400617 python3 pipelines/athena/transform/silver/build_silver_playbyplay_events.py
```

Example direct full refresh:

```bash
PBPSTATS_EVENT_PROJECTION_FORCE_FULL_REFRESH=true python3 pipelines/athena/transform/silver/build_silver_pbpstats_event_projection_v1.py
```

## Audits And Details

Silver writes audit artifacts under:
- `s3://nba-analytics-lakehouse-dev/silver/_audit/<table>/...`

Heavy tables now standardize these run metadata fields where applicable:
- `selection_mode`
- `force_full_refresh`
- `target_game_ids`
- `selected_game_count`
- `written_game_count`
- `checkpoint_enabled`
- `legacy_state_fallback_used`

Use the latest audit JSON/parquet plus any details JSON to understand:
- selected games
- skipped games
- warnings
- per-game failures

## Possessions Table

`build_silver_possessions.py` is current and supported, but it is table-scoped rather than part of the default silver runner.

Implementation note:
- the shared possession domain logic now lives under `pipelines/athena/transform/silver/possessions/`
- `build_silver_possessions.py` and `build_silver_possessions_ot_fallback.py` remain the operational entrypoints, but they are now thin wrappers over that package
- the package owns the in-memory exact possession materialization and OT fallback family selection, while S3/checkpoint/audit orchestration stays in the wrappers

Current unresolved possession failures and the OT fallback ledger are tracked in:

- `pipelines/athena/transform/silver/PBPSTATS_POSSESSIONS_UNRESOLVED_GAMES.md`

Run it directly:

```bash
python3 pipelines/athena/transform/silver/build_silver_possessions.py
```

Targeted rerun:

```bash
POSSESSIONS_TARGET_GAME_IDS=0022400617 python3 pipelines/athena/transform/silver/build_silver_possessions.py
```

## Validation

Core runner validation:

```bash
python3 pipelines/athena/transform/silver/verify_silver_pipeline.py
```

Current parity/closeout scripts:
- `pipelines/athena/tests/silver/run_pbpstats_event_projection_phase3_validation.py`
- `pipelines/athena/tests/silver/run_pbpstats_event_context_phase3_validation.py`

Use those when validating contract parity or post-change regressions rather than relying on old planning docs.

## Basketball Reference Side Flow

The Basketball Reference player enrichment flow remains outside the main silver runner.

Implementation note:
- the shared BBR domain logic now lives under `pipelines/athena/transform/silver/bbr/`
- the top-level build scripts remain the operational entrypoints, but they are thin wrappers over that package
- `gold/transform_to_extended_player_dim_parquet.py` now consumes the same BBR package for accepted current-player enrichment instead of rebuilding bridge/profile joins locally

Recommended order:

1. Fetch player index HTML
```bash
python3 pipelines/ingestion/bbr/backfill_bbr_players_index.py
```

2. Build the silver index table
```bash
python3 pipelines/athena/transform/silver/build_silver_bbr_player_index.py
```

3. Fetch player profile HTML
```bash
python3 pipelines/ingestion/bbr/backfill_bbr_player_profiles.py
```

4. Build profile label inventory
```bash
python3 pipelines/athena/transform/silver/build_silver_bbr_player_profile_label_inventory.py
```

5. Build flat player profiles
```bash
python3 pipelines/athena/transform/silver/build_silver_bbr_player_profile.py
```

6. Build structured player awards
```bash
python3 pipelines/athena/transform/silver/build_silver_bbr_player_awards.py
```

7. Build the conservative BBR/NBA identity bridge
```bash
python3 pipelines/athena/transform/silver/build_silver_player_identity_bridge_bbr_nba.py
```

Remaining ambiguous bridge rows are tracked in:
- [BBR_BRIDGE_REMAINING_AMBIGUOUS.md](pipelines/athena/transform/silver/BBR_BRIDGE_REMAINING_AMBIGUOUS.md)

## Troubleshooting

Heavy job processed too much data:
- inspect the checkpoint parquet for that table under `silver/_state/`
- confirm `*_TARGET_GAME_IDS` and `*_FORCE_FULL_REFRESH` were not set
- inspect audit metadata for `selection_mode`

Heavy job skipped an expected game:
- check whether the source fingerprint changed
- confirm the source object exists for that `game_id`
- inspect details JSON for missing-target or missing-source metadata

Reconciliation warnings:
- inspect `silver/_audit/silver_reconciliation/..._details.json`
- determine whether the mismatch is expected coverage drift or a real integrity issue

## Success Criteria

- runner summary shows `Failures: 0`
- targeted heavy reruns only rewrite the intended game ids
- checkpoint parquet updates for successfully written games
- latest audits show expected selection metadata and zero unexpected errors
