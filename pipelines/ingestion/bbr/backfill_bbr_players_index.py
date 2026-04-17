"""
Backfill Basketball Reference player index HTML pages into raw S3 storage.

Fetch flow:
1. Fetch the seed page: https://www.basketball-reference.com/players/
2. Discover letter index pages from the seed HTML.
3. Fetch each letter page with a 4-second delay between requests.
4. Write gzipped raw HTML to:
   s3://nba-analytics-lakehouse-dev/raw/bball-reference/

Outputs:
  - raw/bball-reference/players_root/run_date=YYYY-MM-DD/fetched_at=TIMESTAMP.html.gz
  - raw/bball-reference/players_index/letter={letter}/run_date=YYYY-MM-DD/fetched_at=TIMESTAMP.html.gz

This script intentionally preserves the source HTML body in raw. Parsing belongs in silver.
"""

from __future__ import annotations

import gzip
import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Iterable

import boto3
import requests
from dotenv import load_dotenv

load_dotenv(override=True)  # Ensure .env credentials override any system variables

S3_BUCKET = "nba-analytics-lakehouse-dev"
DESTINATION_PREFIX = "raw/bball-reference"

SEED_URL = "https://www.basketball-reference.com/players/"
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

LETTER_LINK_PATTERN = re.compile(r'href="(/players/([a-z])/)"')


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def run_date(value: datetime) -> str:
    """Render a UTC timestamp as YYYY-MM-DD for key partitioning."""
    return value.strftime("%Y-%m-%d")


def timestamp_slug(value: datetime) -> str:
    """Render a UTC timestamp as a compact object-key-safe slug."""
    return value.strftime("%Y%m%dT%H%M%SZ")


def root_destination_key(fetched_at_utc: datetime) -> str:
    """S3 key for the /players/ seed page snapshot."""
    return (
        f"{DESTINATION_PREFIX}/players_root/run_date={run_date(fetched_at_utc)}/"
        f"fetched_at={timestamp_slug(fetched_at_utc)}.html.gz"
    )


def letter_destination_key(letter: str, fetched_at_utc: datetime) -> str:
    """S3 key for one player letter index page snapshot."""
    return (
        f"{DESTINATION_PREFIX}/players_index/letter={letter}/run_date={run_date(fetched_at_utc)}/"
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


def extract_letter_pages(seed_html: str) -> list[tuple[str, str]]:
    """Return sorted unique (letter, absolute_url) pairs discovered from /players/."""
    discovered: dict[str, str] = {}
    for relative_path, letter in LETTER_LINK_PATTERN.findall(seed_html):
        discovered[letter] = f"https://www.basketball-reference.com{relative_path}"

    if not discovered:
        raise ValueError("No player letter index links were discovered on the seed page.")

    return sorted(discovered.items(), key=lambda item: item[0])


def write_html_snapshot(
    payload: bytes,
    source_url: str,
    destination_key: str,
    fetched_at_utc: datetime,
    status_code: int,
    s3_client,
) -> None:
    """Write one gzipped raw HTML snapshot to S3 with lightweight fetch metadata."""
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=destination_key,
        Body=gzip_bytes(payload),
        ContentType="text/html; charset=utf-8",
        ContentEncoding="gzip",
        Metadata={
            "source_system": "basketball_reference",
            "source_url": source_url,
            "fetched_at_utc": fetched_at_utc.isoformat(),
            "status_code": str(status_code),
            "content_sha256": sha256_hex(payload),
        },
    )
    print(f"Wrote s3://{S3_BUCKET}/{destination_key}")


def iter_letter_requests(seed_html: str) -> Iterable[tuple[str, str]]:
    """Yield discovered player letter page requests."""
    return extract_letter_pages(seed_html)


def sleep_between_requests() -> None:
    """Apply the user-requested crawl delay cushion."""
    print(f"Sleeping {REQUEST_DELAY_SECONDS:.1f}s before next request...")
    time.sleep(REQUEST_DELAY_SECONDS)


def main() -> None:
    """Backfill Basketball Reference player index pages into raw S3 storage."""
    print(f"Starting Basketball Reference player index backfill to s3://{S3_BUCKET}/{DESTINATION_PREFIX}/")
    print(f"Configured request delay: {REQUEST_DELAY_SECONDS:.1f}s")

    s3_client = boto3.client("s3")
    session = configure_session()

    print(f"Fetching seed page: {SEED_URL}")
    seed_response = fetch_html(SEED_URL, session)
    seed_fetched_at_utc = utc_now()
    write_html_snapshot(
        payload=seed_response.content,
        source_url=SEED_URL,
        destination_key=root_destination_key(seed_fetched_at_utc),
        fetched_at_utc=seed_fetched_at_utc,
        status_code=seed_response.status_code,
        s3_client=s3_client,
    )

    letters = list(iter_letter_requests(seed_response.text))
    print(f"Discovered {len(letters)} letter index pages")

    for index, (letter, url) in enumerate(letters):
        sleep_between_requests()
        print(f"Fetching letter page {index + 1}/{len(letters)}: {url}")
        response = fetch_html(url, session)
        fetched_at_utc = utc_now()
        write_html_snapshot(
            payload=response.content,
            source_url=url,
            destination_key=letter_destination_key(letter, fetched_at_utc),
            fetched_at_utc=fetched_at_utc,
            status_code=response.status_code,
            s3_client=s3_client,
        )

    print("Basketball Reference player index backfill complete.")


if __name__ == "__main__":
    main()
