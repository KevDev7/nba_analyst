"""Backfill shufinskiy/nba_data matchup archive files into raw S3.

Source:
  https://github.com/shufinskiy/nba_data/raw/main/datasets/matchups_<season>.tar.xz
  https://github.com/shufinskiy/nba_data/raw/main/datasets/matchups_po_<season>.tar.xz

Destination pattern:
  s3://nba-analytics-lakehouse-dev/raw/nba_data/matchups/
    season=<start_year>/season_type=<regular|playoffs>/<archive_name>.tar.xz

This preserves the source archive file type in bronze/raw. The silver transform is
responsible for extracting the CSV payload from each archive.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

load_dotenv(override=True)  # Ensure .env credentials override any system variables
if os.environ.get("AWS_PROFILE") == "":
    os.environ.pop("AWS_PROFILE")

import boto3
from botocore.exceptions import ClientError


DEFAULT_SEASON_START_YEARS = tuple(range(2020, 2026))
DEFAULT_SEASON_TYPES = ("regular", "playoffs")
S3_BUCKET = "nba-analytics-lakehouse-dev"
DESTINATION_PREFIX = "raw/nba_data/matchups"
REQUEST_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class MatchupArchive:
    season_start_year: int
    season_type: str
    archive_name: str
    url: str
    destination_key: str


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


def parse_csv_strings(value: str | None) -> tuple[str, ...]:
    if value is None or value.strip() == "":
        return DEFAULT_SEASON_TYPES
    values: list[str] = []
    seen: set[str] = set()
    for raw in value.split(","):
        text = raw.strip().lower()
        if not text or text in seen:
            continue
        values.append(text)
        seen.add(text)
    return tuple(values)


def archive_for(season_start_year: int, season_type: str) -> MatchupArchive:
    if season_type not in {"regular", "playoffs"}:
        raise ValueError(f"Unsupported season_type: {season_type}")
    prefix = "matchups" if season_type == "regular" else "matchups_po"
    archive_name = f"{prefix}_{season_start_year}.tar.xz"
    url = f"https://github.com/shufinskiy/nba_data/raw/main/datasets/{archive_name}"
    destination_key = (
        f"{DESTINATION_PREFIX}/season={season_start_year}/"
        f"season_type={season_type}/{archive_name}"
    )
    return MatchupArchive(
        season_start_year=season_start_year,
        season_type=season_type,
        archive_name=archive_name,
        url=url,
        destination_key=destination_key,
    )


def build_archives(season_start_years: tuple[int, ...], season_types: tuple[str, ...]) -> list[MatchupArchive]:
    return [
        archive_for(season_start_year, season_type)
        for season_start_year in season_start_years
        for season_type in season_types
    ]


def s3_object_exists(s3_client, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def fetch_archive(archive: MatchupArchive) -> bytes:
    response = requests.get(archive.url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content


def write_archive_to_s3(payload: bytes, archive: MatchupArchive, s3_client) -> None:
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=archive.destination_key,
        Body=payload,
        ContentType="application/x-xz",
    )
    print(f"Wrote s3://{S3_BUCKET}/{archive.destination_key}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--season-start-years",
        type=parse_csv_ints,
        default=DEFAULT_SEASON_START_YEARS,
        help="Comma-separated NBA season start years. Default: 2020,2021,2022,2023,2024,2025.",
    )
    parser.add_argument(
        "--season-types",
        type=parse_csv_strings,
        default=DEFAULT_SEASON_TYPES,
        help="Comma-separated season types: regular,playoffs. Default: regular,playoffs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected archives without fetching or writing.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing raw archive objects.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    archives = build_archives(args.season_start_years, args.season_types)
    s3_client = boto3.client("s3")

    print(f"Selected archives: {len(archives)}")
    for archive in archives:
        exists = s3_object_exists(s3_client, archive.destination_key)
        status = "exists" if exists else "missing"
        print(f"- {archive.archive_name} -> {archive.destination_key} ({status})")

    if args.dry_run:
        print("Dry run only; skipping fetch and write steps.")
        return

    written = 0
    skipped_existing = 0
    for archive in archives:
        if s3_object_exists(s3_client, archive.destination_key) and not args.overwrite:
            skipped_existing += 1
            print(f"Already exists; skipping s3://{S3_BUCKET}/{archive.destination_key}")
            continue
        print(f"Fetching {archive.url}")
        payload = fetch_archive(archive)
        write_archive_to_s3(payload, archive, s3_client)
        written += 1

    print(f"Archive backfill complete. written={written}, skipped_existing={skipped_existing}")


if __name__ == "__main__":
    main()
