"""
Refresh the live CDN scheduleLeagueV2_1 JSON payload.

Copies the source payload as-is to:
s3://nba-analytics-lakehouse-dev/raw/cdn/scheduleLeagueV2_1.json
"""

from __future__ import annotations

import argparse

import boto3
import httpx
from dotenv import load_dotenv

load_dotenv(override=True)  # Ensure .env credentials override any system variables

CDN_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
S3_BUCKET = "nba-analytics-lakehouse-dev"
S3_KEY = "raw/cdn/scheduleLeagueV2_1.json"
REQUEST_TIMEOUT_SECONDS = 30

DEFAULT_CDN_HEADERS = {
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


def fetch_cdn_payload() -> bytes:
    """Fetch raw JSON bytes from the NBA CDN endpoint."""
    with httpx.Client(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers=DEFAULT_CDN_HEADERS,
    ) as client:
        response = client.get(CDN_URL)
        response.raise_for_status()
        return response.content


def write_payload_to_s3(payload: bytes, s3_client) -> None:
    """Upload raw JSON payload to the fixed S3 destination."""
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=S3_KEY,
        Body=payload,
        ContentType="application/json",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch the payload and print its size without writing to S3.",
    )
    return parser.parse_args()


def main() -> None:
    """Refresh the live schedule payload from CDN into S3."""
    args = parse_args()
    print(f"Fetching payload from {CDN_URL}")
    payload = fetch_cdn_payload()
    print(f"Fetched {len(payload)} bytes")

    if args.dry_run:
        print("Dry run only; skipping S3 write.")
        return

    s3_client = boto3.client("s3")
    write_payload_to_s3(payload, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{S3_KEY}")


if __name__ == "__main__":
    main()
