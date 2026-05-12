from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

try:
    from heavy_silver_runtime import datetime_to_iso, normalize_utc_datetime
except ModuleNotFoundError:
    from pipelines.athena.transform.silver.heavy_silver_runtime import (
        datetime_to_iso,
        normalize_utc_datetime,
    )


def parse_state_datetime(value: Any) -> datetime | None:
    """Parse persisted state datetime values into UTC datetimes."""
    return normalize_utc_datetime(value)


def state_datetime_to_iso(value: datetime | None) -> str | None:
    """Serialize state datetimes to the existing ISO-Z format."""
    return datetime_to_iso(value)


def select_incremental_game_ids_from_watermark_state(
    source_index: dict[str, list[dict[str, Any]]],
    state: dict[str, Any],
    *,
    lookback_minutes: int,
    source_key_prefix: str | None = None,
) -> tuple[set[str], dict[str, Any]]:
    """Return game IDs selected by the legacy max-source-last-modified watermark."""
    state_watermark = parse_state_datetime(state.get("max_source_last_modified_utc"))
    if state_watermark is None:
        return set(source_index), {
            "selection_mode": "legacy_full_initial",
            "watermark_utc": None,
            "lookback_minutes": lookback_minutes,
        }

    effective_watermark = state_watermark - timedelta(minutes=lookback_minutes)
    selected_game_ids: set[str] = set()
    for game_id, artifacts in source_index.items():
        artifact_last_modified = max(
            (
                parse_state_datetime(artifact.get("last_modified_utc"))
                for artifact in artifacts
                if source_key_prefix is None
                or str(artifact.get("key", "")).startswith(source_key_prefix)
            ),
            default=None,
        )
        if artifact_last_modified is not None and artifact_last_modified >= effective_watermark:
            selected_game_ids.add(game_id)

    selection_meta = {
        "selection_mode": "legacy_state_incremental",
        "watermark_utc": state_datetime_to_iso(state_watermark),
        "effective_watermark_utc": state_datetime_to_iso(effective_watermark),
        "lookback_minutes": lookback_minutes,
    }
    return selected_game_ids, selection_meta
