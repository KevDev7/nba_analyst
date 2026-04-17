"""Backfill CDN boxscore JSON payloads with targeted current-season controls."""

from __future__ import annotations

import argparse
import random
import time
from collections import deque
from datetime import date, datetime

import requests
from dotenv import load_dotenv

load_dotenv(override=True)  # Ensure .env credentials override any system variables

import boto3
from botocore.exceptions import ClientError

try:
    from pipelines.ingestion.cdn.backfill_manifest import (
        LIVE_MANIFEST_SOURCE,
        MANIFEST_SOURCES,
        ManifestGame,
        apply_existing_skip_and_cap,
        build_selection_report,
        discover_manifest_games,
        effective_game_date,
        filter_manifest_games,
        normalize_game_id,
        parse_cli_game_ids,
    )
except ModuleNotFoundError:
    from backfill_manifest import (  # type: ignore[no-redef]
        LIVE_MANIFEST_SOURCE,
        MANIFEST_SOURCES,
        ManifestGame,
        apply_existing_skip_and_cap,
        build_selection_report,
        discover_manifest_games,
        effective_game_date,
        filter_manifest_games,
        normalize_game_id,
        parse_cli_game_ids,
    )


DEFAULT_MAX_GAMES_PER_RUN = 1200

SLEEP_SECONDS = 1.4
SLEEP_JITTER_SECONDS = 0.9

COOLDOWN_EVERY_GAMES = 300
COOLDOWN_SECONDS = 120
COOLDOWN_JITTER_SECONDS = 60

API_TIMEOUT_SECONDS = 25
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0
RETRY_JITTER_SECONDS = 2.0

# Circuit-breaker guards to avoid prolonged bans/throttling windows.
HALT_ON_CONSECUTIVE_403 = 2
HALT_ON_429_COUNT = 2
HALT_ON_429_WINDOW_SECONDS = 300
HALT_ON_CONSECUTIVE_TIMEOUTS = 3

S3_BUCKET = "nba-analytics-lakehouse-dev"
LIVE_SCHEDULE_SOURCE_KEY = "raw/cdn/scheduleLeagueV2_1.json"
HISTORICAL_SCHEDULE_SOURCE_PREFIX = "raw/scheduleleaguev2/seasongames/"
DESTINATION_PREFIX = "raw/cdn/boxscore"

