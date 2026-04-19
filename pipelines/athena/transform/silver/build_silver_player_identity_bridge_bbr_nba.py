"""
Build a conservative silver identity bridge between Basketball Reference player IDs and NBA player IDs.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/players.parquet
  s3://nba-analytics-lakehouse-dev/silver/bbr_player_profile.parquet

Writes:
  s3://nba-analytics-lakehouse-dev/silver/player_identity_bridge_bbr_nba.parquet
  s3://nba-analytics-lakehouse-dev/silver/player_identity_bridge_bbr_nba_duplicate_nba.parquet
  s3://nba-analytics-lakehouse-dev/silver/player_identity_bridge_bbr_nba_ambiguous.parquet
  s3://nba-analytics-lakehouse-dev/silver/player_identity_bridge_bbr_nba_unmatched_nba.parquet
  s3://nba-analytics-lakehouse-dev/silver/player_identity_bridge_bbr_nba_unmatched_bbr.parquet
"""

from __future__ import annotations

import io
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from silver_pipeline_helpers import write_audit_artifacts

from bbr.artifacts import build_identity_artifacts
from bbr.identity import (
    EXACT_NAME_MATCH_BLOCKLIST,
    MATCH_METHOD_PRIORITY,
    NBA_TO_BBR_OWNER_OVERRIDES,
    build_accepted_proposal,
    build_ambiguous_row,
    build_bbr_rows,
    build_manual_override_proposal,
    build_nba_rows,
    build_unresolved_entry,
    choose_candidates,
    normalize_bbr_position,
    normalize_nba_position,
    normalize_school,
    normalize_text,
    normalize_text_preserve_suffix,
    null_if_empty,
    nba_metadata_completeness,
    score_candidate,
    summarize_candidate,
    to_date_or_none,
    to_int_or_none,
)
from bbr.ownership import (
    build_bridge_row_from_proposal,
    build_duplicate_nba_row,
    classify_single_unresolved_shared_name_entry,
    group_has_duplicate_nba_shell_rows,
    proposal_sort_key,
    resolve_bbr_ownership,
    resolve_shared_name_group,
)
from bbr.pipeline import BbrPlayerEnrichmentPipeline

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"
NBA_SOURCE_KEY = "silver/players.parquet"
BBR_SOURCE_KEY = "silver/bbr_player_profile.parquet"
BRIDGE_DESTINATION_KEY = "silver/player_identity_bridge_bbr_nba.parquet"
DUPLICATE_NBA_DESTINATION_KEY = "silver/player_identity_bridge_bbr_nba_duplicate_nba.parquet"
AMBIGUOUS_DESTINATION_KEY = "silver/player_identity_bridge_bbr_nba_ambiguous.parquet"
UNMATCHED_NBA_DESTINATION_KEY = "silver/player_identity_bridge_bbr_nba_unmatched_nba.parquet"
UNMATCHED_BBR_DESTINATION_KEY = "silver/player_identity_bridge_bbr_nba_unmatched_bbr.parquet"
TABLE_NAME = "player_identity_bridge_bbr_nba"
META_SOURCE_SYSTEM = "silver_players|silver_bbr_player_profile"
META_SCHEMA_VERSION = 1
META_SOURCE_KEY = "legacy_gold.silver.players|legacy_gold.silver.bbr_player_profile"

