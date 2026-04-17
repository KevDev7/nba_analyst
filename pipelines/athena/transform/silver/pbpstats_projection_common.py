"""Shared helpers for Athena standalone pbpstats-backed silver sidecars."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
PBPSTATS_ROOT = REPO_ROOT / "reference" / "pbpstats"
PBPSTATS_OVERRIDE_DATA_DIR = PBPSTATS_ROOT / "tests" / "data"
GAME_ID_FROM_PATH_RE = re.compile(r"game_id=([0-9]+)\.json$")

if str(PBPSTATS_ROOT) not in sys.path:
    sys.path.insert(0, str(PBPSTATS_ROOT))

from pbpstats.data_loader.live.enhanced_pbp.loader import LiveEnhancedPbpLoader  # noqa: E402
from pbpstats.data_loader.live.possessions.loader import LivePossessionLoader  # noqa: E402
from pbpstats.resources.enhanced_pbp.start_of_period import InvalidNumberOfStartersException  # noqa: E402


class ProjectionFailure(RuntimeError):
    """Raised when a game's event graph cannot be safely projected."""


class _InMemoryLiveEnhancedPbpSourceLoader:
    def __init__(self, payload: dict[str, Any], file_directory: str | None = None):
        self.payload = payload
        self.file_directory = file_directory

    def load_data(self, game_id: str) -> dict[str, Any]:
        return self.payload


class _InMemoryLivePossessionSourceLoader:
    def __init__(self, payload: dict[str, Any], file_directory: str | None = None):
        self.file_directory = file_directory
        self.enhanced_pbp_source_loader = _InMemoryLiveEnhancedPbpSourceLoader(
            payload,
            file_directory=file_directory,
        )


class _StarterWarningLiveEnhancedPbpLoader(LiveEnhancedPbpLoader):
    """Live loader variant that records incomplete period-starter inference."""

    def _set_period_start_items(self):  # type: ignore[override]
        self.period_starter_warnings: list[dict[str, Any]] = []
        for i in self.start_period_indices:
            event = self.items[i]
            team_id = event.get_team_starting_with_ball()
            event.team_starting_with_ball = team_id
            period_starters = event.get_period_starters(
                file_directory=self.file_directory,
                ignore_missing_starters=True,
            )
            event.period_starters = period_starters
            if not _has_complete_period_starters(period_starters):
                self.period_starter_warnings.append(
                    {
                        "game_id": normalize_string(getattr(event, "game_id", None)),
                        "event_num": normalize_long(getattr(event, "event_num", None)),
                        "period": normalize_long(getattr(event, "period", None)),
                        "starter_team_sizes": {
                            str(team_id): len(players)
                            for team_id, players in (period_starters or {}).items()
                        },
                    }
                )


def extract_game_id_from_path(path: str | None) -> str | None:
    if not path:
        return None
    match = GAME_ID_FROM_PATH_RE.search(path)
    if match is None:
        return None
    return match.group(1).zfill(10)


def decode_raw_payload(content: Any) -> dict[str, Any]:
    if isinstance(content, memoryview):
        content = content.tobytes()
    if isinstance(content, bytearray):
        content = bytes(content)
    if isinstance(content, bytes):
        text = content.decode("utf-8")
    elif isinstance(content, str):
        text = content
    else:
        raise ProjectionFailure(f"Unsupported raw payload type: {type(content).__name__}")
    return json.loads(text)


def normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def normalize_long(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_double(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_boolean(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def normalize_string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def normalize_long_list(value: Any) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        value = [value]
    normalized = [normalize_long(item) for item in value]
    if any(item is None for item in normalized):
        return None
    return [item for item in normalized if item is not None]


def sort_long_list(value: list[int] | None) -> list[int] | None:
    if value is None:
        return None
    return sorted(value, key=str)


def load_live_enhanced_pbp_items(
    payload: dict[str, Any],
    *,
    fallback_game_id: str | None = None,
) -> tuple[str, list[Any]]:
    game = payload.get("game") or {}
    game_id = normalize_string(game.get("gameId")) or fallback_game_id
    if not game_id:
        raise ProjectionFailure("Missing game_id in raw payload and path fallback")
    source_loader = _InMemoryLiveEnhancedPbpSourceLoader(
        payload,
        file_directory=str(PBPSTATS_OVERRIDE_DATA_DIR),
    )
    loader = LiveEnhancedPbpLoader(game_id, source_loader)
    return game_id, list(loader.items)


def load_live_possession_items(
    payload: dict[str, Any],
    *,
    fallback_game_id: str | None = None,
) -> tuple[str, list[Any]]:
    game = payload.get("game") or {}
    game_id = normalize_string(game.get("gameId")) or fallback_game_id
    if not game_id:
        raise ProjectionFailure("Missing game_id in raw payload and path fallback")
    source_loader = _InMemoryLivePossessionSourceLoader(
        payload,
        file_directory=str(PBPSTATS_OVERRIDE_DATA_DIR),
    )
    loader = LivePossessionLoader(game_id, source_loader)
    return game_id, list(loader.items)


def load_live_enhanced_pbp_items_with_period_starter_warnings(
    payload: dict[str, Any],
    *,
    fallback_game_id: str | None = None,
) -> tuple[str, list[Any], list[dict[str, Any]]]:
    game = payload.get("game") or {}
    game_id = normalize_string(game.get("gameId")) or fallback_game_id
    if not game_id:
        raise ProjectionFailure("Missing game_id in raw payload and path fallback")
    source_loader = _InMemoryLiveEnhancedPbpSourceLoader(
        payload,
        file_directory=str(PBPSTATS_OVERRIDE_DATA_DIR),
    )
    loader = _StarterWarningLiveEnhancedPbpLoader(game_id, source_loader)
    return game_id, list(loader.items), list(getattr(loader, "period_starter_warnings", []))


def _has_complete_period_starters(period_starters: Any) -> bool:
    if not isinstance(period_starters, dict) or len(period_starters) != 2:
        return False
    for players in period_starters.values():
        if not isinstance(players, list) or len(players) != 5:
            return False
    return True


def is_complete_period_starters(period_starters: Any) -> bool:
    return _has_complete_period_starters(period_starters)


def normalize_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def add_silver_metadata(
    rows: list[dict[str, Any]],
    *,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    source_system: str,
    source_key: str,
    source_last_modified_utc: datetime | None,
    schema_version: int,
) -> list[dict[str, Any]]:
    normalized_ingested_at = normalize_timestamp(ingested_at_utc)
    normalized_source_last_modified = normalize_timestamp(source_last_modified_utc)
    output_rows: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        enriched["_meta_pipeline_run_id"] = pipeline_run_id
        enriched["_meta_ingested_at_utc"] = normalized_ingested_at
        enriched["_meta_source_system"] = source_system
        enriched["_meta_source_key"] = source_key
        enriched["_meta_source_last_modified_utc"] = normalized_source_last_modified
        enriched["_meta_schema_version"] = schema_version
        output_rows.append(enriched)
    return output_rows


def list_size(values: list[Any] | None) -> int | None:
    if values is None:
        return None
    return len(values)
