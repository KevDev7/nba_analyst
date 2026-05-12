"""Fetch raw NBA Stats BoxScoreTraditionalV3 period-range JSON payloads.

Destination pattern:
  s3://nba-analytics-lakehouse-dev/raw/boxscoretraditionalv3/period_player_stats/game_id=<GAME_ID>/period=<PERIOD>.json

This is intentionally a targeted utility for silver lineup QA. It preserves the
original JSON response instead of converting bronze/raw data to parquet.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import boto3
import requests
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv(override=True)
if os.environ.get("AWS_PROFILE") == "":
    os.environ.pop("AWS_PROFILE")

try:
    from pipelines.ingestion.cdn.backfill_manifest import normalize_game_id
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.ingestion.cdn.backfill_manifest import normalize_game_id  # type: ignore[no-redef]

S3_BUCKET = "nba-analytics-lakehouse-dev"
DESTINATION_PREFIX = "raw/boxscoretraditionalv3/period_player_stats"
BOXSCORE_TRADITIONAL_V3_URL = "https://stats.nba.com/stats/boxscoretraditionalv3"

API_TIMEOUT_SECONDS = 30
MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = 3.0
RETRY_JITTER_SECONDS = 2.0
SLEEP_SECONDS = 2.5
SLEEP_JITTER_SECONDS = 1.0

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Host": "stats.nba.com",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}


def parse_csv_game_ids(value: str) -> list[str]:
    game_ids: list[str] = []
    seen: set[str] = set()
    for item in value.split(","):
        normalized = normalize_game_id(item.strip())
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        game_ids.append(normalized)
    return game_ids


def parse_csv_periods(value: str) -> list[int]:
    periods: list[int] = []
    seen: set[int] = set()
    for item in value.split(","):
        if item.strip() == "":
            continue
        period = int(item.strip())
        if period < 1:
            raise argparse.ArgumentTypeError("periods must be >= 1")
        if period not in seen:
            seen.add(period)
            periods.append(period)
    return periods


def period_start_seconds(period: int) -> int:
    if period <= 4:
        return 720 * (period - 1)
    return (720 * 4) + (300 * (period - 5))


def period_range_tenths(period: int) -> tuple[int, int]:
    start = period_start_seconds(period) * 10
    end = period_start_seconds(period + 1) * 10
    return start + 5, end - 5


def destination_key(game_id: str, period: int) -> str:
    normalized = normalize_game_id(game_id)
    if normalized is None:
        raise ValueError(f"Invalid game_id: {game_id!r}")
    return f"{DESTINATION_PREFIX}/game_id={normalized}/period={period}.json"


def s3_object_exists(s3_client, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def request_params(game_id: str, period: int) -> dict[str, Any]:
    start_range, end_range = period_range_tenths(period)
    return {
        "GameID": normalize_game_id(game_id),
        "StartPeriod": 0,
        "EndPeriod": 0,
        "StartRange": start_range,
        "EndRange": end_range,
        "RangeType": 2,
    }


def is_likely_transient_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("timeout", "timed out", "connection", "temporar", "429", "502", "503", "504")
    )


def fetch_period_payload(session: requests.Session, game_id: str, period: int) -> dict[str, Any]:
    response = session.get(
        BOXSCORE_TRADITIONAL_V3_URL,
        params=request_params(game_id, period),
        headers=DEFAULT_HEADERS,
        timeout=API_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def fetch_period_payload_with_retry(session: requests.Session, game_id: str, period: int) -> dict[str, Any]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_period_payload(session, game_id, period)
        except Exception as exc:
            if attempt == MAX_RETRIES or not is_likely_transient_error(exc):
                raise
            sleep_seconds = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, RETRY_JITTER_SECONDS)
            print(
                f"{game_id} period {period} failed attempt {attempt}/{MAX_RETRIES} "
                f"({type(exc).__name__}: {exc}); retrying in {sleep_seconds:.1f}s"
            )
            time.sleep(sleep_seconds)
    raise RuntimeError("unreachable retry branch")


def write_json_to_s3(s3_client, key: str, payload: dict[str, Any]) -> None:
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(payload, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
    )


def sleep_with_jitter() -> None:
    time.sleep(random.uniform(max(0.0, SLEEP_SECONDS - SLEEP_JITTER_SECONDS), SLEEP_SECONDS + SLEEP_JITTER_SECONDS))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-ids", required=True, help="Comma-separated game IDs to fetch.")
    parser.add_argument("--periods", type=parse_csv_periods, default=parse_csv_periods("1,2,3,4,5,6,7,8,9,10"))
    parser.add_argument("--overwrite", action="store_true", help="Refetch objects even when the raw JSON key exists.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected objects without fetching or writing.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    game_ids = parse_csv_game_ids(args.game_ids)
    if not game_ids:
        raise SystemExit("No valid --game-ids supplied.")

    selected = [(game_id, period, destination_key(game_id, period)) for game_id in game_ids for period in args.periods]
    print(f"Selected {len(selected)} game-period requests.")
    if args.dry_run:
        for game_id, period, key in selected:
            print(f"DRY RUN game_id={game_id} period={period} -> s3://{S3_BUCKET}/{key}")
        return

    s3_client = boto3.client("s3")
    session = requests.Session()
    fetched = 0
    skipped = 0
    try:
        for index, (game_id, period, key) in enumerate(selected, start=1):
            if not args.overwrite and s3_object_exists(s3_client, key):
                skipped += 1
                print(f"[{index}/{len(selected)}] Exists; skipping s3://{S3_BUCKET}/{key}")
                continue
            print(f"[{index}/{len(selected)}] Fetching game_id={game_id} period={period}")
            payload = fetch_period_payload_with_retry(session, game_id, period)
            write_json_to_s3(s3_client, key, payload)
            fetched += 1
            print(f"[{index}/{len(selected)}] Wrote s3://{S3_BUCKET}/{key}")
            if index < len(selected):
                sleep_with_jitter()
    finally:
        session.close()
    print(f"Completed period-range backfill. fetched={fetched} skipped={skipped}")


if __name__ == "__main__":
    main()
