"""
Build a discovery-oriented silver inventory of labels found on Basketball Reference player profile pages.

Reads latest snapshot per player from:
  s3://nba-analytics-lakehouse-dev/raw/bball-reference/player_profile/

Writes:
  s3://nba-analytics-lakehouse-dev/silver/bbr_player_profile_label_inventory.parquet

Purpose:
  - inventory which labeled fields exist across profile pages
  - count frequency of labels before designing the final bbr_player_profile schema
  - preserve unlabeled paragraphs for review because not every useful fact appears as label:value

Final grain:
  - one row per detected label occurrence
  - if a paragraph has no detected labels, emit one row with null label fields for that paragraph
"""

from __future__ import annotations

import gzip
import io
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from silver_pipeline_helpers import write_audit_artifacts

load_dotenv(override=True)  # Ensure .env credentials override any system variables

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "raw/bball-reference/player_profile/"
DESTINATION_KEY = "silver/bbr_player_profile_label_inventory.parquet"
TABLE_NAME = "bbr_player_profile_label_inventory"
META_SOURCE_SYSTEM = "basketball_reference_player_profile_html"
META_SCHEMA_VERSION = 1

SOURCE_KEY_PATTERN = re.compile(
    r"^raw/bball-reference/player_profile/player_id=([^/]+)/run_date=\d{4}-\d{2}-\d{2}/"
    r"fetched_at=(\d{8}T\d{6}Z)\.html\.gz$"
)
META_START_PATTERN = re.compile(r'<div id="meta">', re.IGNORECASE)
META_END_PATTERNS = [
    re.compile(r"</div>\s*</div><!-- div#meta -->", re.IGNORECASE),
    re.compile(r'<ul id="bling">', re.IGNORECASE),
    re.compile(r'<div id="leaderboard_wrapper">', re.IGNORECASE),
]
PARAGRAPH_PATTERN = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
STRONG_PATTERN = re.compile(r"<strong[^>]*>(.*?)</strong>", re.IGNORECASE | re.DOTALL)
H1_NAME_PATTERN = re.compile(
    r"<h1[^>]*>\s*<span>(.*?)</span>\s*</h1>",
    re.IGNORECASE | re.DOTALL,
)
TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")

