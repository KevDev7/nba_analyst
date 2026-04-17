"""Audit completeness of raw CDN play-by-play JSON against schedule-derived game IDs.

This compares the canonical game list from:
  s3://nba-analytics-lakehouse-dev/raw/scheduleleaguev2/seasongames/

against the raw CDN play-by-play payloads in:
  s3://nba-analytics-lakehouse-dev/raw/cdn/playbyplay/

Optionally writes the missing game IDs to a CSV for inspection.
"""

from __future__ import annotations

import argparse
import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import boto3
import pyarrow.parquet as pq

S3_BUCKET = "nba-analytics-lakehouse-dev"
SCHEDULE_SOURCE_PREFIX = "raw/scheduleleaguev2/seasongames/"
PLAYBYPLAY_SOURCE_PREFIX = "raw/cdn/playbyplay/"
# Match the play-by-play backfill: these seasons are intentionally excluded because the
# NBA CDN endpoint does not reliably serve historical play-by-play for them.
UNSUPPORTED_SEASON_START_YEARS = {2017, 2018, 2019}


@dataclass(frozen=True)
class ScheduledGame:
    game_id: str
    game_datetime_utc: str
    season_start_year: int | None
    season_year: str | None
    schedule_key: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit raw CDN play-by-play completeness against schedule game IDs."
    )
    parser.add_argument(
        "--output-csv",
        default="",
        help="Optional local CSV path for missing game IDs.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="Number of missing rows to print as a sample.",
    )
    return parser.parse_args()


def parse_game_datetime(value: str) -> datetime:
    if not value:
        return datetime.min
    value = value.strip()
    if not value:
        return datetime.min
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min


def normalize_game_id(value: str | None) -> str | None:
    if value is None:
        return None
    digits = str(value).strip()
    if not digits:
        return None
    if not digits.isdigit():
        return digits
    return digits.zfill(10)


def infer_season_start_year_from_key(key: str) -> int | None:
    for part in key.split("/"):
        if part.startswith("season="):
            raw = part.split("=", 1)[1].strip()
            if raw.isdigit():
                return int(raw)
    return None


def season_label(start_year: int | None) -> str | None:
    if start_year is None:
        return None
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def list_parquet_keys(s3_client, prefix: str) -> list[str]:
    paginator = s3_client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            season_start_year = infer_season_start_year_from_key(key)
            if season_start_year in UNSUPPORTED_SEASON_START_YEARS:
                continue
            if key.endswith(".parquet"):
                keys.append(key)
    return sorted(keys)


def fetch_scheduled_games(s3_client) -> dict[str, ScheduledGame]:
    rows: list[tuple[datetime, ScheduledGame]] = []

    for key in list_parquet_keys(s3_client, SCHEDULE_SOURCE_PREFIX):
        start_year = infer_season_start_year_from_key(key)
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
        table = pq.read_table(io.BytesIO(response["Body"].read()), columns=["gameId", "gameDateTimeUTC"])

        for row in table.to_pylist():
            game_id = normalize_game_id(row.get("gameId"))
            if not game_id:
                continue
            game_datetime_utc = str(row.get("gameDateTimeUTC") or "").strip()
            scheduled_game = ScheduledGame(
                game_id=game_id,
                game_datetime_utc=game_datetime_utc,
                season_start_year=start_year,
                season_year=season_label(start_year),
                schedule_key=key,
            )
            rows.append((parse_game_datetime(game_datetime_utc), scheduled_game))

    rows.sort(key=lambda item: (item[0], item[1].game_id), reverse=True)

    ordered_unique: dict[str, ScheduledGame] = {}
    for _, scheduled_game in rows:
        if scheduled_game.game_id in ordered_unique:
            continue
        ordered_unique[scheduled_game.game_id] = scheduled_game
    return ordered_unique


def extract_game_id_from_json_key(key: str) -> str | None:
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id=") or not filename.endswith(".json"):
        return None
    return normalize_game_id(filename[len("game_id=") : -len(".json")])


def fetch_raw_playbyplay_game_ids(s3_client) -> set[str]:
    paginator = s3_client.get_paginator("list_objects_v2")
    game_ids: set[str] = set()
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=PLAYBYPLAY_SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            game_id = extract_game_id_from_json_key(key)
            if game_id:
                game_ids.add(game_id)
    return game_ids


def write_missing_csv(path: Path, rows: list[ScheduledGame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "season_start_year",
                "season_year",
                "game_id",
                "game_datetime_utc",
                "schedule_key",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "season_start_year": row.season_start_year,
                    "season_year": row.season_year,
                    "game_id": row.game_id,
                    "game_datetime_utc": row.game_datetime_utc,
                    "schedule_key": row.schedule_key,
                }
            )


def main() -> None:
    args = parse_args()
    s3_client = boto3.client("s3")

    scheduled_games = fetch_scheduled_games(s3_client)
    raw_playbyplay_game_ids = fetch_raw_playbyplay_game_ids(s3_client)

    missing_game_ids = sorted(set(scheduled_games) - raw_playbyplay_game_ids)
    missing_games = [scheduled_games[game_id] for game_id in missing_game_ids]
    season_counts = Counter(game.season_year or "unknown" for game in missing_games)

    print(f"Schedule source prefix: s3://{S3_BUCKET}/{SCHEDULE_SOURCE_PREFIX}")
    print(f"Raw play-by-play prefix: s3://{S3_BUCKET}/{PLAYBYPLAY_SOURCE_PREFIX}")
    print(
        "Excluded unsupported season_start_year values: "
        f"{sorted(UNSUPPORTED_SEASON_START_YEARS)}"
    )
    print(f"Unique scheduled game IDs: {len(scheduled_games)}")
    print(f"Raw play-by-play JSON files: {len(raw_playbyplay_game_ids)}")
    print(f"Missing raw play-by-play game IDs: {len(missing_games)}")

    print("Missing game counts by season:")
    for season_year, count in sorted(
        season_counts.items(),
        key=lambda item: (item[0] == "unknown", item[0]),
    ):
        print(f"- {season_year}: {count}")

    if args.sample_size > 0:
        print(f"Sample missing rows (first {min(args.sample_size, len(missing_games))}):")
        for row in missing_games[: args.sample_size]:
            print(
                f"- season_year={row.season_year} game_id={row.game_id} "
                f"game_datetime_utc={row.game_datetime_utc}"
            )

    if args.output_csv:
        output_path = Path(args.output_csv).expanduser().resolve()
        write_missing_csv(output_path, missing_games)
        print(f"Wrote missing game CSV: {output_path}")


if __name__ == "__main__":
    main()
