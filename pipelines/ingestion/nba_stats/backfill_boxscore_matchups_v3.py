"""Backfill NBA Stats BoxScoreMatchupsV3 raw JSON payloads.

Source:
  https://stats.nba.com/stats/boxscorematchupsv3

Destination pattern:
  s3://nba-analytics-lakehouse-dev/raw/boxscorematchupsv3/game_id=<GAME_ID>.json

The default season window is intentionally limited to the first production slice:
2020-21 through 2025-26, completed games only, regular season + playoffs +
play-in game id families.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from collections import deque
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(override=True)  # Ensure .env credentials override any system variables
if os.environ.get("AWS_PROFILE") == "":
    os.environ.pop("AWS_PROFILE")

import boto3
from botocore.exceptions import ClientError

try:
    from pipelines.ingestion.cdn.backfill_manifest import (
        HYBRID_MANIFEST_SOURCE,
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
        season_start_year_to_string,
    )
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.ingestion.cdn.backfill_manifest import (  # type: ignore[no-redef]
        HYBRID_MANIFEST_SOURCE,
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
        season_start_year_to_string,
    )


DEFAULT_SEASON_START_YEARS = tuple(range(2020, 2026))
DEFAULT_GAME_ID_PREFIXES = ("002", "004", "005")
DEFAULT_MAX_GAMES_PER_RUN = 300

SLEEP_SECONDS = 2.5
SLEEP_JITTER_SECONDS = 1.0

COOLDOWN_EVERY_GAMES = 75
COOLDOWN_SECONDS = 180
COOLDOWN_JITTER_SECONDS = 60

API_TIMEOUT_SECONDS = 30
MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = 3.0
RETRY_JITTER_SECONDS = 2.0

HALT_ON_CONSECUTIVE_403 = 2
HALT_ON_429_COUNT = 2
HALT_ON_429_WINDOW_SECONDS = 300
HALT_ON_CONSECUTIVE_TIMEOUTS = 3

S3_BUCKET = "nba-analytics-lakehouse-dev"
LIVE_SCHEDULE_SOURCE_KEY = "raw/cdn/scheduleLeagueV2_1.json"
HISTORICAL_SCHEDULE_SOURCE_PREFIX = "raw/scheduleleaguev2/seasongames/"
DESTINATION_PREFIX = "raw/boxscorematchupsv3"

BOXSCORE_MATCHUPS_URL = "https://stats.nba.com/stats/boxscorematchupsv3"

DEFAULT_STATS_HEADERS = {
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


def destination_key_for_game(game_id: str) -> str:
    """S3 destination key for one game's raw matchup JSON."""
    normalized = normalize_game_id(game_id)
    if normalized is None:
        raise ValueError(f"Invalid game_id for destination key: {game_id!r}")
    return f"{DESTINATION_PREFIX}/game_id={normalized}.json"


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
    return s3_object_exists(s3_client, destination_key_for_game(game_id))


def parse_csv_ints(value: str | None) -> tuple[int, ...]:
    if value is None or value.strip() == "":
        return DEFAULT_SEASON_START_YEARS
    years: list[int] = []
    seen: set[int] = set()
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        year = int(raw)
        if year not in seen:
            years.append(year)
            seen.add(year)
    return tuple(years)


def parse_csv_prefixes(value: str | None) -> tuple[str, ...]:
    if value is None or value.strip() == "":
        return DEFAULT_GAME_ID_PREFIXES
    prefixes: list[str] = []
    seen: set[str] = set()
    for raw in value.split(","):
        prefix = raw.strip()
        if not prefix or prefix in seen:
            continue
        prefixes.append(prefix)
        seen.add(prefix)
    return tuple(prefixes)


def parse_date_arg(value: str) -> date:
    return date.fromisoformat(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest-source",
        choices=MANIFEST_SOURCES,
        default=HYBRID_MANIFEST_SOURCE,
        help="Schedule manifest source used to discover candidate game IDs.",
    )
    parser.add_argument(
        "--season-start-years",
        type=parse_csv_ints,
        default=DEFAULT_SEASON_START_YEARS,
        help="Comma-separated NBA season start years. Default: 2020,2021,2022,2023,2024,2025.",
    )
    parser.add_argument(
        "--game-id-prefixes",
        type=parse_csv_prefixes,
        default=DEFAULT_GAME_ID_PREFIXES,
        help="Comma-separated game id prefixes to include. Default: 002,004,005.",
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
        help="Print selected candidates without fetching or writing raw payloads.",
    )
    parser.add_argument(
        "--include-future",
        action="store_true",
        help="Include future scheduled games when selecting candidates.",
    )
    return parser.parse_args()


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
        return exc.response.status_code in {429, 500, 502, 503, 504}
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("timeout", "timed out", "connection", "too many requests", "429", "502", "503", "504")
    )


