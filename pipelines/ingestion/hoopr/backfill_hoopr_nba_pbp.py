"""
Historical backfill for NBA-native play-by-play into per-game raw parquet/RDS.

This pipeline uses canonical 10-digit NBA game IDs from the historical schedule
inventory, prefers already-landed raw CDN JSON when available, and otherwise
fetches the same NBA CDN play-by-play payload directly.

It writes one per-game `.rds` object to:
  s3://nba-analytics-lakehouse-dev/raw/hoopR/nba_pbp/game_id=<GAME_ID>.rds

It also writes one per-game parquet object to:
  s3://nba-analytics-lakehouse-dev/raw/hoopR/nba_pbp/game_id=<GAME_ID>.parquet

The tabular export is built from the raw CDN action list. Nested list/dict
fields are preserved as JSON strings so both parquet and `.rds` stay stable.

Safe test flow:
1. Keep DRY_RUN=True (default).
2. Run and confirm it prints a small sample of planned per-game exports.
3. After validation, set DRY_RUN=False to write both `.rds` and `.parquet`.
"""

from __future__ import annotations

import io
import json
import random
import tempfile
import time
from collections.abc import Iterable
from datetime import date
from datetime import datetime
from typing import Any

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


DRY_RUN = False
DRY_RUN_MAX_GAMES = 5

LATEST_START_YEAR = 2025
EARLIEST_START_YEAR = 2020

SLEEP_SECONDS = 0.4
SLEEP_JITTER_SECONDS = 0.2

API_TIMEOUT_SECONDS = 25
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2.0
RETRY_JITTER_SECONDS = 1.5

S3_BUCKET = "nba-analytics-lakehouse-dev"
SCHEDULE_SOURCE_PREFIX = "raw/scheduleleaguev2/seasongames/"
RAW_CDN_SOURCE_PREFIX = "raw/cdn/playbyplay"
DESTINATION_PREFIX = "raw/hoopR/nba_pbp"

CDN_PLAYBYPLAY_URL_TEMPLATE = (
    "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
)

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

SEASON_TYPE_LABELS = {
    "001": "preseason",
    "002": "regular_season",
    "003": "all_star",
    "004": "playoffs",
    "005": "play_in",
    "006": "nba_cup_final",
}

TARGET_GAME_IDS: set[str] | None = None


def destination_rds_key_for_game(game_id: str) -> str:
    """S3 destination key for one game's `.rds` export."""
    normalized_game_id = normalize_game_id(game_id)
    return f"{DESTINATION_PREFIX}/game_id={normalized_game_id}.rds"


def destination_parquet_key_for_game(game_id: str) -> str:
    """S3 destination key for one game's parquet export."""
    normalized_game_id = normalize_game_id(game_id)
    return f"{DESTINATION_PREFIX}/game_id={normalized_game_id}.parquet"


def source_cdn_key_for_game(game_id: str) -> str:
    """S3 source key for one game's raw CDN JSON payload."""
    normalized_game_id = normalize_game_id(game_id)
    return f"{RAW_CDN_SOURCE_PREFIX}/game_id={normalized_game_id}.json"


def source_url_for_game(game_id: str) -> str:
    """Live CDN source URL for one game."""
    normalized_game_id = normalize_game_id(game_id)
    return CDN_PLAYBYPLAY_URL_TEMPLATE.format(game_id=normalized_game_id)


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


def is_likely_transient_error(exc: Exception) -> bool:
    """Return True for timeout/connectivity/rate-limit style failures."""
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        if exc.response.status_code in {429, 500, 502, 503, 504}:
            return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ["timeout", "timed out", "connection", "too many requests", "429", "502", "503", "504"]
    )


def parse_game_datetime(value: str) -> datetime:
    """Parse ISO-ish schedule datetimes; fallback to datetime.min when malformed."""
    text = str(value or "").strip()
    if not text:
        return datetime.min
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.min


def infer_schedule_partition_start_year(key: str) -> int | None:
    """Extract season start year from keys like season=2024/season_games.parquet."""
    for part in key.split("/"):
        if not part.startswith("season="):
            continue
        raw = part.split("=", 1)[1].strip()
        if raw.isdigit():
            return int(raw)
    return None


def list_schedule_parquet_keys(s3_client) -> list[str]:
    """List season schedule parquet keys for the configured season window."""
    paginator = s3_client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SCHEDULE_SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if not key.endswith(".parquet"):
                continue
            start_year = infer_schedule_partition_start_year(key)
            if start_year is None:
                continue
            if EARLIEST_START_YEAR <= start_year <= LATEST_START_YEAR:
                keys.append(key)
    return sorted(keys)


