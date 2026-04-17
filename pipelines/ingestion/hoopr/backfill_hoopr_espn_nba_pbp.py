"""
Historical backfill for hoopR ESPN NBA play-by-play into per-game raw parquet.

The upstream hoopR / SportsDataverse release asset is still season-scoped
(`play_by_play_<season>.rds`), but this pipeline lands per-game raw artifacts.
Note that hoopR uses ESPN-style `game_id` values (for example `401766128`),
not the 10-digit NBA game IDs used elsewhere in this repo.

This script is intentionally ESPN-specific. If we later add a hoopR backfill
for NBA-native 10-digit game IDs, that should live in a separate script.

1. downloads one season snapshot
2. decodes the `.rds` tabular payload
3. groups rows by `game_id`
4. writes one per-game `.rds` object to:
   s3://nba-analytics-lakehouse-dev/raw/hoopR/espn_nba_pbp/game_id=<GAME_ID>.rds
5. writes one parquet object per game to:
   s3://nba-analytics-lakehouse-dev/raw/hoopR/espn_nba_pbp/game_id=<GAME_ID>.parquet

This keeps hoopR raw aligned with the rest of the project's game-scoped raw
storage pattern while still preserving a per-game `.rds` artifact alongside the
operational parquet object.

Safe test flow:
1. Keep DRY_RUN=True (default).
2. Run and confirm it prints a tiny season sample plus planned per-game keys.
3. After validation, set DRY_RUN=False to write one parquet object per game.
4. After validation, set DRY_RUN=False to write both per-game `.rds`
   and `.parquet` objects.
5. Optionally set DELETE_LEGACY_SEASON_OBJECTS=True only if you want to
   remove the older season-level `.rds` objects.
"""

from __future__ import annotations

import io
import random
import tempfile
import time
from collections.abc import Iterable
from datetime import date
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(override=True)  # Ensure .env credentials override any system variables

import boto3
from botocore.exceptions import ClientError
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pandas.api.types import is_datetime64_any_dtype
from pandas.api.types import is_object_dtype


# Safety flag: True processes only a tiny season sample and skips all S3 writes.
DRY_RUN = False
DRY_RUN_MAX_SEASONS = 2

LATEST_START_YEAR = 2025
EARLIEST_START_YEAR = 2020

SLEEP_SECONDS = 1.2
SLEEP_JITTER_SECONDS = 0.6

API_TIMEOUT_SECONDS = 60
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2.0
RETRY_JITTER_SECONDS = 1.5

S3_BUCKET = "nba-analytics-lakehouse-dev"
PARQUET_PREFIX = "raw/hoopR/espn_nba_pbp"
DELETE_LEGACY_SEASON_OBJECTS = False

HOOPR_NBA_PBP_URL_TEMPLATE = (
    "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
    "espn_nba_pbp/play_by_play_{season}.rds"
)

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

# Keep this as a simple explicit override point for manual runs.
TARGET_START_YEARS: list[int] | None = None
TARGET_GAME_IDS: set[str] | None = None


def legacy_season_key(start_year: int) -> str:
    """Legacy S3 key used by the older season-snapshot raw layout."""
    return f"{PARQUET_PREFIX}/season={start_year}/play_by_play_{start_year}.rds"


def destination_rds_key_for_game(game_id: str) -> str:
    """S3 destination key for one game's untouched vendor `.rds` payload."""
    normalized_game_id = normalize_game_id(game_id)
    return f"{PARQUET_PREFIX}/game_id={normalized_game_id}.rds"


def source_url_for_season(start_year: int) -> str:
    """Source download URL for one hoopR NBA PBP season snapshot."""
    return HOOPR_NBA_PBP_URL_TEMPLATE.format(season=start_year)


def destination_key_for_game(game_id: str) -> str:
    """S3 destination key for one game's hoopR raw parquet payload."""
    normalized_game_id = normalize_game_id(game_id)
    return f"{PARQUET_PREFIX}/game_id={normalized_game_id}.parquet"


def sleep_with_jitter(base_seconds: float, jitter_seconds: float, reason: str) -> None:
    """Sleep for a randomized duration in [base-jitter, base+jitter], bounded at 0."""
    lower = max(0.0, base_seconds - jitter_seconds)
    upper = base_seconds + jitter_seconds
    sleep_seconds = random.uniform(lower, upper)
    print(f"{reason} Sleeping {sleep_seconds:.1f}s...")
    time.sleep(sleep_seconds)


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