def classify_fetch_exception(exc: Exception) -> str:
    """Classify final fetch exception for circuit-breaker decisions."""
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        if exc.response.status_code == 403:
            return "http_403"
        if exc.response.status_code == 429:
            return "http_429"
    return "other"


def configure_stats_session() -> requests.Session:
    """Create a session with browser-like headers for stats.nba.com compatibility."""
    session = requests.Session()
    session.headers.update(DEFAULT_STATS_HEADERS)
    return session


def fetch_matchups_for_game(game_id: str, session: requests.Session) -> bytes:
    """Fetch raw BoxScoreMatchupsV3 JSON bytes for one game."""
    normalized = normalize_game_id(game_id)
    if normalized is None:
        raise ValueError(f"Invalid game_id for fetch: {game_id!r}")
    response = session.get(
        BOXSCORE_MATCHUPS_URL,
        params={"GameID": normalized, "LeagueID": "00"},
        timeout=API_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.content


def fetch_matchups_with_retry(game_id: str, session: requests.Session) -> bytes:
    """Fetch matchup JSON with retries for transient failures."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_matchups_for_game(game_id, session)
        except Exception as exc:
            is_transient = is_likely_transient_error(exc)
            if (not is_transient) or attempt == MAX_RETRIES:
                raise
            sleep_seconds = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)) + random.uniform(0.0, RETRY_JITTER_SECONDS)
            print(
                f"GAME_ID {game_id} failed on attempt {attempt}/{MAX_RETRIES} "
                f"({type(exc).__name__}: {exc}). Retrying in {sleep_seconds:.1f}s..."
            )
            time.sleep(sleep_seconds)

    raise RuntimeError("Unreachable retry branch")


def write_json_to_s3(payload: bytes, game_id: str, s3_client) -> None:
    """Write one game's raw NBA Stats payload to S3 as JSON."""
    key = destination_key_for_game(game_id)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=payload,
        ContentType="application/json",
    )
    print(f"Wrote s3://{S3_BUCKET}/{key}")


def season_strings_from_start_years(start_years: tuple[int, ...]) -> set[str]:
    return {season_start_year_to_string(year) for year in start_years}


def filter_to_game_id_prefixes(games: list[ManifestGame], prefixes: tuple[str, ...]) -> list[ManifestGame]:
    return [game for game in games if any(game.game_id.startswith(prefix) for prefix in prefixes)]


def print_selection_summary(*, report, sample_games: list[ManifestGame]) -> None:
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


def main() -> None:
    """Backfill BoxScoreMatchupsV3 JSON from newest selected games to oldest."""
    args = parse_args()
    explicit_game_ids = parse_cli_game_ids(args.game_ids)
    if args.max_games_per_run <= 0:
        raise SystemExit("--max-games-per-run must be > 0")
    if args.date_from and args.date_to and args.date_from > args.date_to:
        raise SystemExit("--date-from must be <= --date-to")

    season_strings = season_strings_from_start_years(args.season_start_years)
    print(
        "Starting BoxScoreMatchupsV3 backfill. "
        f"Manifest source={args.manifest_source}, seasons={sorted(season_strings)}, "
        f"game_id_prefixes={args.game_id_prefixes}, dry_run={args.dry_run}"
    )

    s3_client = boto3.client("s3")
    session = configure_stats_session()

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
            season=None,
            date_from=args.date_from,
            date_to=args.date_to,
            include_future=args.include_future,
            today=date.today(),
        )
        if not explicit_game_ids:
            filtered_games = [game for game in filtered_games if game.season_year in season_strings]
            filtered_games = filter_to_game_id_prefixes(filtered_games, args.game_id_prefixes)

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
                payload = fetch_matchups_with_retry(game_id, session)
            except Exception as exc:
                failed += 1
                failed_game_ids.append(game_id)
                failure_type = classify_fetch_exception(exc)

                now = time.time()
                while recent_429_failures and now - recent_429_failures[0] > HALT_ON_429_WINDOW_SECONDS:
                    recent_429_failures.popleft()

                consecutive_403 = consecutive_403 + 1 if failure_type == "http_403" else 0
                consecutive_timeouts = consecutive_timeouts + 1 if failure_type == "timeout" else 0
                if failure_type == "http_429":
                    recent_429_failures.append(now)

                print(
                    f"Game {game_id} failed after retries "
                    f"({type(exc).__name__}: {exc}). Continuing."
                )

                if consecutive_403 >= HALT_ON_CONSECUTIVE_403:
                    halted_reason = f"Circuit breaker: {consecutive_403} consecutive 403 responses."
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
                    halted_reason = f"Circuit breaker: {consecutive_timeouts} consecutive timeouts."
                    print(halted_reason)
                    break
                continue

            fetched += 1
            consecutive_403 = 0
            consecutive_timeouts = 0
            write_json_to_s3(payload, game_id, s3_client)

            if index < len(selected_games):
                sleep_with_jitter(SLEEP_SECONDS, SLEEP_JITTER_SECONDS, reason="Inter-game pacing.")
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