BRIDGE_SCHEMA = pa.schema(
    [
        pa.field("nba_person_id", pa.int64()),
        pa.field("nba_player_name", pa.string()),
        pa.field("basketball_reference_player_id", pa.string()),
        pa.field("bbr_player_name", pa.string()),
        pa.field("match_method", pa.string()),
        pa.field("match_confidence", pa.float64()),
        pa.field("name_key", pa.string()),
        pa.field("draft_match_flag", pa.int64()),
        pa.field("weight_match_flag", pa.int64()),
        pa.field("school_match_flag", pa.int64()),
        pa.field("position_match_flag", pa.int64()),
        pa.field("era_sanity_flag", pa.int64()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)

AMBIGUOUS_SCHEMA = pa.schema(
    [
        pa.field("nba_person_id", pa.int64()),
        pa.field("nba_player_name", pa.string()),
        pa.field("name_key", pa.string()),
        pa.field("candidate_count", pa.int64()),
        pa.field("candidate_player_ids", pa.string()),
        pa.field("candidate_player_names", pa.string()),
        pa.field("candidate_reasons", pa.string()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)

DUPLICATE_NBA_SCHEMA = pa.schema(
    [
        pa.field("nba_person_id", pa.int64()),
        pa.field("nba_player_name", pa.string()),
        pa.field("name_key", pa.string()),
        pa.field("basketball_reference_player_id", pa.string()),
        pa.field("bbr_player_name", pa.string()),
        pa.field("candidate_match_method", pa.string()),
        pa.field("candidate_match_score", pa.int64()),
        pa.field("winning_nba_person_id", pa.int64()),
        pa.field("winning_nba_player_name", pa.string()),
        pa.field("winning_match_method", pa.string()),
        pa.field("winning_match_score", pa.int64()),
        pa.field("duplicate_reason", pa.string()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)

UNMATCHED_NBA_SCHEMA = pa.schema(
    [
        pa.field("nba_person_id", pa.int64()),
        pa.field("nba_player_name", pa.string()),
        pa.field("name_key", pa.string()),
        pa.field("height_inches", pa.int64()),
        pa.field("weight_lbs", pa.int64()),
        pa.field("draft_year", pa.int64()),
        pa.field("draft_round", pa.int64()),
        pa.field("draft_number", pa.int64()),
        pa.field("school", pa.string()),
        pa.field("primary_position", pa.string()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)

UNMATCHED_BBR_SCHEMA = pa.schema(
    [
        pa.field("basketball_reference_player_id", pa.string()),
        pa.field("bbr_player_name", pa.string()),
        pa.field("name_key", pa.string()),
        pa.field("weight_lbs", pa.int64()),
        pa.field("draft_year", pa.int64()),
        pa.field("draft_round", pa.int64()),
        pa.field("draft_pick_overall", pa.int64()),
        pa.field("college_raw", pa.string()),
        pa.field("current_team_raw", pa.string()),
        pa.field("position_raw", pa.string()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def add_metadata_columns(rows: list[dict[str, Any]], *, pipeline_run_id: str, ingested_at_utc: datetime) -> None:
    for row in rows:
        row["_meta_pipeline_run_id"] = pipeline_run_id
        row["_meta_ingested_at_utc"] = ingested_at_utc
        row["_meta_source_system"] = META_SOURCE_SYSTEM
        row["_meta_source_key"] = META_SOURCE_KEY
        row["_meta_schema_version"] = META_SCHEMA_VERSION


def write_rows(rows: list[dict[str, Any]], schema: pa.Schema, key: str, s3_client) -> None:
    table = pa.Table.from_pylist(rows, schema=schema)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=buffer.getvalue(), ContentType="application/octet-stream")


def main() -> None:
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"player_identity_bridge_bbr_nba_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    pipeline = BbrPlayerEnrichmentPipeline(s3_client=s3_client)
    artifacts = pipeline.build_silver_artifacts()

    bridge_rows = list(artifacts.accepted_bridge_rows)
    duplicate_nba_rows = list(artifacts.duplicate_nba_rows)
    ambiguous_rows = list(artifacts.ambiguous_rows)
    unmatched_nba_rows = list(artifacts.unmatched_nba_rows)
    unmatched_bbr_rows = list(artifacts.unmatched_bbr_rows)

    add_metadata_columns(bridge_rows, pipeline_run_id=pipeline_run_id, ingested_at_utc=ingested_at_utc)
    add_metadata_columns(duplicate_nba_rows, pipeline_run_id=pipeline_run_id, ingested_at_utc=ingested_at_utc)
    add_metadata_columns(ambiguous_rows, pipeline_run_id=pipeline_run_id, ingested_at_utc=ingested_at_utc)
    add_metadata_columns(unmatched_nba_rows, pipeline_run_id=pipeline_run_id, ingested_at_utc=ingested_at_utc)
    add_metadata_columns(unmatched_bbr_rows, pipeline_run_id=pipeline_run_id, ingested_at_utc=ingested_at_utc)

    write_rows(bridge_rows, BRIDGE_SCHEMA, BRIDGE_DESTINATION_KEY, s3_client)
    write_rows(duplicate_nba_rows, DUPLICATE_NBA_SCHEMA, DUPLICATE_NBA_DESTINATION_KEY, s3_client)
    write_rows(ambiguous_rows, AMBIGUOUS_SCHEMA, AMBIGUOUS_DESTINATION_KEY, s3_client)
    write_rows(unmatched_nba_rows, UNMATCHED_NBA_SCHEMA, UNMATCHED_NBA_DESTINATION_KEY, s3_client)
    write_rows(unmatched_bbr_rows, UNMATCHED_BBR_SCHEMA, UNMATCHED_BBR_DESTINATION_KEY, s3_client)

    warning_reason_counts: Counter[str] = Counter()
    warning_reason_counts["duplicate_nba_rows"] = len(duplicate_nba_rows)
    warning_reason_counts["ambiguous_rows"] = len(ambiguous_rows)
    warning_reason_counts["unmatched_nba_rows"] = len(unmatched_nba_rows)
    warning_reason_counts["unmatched_bbr_rows"] = len(unmatched_bbr_rows)

    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": "success_with_warnings" if warning_reason_counts else "success",
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_keys": f"{NBA_SOURCE_KEY}|{BBR_SOURCE_KEY}",
        "destination_key": BRIDGE_DESTINATION_KEY,
        "duplicate_nba_destination_key": DUPLICATE_NBA_DESTINATION_KEY,
        "ambiguous_destination_key": AMBIGUOUS_DESTINATION_KEY,
        "unmatched_nba_destination_key": UNMATCHED_NBA_DESTINATION_KEY,
        "unmatched_bbr_destination_key": UNMATCHED_BBR_DESTINATION_KEY,
        "nba_input_row_count": len(pipeline._load_nba_player_rows()),
        "bbr_input_row_count": len(artifacts.profile_rows),
        "output_row_count": len(bridge_rows),
        "duplicate_nba_row_count": len(duplicate_nba_rows),
        "ambiguous_row_count": len(ambiguous_rows),
        "unmatched_nba_row_count": len(unmatched_nba_rows),
        "unmatched_bbr_row_count": len(unmatched_bbr_rows),
        "warning_count": sum(warning_reason_counts.values()),
        "error_count": 0,
        "warning_reason_counts": json.dumps(dict(warning_reason_counts), sort_keys=True),
        "error_reason_counts": "{}",
    }
    write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )


if __name__ == "__main__":
    main()
