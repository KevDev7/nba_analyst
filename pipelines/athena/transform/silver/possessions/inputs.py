from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PossessionGameInput:
    game_id: str | None
    payload: dict[str, Any]
    playbyplay_rows: list[dict[str, Any]]
    on_court_rows: list[dict[str, Any]] = field(default_factory=list)
    source_key: str | None = None
    source_last_modified_utc: datetime | None = None