def fetch_snapshot_for_season(start_year: int, session: requests.Session) -> bytes:
    """Download raw hoopR NBA PBP `.rds` bytes for one season."""
    url = source_url_for_season(start_year)
    response = session.get(url, timeout=API_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content


def fetch_snapshot_with_retry(start_year: int, session: requests.Session) -> bytes:
    """Fetch one season snapshot with bounded retries for transient failures."""
    url = source_url_for_season(start_year)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_snapshot_for_season(start_year, session)
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            sleep_seconds = (
                RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                + random.uniform(0.0, RETRY_JITTER_SECONDS)
            )
            print(
                f"{start_year}: attempt {attempt}/{MAX_RETRIES} failed "
                f"({type(exc).__name__}: {exc}). Retrying {url} in {sleep_seconds:.1f}s..."
            )
            time.sleep(sleep_seconds)
    raise RuntimeError("Unreachable retry branch")


def import_pyreadr():
    """Import pyreadr lazily so the rest of the repo stays importable without it."""
    try:
        import pyreadr  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pyreadr is required for hoopR `.rds` decoding. "
            "Install it with `pip install pyreadr` or `pip install -r requirements.txt`."
        ) from exc
    return pyreadr


def load_frame_from_rds_bytes(snapshot_bytes: bytes) -> pd.DataFrame:
    """Decode one season `.rds` snapshot into a pandas DataFrame."""
    pyreadr = import_pyreadr()
    with tempfile.NamedTemporaryFile(suffix=".rds") as tmp:
        tmp.write(snapshot_bytes)
        tmp.flush()
        result = pyreadr.read_r(tmp.name)

    if not result:
        raise ValueError("Decoded `.rds` payload contained no data frames.")

    frame = next(iter(result.values()))
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"Expected pandas DataFrame from pyreadr, got {type(frame)!r}")
    if frame.empty:
        return frame
    if "game_id" not in frame.columns:
        raise ValueError("Decoded hoopR payload does not contain required `game_id` column.")
    return frame


def normalize_game_id(game_id: object) -> str:
    """Normalize raw hoopR/ESPN game_id values into a stable digit string."""
    text = str(game_id).strip()
    if not text:
        raise ValueError("game_id cannot be blank")
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit():
        raise ValueError(f"game_id must be numeric, got {game_id!r}")
    return text


def normalize_game_ids(raw_ids: Iterable[object]) -> set[str]:
    """Normalize a user override list of target game IDs."""
    return {normalize_game_id(raw_id) for raw_id in raw_ids}


def build_game_frames(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """Split a season DataFrame into one sorted frame per game."""
    if frame.empty:
        return []

    working = frame.copy()
    working["game_id"] = working["game_id"].map(normalize_game_id)

    if "season" in working.columns:
        season_series = pd.to_numeric(working["season"], errors="coerce")
        working = working.loc[
            season_series.between(EARLIEST_START_YEAR, LATEST_START_YEAR)
        ].copy()

    if TARGET_GAME_IDS:
        working = working.loc[working["game_id"].isin(TARGET_GAME_IDS)].copy()
        if working.empty:
            return []

    sort_columns = [
        column
        for column in ["game_id", "game_play_number", "period", "id", "sequence_number"]
        if column in working.columns
    ]
    if sort_columns:
        working = working.sort_values(sort_columns, kind="stable").reset_index(drop=True)

    frames: list[tuple[str, pd.DataFrame]] = []
    for game_id, game_frame in working.groupby("game_id", sort=True, dropna=False):
        frames.append((str(game_id), game_frame.reset_index(drop=True)))
    return frames


def parquet_bytes_for_frame(frame: pd.DataFrame) -> bytes:
    """Serialize one game frame as parquet bytes."""
    table = pa.Table.from_pandas(frame, preserve_index=False)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


def write_game_frame_to_s3(game_id: str, frame: pd.DataFrame, s3_client) -> None:
    """Write one per-game hoopR parquet object to S3."""
    key = destination_key_for_game(game_id)
    payload = parquet_bytes_for_frame(frame)
    s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=payload)
    print(f"Wrote s3://{S3_BUCKET}/{key} ({len(frame)} rows)")


