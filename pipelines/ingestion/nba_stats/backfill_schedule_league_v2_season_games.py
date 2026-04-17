"""
One-time historical backfill for nba_api ScheduleLeagueV2.SeasonGames.

Safe test flow:
1. Keep DRY_RUN=True (default).
2. Run the script and confirm it fetches only one season and prints row counts.
3. After validating output and AWS credentials, set DRY_RUN=False to run full backfill
   and write parquet files to S3.
"""

from __future__ import annotations

import io
import random
import time
from datetime import date

from dotenv import load_dotenv
load_dotenv(override=True)  # Ensure .env credentials override any system variables

import boto3
import pyarrow as pa
import pyarrow.parquet as pq


# Safety flag: True fetches a single season and skips all S3 writes.
DRY_RUN = False

LEAGUE_ID = "00"
EARLIEST_START_YEAR = 1946
SLEEP_SECONDS = 2.5
API_TIMEOUT_SECONDS = 60
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2.0
RETRY_JITTER_SECONDS = 1.0

S3_BUCKET = "nba-analytics-lakehouse-dev"
S3_PREFIX = "raw/scheduleleaguev2/seasongames"


def current_nba_season_start_year(today: date | None = None) -> int:
    """Return the NBA season start-year for the current date."""
    today = today or date.today()
    return today.year if today.month >= 9 else today.year - 1


def season_string_from_start_year(start_year: int) -> str:
    """Convert start year (e.g., 2024) into NBA season string (e.g., 2024-25)."""
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def fetch_season_games(start_year: int):
    """Fetch the ScheduleLeagueV2.SeasonGames dataframe for one season."""
    from nba_api.stats.endpoints import ScheduleLeagueV2

    season = season_string_from_start_year(start_year)
    print(f"Fetching {season}...")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            endpoint = ScheduleLeagueV2(
                season=season,
                league_id=LEAGUE_ID,
                timeout=API_TIMEOUT_SECONDS,
            )
            df = endpoint.season_games.get_data_frame()
            print(f"{season}: {len(df)} rows")
            return df
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            sleep_seconds = (
                RETRY_BACKOFF_SECONDS * attempt
                + random.uniform(0.0, RETRY_JITTER_SECONDS)
            )
            print(
                f"{season}: attempt {attempt}/{MAX_RETRIES} failed "
                f"({type(exc).__name__}: {exc}). Retrying in {sleep_seconds:.1f}s..."
            )
            time.sleep(sleep_seconds)

    raise RuntimeError("Unreachable retry branch")


def write_dataframe_to_s3_parquet(df, start_year: int, s3_client) -> None:
    """Write one season dataframe to S3 parquet at season-partitioned path."""
    table = pa.Table.from_pandas(df, preserve_index=False)
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    buffer.seek(0)

    key = f"{S3_PREFIX}/season={start_year}/season_games.parquet"
    s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=buffer.getvalue())
    print(f"Wrote s3://{S3_BUCKET}/{key}")


def main() -> None:
    """Run season loop from the current NBA season back to 1946-47 with optional dry run."""
    s3_client = boto3.client("s3") if not DRY_RUN else None
    latest_start_year = current_nba_season_start_year()
    years = list(range(latest_start_year, EARLIEST_START_YEAR - 1, -1))

    if DRY_RUN:
        years = years[:1]
        print("DRY_RUN=True: fetching one season only and skipping S3 writes.")

    for index, start_year in enumerate(years):
        season = season_string_from_start_year(start_year)
        try:
            df = fetch_season_games(start_year)
        except Exception as exc:
            print(
                f"{season}: failed after {MAX_RETRIES} attempts "
                f"({type(exc).__name__}: {exc}). Skipping season."
            )
            continue

        if not DRY_RUN and s3_client is not None:
            write_dataframe_to_s3_parquet(df, start_year, s3_client)

        # Sleep between requests to reduce API pressure and avoid rate limiting.
        if index < len(years) - 1:
            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
