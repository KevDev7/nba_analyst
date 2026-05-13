from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import duckdb

from scripts.load_gold_snapshot import load_database


FALLBACK_DEFAULT_SEASON_YEAR = "2025-26"
FALLBACK_DEFAULT_SEASON_TYPE = "regular_season"
DefaultScopeSource = Literal["snapshot_metadata", "fallback_constants"]


@dataclass(frozen=True)
class DefaultTimeScope:
    season_year: str
    season_type: str
    source: DefaultScopeSource


@lru_cache(maxsize=1)
def get_default_time_scope() -> DefaultTimeScope:
    try:
        database_path = load_database()
        with duckdb.connect(str(database_path), read_only=True) as conn:
            seasons = [
                row[0]
                for row in conn.execute("SELECT DISTINCT season_year FROM game ORDER BY season_year").fetchall()
                if row[0]
            ]
            season_types = [
                row[0]
                for row in conn.execute("SELECT DISTINCT season_type FROM game ORDER BY season_type").fetchall()
                if row[0]
            ]
        if seasons:
            season_type = (
                FALLBACK_DEFAULT_SEASON_TYPE
                if FALLBACK_DEFAULT_SEASON_TYPE in season_types
                else (season_types[0] if season_types else FALLBACK_DEFAULT_SEASON_TYPE)
            )
            return DefaultTimeScope(
                season_year=str(seasons[-1]),
                season_type=str(season_type),
                source="snapshot_metadata",
            )
    except Exception:
        pass
    return DefaultTimeScope(
        season_year=FALLBACK_DEFAULT_SEASON_YEAR,
        season_type=FALLBACK_DEFAULT_SEASON_TYPE,
        source="fallback_constants",
    )
