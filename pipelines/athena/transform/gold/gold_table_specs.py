from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


try:
    from pipelines.athena.transform.gold.player_surface import PLAYER_SURFACE_TABLE_SPECS
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.athena.transform.gold.player_surface import PLAYER_SURFACE_TABLE_SPECS


S3_BUCKET = "nba-analytics-lakehouse-dev"


@dataclass(frozen=True)
class GoldTableSpec:
    table_name: str
    data_key: str
    table_location: str


CORE_TABLE_SPECS = [
    GoldTableSpec(
        table_name="dim_date",
        data_key="legacy_gold/dim_date/dim_date.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/dim_date/",
    ),
    GoldTableSpec(
        table_name="dim_game",
        data_key="legacy_gold/dim_game/dim_game.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/dim_game/",
    ),
    GoldTableSpec(
        table_name="dim_team",
        data_key="legacy_gold/dim_team/dim_team.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/dim_team/",
    ),
    GoldTableSpec(
        table_name="fct_player_game",
        data_key="legacy_gold/fct_player_game/fct_player_game.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/fct_player_game/",
    ),
    GoldTableSpec(
        table_name="fct_team_game",
        data_key="legacy_gold/fct_team_game/fct_team_game.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/fct_team_game/",
    ),
    GoldTableSpec(
        table_name="fct_player_game_shot_profile_standard",
        data_key=(
            "legacy_gold/fct_player_game_shot_profile_standard/"
            "fct_player_game_shot_profile_standard.parquet"
        ),
        table_location=f"s3://{S3_BUCKET}/legacy_gold/fct_player_game_shot_profile_standard/",
    ),
    GoldTableSpec(
        table_name="fct_player_game_shot_profile_source",
        data_key=(
            "legacy_gold/fct_player_game_shot_profile_source/"
            "fct_player_game_shot_profile_source.parquet"
        ),
        table_location=f"s3://{S3_BUCKET}/legacy_gold/fct_player_game_shot_profile_source/",
    ),
    GoldTableSpec(
        table_name="fct_player_game_shot_type_source",
        data_key=(
            "legacy_gold/fct_player_game_shot_type_source/"
            "fct_player_game_shot_type_source.parquet"
        ),
        table_location=f"s3://{S3_BUCKET}/legacy_gold/fct_player_game_shot_type_source/",
    ),
    GoldTableSpec(
        table_name="agg_player_season",
        data_key="legacy_gold/agg_player_season/agg_player_season.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/agg_player_season/",
    ),
    GoldTableSpec(
        table_name="agg_team_season",
        data_key="legacy_gold/agg_team_season/agg_team_season.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/agg_team_season/",
    ),
    GoldTableSpec(
        table_name="team_season_provenance_sidecar",
        data_key=(
            "legacy_gold/team_season_provenance_sidecar/"
            "team_season_provenance_sidecar.parquet"
        ),
        table_location=f"s3://{S3_BUCKET}/legacy_gold/team_season_provenance_sidecar/",
    ),
    GoldTableSpec(
        table_name="player_season_percentiles",
        data_key="legacy_gold/player_season_percentiles/player_season_percentiles.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/player_season_percentiles/",
    ),
    GoldTableSpec(
        table_name="team_season_percentiles",
        data_key="legacy_gold/team_season_percentiles/team_season_percentiles.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/team_season_percentiles/",
    ),
    GoldTableSpec(
        table_name="player_award_history",
        data_key="legacy_gold/player_award_history/player_award_history.parquet",
        table_location=f"s3://{S3_BUCKET}/legacy_gold/player_award_history/",
    ),
]


TABLE_SPECS = CORE_TABLE_SPECS + [
    GoldTableSpec(
        table_name=spec.table_name,
        data_key=spec.data_key,
        table_location=spec.table_location,
    )
    for spec in PLAYER_SURFACE_TABLE_SPECS
]
