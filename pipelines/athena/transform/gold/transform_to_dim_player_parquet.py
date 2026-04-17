"""
Build gold dim_player as a lean SCD2 dimension from silver player-game history.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_player_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/players.parquet
  s3://nba-analytics-lakehouse-dev/gold/dim_team/dim_team.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/gold/dim_player/dim_player.parquet
"""

from __future__ import annotations

import boto3
from dotenv import load_dotenv

try:
    from .gold_transform_helpers import S3_BUCKET, write_parquet_to_s3
    from .player_surface import DIM_PLAYER_DESTINATION_KEY, DIM_PLAYER_TARGET_SCHEMA, GoldPlayerSurfacePipeline, load_sources_from_s3
    from .player_surface.history import (
        DIM_PLAYER_RECORD_SOURCE as RECORD_SOURCE,
        TRACKED_COLS,
        build_current_nba_team_ids,
        build_display_name,
        build_dim_player_rows,
        build_game_time_map,
        build_player_bio_map,
        build_player_events,
        finalize_rows,
        merge_bbr_birth_date_fallbacks,
    )
    from .player_surface.sources import (
        DIM_TEAM_REQUIRED_COLUMNS,
        DIM_TEAM_SOURCE_KEY,
        GAME_REQUIRED_COLUMNS,
        GAME_SOURCE_KEY,
        PLAYER_BIO_REQUIRED_COLUMNS,
        PLAYER_BIO_SOURCE_KEY,
        PLAYER_REQUIRED_COLUMNS,
        PLAYER_SOURCE_KEY,
    )
except ImportError:
    from gold_transform_helpers import S3_BUCKET, write_parquet_to_s3  # type: ignore[no-redef]
    from player_surface import (  # type: ignore[no-redef]
        DIM_PLAYER_DESTINATION_KEY,
        DIM_PLAYER_TARGET_SCHEMA,
        GoldPlayerSurfacePipeline,
        load_sources_from_s3,
    )
    from player_surface.history import (  # type: ignore[no-redef]
        DIM_PLAYER_RECORD_SOURCE as RECORD_SOURCE,
        TRACKED_COLS,
        build_current_nba_team_ids,
        build_display_name,
        build_dim_player_rows,
        build_game_time_map,
        build_player_bio_map,
        build_player_events,
        finalize_rows,
        merge_bbr_birth_date_fallbacks,
    )
    from player_surface.sources import (  # type: ignore[no-redef]
        DIM_TEAM_REQUIRED_COLUMNS,
        DIM_TEAM_SOURCE_KEY,
        GAME_REQUIRED_COLUMNS,
        GAME_SOURCE_KEY,
        PLAYER_BIO_REQUIRED_COLUMNS,
        PLAYER_BIO_SOURCE_KEY,
        PLAYER_REQUIRED_COLUMNS,
        PLAYER_SOURCE_KEY,
    )

load_dotenv(override=True)

DESTINATION_KEY = DIM_PLAYER_DESTINATION_KEY
TARGET_SCHEMA = DIM_PLAYER_TARGET_SCHEMA


def main() -> None:
    s3_client = boto3.client("s3")
    sources = load_sources_from_s3(s3_client)
    artifacts = GoldPlayerSurfacePipeline().build_player_surface(sources)
    write_parquet_to_s3(artifacts.dim_player_rows, TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
