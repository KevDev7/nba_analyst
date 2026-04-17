"""
One-season historical backfill for nba_api BoxScoreTraditionalV3.PlayerStats.

Design goals:
1. Process only one target season per run.
2. Use game-level idempotency in S3 (one parquet per GAME_ID).
3. Reuse one persistent requests.Session for all API calls in this run.
4. Keep retry + exponential backoff for transient API failures.
"""

from __future__ import annotations

import io
import random
import time

import requests
from dotenv import load_dotenv

load_dotenv(override=True)  # Ensure .env credentials override any system variables

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError
from nba_api.stats.endpoints import BoxScoreTraditionalV3
from nba_api.stats.library.http import NBAStatsHTTP


TARGET_SEASON_YEAR = 2024

MAX_GAMES_PER_RUN = 650

SLEEP_SECONDS = 2.0
SLEEP_JITTER_SECONDS = 0.5
COOLDOWN_EVERY_GAMES = 50
COOLDOWN_SECONDS = 180
COOLDOWN_JITTER_SECONDS = 30

API_TIMEOUT_SECONDS = 25
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2.0
RETRY_JITTER_SECONDS = 1.0

# BoxScoreTraditionalV3 required range parameters for full-game results.
START_PERIOD = 0
END_PERIOD = 0
START_RANGE = 0
END_RANGE = 0
RANGE_TYPE = 0

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "raw/leaguegamelog/leaguegamelog"
DESTINATION_PREFIX = "raw/boxscoretraditionalv3/playerstats"


def season_string_from_start_year(start_year: int) -> str:
    """Convert start year (e.g., 2025) into NBA season string (e.g., 2025-26)."""
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def source_key_for_target_season() -> str:
    """S3 source key for LeagueGameLog regular-season parquet for TARGET_SEASON_YEAR."""
    return f"{SOURCE_PREFIX}/season={TARGET_SEASON_YEAR}/regular_season.parquet"


def destination_key_for_game(game_id: str) -> str:
    """S3 destination key for one game's PlayerStats parquet."""
    return (
        f"{DESTINATION_PREFIX}/season={TARGET_SEASON_YEAR}/regular_season/"
        f"game_id={game_id}.parquet"
    )


def sleep_with_jitter(base_seconds: float, jitter_seconds: float, reason: str) -> None:
    """Sleep for a randomized duration in [base-jitter, base+jitter], bounded at 0."""
    lower = max(0.0, base_seconds - jitter_seconds)
    upper = base_seconds + jitter_seconds
    sleep_seconds = random.uniform(lower, upper)
    print(f"{reason} Sleeping {sleep_seconds:.1f}s...")
    time.sleep(sleep_seconds)


def is_likely_transient_error(exc: Exception) -> bool:
    """Return True for timeout/connectivity/rate-limit style failures."""
    message = str(exc).lower()
    transient_markers = [
        "timeout",
        "timed out",
        "connection",
        "temporar",
        "too many requests",
        "429",
        "502",
        "503",
        "504",
    ]
    return any(marker in message for marker in transient_markers)


def configure_persistent_nba_session() -> requests.Session:
    """Create and register a single session reused by nba_api HTTP calls."""
    session = requests.Session()
    NBAStatsHTTP.set_session(session)
    return session


def fetch_game_ids_from_s3(s3_client) -> list[str]:
    """Read regular-season GAME_ID values for TARGET_SEASON_YEAR from S3."""
    key = source_key_for_target_season()
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
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


def s3_object_exists(s3_client, key: str) -> bool:
    """Return True when S3 object exists at key; False for not found."""
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def fetch_player_stats_for_game(game_id: str):
    """Fetch BoxScoreTraditionalV3.PlayerStats dataframe for one game."""
    endpoint = BoxScoreTraditionalV3(
        game_id=game_id,
        end_period=END_PERIOD,
        end_range=END_RANGE,
        range_type=RANGE_TYPE,
        start_period=START_PERIOD,
        start_range=START_RANGE,
        timeout=API_TIMEOUT_SECONDS,
    )
    df = endpoint.player_stats.get_data_frame()
    if "GAME_ID" not in df.columns:
        df["GAME_ID"] = game_id
    return df


def fetch_player_stats_with_retry(game_id: str):
    """Fetch player stats with retries for transient API failures."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_player_stats_for_game(game_id)
        except Exception as exc:
            is_transient = is_likely_transient_error(exc)
            if (not is_transient) or attempt == MAX_RETRIES:
                raise
            sleep_seconds = (
                RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                + random.uniform(0.0, RETRY_JITTER_SECONDS)
            )
            print(
                f"GAME_ID {game_id} failed on attempt {attempt}/{MAX_RETRIES} "
                f"({type(exc).__name__}: {exc}). Retrying in {sleep_seconds:.1f}s..."
            )
            time.sleep(sleep_seconds)

    raise RuntimeError("Unreachable retry branch")


def write_game_dataframe_to_s3_parquet(df, game_id: str, s3_client) -> None:
    """Write one game's dataframe as parquet to game-level S3 key."""
    key = destination_key_for_game(game_id)
    table = pa.Table.from_pandas(df, preserve_index=False)
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    buffer.seek(0)
    s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=buffer.getvalue())
    print(f"Wrote s3://{S3_BUCKET}/{key}")


def main() -> None:
    """Backfill one target season and exit cleanly."""
    season = season_string_from_start_year(TARGET_SEASON_YEAR)
    print(f"Running one-season backfill for {season} (start_year={TARGET_SEASON_YEAR}).")

    s3_client = boto3.client("s3")
    session = configure_persistent_nba_session()
    try:
        game_ids = fetch_game_ids_from_s3(s3_client)
        print(f"{season}: discovered {len(game_ids)} unique GAME_ID values.")
        processed_this_run = 0

        for index, game_id in enumerate(game_ids, start=1):
            if processed_this_run >= MAX_GAMES_PER_RUN:
                print(
                    f"Reached MAX_GAMES_PER_RUN ({MAX_GAMES_PER_RUN}) new fetches. "
                    "Stopping early to avoid throttle window."
                )
                break

            did_fetch = False
            key = destination_key_for_game(game_id)
            if s3_object_exists(s3_client, key):
                print(f"{season}: game {index}/{len(game_ids)} ({game_id}) already exists; skipping.")
            else:
                print(f"{season}: fetching game {index}/{len(game_ids)} ({game_id})...")
                df = fetch_player_stats_with_retry(game_id)
                write_game_dataframe_to_s3_parquet(df, game_id, s3_client)
                processed_this_run += 1
                did_fetch = True

            # Only add pacing/cooldown delays after real API fetches, not skips.
            if did_fetch and index < len(game_ids):
                sleep_with_jitter(
                    SLEEP_SECONDS,
                    SLEEP_JITTER_SECONDS,
                    reason=f"{season}: inter-game pacing.",
                )
                if processed_this_run % COOLDOWN_EVERY_GAMES == 0:
                    sleep_with_jitter(
                        COOLDOWN_SECONDS,
                        COOLDOWN_JITTER_SECONDS,
                        reason=f"{season}: cooldown after {processed_this_run} new fetches.",
                    )
    finally:
        session.close()
        NBAStatsHTTP.set_session(None)

    print(f"Completed one-season run for {season}.")


if __name__ == "__main__":
    main()
