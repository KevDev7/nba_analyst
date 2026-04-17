"""
Backfill Basketball Reference player profile HTML pages into raw S3 storage.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/bbr_player_index.parquet

Writes:
  s3://nba-analytics-lakehouse-dev/raw/bball-reference/player_profile/

Output shape:
  - raw/bball-reference/player_profile/player_id={player_id}/run_date=YYYY-MM-DD/fetched_at=TIMESTAMP.html.gz

Fetch behavior:
  - Uses player_profile_url from the silver index table as the source of truth.
  - Waits 4 seconds between requests to stay comfortably above the robots crawl-delay.
  - Preserves raw HTML in gzipped form; parsing belongs in silver.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import time
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow.parquet as pq
import requests
from dotenv import load_dotenv

load_dotenv(override=True)  # Ensure .env credentials override any system variables

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_KEY = "silver/bbr_player_index.parquet"
DESTINATION_PREFIX = "raw/bball-reference/player_profile"

REQUEST_DELAY_SECONDS = 4.0
API_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5.0

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
}


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def run_date(value: datetime) -> str:
    """Render a UTC timestamp as YYYY-MM-DD for key partitioning."""
    return value.strftime("%Y-%m-%d")


def timestamp_slug(value: datetime) -> str:
    """Render a UTC timestamp as a compact object-key-safe slug."""
    return value.strftime("%Y%m%dT%H%M%SZ")


def destination_key(player_id: str, fetched_at_utc: datetime) -> str:
    """S3 key for one raw player profile HTML snapshot."""
    return (
        f"{DESTINATION_PREFIX}/player_id={player_id}/run_date={run_date(fetched_at_utc)}/"
        f"fetched_at={timestamp_slug(fetched_at_utc)}.html.gz"
    )


def gzip_bytes(payload: bytes) -> bytes:
    """Compress response bytes for raw-layer storage."""
    return gzip.compress(payload)


def sha256_hex(payload: bytes) -> str:
    """Return SHA256 checksum for traceability."""
    return hashlib.sha256(payload).hexdigest()


def configure_session() -> requests.Session:
    """Create a requests session with a browser-like header set."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def fetch_html(url: str, session: requests.Session) -> requests.Response:
    """Fetch one HTML page with simple retry handling."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=API_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            sleep_seconds = RETRY_BACKOFF_SECONDS * attempt
            print(
                f"{url}: attempt {attempt}/{MAX_RETRIES} failed "
                f"({type(exc).__name__}: {exc}). Retrying in {sleep_seconds:.1f}s..."
            )
            time.sleep(sleep_seconds)

    raise RuntimeError("Unreachable retry branch")


def read_driver_rows(s3_client) -> list[dict[str, str]]:
    """Read the silver player index parquet and return deterministic profile fetch rows."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=SOURCE_KEY)
    table = pq.read_table(io.BytesIO(response["Body"].read()))

    rows: list[dict[str, str]] = []
    seen_player_ids: set[str] = set()

    for row in table.to_pylist():
        player_id = str(row.get("basketball_reference_player_id") or "").strip()
        player_profile_url = str(row.get("player_profile_url") or "").strip()

        if not player_id or not player_profile_url:
            continue
        if player_id in seen_player_ids:
            continue

        seen_player_ids.add(player_id)
        rows.append(
            {
                "player_id": player_id,
                "player_profile_url": player_profile_url,
            }
        )

    rows.sort(key=lambda row: row["player_id"])
    return rows


def write_html_snapshot(
    *,
    payload: bytes,
    player_id: str,
    source_url: str,
    fetched_at_utc: datetime,
    status_code: int,
    s3_client,
) -> None:
    """Write one gzipped raw HTML snapshot to S3 with lightweight fetch metadata."""
    key = destination_key(player_id, fetched_at_utc)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=gzip_bytes(payload),
        ContentType="text/html; charset=utf-8",
        ContentEncoding="gzip",
        Metadata={
            "source_system": "basketball_reference",
            "player_id": player_id,
            "source_url": source_url,
            "fetched_at_utc": fetched_at_utc.isoformat(),
            "status_code": str(status_code),
            "content_sha256": sha256_hex(payload),
        },
    )
    print(f"Wrote s3://{S3_BUCKET}/{key}")


def sleep_between_requests() -> None:
    """Apply the user-requested crawl delay cushion."""
    print(f"Sleeping {REQUEST_DELAY_SECONDS:.1f}s before next request...")
    time.sleep(REQUEST_DELAY_SECONDS)


def main() -> None:
    """Backfill Basketball Reference player profile pages into raw S3 storage."""
    print(f"Starting Basketball Reference player profile backfill to s3://{S3_BUCKET}/{DESTINATION_PREFIX}/")
    print(f"Driver parquet: s3://{S3_BUCKET}/{SOURCE_KEY}")
    print(f"Configured request delay: {REQUEST_DELAY_SECONDS:.1f}s")

    s3_client = boto3.client("s3")
    session = configure_session()

    driver_rows = read_driver_rows(s3_client)
    print(f"Loaded {len(driver_rows)} player profile URLs from silver driver table")

    for index, row in enumerate(driver_rows):
        if index > 0:
            sleep_between_requests()

        player_id = row["player_id"]
        url = row["player_profile_url"]

        print(f"Fetching player {index + 1}/{len(driver_rows)}: {player_id} -> {url}")
        response = fetch_html(url, session)
        fetched_at_utc = utc_now()
        write_html_snapshot(
            payload=response.content,
            player_id=player_id,
            source_url=url,
            fetched_at_utc=fetched_at_utc,
            status_code=response.status_code,
            s3_client=s3_client,
        )

    print("Basketball Reference player profile backfill complete.")


if __name__ == "__main__":
    main()
