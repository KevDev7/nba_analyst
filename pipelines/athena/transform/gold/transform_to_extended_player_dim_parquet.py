"""
Build gold extended_player_dim as a current-state player enrichment table.

Reads:
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_player/dim_player.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_team/dim_team.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_player_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/players.parquet
  s3://nba-analytics-lakehouse-dev/silver/player_identity_bridge_bbr_nba.parquet
  s3://nba-analytics-lakehouse-dev/silver/bbr_player_profile.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/legacy_gold/extended_player_dim/extended_player_dim.parquet
"""

from __future__ import annotations

import boto3
from dotenv import load_dotenv

try:
    from .gold_transform_helpers import S3_BUCKET, write_parquet_to_s3
    from .player_surface import (
        EXTENDED_PLAYER_DIM_DESTINATION_KEY,
        EXTENDED_PLAYER_DIM_TARGET_SCHEMA,
        GoldPlayerSurfacePipeline,
        load_sources_from_s3,
    )
    from .player_surface.bbr_projection import build_bbr_by_person_id
    from .player_surface.current_profile import (
        EXTENDED_PLAYER_DIM_RECORD_SOURCE as RECORD_SOURCE,
        build_current_person_ids,
        build_current_profile_map,
        build_extended_rows as build_rows,
        map_bbr_draft_team_id,
        build_profile_flags_map,
    )
    from .player_surface.sources import (
        BBR_BRIDGE_REQUIRED_COLUMNS,
        BBR_BRIDGE_SOURCE_KEY,
        BBR_PROFILE_REQUIRED_COLUMNS,
        BBR_PROFILE_SOURCE_KEY,
        DIM_PLAYER_REQUIRED_COLUMNS,
        DIM_PLAYER_SOURCE_KEY,
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
        EXTENDED_PLAYER_DIM_DESTINATION_KEY,
        EXTENDED_PLAYER_DIM_TARGET_SCHEMA,
        GoldPlayerSurfacePipeline,
        load_sources_from_s3,
    )
    from player_surface.bbr_projection import build_bbr_by_person_id  # type: ignore[no-redef]
    from player_surface.current_profile import (  # type: ignore[no-redef]
        EXTENDED_PLAYER_DIM_RECORD_SOURCE as RECORD_SOURCE,
        build_current_person_ids,
        build_current_profile_map,
        build_extended_rows as build_rows,
        map_bbr_draft_team_id,
        build_profile_flags_map,
    )
    from player_surface.sources import (  # type: ignore[no-redef]
        BBR_BRIDGE_REQUIRED_COLUMNS,
        BBR_BRIDGE_SOURCE_KEY,
        BBR_PROFILE_REQUIRED_COLUMNS,
        BBR_PROFILE_SOURCE_KEY,
        DIM_PLAYER_REQUIRED_COLUMNS,
        DIM_PLAYER_SOURCE_KEY,
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

DESTINATION_KEY = EXTENDED_PLAYER_DIM_DESTINATION_KEY
TARGET_SCHEMA = EXTENDED_PLAYER_DIM_TARGET_SCHEMA


def main() -> None:
    s3_client = boto3.client("s3")
    sources = load_sources_from_s3(s3_client)
    artifacts = GoldPlayerSurfacePipeline().build_player_surface(sources)
    write_parquet_to_s3(artifacts.extended_player_dim_rows, TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
