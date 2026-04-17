Frozen golden fixtures for `pbpstats_event_projection_v1`.

Purpose:
- Provide a stable local parity oracle for `event_projection_v2`.
- Avoid relying on live S3 `silver/pbpstats_event_projection_v1` outputs during `v2` development.

Contents:
- `game_id=<GAME_ID>.parquet`: one frozen fixture per selected game
- `manifest.json`: fixture set metadata, source S3 keys, row counts, and preserved column order

Fixture contract:
- These files keep only the stable projection columns from `build_silver_pbpstats_event_projection_v1.PROJECTION_COLUMNS`.
- Silver metadata columns are intentionally removed:
  - `_meta_pipeline_run_id`
  - `_meta_ingested_at_utc`
  - `_meta_source_system`
  - `_meta_source_key`
  - `_meta_source_last_modified_utc`
  - `_meta_schema_version`

Initial game set:
- `0012000001`
- `0012000002`
- `0022000001`
- `0022000002`
- `0022100001`
- `0022100732`
- `0022200001`
- `0022300001`
- `0022400001`
- `0022500001`
