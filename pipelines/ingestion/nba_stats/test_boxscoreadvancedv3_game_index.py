"""
Standalone check for one BoxScoreAdvancedV3 game by season game index.

Use this to validate whether a specific GAME_ID is failing versus a broader API issue.
This script is read-only: it fetches source GAME_IDs from S3 and prints API results.
"""

from __future__ import annotations

import random
import time

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError
from nba_api.stats.endpoints import BoxScoreAdvancedV3
from nba_api.stats.library.http import NBAStatsHTTP


TARGET_SEASON_YEAR = 2020
TARGET_GAME_INDEX = 802  # 1-based index in regular-season GAME_ID list

API_TIMEOUT_SECONDS = 25
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2.0
RETRY_JITTER_SECONDS = 1.0

START_PERIOD = 0
END_PERIOD = 0
START_RANGE = 0
END_RANGE = 0
RANGE_TYPE = 0

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "raw/leaguegamelog/leaguegamelog"


def season_string_from_start_year(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def source_key_for_target_season() -> str:
    return f"{SOURCE_PREFIX}/season={TARGET_SEASON_YEAR}/regular_season.parquet"


def is_likely_transient_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = ["timeout", "timed out", "connection", "temporar", "429", "502", "503", "504"]
    return any(marker in message for marker in markers)


def fetch_game_ids_from_s3(s3_client) -> list[str]:
    key = source_key_for_target_season()
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            print(f"Missing source file: s3://{S3_BUCKET}/{key}")
            return []
        raise

    payload = response["Body"].read()
    table = pq.read_table(pa.BufferReader(payload), columns=["GAME_ID"])

    game_ids: list[str] = []
    seen: set[str] = set()
    for raw_game_id in table.column("GAME_ID").to_pylist():
        if raw_game_id is None:
            continue
        game_id = str(raw_game_id).strip()
        if not game_id or game_id in seen:
            continue
        seen.add(game_id)
        game_ids.append(game_id)
    return game_ids


def fetch_advanced_player_stats_with_retry(game_id: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            endpoint = BoxScoreAdvancedV3(
                game_id=game_id,
                end_period=END_PERIOD,
                end_range=END_RANGE,
                range_type=RANGE_TYPE,
                start_period=START_PERIOD,
                start_range=START_RANGE,
                timeout=API_TIMEOUT_SECONDS,
            )
            return endpoint.player_stats.get_data_frame()
        except Exception as exc:
            if (not is_likely_transient_error(exc)) or attempt == MAX_RETRIES:
                raise
            delay = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)) + random.uniform(
                0.0, RETRY_JITTER_SECONDS
            )
            print(
                f"Attempt {attempt}/{MAX_RETRIES} failed for GAME_ID {game_id} "
                f"({type(exc).__name__}: {exc}). Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

    raise RuntimeError("Unreachable retry branch")


def main() -> None:
    season = season_string_from_start_year(TARGET_SEASON_YEAR)
    print(f"Testing BoxScoreAdvancedV3 for season {season}, game index {TARGET_GAME_INDEX}...")

    s3_client = boto3.client("s3")
    session = requests.Session()
    NBAStatsHTTP.set_session(session)
    try:
        game_ids = fetch_game_ids_from_s3(s3_client)
        if not game_ids:
            print("No game IDs found; stopping.")
            return

        if TARGET_GAME_INDEX < 1 or TARGET_GAME_INDEX > len(game_ids):
            print(
                f"TARGET_GAME_INDEX={TARGET_GAME_INDEX} is out of range. "
                f"Valid range is 1..{len(game_ids)}."
            )
            return

        game_id = game_ids[TARGET_GAME_INDEX - 1]
        print(f"Resolved GAME_ID at index {TARGET_GAME_INDEX}: {game_id}")

        df = fetch_advanced_player_stats_with_retry(game_id)
        print(f"SUCCESS for GAME_ID {game_id}: rows={len(df)}, cols={len(df.columns)}")
        print(f"Columns: {list(df.columns)}")
    finally:
        session.close()
        NBAStatsHTTP.set_session(None)


if __name__ == "__main__":
    main()
