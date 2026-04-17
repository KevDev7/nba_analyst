from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa

S3_BUCKET = "nba-analytics-lakehouse-dev"

DIM_PLAYER_DESTINATION_KEY = "gold/dim_player/dim_player.parquet"
EXTENDED_PLAYER_DIM_DESTINATION_KEY = "gold/extended_player_dim/extended_player_dim.parquet"

DIM_PLAYER_TARGET_SCHEMA = pa.schema(
    [
        pa.field("player_sk", pa.int64()),
        pa.field("person_id", pa.int64()),
        pa.field("player_name", pa.string()),
        pa.field("first_name", pa.string()),
        pa.field("family_name", pa.string()),
        pa.field("display_name", pa.string()),
        pa.field("primary_position", pa.string()),
        pa.field("latest_team_id", pa.int64()),
        pa.field("latest_nba_team_id", pa.int64()),
        pa.field("record_source", pa.string()),
        pa.field("valid_from_utc", pa.timestamp("us", tz="UTC")),
        pa.field("valid_to_utc", pa.timestamp("us", tz="UTC")),
        pa.field("is_current", pa.int64()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("birth_date", pa.date32()),
        pa.field("school", pa.string()),
        pa.field("country", pa.string()),
        pa.field("height_inches", pa.int64()),
        pa.field("weight_lbs", pa.int64()),
        pa.field("draft_year", pa.int64()),
        pa.field("draft_round", pa.int64()),
        pa.field("draft_number", pa.int64()),
    ]
)

EXTENDED_PLAYER_DIM_TARGET_SCHEMA = pa.schema(
    [
        pa.field("person_id", pa.int64()),
        pa.field("player_name_short", pa.string()),
        pa.field("latest_jersey_number", pa.string()),
        pa.field("latest_status", pa.string()),
        pa.field("position_group", pa.string()),
        pa.field("first_seen_game_date", pa.date32()),
        pa.field("last_seen_game_date", pa.date32()),
        pa.field("first_season_played", pa.string()),
        pa.field("last_season_played", pa.string()),
        pa.field("is_guard", pa.int64()),
        pa.field("is_forward", pa.int64()),
        pa.field("is_center", pa.int64()),
        pa.field("basketball_reference_player_id", pa.string()),
        pa.field("bbr_match_method", pa.string()),
        pa.field("bbr_match_confidence", pa.float64()),
        pa.field("bbr_profile_url", pa.string()),
        pa.field("bbr_formal_name", pa.string()),
        pa.field("bbr_pronunciation", pa.string()),
        pa.field("bbr_former_name_note", pa.string()),
        pa.field("bbr_nicknames_raw", pa.string()),
        pa.field("bbr_instagram_handle", pa.string()),
        pa.field("bbr_position_raw", pa.string()),
        pa.field("bbr_shoots", pa.string()),
        pa.field("bbr_height_raw", pa.string()),
        pa.field("bbr_height_cm", pa.int64()),
        pa.field("bbr_weight_kg", pa.int64()),
        pa.field("bbr_current_team_raw", pa.string()),
        pa.field("bbr_birth_place_raw", pa.string()),
        pa.field("bbr_birth_country_code", pa.string()),
        pa.field("bbr_death_date", pa.date32()),
        pa.field("bbr_college_raw", pa.string()),
        pa.field("bbr_colleges_raw", pa.string()),
        pa.field("bbr_high_school_raw", pa.string()),
        pa.field("bbr_high_schools_raw", pa.string()),
        pa.field("bbr_recruiting_rank_raw", pa.string()),
        pa.field("bbr_recruiting_rank_year", pa.int64()),
        pa.field("bbr_recruiting_rank_ordinal", pa.int64()),
        pa.field("bbr_relatives_raw", pa.string()),
        pa.field("bbr_draft_raw", pa.string()),
        pa.field("bbr_draft_team_raw", pa.string()),
        pa.field("draft_team_id", pa.int64()),
        pa.field("bbr_draft_pick_in_round", pa.int64()),
        pa.field("bbr_draft_league", pa.string()),
        pa.field("bbr_draft_selection_note", pa.string()),
        pa.field("bbr_nba_debut_date", pa.date32()),
        pa.field("bbr_aba_debut_date", pa.date32()),
        pa.field("bbr_experience_years", pa.int64()),
        pa.field("bbr_career_length_years", pa.int64()),
        pa.field("bbr_hall_of_fame_flag", pa.int64()),
        pa.field("bbr_hall_of_fame_role", pa.string()),
        pa.field("bbr_hall_of_fame_year", pa.int64()),
        pa.field("bbr_hall_of_fame_raw", pa.string()),
        pa.field("bbr_headshot_url", pa.string()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)


@dataclass(frozen=True)
class PlayerSurfaceTableSpec:
    table_name: str
    data_key: str
    table_location: str


PLAYER_SURFACE_TABLE_SPECS = [
    PlayerSurfaceTableSpec(
        table_name="dim_player",
        data_key=DIM_PLAYER_DESTINATION_KEY,
        table_location=f"s3://{S3_BUCKET}/gold/dim_player/",
    ),
    PlayerSurfaceTableSpec(
        table_name="extended_player_dim",
        data_key=EXTENDED_PLAYER_DIM_DESTINATION_KEY,
        table_location=f"s3://{S3_BUCKET}/gold/extended_player_dim/",
    ),
]