TARGET_SCHEMA = pa.schema(
    [
        pa.field("basketball_reference_player_id", pa.string()),
        pa.field("page_player_name", pa.string()),
        pa.field("paragraph_index", pa.int64()),
        pa.field("paragraph_html_raw", pa.string()),
        pa.field("paragraph_text_raw", pa.string()),
        pa.field("has_detected_label", pa.int64()),
        pa.field("label_ordinal_in_paragraph", pa.int64()),
        pa.field("label_count_in_paragraph", pa.int64()),
        pa.field("label_text_raw", pa.string()),
        pa.field("label_name_normalized", pa.string()),
        pa.field("source_snapshot_fetched_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def null_if_empty(value: Any) -> Any:
    """Convert empty/blank strings to None."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def strip_tags(html: str) -> str:
    """Remove HTML tags, unescape entities, and normalize whitespace."""
    text = TAG_PATTERN.sub(" ", html)
    text = unescape(text)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def normalize_label_name(label_text: str | None) -> str | None:
    """Normalize a raw label into a lowercase underscore-separated token."""
    label_text = null_if_empty(label_text)
    if label_text is None:
        return None
    normalized = unescape(str(label_text)).strip().rstrip(":").lower()
    normalized = NON_ALNUM_PATTERN.sub("_", normalized).strip("_")
    return normalized or None


def list_source_objects(s3_client) -> list[dict[str, Any]]:
    """List all raw Basketball Reference player profile snapshots."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".html.gz"):
                objects.append(obj)

    return objects


def parse_source_key(key: str) -> tuple[str, datetime] | None:
    """Parse source key into (player_id, fetched_at_utc)."""
    match = SOURCE_KEY_PATTERN.match(key)
    if match is None:
        return None
    player_id = match.group(1)
    fetched_at_utc = datetime.strptime(match.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    return player_id, fetched_at_utc


def is_newer_source(
    current_fetched_at_utc: datetime,
    current_last_modified_utc: datetime | None,
    candidate_fetched_at_utc: datetime,
    candidate_last_modified_utc: datetime | None,
) -> bool:
    """Return True when the candidate raw snapshot should replace the current one."""
    if candidate_fetched_at_utc > current_fetched_at_utc:
        return True
    if candidate_fetched_at_utc < current_fetched_at_utc:
        return False

    min_utc = datetime.min.replace(tzinfo=timezone.utc)
    return (candidate_last_modified_utc or min_utc) > (current_last_modified_utc or min_utc)


def latest_source_per_player(source_objects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Select the latest raw source object for each player profile."""
    latest: dict[str, dict[str, Any]] = {}

    for obj in source_objects:
        key = obj.get("Key", "")
        parsed = parse_source_key(key)
        if parsed is None:
            continue

        player_id, fetched_at_utc = parsed
        candidate_last_modified_utc = obj.get("LastModified")
        if isinstance(candidate_last_modified_utc, datetime) and candidate_last_modified_utc.tzinfo is None:
            candidate_last_modified_utc = candidate_last_modified_utc.replace(tzinfo=timezone.utc)

        current = latest.get(player_id)
        if current is None:
            latest[player_id] = {
                "key": key,
                "player_id": player_id,
                "fetched_at_utc": fetched_at_utc,
                "last_modified_utc": candidate_last_modified_utc,
            }
            continue

        if is_newer_source(
            current_fetched_at_utc=current["fetched_at_utc"],
            current_last_modified_utc=current["last_modified_utc"],
            candidate_fetched_at_utc=fetched_at_utc,
            candidate_last_modified_utc=candidate_last_modified_utc,
        ):
            latest[player_id] = {
                "key": key,
                "player_id": player_id,
                "fetched_at_utc": fetched_at_utc,
                "last_modified_utc": candidate_last_modified_utc,
            }

    if not latest:
        raise ValueError(f"No source snapshots found under s3://{S3_BUCKET}/{SOURCE_PREFIX}")

    return latest


def read_gzipped_html(s3_client, key: str) -> str:
    """Read and decode one gzipped raw HTML object from S3."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload = response["Body"].read()
    return gzip.decompress(payload).decode("utf-8", errors="replace")


def extract_meta_block(html: str) -> str | None:
    """Extract the player bio/meta HTML block used for label discovery."""
    start_match = META_START_PATTERN.search(html)
    if start_match is None:
        return None

    start = start_match.start()
    end_candidates: list[int] = []
    for pattern in META_END_PATTERNS:
        end_match = pattern.search(html, start_match.end())
        if end_match is not None:
            end_candidates.append(end_match.start())

    if not end_candidates:
        return html[start:]
    return html[start : min(end_candidates)]


def extract_page_player_name(meta_html: str) -> str | None:
    """Extract the rendered page player name from the meta block h1."""
    match = H1_NAME_PATTERN.search(meta_html)
    if match is None:
        return None
    return null_if_empty(strip_tags(match.group(1)))


def detect_labels_in_paragraph(paragraph_html: str) -> list[str]:
    """
    Detect label-like strong segments in one paragraph.

    Heuristic:
      - a strong segment is treated as a label when the strong text itself ends with ':'
      - or when the immediate following text after </strong> begins with ':'
    This excludes strong-name paragraphs while still catching cases like Pronunciation.
    """
    labels: list[str] = []

    for match in STRONG_PATTERN.finditer(paragraph_html):
        strong_text = strip_tags(match.group(1))
        if not strong_text:
            continue

        strong_text_compact = strong_text.strip()
        trailing_text = paragraph_html[match.end() :]
        trailing_text_stripped = trailing_text.lstrip()

        is_label = strong_text_compact.endswith(":") or trailing_text_stripped.startswith(":")
        if not is_label:
            continue

        labels.append(strong_text_compact.rstrip(":").strip())

    return labels


def build_rows_from_meta(
    *,
    player_id: str,
    meta_html: str,
    source_key: str,
    source_last_modified_utc: datetime | None,
    source_snapshot_fetched_at_utc: datetime,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Build label-inventory rows from one profile meta block."""
    rows: list[dict[str, Any]] = []
    label_counter: Counter[str] = Counter()

    page_player_name = extract_page_player_name(meta_html)
    paragraphs = PARAGRAPH_PATTERN.findall(meta_html)

    for paragraph_index, paragraph_html in enumerate(paragraphs, start=1):
        paragraph_text_raw = null_if_empty(strip_tags(paragraph_html))
        labels = detect_labels_in_paragraph(paragraph_html)

        if not labels:
            rows.append(
                {
                    "basketball_reference_player_id": player_id,
                    "page_player_name": page_player_name,
                    "paragraph_index": paragraph_index,
                    "paragraph_html_raw": null_if_empty(WHITESPACE_PATTERN.sub(" ", paragraph_html).strip()),
                    "paragraph_text_raw": paragraph_text_raw,
                    "has_detected_label": 0,
                    "label_ordinal_in_paragraph": None,
                    "label_count_in_paragraph": 0,
                    "label_text_raw": None,
                    "label_name_normalized": None,
                    "source_snapshot_fetched_at_utc": source_snapshot_fetched_at_utc,
                    "_meta_source_key": source_key,
                    "_meta_source_last_modified_utc": source_last_modified_utc,
                }
            )
            continue

        label_count = len(labels)
        for label_ordinal, label_text_raw in enumerate(labels, start=1):
            label_name_normalized = normalize_label_name(label_text_raw)
            if label_name_normalized is not None:
                label_counter[label_name_normalized] += 1

            rows.append(
                {
                    "basketball_reference_player_id": player_id,
                    "page_player_name": page_player_name,
                    "paragraph_index": paragraph_index,
                    "paragraph_html_raw": null_if_empty(WHITESPACE_PATTERN.sub(" ", paragraph_html).strip()),
                    "paragraph_text_raw": paragraph_text_raw,
                    "has_detected_label": 1,
                    "label_ordinal_in_paragraph": label_ordinal,
                    "label_count_in_paragraph": label_count,
                    "label_text_raw": null_if_empty(label_text_raw),
                    "label_name_normalized": label_name_normalized,
                    "source_snapshot_fetched_at_utc": source_snapshot_fetched_at_utc,
                    "_meta_source_key": source_key,
                    "_meta_source_last_modified_utc": source_last_modified_utc,
                }
            )

    return rows, label_counter


def add_metadata_columns(
    rows: list[dict[str, Any]],
    *,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
) -> None:
    """Attach standardized silver metadata columns."""
    for row in rows:
        row["_meta_pipeline_run_id"] = pipeline_run_id
        row["_meta_ingested_at_utc"] = ingested_at_utc
        row["_meta_source_system"] = META_SOURCE_SYSTEM
        row["_meta_schema_version"] = META_SCHEMA_VERSION


def write_parquet(rows: list[dict[str, Any]], s3_client) -> None:
    """Write label inventory rows to a single parquet object."""
    table = pa.Table.from_pylist(rows, schema=TARGET_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=DESTINATION_KEY,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )


def main() -> None:
    """Build the Basketball Reference profile label inventory parquet."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = (
        f"bbr_player_profile_label_inventory_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_"
        f"{uuid.uuid4().hex[:8]}"
    )

    print(f"Listing raw source objects under s3://{S3_BUCKET}/{SOURCE_PREFIX}")
    source_objects = list_source_objects(s3_client)
    print(f"Found {len(source_objects)} raw source objects")

    latest_sources = latest_source_per_player(source_objects)
    print(f"Selected {len(latest_sources)} latest player profile snapshots")

    rows: list[dict[str, Any]] = []
    discovered_label_counts: Counter[str] = Counter()
    parse_failures = 0
    players_missing_meta = 0
    players_with_zero_paragraphs = 0

    for player_id in sorted(latest_sources):
        source = latest_sources[player_id]
        key = source["key"]
        print(f"Scanning labels for {player_id}: s3://{S3_BUCKET}/{key}")

        try:
            html = read_gzipped_html(s3_client, key)
            meta_html = extract_meta_block(html)
            if meta_html is None:
                players_missing_meta += 1
                continue

            player_rows, player_label_counts = build_rows_from_meta(
                player_id=player_id,
                meta_html=meta_html,
                source_key=key,
                source_last_modified_utc=source["last_modified_utc"],
                source_snapshot_fetched_at_utc=source["fetched_at_utc"],
            )
        except Exception as exc:
            parse_failures += 1
            print(f"{key}: failed to inventory labels ({type(exc).__name__}: {exc})")
            continue

        if not player_rows:
            players_with_zero_paragraphs += 1
            continue

        rows.extend(player_rows)
        discovered_label_counts.update(player_label_counts)

    add_metadata_columns(
        rows,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
    )

    print(f"Writing {len(rows)} rows to s3://{S3_BUCKET}/{DESTINATION_KEY}")
    write_parquet(rows, s3_client)

    warning_reason_counts: Counter[str] = Counter()
    if parse_failures > 0:
        warning_reason_counts["source_parse_failures"] = parse_failures
    if players_missing_meta > 0:
        warning_reason_counts["players_missing_meta_block"] = players_missing_meta
    if players_with_zero_paragraphs > 0:
        warning_reason_counts["players_with_zero_paragraphs"] = players_with_zero_paragraphs

    run_status = "success"
    if warning_reason_counts:
        run_status = "success_with_warnings"

    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": run_status,
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_prefix": SOURCE_PREFIX,
        "destination_key": DESTINATION_KEY,
        "input_object_count": len(source_objects),
        "selected_latest_object_count": len(latest_sources),
        "output_row_count": len(rows),
        "distinct_player_count": len(latest_sources),
        "distinct_label_count": len(discovered_label_counts),
        "warning_count": sum(warning_reason_counts.values()),
        "error_count": 0,
        "warning_reason_counts": json.dumps(dict(warning_reason_counts), sort_keys=True),
        "error_reason_counts": "{}",
        "top_25_labels_json": json.dumps(discovered_label_counts.most_common(25)),
    }
    audit_json_key, audit_parquet_key = write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )

    print(f"Wrote audit JSON: s3://{S3_BUCKET}/{audit_json_key}")
    print(f"Wrote audit parquet: s3://{S3_BUCKET}/{audit_parquet_key}")

    if discovered_label_counts:
        print("Top discovered labels:")
        for label, count in discovered_label_counts.most_common(15):
            print(f"  {label}: {count}")


if __name__ == "__main__":
    main()