def fetch_ordered_game_ids_from_s3(s3_client) -> list[str]:
    """Read schedule parquet files and return unique game IDs ordered newest to oldest."""
    rows: list[tuple[datetime, str]] = []
    for key in list_schedule_parquet_keys(s3_client):
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
        table = pq.read_table(io.BytesIO(response["Body"].read()), columns=["gameId", "gameDateTimeUTC"])
        for row in table.to_pylist():
            game_id = normalize_game_id(row.get("gameId"))
            if game_id is None:
                continue
            rows.append((parse_game_datetime(row.get("gameDateTimeUTC")), game_id))

    rows.sort(key=lambda item: (item[0], item[1]), reverse=True)

    ordered_game_ids: list[str] = []
    seen: set[str] = set()
    for _, game_id in rows:
        if game_id in seen:
            continue
        seen.add(game_id)
        ordered_game_ids.append(game_id)
    return ordered_game_ids


def fetch_playbyplay_for_game(game_id: str, session: requests.Session) -> bytes:
    """Fetch raw CDN play-by-play JSON bytes for one game."""
    response = session.get(source_url_for_game(game_id), timeout=API_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content


def fetch_playbyplay_with_retry(game_id: str, session: requests.Session) -> bytes:
    """Fetch play-by-play JSON with retries for transient failures."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_playbyplay_for_game(game_id, session)
        except Exception as exc:
            if (not is_likely_transient_error(exc)) or attempt == MAX_RETRIES:
                raise
            sleep_seconds = (
                RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                + random.uniform(0.0, RETRY_JITTER_SECONDS)
            )
            print(
                f"{game_id}: attempt {attempt}/{MAX_RETRIES} failed "
                f"({type(exc).__name__}: {exc}). Retrying in {sleep_seconds:.1f}s..."
            )
            time.sleep(sleep_seconds)
    raise RuntimeError("Unreachable retry branch")


def load_payload_bytes(game_id: str, s3_client, session: requests.Session) -> tuple[bytes, str]:
    """Load a game's CDN payload from S3 when present, else fetch live from the CDN."""
    source_key = source_cdn_key_for_game(game_id)
    if s3_object_exists(s3_client, source_key):
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=source_key)
        return response["Body"].read(), f"s3://{S3_BUCKET}/{source_key}"
    return fetch_playbyplay_with_retry(game_id, session), source_url_for_game(game_id)


def configure_cdn_session() -> requests.Session:
    """Create a session with browser-like headers for CDN compatibility."""
    session = requests.Session()
    session.headers.update(DEFAULT_CDN_HEADERS)
    return session


def import_pyreadr():
    """Import pyreadr lazily so the rest of the repo stays importable without it."""
    try:
        import pyreadr  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pyreadr is required for `.rds` export. "
            "Install it with `pip install pyreadr` or `pip install -r requirements.txt`."
        ) from exc
    return pyreadr


def normalize_game_id(game_id: object) -> str | None:
    """Normalize raw game IDs into a 10-digit NBA game_id string."""
    if game_id is None:
        return None
    digits = "".join(ch for ch in str(game_id).strip() if ch.isdigit())
    if not digits:
        return None
    if len(digits) >= 10:
        return digits[-10:]
    return digits.zfill(10)


def normalize_game_ids(raw_ids: Iterable[object]) -> set[str]:
    """Normalize a user override list of target game IDs."""
    normalized = {normalize_game_id(raw_id) for raw_id in raw_ids}
    return {game_id for game_id in normalized if game_id is not None}


def infer_season_fields(game_id: str) -> tuple[int | None, str | None, str | None]:
    """Infer season metadata from a normalized NBA game_id."""
    if len(game_id) < 5 or not game_id[:5].isdigit():
        return None, None, None
    season_type_code = game_id[:3]
    yy = int(game_id[3:5])
    start_year = 2000 + yy if yy <= 50 else 1900 + yy
    season_year = f"{start_year}-{(start_year + 1) % 100:02d}"
    if season_type_code not in SEASON_TYPE_LABELS:
        return start_year, season_year, None
    return start_year, season_year, season_type_code


def build_frame_from_payload(payload_bytes: bytes, expected_game_id: str, payload_source: str) -> pd.DataFrame:
    """Flatten one CDN payload into a tabular action DataFrame."""
    payload = json.loads(payload_bytes)
    meta = payload.get("meta") or {}
    game = payload.get("game") or {}
    actions = game.get("actions") or []

    game_id = normalize_game_id(game.get("gameId")) or normalize_game_id(expected_game_id)
    if game_id is None:
        raise ValueError(f"Unable to determine game_id for payload source {payload_source}")

    frame = pd.json_normalize(actions, sep="_")
    if frame.empty:
        frame = pd.DataFrame({"gameId": [game_id]})

    frame["gameId"] = game_id
    season_start_year, season_year, season_type_code = infer_season_fields(game_id)
    frame["season_start_year"] = season_start_year
    frame["season_year"] = season_year
    frame["season_type_code"] = season_type_code
    frame["season_type"] = (
        SEASON_TYPE_LABELS.get(season_type_code) if season_type_code is not None else None
    )
    frame["source_system"] = "nba_cdn_playbyplay"
    frame["source_payload"] = payload_source
    frame["meta_version"] = meta.get("version")
    frame["meta_code"] = meta.get("code")
    frame["meta_request"] = meta.get("request")
    frame["meta_time"] = meta.get("time")

    sort_columns = [column for column in ["orderNumber", "actionNumber"] if column in frame.columns]
    if sort_columns:
        frame = frame.sort_values(sort_columns, kind="stable").reset_index(drop=True)
    return frame


