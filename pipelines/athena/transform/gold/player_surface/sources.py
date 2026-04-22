from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa

try:
    from ..gold_transform_helpers import read_parquet_table_from_s3
except ImportError:
    from gold_transform_helpers import read_parquet_table_from_s3  # type: ignore[no-redef]


PLAYER_SOURCE_KEY = "silver/boxscore_player_game.parquet"
GAME_SOURCE_KEY = "silver/boxscore_game.parquet"
PLAYER_BIO_SOURCE_KEY = "silver/players.parquet"
DIM_TEAM_SOURCE_KEY = "legacy_gold/dim_team/dim_team.parquet"
DIM_PLAYER_SOURCE_KEY = "legacy_gold/dim_player/dim_player.parquet"
BBR_BRIDGE_SOURCE_KEY = "silver/player_identity_bridge_bbr_nba.parquet"
BBR_PROFILE_SOURCE_KEY = "silver/bbr_player_profile.parquet"

PLAYER_REQUIRED_COLUMNS = [
    "gameId",
    "personId",
    "teamId",
    "name",
    "firstName",
    "familyName",
    "position",
    "nameI",
    "jerseyNum",
    "status",
]
GAME_REQUIRED_COLUMNS = ["gameId", "gameTimeUTC"]
DIM_TEAM_REQUIRED_COLUMNS = ["team_id", "is_current"]
PLAYER_BIO_REQUIRED_COLUMNS = [
    "personId",
    "firstName",
    "lastName",
    "birthDate",
    "school",
    "country",
    "heightInches",
    "bodyWeightLbs",
    "draftYear",
    "draftRound",
    "draftNumber",
    "guard",
    "forward",
    "center",
]
DIM_PLAYER_REQUIRED_COLUMNS = ["person_id", "is_current"]
BBR_BRIDGE_REQUIRED_COLUMNS = [
    "nba_person_id",
    "basketball_reference_player_id",
    "match_method",
    "match_confidence",
]
BBR_PROFILE_REQUIRED_COLUMNS = [
    "basketball_reference_player_id",
    "player_profile_url",
    "formal_name",
    "birth_date",
    "pronunciation",
    "former_name_note",
    "nicknames_raw",
    "instagram_handle",
    "position_raw",
    "shoots",
    "height_raw",
    "height_cm",
    "weight_kg",
    "current_team_raw",
    "birth_place_raw",
    "birth_country_code",
    "death_date",
    "college_raw",
    "colleges_raw",
    "high_school_raw",
    "high_schools_raw",
    "recruiting_rank_raw",
    "recruiting_rank_year",
    "recruiting_rank_ordinal",
    "relatives_raw",
    "draft_raw",
    "draft_team_raw",
    "draft_pick_in_round",
    "draft_league",
    "draft_selection_note",
    "nba_debut_date",
    "aba_debut_date",
    "experience_years",
    "career_length_years",
    "hall_of_fame_flag",
    "hall_of_fame_role",
    "hall_of_fame_year",
    "hall_of_fame_raw",
    "headshot_url",
]


@dataclass(frozen=True)
class GoldPlayerSurfaceSources:
    player_table: pa.Table
    game_table: pa.Table
    player_bio_table: pa.Table
    dim_team_table: pa.Table
    dim_player_table: pa.Table
    bbr_bridge_table: pa.Table
    bbr_profile_table: pa.Table


def load_sources_from_s3(s3_client) -> GoldPlayerSurfaceSources:
    return GoldPlayerSurfaceSources(
        player_table=read_parquet_table_from_s3(s3_client, PLAYER_SOURCE_KEY, PLAYER_REQUIRED_COLUMNS),
        game_table=read_parquet_table_from_s3(s3_client, GAME_SOURCE_KEY, GAME_REQUIRED_COLUMNS),
        player_bio_table=read_parquet_table_from_s3(s3_client, PLAYER_BIO_SOURCE_KEY, PLAYER_BIO_REQUIRED_COLUMNS),
        dim_team_table=read_parquet_table_from_s3(s3_client, DIM_TEAM_SOURCE_KEY, DIM_TEAM_REQUIRED_COLUMNS),
        dim_player_table=read_parquet_table_from_s3(s3_client, DIM_PLAYER_SOURCE_KEY, DIM_PLAYER_REQUIRED_COLUMNS),
        bbr_bridge_table=read_parquet_table_from_s3(s3_client, BBR_BRIDGE_SOURCE_KEY, BBR_BRIDGE_REQUIRED_COLUMNS),
        bbr_profile_table=read_parquet_table_from_s3(s3_client, BBR_PROFILE_SOURCE_KEY, BBR_PROFILE_REQUIRED_COLUMNS),
    )
