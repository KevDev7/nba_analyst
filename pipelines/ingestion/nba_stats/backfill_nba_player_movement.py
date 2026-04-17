"""
Bronze snapshot backfill for NBA player movement cumulative JSON.

Source:
  https://stats.nba.com/js/data/playermovement/NBA_Player_Movement.json

Destination pattern:
  s3://nba-analytics-lakehouse-dev/raw/cdn/player_movement/
  snapshot_date=YYYY-MM-DD/player_movement.json

Notes:
  - snapshot_date uses UTC date at ingestion time.
  - Re-runs on the same UTC date overwrite that day's snapshot file.
"""

from __future__ import annotations

from datetime import datetime, timezone

import boto3
import httpx
from dotenv import load_dotenv

load_dotenv(override=True)  # Ensure .env credentials override any system variables

SOURCE_URL = "https://stats.nba.com/js/data/playermovement/NBA_Player_Movement.json"
S3_BUCKET = "nba-analytics-lakehouse-dev"
DESTINATION_PREFIX = "raw/cdn/player_movement"
REQUEST_TIMEOUT_SECONDS = 30

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


def snapshot_date_utc() -> str:
    """Return ingestion date in UTC formatted as YYYY-MM-DD."""
    return datetime.now(timezone.utc).date().isoformat()


def destination_key(snapshot_date: str) -> str:
    """Build S3 key for the UTC snapshot date partition."""
    return (
        f"{DESTINATION_PREFIX}/snapshot_date={snapshot_date}/"
        "player_movement.json"
    )


def fetch_payload() -> bytes:
    """Fetch full raw JSON payload from stats.nba.com."""
    with httpx.Client(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as client:
        response = client.get(SOURCE_URL)
        response.raise_for_status()
        return response.content


def write_snapshot_to_s3(payload: bytes, key: str, s3_client) -> None:
    """Write raw JSON payload to S3 snapshot location."""
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=payload,
        ContentType="application/json",
    )


def main() -> None:
    """Run one snapshot ingestion from source URL to S3 bronze."""
    date_utc = snapshot_date_utc()
    key = destination_key(date_utc)

    print(f"Fetching payload from {SOURCE_URL}")
    payload = fetch_payload()
    print(f"Fetched {len(payload)} bytes")

    s3_client = boto3.client("s3")
    write_snapshot_to_s3(payload, key, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{key}")


if __name__ == "__main__":
    main()