def serialize_cell(value: Any) -> Any:
    """Convert nested/list-like cells into stable scalar values for parquet/RDS export."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return json.dumps(list(value), separators=(",", ":"), default=str)
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)
    return value


def make_serializable_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert unsupported nested/object values into scalar strings."""
    serializable = frame.copy()
    for column_name in serializable.columns:
        column = serializable[column_name]
        if is_datetime64_any_dtype(column):
            serializable[column_name] = column.map(
                lambda value: value.isoformat() if pd.notna(value) else None
            )
            continue
        if is_object_dtype(column):
            serializable[column_name] = column.map(serialize_cell)
    return serializable


def parquet_bytes_for_frame(frame: pd.DataFrame) -> bytes:
    """Serialize one game frame as parquet bytes."""
    table = pa.Table.from_pandas(make_serializable_frame(frame), preserve_index=False)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


def rds_bytes_for_frame(frame: pd.DataFrame) -> bytes:
    """Serialize one game frame as `.rds` bytes using pyreadr."""
    pyreadr = import_pyreadr()
    serializable_frame = make_serializable_frame(frame)
    with tempfile.NamedTemporaryFile(suffix=".rds") as tmp:
        pyreadr.write_rds(tmp.name, serializable_frame)
        tmp.seek(0)
        return tmp.read()


def write_game_exports_to_s3(game_id: str, frame: pd.DataFrame, s3_client) -> None:
    """Write missing parquet/RDS exports for one game."""
    parquet_key = destination_parquet_key_for_game(game_id)
    if not s3_object_exists(s3_client, parquet_key):
        s3_client.put_object(Bucket=S3_BUCKET, Key=parquet_key, Body=parquet_bytes_for_frame(frame))
        print(f"Wrote s3://{S3_BUCKET}/{parquet_key} ({len(frame)} rows)")

    rds_key = destination_rds_key_for_game(game_id)
    if not s3_object_exists(s3_client, rds_key):
        s3_client.put_object(Bucket=S3_BUCKET, Key=rds_key, Body=rds_bytes_for_frame(frame))
        print(f"Wrote s3://{S3_BUCKET}/{rds_key}")


def main() -> None:
    """Backfill NBA-native per-game exports for the configured season range."""
    s3_client = boto3.client("s3")
    session = configure_cdn_session()

    game_ids = fetch_ordered_game_ids_from_s3(s3_client)
    if TARGET_GAME_IDS:
        target_ids = normalize_game_ids(TARGET_GAME_IDS)
        game_ids = [game_id for game_id in game_ids if game_id in target_ids]

    if DRY_RUN:
        game_ids = game_ids[:DRY_RUN_MAX_GAMES]
        print(
            "DRY_RUN=True: processing a small sample only and skipping all S3 writes "
            f"to s3://{S3_BUCKET}/{DESTINATION_PREFIX}/"
        )

    for index, game_id in enumerate(game_ids):
        parquet_key = destination_parquet_key_for_game(game_id)
        rds_key = destination_rds_key_for_game(game_id)
        if not DRY_RUN and s3_object_exists(s3_client, parquet_key) and s3_object_exists(s3_client, rds_key):
            print(f"{game_id}: exports already exist; skipping.")
            continue

        try:
            payload_bytes, payload_source = load_payload_bytes(game_id, s3_client, session)
            frame = build_frame_from_payload(payload_bytes, game_id, payload_source)
        except Exception as exc:
            print(f"{game_id}: failed ({type(exc).__name__}: {exc}). Skipping.")
            continue

        print(
            f"{game_id}: built {len(frame)} action rows x {len(frame.columns)} cols "
            f"from {payload_source}"
        )
        print(f"{game_id}: parquet -> s3://{S3_BUCKET}/{parquet_key}")
        print(f"{game_id}: rds     -> s3://{S3_BUCKET}/{rds_key}")

        if not DRY_RUN:
            write_game_exports_to_s3(game_id, frame, s3_client)

        if index < len(game_ids) - 1:
            sleep_with_jitter(SLEEP_SECONDS, SLEEP_JITTER_SECONDS, f"{game_id}: done.")


if __name__ == "__main__":
    main()
