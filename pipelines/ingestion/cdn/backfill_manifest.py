from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable

import pyarrow.parquet as pq


LIVE_MANIFEST_SOURCE = "live"
HISTORICAL_MANIFEST_SOURCE = "historical"
HYBRID_MANIFEST_SOURCE = "hybrid"
MANIFEST_SOURCES = (
    LIVE_MANIFEST_SOURCE,
    HISTORICAL_MANIFEST_SOURCE,
    HYBRID_MANIFEST_SOURCE,
)


@dataclass(frozen=True)
class ManifestGame:
    game_id: str
    season_year: str | None
    game_date: date | None
    game_datetime_utc: datetime | None
    game_status_text: str | None
    manifest_source: str


@dataclass(frozen=True)
class ManifestSelectionReport:
    manifest_source: str
    discovered_count: int
    filtered_count: int
    skipped_existing_count: int
    selected_count: int
    first_selected_date: date | None
    last_selected_date: date | None


def normalize_game_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return text.zfill(10)
    return text


def season_start_year_to_string(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def infer_season_start_year_from_key(key: str) -> int | None:
    for part in key.split("/"):
        if part.startswith("season="):
            raw = part.split("=", 1)[1].strip()
            if raw.isdigit():
                return int(raw)
    return None


def parse_schedule_game_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return datetime.strptime(text, "%m/%d/%Y %H:%M:%S").date()


def parse_iso_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def effective_game_date(game: ManifestGame) -> date | None:
    if game.game_date is not None:
        return game.game_date
    if game.game_datetime_utc is not None:
        return game.game_datetime_utc.date()
    return None


def parse_cli_game_ids(value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return []
    output: list[str] = []
    seen: set[str] = set()
    for raw in value.split(","):
        normalized = normalize_game_id(raw)
        if normalized is None or normalized in seen:
            continue
        output.append(normalized)
        seen.add(normalized)
    return output


def build_live_manifest_games(payload: dict[str, Any]) -> list[ManifestGame]:
    schedule = payload.get("leagueSchedule") or {}
    season_year = schedule.get("seasonYear")
    rows: dict[str, ManifestGame] = {}

    for game_date_entry in schedule.get("gameDates") or []:
        parsed_date = parse_schedule_game_date(game_date_entry.get("gameDate"))
        for game in game_date_entry.get("games") or []:
            game_id = normalize_game_id(game.get("gameId"))
            if game_id is None:
                continue
            rows[game_id] = ManifestGame(
                game_id=game_id,
                season_year=str(season_year).strip() if season_year else None,
                game_date=parsed_date,
                game_datetime_utc=parse_iso_datetime(game.get("gameDateTimeUTC")),
                game_status_text=(str(game.get("gameStatusText")).strip() if game.get("gameStatusText") else None),
                manifest_source=LIVE_MANIFEST_SOURCE,
            )

    return sorted_manifest_games(rows.values())


def build_historical_manifest_games(
    rows: Iterable[dict[str, Any]],
    *,
    season_start_year: int,
) -> list[ManifestGame]:
    season_year = season_start_year_to_string(season_start_year)
    output: dict[str, ManifestGame] = {}

    for row in rows:
        game_id = normalize_game_id(row.get("gameId"))
        if game_id is None:
            continue
        game_datetime_utc = parse_iso_datetime(row.get("gameDateTimeUTC"))
        output[game_id] = ManifestGame(
            game_id=game_id,
            season_year=season_year,
            game_date=(game_datetime_utc.date() if game_datetime_utc is not None else None),
            game_datetime_utc=game_datetime_utc,
            game_status_text=None,
            manifest_source=HISTORICAL_MANIFEST_SOURCE,
        )

    return sorted_manifest_games(output.values())


def sorted_manifest_games(games: Iterable[ManifestGame]) -> list[ManifestGame]:
    return sorted(
        games,
        key=lambda game: (
            game.game_datetime_utc or datetime.min.replace(tzinfo=timezone.utc),
            effective_game_date(game) or date.min,
            game.game_id,
        ),
        reverse=True,
    )


def merge_manifest_games(live_games: Iterable[ManifestGame], historical_games: Iterable[ManifestGame]) -> list[ManifestGame]:
    merged: dict[str, ManifestGame] = {}
    for game in historical_games:
        merged[game.game_id] = game
    for game in live_games:
        merged[game.game_id] = game
    return sorted_manifest_games(merged.values())


def load_live_manifest_games_from_s3(
    s3_client,
    *,
    bucket: str,
    key: str,
) -> list[ManifestGame]:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    payload = json.loads(response["Body"].read())
    return build_live_manifest_games(payload)


def load_historical_manifest_games_from_s3(
    s3_client,
    *,
    bucket: str,
    prefix: str,
    unsupported_season_start_years: set[int] | None = None,
) -> list[ManifestGame]:
    unsupported = unsupported_season_start_years or set()
    paginator = s3_client.get_paginator("list_objects_v2")
    all_games: dict[str, ManifestGame] = {}

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if not key.endswith(".parquet"):
                continue
            season_start_year = infer_season_start_year_from_key(key)
            if season_start_year is None or season_start_year in unsupported:
                continue
            response = s3_client.get_object(Bucket=bucket, Key=key)
            table = pq.read_table(io.BytesIO(response["Body"].read()), columns=["gameId", "gameDateTimeUTC"])
            for game in build_historical_manifest_games(
                table.to_pylist(),
                season_start_year=season_start_year,
            ):
                all_games[game.game_id] = game

    return sorted_manifest_games(all_games.values())


def discover_manifest_games(
    s3_client,
    *,
    bucket: str,
    manifest_source: str,
    live_manifest_key: str,
    historical_manifest_prefix: str,
    unsupported_historical_season_start_years: set[int] | None = None,
) -> list[ManifestGame]:
    if manifest_source not in MANIFEST_SOURCES:
        raise ValueError(f"Unsupported manifest source: {manifest_source}")

    live_games: list[ManifestGame] = []
    historical_games: list[ManifestGame] = []

    if manifest_source in {LIVE_MANIFEST_SOURCE, HYBRID_MANIFEST_SOURCE}:
        live_games = load_live_manifest_games_from_s3(
            s3_client,
            bucket=bucket,
            key=live_manifest_key,
        )

    if manifest_source in {HISTORICAL_MANIFEST_SOURCE, HYBRID_MANIFEST_SOURCE}:
        historical_games = load_historical_manifest_games_from_s3(
            s3_client,
            bucket=bucket,
            prefix=historical_manifest_prefix,
            unsupported_season_start_years=unsupported_historical_season_start_years,
        )

    if manifest_source == LIVE_MANIFEST_SOURCE:
        return live_games
    if manifest_source == HISTORICAL_MANIFEST_SOURCE:
        return historical_games
    return merge_manifest_games(live_games, historical_games)


def filter_manifest_games(
    games: Iterable[ManifestGame],
    *,
    explicit_game_ids: list[str] | None = None,
    season: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_future: bool,
    today: date,
) -> list[ManifestGame]:
    normalized_games = list(games)
    if explicit_game_ids:
        index = {game.game_id: game for game in normalized_games}
        selected: list[ManifestGame] = []
        for game_id in explicit_game_ids:
            selected.append(
                index.get(
                    game_id,
                    ManifestGame(
                        game_id=game_id,
                        season_year=None,
                        game_date=None,
                        game_datetime_utc=None,
                        game_status_text=None,
                        manifest_source="explicit",
                    ),
                )
            )
        return selected

    output: list[ManifestGame] = []
    for game in normalized_games:
        if season is not None and game.season_year != season:
            continue
        game_day = effective_game_date(game)
        if not include_future and game_day is not None and game_day > today:
            continue
        if date_from is not None and game_day is not None and game_day < date_from:
            continue
        if date_to is not None and game_day is not None and game_day > date_to:
            continue
        output.append(game)

    return sorted_manifest_games(output)


def apply_existing_skip_and_cap(
    games: Iterable[ManifestGame],
    *,
    object_exists_for_game_id: Callable[[str], bool],
    max_games_per_run: int,
) -> tuple[list[ManifestGame], int]:
    selected: list[ManifestGame] = []
    skipped_existing = 0

    for game in games:
        if object_exists_for_game_id(game.game_id):
            skipped_existing += 1
            continue
        selected.append(game)
        if len(selected) >= max_games_per_run:
            break

    return selected, skipped_existing


def build_selection_report(
    *,
    manifest_source: str,
    discovered_count: int,
    filtered_games: list[ManifestGame],
    selected_games: list[ManifestGame],
    skipped_existing_count: int,
) -> ManifestSelectionReport:
    selected_dates = [effective_game_date(game) for game in selected_games if effective_game_date(game) is not None]
    first_selected_date = selected_dates[0] if selected_dates else None
    last_selected_date = selected_dates[-1] if selected_dates else None
    return ManifestSelectionReport(
        manifest_source=manifest_source,
        discovered_count=discovered_count,
        filtered_count=len(filtered_games),
        skipped_existing_count=skipped_existing_count,
        selected_count=len(selected_games),
        first_selected_date=first_selected_date,
        last_selected_date=last_selected_date,
    )
