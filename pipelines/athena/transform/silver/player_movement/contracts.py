from __future__ import annotations

import pyarrow as pa


S3_BUCKET = "nba-analytics-lakehouse-dev"
SNAPSHOT_PARTITION = "snapshot_date=2026-03-01"
SOURCE_KEY = f"raw/cdn/player_movement/{SNAPSHOT_PARTITION}/player_movement.json"
DESTINATION_KEY = "silver/player_movement.parquet"
TABLE_NAME = "player_movement"
META_SOURCE_SYSTEM = "nba_cdn_player_movement"
META_SCHEMA_VERSION = 1

TARGET_SCHEMA = pa.schema(
    [
        pa.field("Transaction_Type", pa.string()),
        pa.field("TRANSACTION_DATE", pa.timestamp("us")),
        pa.field("TRANSACTION_DESCRIPTION", pa.string()),
        pa.field("TEAM_ID", pa.int64()),
        pa.field("TEAM_SLUG", pa.string()),
        pa.field("PLAYER_ID", pa.int64()),
        pa.field("PLAYER_SLUG", pa.string()),
        pa.field("Additional_Sort", pa.int64()),
        pa.field("GroupSort", pa.string()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)