CDN_BOXSCORE_URL_TEMPLATE = (
    "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
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


def destination_key_for_game(game_id: str) -> str:
    """S3 destination key for one game's boxscore JSON."""
    normalized = normalize_game_id(game_id)
    if normalized is None:
        raise ValueError(f"Invalid game_id for destination key: {game_id!r}")
    return f"{DESTINATION_PREFIX}/game_id={normalized}.json"


def legacy_destination_key_for_game(game_id: str) -> str:
    """Legacy regular-season key format without left-padding."""
    normalized = normalize_game_id(game_id)
    if normalized is None:
        raise ValueError(f"Invalid game_id for legacy destination key: {game_id!r}")
    stripped = normalized.lstrip("0") or "0"
    return f"{DESTINATION_PREFIX}/game_id={stripped}.json"


def destination_key_candidates_for_game(game_id: str) -> list[str]:
    """Return all known compatible raw boxscore keys for one game."""
    candidates = [destination_key_for_game(game_id)]
    legacy_key = legacy_destination_key_for_game(game_id)
    if legacy_key not in candidates:
        candidates.append(legacy_key)
    return candidates


def sleep_with_jitter(base_seconds: float, jitter_seconds: float, reason: str) -> None:
    """Sleep for a randomized duration in [base-jitter, base+jitter], bounded at 0."""
    lower = max(0.0, base_seconds - jitter_seconds)
    upper = base_seconds + jitter_seconds
    sleep_seconds = random.uniform(lower, upper)
    print(f"{reason} Sleeping {sleep_seconds:.1f}s...")
    time.sleep(sleep_seconds)


def is_likely_transient_error(exc: Exception) -> bool:
    """Return True for timeout/connectivity/rate-limit style failures."""
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True

    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        status_code = exc.response.status_code
        if status_code in {429, 500, 502, 503, 504}:
            return True

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


def classify_fetch_exception(exc: Exception) -> str:
    """Classify final fetch exception for circuit-breaker decisions."""
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        status_code = exc.response.status_code
        if status_code == 403:
            return "http_403"
        if status_code == 429:
            return "http_429"
    return "other"


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


def object_exists_for_game_id(s3_client, game_id: str) -> bool:
    """Return True when any compatible raw boxscore key exists for one game."""
    for key in destination_key_candidates_for_game(game_id):
        if s3_object_exists(s3_client, key):
            return True
    return False


def parse_date_arg(value: str) -> date:
    return date.fromisoformat(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest-source",
        choices=MANIFEST_SOURCES,
        default=LIVE_MANIFEST_SOURCE,
        help="Schedule manifest source used to discover candidate game IDs.",
    )
    parser.add_argument(
        "--season",
        type=str,
        default=None,
        help="Restrict candidate discovery to one NBA season string like 2025-26.",
    )
    parser.add_argument(
        "--date-from",
        type=parse_date_arg,
        default=None,
        help="Inclusive lower bound for game_date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--date-to",
        type=parse_date_arg,
        default=None,
        help="Inclusive upper bound for game_date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--game-ids",
        type=str,
        default="",
        help="Comma-separated explicit game IDs. Overrides manifest/date filters.",
    )
    parser.add_argument(
        "--max-games-per-run",
        type=int,
        default=DEFAULT_MAX_GAMES_PER_RUN,
        help=f"Maximum number of missing games to fetch in one run (default: {DEFAULT_MAX_GAMES_PER_RUN}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected candidates without fetching or writing any raw payloads.",
    )
    parser.add_argument(
        "--include-future",
        action="store_true",
        help="Include future scheduled games when selecting candidates.",
    )
    return parser.parse_args()


def print_selection_summary(
    *,
    report,
    sample_games: list[ManifestGame],
) -> None:
    print(f"Manifest source: {report.manifest_source}")
    print(f"Discovered candidates before filtering: {report.discovered_count}")
    print(f"Candidates after manifest filters: {report.filtered_count}")
    print(f"Skipped because raw already exists: {report.skipped_existing_count}")
    print(f"Selected games to process: {report.selected_count}")
    print(f"First selected game date: {report.first_selected_date}")
    print(f"Last selected game date: {report.last_selected_date}")
    if sample_games:
        print("First selected game IDs:")
        for game in sample_games[:10]:
            print(f"- {game.game_id} ({effective_game_date(game)})")


def fetch_boxscore_for_game(game_id: str, session: requests.Session) -> bytes:
    """Fetch raw CDN boxscore JSON bytes for one game."""
    cdn_game_id = game_id.zfill(10)
    url = CDN_BOXSCORE_URL_TEMPLATE.format(game_id=cdn_game_id)
    response = session.get(url, timeout=API_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content


def fetch_boxscore_with_retry(game_id: str, session: requests.Session) -> bytes:
    """Fetch boxscore JSON with retries for transient failures."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_boxscore_for_game(game_id, session)
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


def write_json_to_s3(payload: bytes, game_id: str, s3_client) -> None:
    """Write one game's raw CDN payload to S3 as JSON."""
    key = destination_key_for_game(game_id)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=payload,
        ContentType="application/json",
    )
    print(f"Wrote s3://{S3_BUCKET}/{key}")


def configure_cdn_session() -> requests.Session:
    """Create a session with browser-like headers for CDN compatibility."""
    session = requests.Session()
    session.headers.update(DEFAULT_CDN_HEADERS)
    return session


def main() -> None:
    """Backfill CDN boxscore JSON from newest selected games to oldest."""
    args = parse_args()
    explicit_game_ids = parse_cli_game_ids(args.game_ids)
    if args.max_games_per_run <= 0:
        raise SystemExit("--max-games-per-run must be > 0")
    if args.date_from and args.date_to and args.date_from > args.date_to:
        raise SystemExit("--date-from must be <= --date-to")

    print(
        f"Starting CDN BoxScore backfill. "
        f"Manifest source={args.manifest_source}, dry_run={args.dry_run}"
    )

    s3_client = boto3.client("s3")
    session = configure_cdn_session()

    discovered = 0
    attempted = 0
    fetched = 0
    skipped_exists = 0
    failed = 0
    failed_game_ids: list[str] = []
    halted_reason: str | None = None

    consecutive_403 = 0
    consecutive_timeouts = 0
    recent_429_failures: deque[float] = deque()

    try:
        manifest_games = discover_manifest_games(
            s3_client,
            bucket=S3_BUCKET,
            manifest_source=args.manifest_source,
            live_manifest_key=LIVE_SCHEDULE_SOURCE_KEY,
            historical_manifest_prefix=HISTORICAL_SCHEDULE_SOURCE_PREFIX,
        )
        discovered = len(manifest_games)
        filtered_games = filter_manifest_games(
            manifest_games,
            explicit_game_ids=explicit_game_ids,
            season=args.season,
            date_from=args.date_from,
            date_to=args.date_to,
            include_future=args.include_future,
            today=date.today(),
        )
        selected_games, skipped_exists = apply_existing_skip_and_cap(
            filtered_games,
            object_exists_for_game_id=lambda game_id: object_exists_for_game_id(s3_client, game_id),
            max_games_per_run=args.max_games_per_run,
        )
        report = build_selection_report(
            manifest_source=args.manifest_source,
            discovered_count=discovered,
            filtered_games=filtered_games,
            selected_games=selected_games,
            skipped_existing_count=skipped_exists,
        )
        print_selection_summary(report=report, sample_games=selected_games)

        if args.dry_run:
            print("Dry run only; skipping fetch and write steps.")
            return

        for index, game in enumerate(selected_games, start=1):
            attempted += 1
            game_id = game.game_id

            print(f"Fetching game {index}/{len(selected_games)} ({game_id})...")
            try:
                payload = fetch_boxscore_with_retry(game_id, session)
            except Exception as exc:
                failed += 1
                failed_game_ids.append(game_id)
                failure_type = classify_fetch_exception(exc)

                now = time.time()
                while recent_429_failures and (
                    now - recent_429_failures[0] > HALT_ON_429_WINDOW_SECONDS
                ):
                    recent_429_failures.popleft()

                if failure_type == "http_403":
                    consecutive_403 += 1
                else:
                    consecutive_403 = 0

                if failure_type == "timeout":
                    consecutive_timeouts += 1
                else:
                    consecutive_timeouts = 0

                if failure_type == "http_429":
                    recent_429_failures.append(now)

                print(
                    f"Game {game_id} failed after retries "
                    f"({type(exc).__name__}: {exc}). Continuing."
                )

                if consecutive_403 >= HALT_ON_CONSECUTIVE_403:
                    halted_reason = (
                        f"Circuit breaker: {consecutive_403} consecutive 403 responses."
                    )
                    print(halted_reason)
                    break

                if len(recent_429_failures) >= HALT_ON_429_COUNT:
                    halted_reason = (
                        f"Circuit breaker: {len(recent_429_failures)} HTTP 429 responses "
                        f"within {HALT_ON_429_WINDOW_SECONDS}s."
                    )
                    print(halted_reason)
                    break

                if consecutive_timeouts >= HALT_ON_CONSECUTIVE_TIMEOUTS:
                    halted_reason = (
                        f"Circuit breaker: {consecutive_timeouts} consecutive timeouts."
                    )
                    print(halted_reason)
                    break

                continue

            fetched += 1
            consecutive_403 = 0
            consecutive_timeouts = 0

            write_json_to_s3(payload, game_id, s3_client)

            if index < len(selected_games):
                sleep_with_jitter(
                    SLEEP_SECONDS,
                    SLEEP_JITTER_SECONDS,
                    reason="Inter-game pacing.",
                )
                if fetched % COOLDOWN_EVERY_GAMES == 0:
                    sleep_with_jitter(
                        COOLDOWN_SECONDS,
                        COOLDOWN_JITTER_SECONDS,
                        reason=f"Cooldown after {fetched} new fetches.",
                    )
    finally:
        session.close()

    print("Backfill complete.")
    if halted_reason is not None:
        print(f"Run halted early: {halted_reason}")
    print(
        "Summary: "
        f"discovered={discovered}, attempted={attempted}, fetched={fetched}, "
        f"skipped_exists={skipped_exists}, failed={failed}"
    )
    if failed_game_ids:
        print("Failed game IDs:")
        for game_id in failed_game_ids:
            print(f"- {game_id}")


if __name__ == "__main__":
    main()
