"""Shared contracts for silver boxscore transforms."""

from __future__ import annotations

S3_BUCKET = "nba-analytics-lakehouse-dev"
CDN_BOXSCORE_SOURCE_PREFIX = "raw/cdn/boxscore/"
CDN_BOXSCORE_SOURCE_SYSTEM = "nba_cdn_boxscore"
META_SCHEMA_VERSION = 1

TEAM_SIDES = {"home", "away"}
OFFICIAL_ASSIGNMENTS = {"OFFICIAL1", "OFFICIAL2", "OFFICIAL3", "ALTERNATE"}

METADATA_COLUMN_NAMES = [
    "_meta_pipeline_run_id",
    "_meta_ingested_at_utc",
    "_meta_source_system",
    "_meta_source_key",
    "_meta_source_last_modified_utc",
    "_meta_schema_version",
]