def rds_bytes_for_frame(frame: pd.DataFrame) -> bytes:
    """Serialize one game frame as `.rds` bytes."""
    pyreadr = import_pyreadr()
    writable = frame.copy()

    # pyreadr.write_rds() does not reliably handle Python date/datetime objects
    # stored inside object-typed columns. Normalize those values to ISO strings
    # for the raw per-game `.rds` artifact while keeping parquet type fidelity.
    def normalize_value(value: object) -> object:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        if isinstance(value, (datetime, date, pd.Timestamp)):
            return value.isoformat()
        return value

    for column in writable.columns:
        series = writable[column]
        if is_datetime64_any_dtype(series):
            writable[column] = series.map(
                lambda value: value.isoformat() if value is not None and not pd.isna(value) else value
            )
            continue
        if is_object_dtype(series):
            writable[column] = series.map(normalize_value)

    with tempfile.NamedTemporaryFile(suffix=".rds") as tmp:
        pyreadr.write_rds(tmp.name, writable)
        tmp.seek(0)
        return tmp.read()


def write_vendor_rds_to_s3(game_id: str, frame: pd.DataFrame, s3_client) -> None:
    """Write one per-game `.rds` payload to S3."""
    key = destination_rds_key_for_game(game_id)
    payload = rds_bytes_for_frame(frame)
    s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=payload)
    print(f"Wrote s3://{S3_BUCKET}/{key}")


def delete_legacy_season_object(start_year: int, s3_client) -> None:
    """Delete the old season-level `.rds` object after the new layout is validated."""
    key = legacy_season_key(start_year)
    if not s3_object_exists(s3_client, key):
        print(f"{start_year}: no legacy season snapshot at s3://{S3_BUCKET}/{key}")
        return
    s3_client.delete_object(Bucket=S3_BUCKET, Key=key)
    print(f"Deleted legacy s3://{S3_BUCKET}/{key}")


def resolve_target_years() -> list[int]:
    """Return the ordered season start years targeted by this run."""
    if TARGET_START_YEARS is not None:
        years = sorted({int(year) for year in TARGET_START_YEARS}, reverse=True)
    else:
        years = list(range(LATEST_START_YEAR, EARLIEST_START_YEAR - 1, -1))

    if DRY_RUN:
        years = years[:DRY_RUN_MAX_SEASONS]
    return years


def main() -> None:
    """Run game-level hoopR NBA PBP raw backfill from season `.rds` snapshots."""
    years = resolve_target_years()
    s3_client = boto3.client("s3") if not DRY_RUN else None

    if DRY_RUN:
        print("DRY_RUN=True: printing planned downloads and per-game destinations, skipping S3 writes.")

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    for index, start_year in enumerate(years):
        url = source_url_for_season(start_year)
        print(f"{start_year}: source={url}")
        try:
            snapshot_bytes = fetch_snapshot_with_retry(start_year, session)
            season_frame = load_frame_from_rds_bytes(snapshot_bytes)
            game_frames = build_game_frames(season_frame)
        except Exception as exc:
            print(
                f"{start_year}: failed after {MAX_RETRIES} attempts or decode step "
                f"({type(exc).__name__}: {exc}). Skipping season."
            )
            continue

        print(f"{start_year}: decoded {len(season_frame)} rows across {len(game_frames)} games")

        if DRY_RUN:
            for game_id, game_frame in game_frames[:5]:
                parquet_key = destination_key_for_game(game_id)
                rds_key = destination_rds_key_for_game(game_id)
                print(f"{start_year}: sample destination=s3://{S3_BUCKET}/{rds_key}")
                print(f"{start_year}: sample destination=s3://{S3_BUCKET}/{parquet_key} rows={len(game_frame)}")
            continue

        if s3_client is None:
            raise RuntimeError("s3_client must be initialized when DRY_RUN=False")

        for game_id, game_frame in game_frames:
            rds_key = destination_rds_key_for_game(game_id)
            key = destination_key_for_game(game_id)
            if s3_object_exists(s3_client, rds_key):
                print(f"{start_year}: game {game_id} raw .rds already exists, skipping.")
            else:
                write_vendor_rds_to_s3(game_id, game_frame, s3_client)
            if s3_object_exists(s3_client, key):
                print(f"{start_year}: game {game_id} already exists, skipping.")
                continue
            write_game_frame_to_s3(game_id, game_frame, s3_client)

        if DELETE_LEGACY_SEASON_OBJECTS:
            delete_legacy_season_object(start_year, s3_client)

        if index < len(years) - 1:
            sleep_with_jitter(
                SLEEP_SECONDS,
                SLEEP_JITTER_SECONDS,
                reason=f"{start_year}: download completed.",
            )


if __name__ == "__main__":
    main()
