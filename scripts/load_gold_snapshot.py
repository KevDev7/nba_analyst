#!/usr/bin/env python3
# Purpose:
# Ensure the live gold-derived DuckDB snapshot exists and matches the current semantic_gold contract.
#
# Uses:
# - fixtures/duckdb/gold_slice.duckdb
# - build_gold_slice_snapshot.py when the snapshot is missing or stale
#
# Produces:
# - a ready-to-query local DuckDB snapshot for the CLI and runtime
#
# Next:
# - apps/cli/main.py

from __future__ import annotations

import os
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
DUCKDB_DIR = ROOT / "fixtures" / "duckdb"
DUCKDB_PATH = DUCKDB_DIR / "gold_slice.duckdb"
DISABLE_REBUILD_ENV = "NBA_DISABLE_SNAPSHOT_REBUILD"
REQUIRED_COLUMNS_BY_TABLE = {
    "player": {
        "person_id",
        "full_name",
        "first_name",
        "last_name",
        "primary_position",
        "position_group",
        "latest_team_id",
        "latest_jersey_number",
        "birth_date",
        "school",
        "country",
        "height_inches",
        "weight_lbs",
        "draft_year",
        "draft_round",
        "draft_pick_number",
    },
    "team": {
        "team_id",
        "team_name",
        "team_city",
        "team_state",
        "team_country",
        "team_abbreviation",
        "conference",
        "division",
    },
    "arena": {
        "arena_id",
        "arena_name",
        "arena_city",
        "arena_state",
        "arena_country",
        "arena_timezone",
    },
    "game": {
        "game_id",
        "season_year",
        "season_type",
        "game_date",
        "game_start_time_utc",
        "arena_id",
        "home_team_id",
        "away_team_id",
    },
    "player_game": {
        "game_id",
        "person_id",
        "team_id",
        "opponent_team_id",
        "season_year",
        "season_type",
        "game_date",
        "game_start_time_utc",
        "team_home_or_away",
        "is_starter",
        "win_loss_result",
        "minutes_played",
        "plus_minus",
        "points",
        "assists",
        "turnovers",
        "total_rebounds",
        "offensive_rebounds",
        "defensive_rebounds",
        "steals",
        "blocks",
        "opponent_blocks",
        "offensive_fouls_committed",
        "personal_fouls_committed",
        "technical_fouls_committed",
        "fouls_drawn",
        "fast_break_points",
        "points_in_paint",
        "second_chance_points",
        "field_goals_made",
        "field_goals_attempted",
        "two_pointers_made",
        "two_pointers_attempted",
        "three_pointers_made",
        "three_pointers_attempted",
        "free_throws_made",
        "free_throws_attempted",
        "offensive_possessions",
        "defensive_possessions",
        "offensive_rating",
        "defensive_rating",
        "assist_percentage",
        "usage_percentage",
        "offensive_rebound_percentage",
        "defensive_rebound_percentage",
        "rebound_percentage",
        "block_percentage",
    },
    "team_game": {
        "game_id",
        "team_id",
        "opponent_team_id",
        "season_year",
        "season_type",
        "game_date",
        "game_start_time_utc",
        "team_home_or_away",
        "win_loss_result",
        "minutes_played",
        "score",
        "opponent_score",
        "assists",
        "opponent_assists",
        "turnovers",
        "opponent_turnovers",
        "total_rebounds",
        "offensive_rebounds",
        "defensive_rebounds",
        "opponent_total_rebounds",
        "opponent_offensive_rebounds",
        "opponent_defensive_rebounds",
        "steals",
        "opponent_steals",
        "blocks",
        "opponent_blocks",
        "offensive_fouls_committed",
        "opponent_offensive_fouls_committed",
        "personal_fouls_committed",
        "opponent_personal_fouls_committed",
        "technical_fouls_committed",
        "opponent_technical_fouls_committed",
        "fouls_drawn",
        "opponent_fouls_drawn",
        "fast_break_points",
        "opponent_fast_break_points",
        "points_in_paint",
        "opponent_points_in_paint",
        "second_chance_points",
        "opponent_second_chance_points",
        "points_off_turnovers",
        "opponent_points_off_turnovers",
        "field_goals_made",
        "field_goals_attempted",
        "opponent_field_goals_made",
        "opponent_field_goals_attempted",
        "two_pointers_made",
        "two_pointers_attempted",
        "opponent_two_pointers_made",
        "opponent_two_pointers_attempted",
        "three_pointers_made",
        "three_pointers_attempted",
        "opponent_three_pointers_made",
        "opponent_three_pointers_attempted",
        "free_throws_made",
        "free_throws_attempted",
        "opponent_free_throws_made",
        "opponent_free_throws_attempted",
        "offensive_possessions",
        "defensive_possessions",
        "block_percentage",
    },
    "player_season": {
        "person_id",
        "season_year",
        "season_type",
        "age_on_jan_31",
        "team_count",
        "is_multi_team_season",
        "games_played",
        "games_started",
        "minutes_total",
        "plus_minus_total",
        "points_total",
        "assists_total",
        "turnovers_total",
        "rebounds_total",
        "offensive_rebounds_total",
        "defensive_rebounds_total",
        "steals_total",
        "blocks_total",
        "opponent_blocks_total",
        "offensive_fouls_committed_total",
        "personal_fouls_committed_total",
        "technical_fouls_committed_total",
        "fouls_drawn_total",
        "fast_break_points_total",
        "points_in_paint_total",
        "second_chance_points_total",
        "field_goals_made_total",
        "field_goals_attempted_total",
        "two_pointers_made_total",
        "two_pointers_attempted_total",
        "three_pointers_made_total",
        "three_pointers_attempted_total",
        "free_throws_made_total",
        "free_throws_attempted_total",
        "offensive_possessions_total",
        "defensive_possessions_total",
        "pace",
        "offensive_rating",
        "defensive_rating",
        "net_rating",
        "assist_percentage",
        "usage_percentage",
        "offensive_rebound_percentage",
        "defensive_rebound_percentage",
        "rebound_percentage",
        "block_percentage",
    },
    "player_season_team": {
        "person_id",
        "team_id",
        "season_year",
        "season_type",
        "games_played",
        "games_started",
        "minutes_total",
        "points_total",
        "assists_total",
        "rebounds_total",
        "offensive_rebounds_total",
        "defensive_rebounds_total",
        "steals_total",
        "blocks_total",
        "opponent_blocks_total",
        "turnovers_total",
        "plus_minus_total",
        "offensive_fouls_committed_total",
        "personal_fouls_committed_total",
        "technical_fouls_committed_total",
        "fouls_drawn_total",
        "fast_break_points_total",
        "points_in_paint_total",
        "second_chance_points_total",
        "field_goals_made_total",
        "field_goals_attempted_total",
        "two_pointers_made_total",
        "two_pointers_attempted_total",
        "three_pointers_made_total",
        "three_pointers_attempted_total",
        "free_throws_made_total",
        "free_throws_attempted_total",
        "offensive_possessions_total",
        "defensive_possessions_total",
        "pace",
        "offensive_rating",
        "defensive_rating",
        "net_rating",
        "assist_percentage",
        "usage_percentage",
        "offensive_rebound_percentage",
        "defensive_rebound_percentage",
        "rebound_percentage",
        "block_percentage",
    },
    "team_season": {
        "team_id",
        "season_year",
        "season_type",
        "games_played",
        "wins",
        "losses",
        "minutes",
        "minutes_per_game",
        "points_total",
        "assists_total",
        "turnovers_total",
        "rebounds_total",
        "offensive_rebounds_total",
        "defensive_rebounds_total",
        "steals_total",
        "blocks_total",
        "offensive_fouls_committed_total",
        "personal_fouls_committed_total",
        "technical_fouls_committed_total",
        "fouls_drawn_total",
        "field_goals_made_total",
        "field_goals_attempted_total",
        "two_pointers_made_total",
        "two_pointers_attempted_total",
        "three_pointers_made_total",
        "three_pointers_attempted_total",
        "free_throws_made_total",
        "free_throws_attempted_total",
        "offensive_possessions",
        "defensive_possessions",
        "pace",
        "defensive_rating",
        "net_rating",
        "offensive_rebound_percentage",
        "defensive_rebound_percentage",
        "rebound_percentage",
        "block_percentage",
    },
}
REQUIRED_TABLES = set(REQUIRED_COLUMNS_BY_TABLE) | {"snapshot_meta"}


def _snapshot_is_current(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
            if not REQUIRED_TABLES.issubset(tables):
                return False
            for table_name, required_columns in REQUIRED_COLUMNS_BY_TABLE.items():
                current_columns = {
                    row[0] for row in conn.execute(f'DESCRIBE "{table_name}"').fetchall()
                }
                if current_columns != required_columns:
                    return False
            return True
        finally:
            conn.close()
    except duckdb.Error:
        return False


def _snapshot_rebuild_disabled() -> bool:
    return os.getenv(DISABLE_REBUILD_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _build_snapshot_from_athena() -> Path:
    try:
        from .build_gold_slice_snapshot import build_snapshot
    except ImportError:  # pragma: no cover - direct script execution
        from build_gold_slice_snapshot import build_snapshot
    return build_snapshot(
        region="us-east-1",
        database="semantic_gold",
        output_location="s3://nba-analytics-lakehouse-dev/athena-results/",
        workgroup="primary",
        catalog="AwsDataCatalog",
        force=True,
    )


def load_database(force: bool = False) -> Path:
    DUCKDB_DIR.mkdir(parents=True, exist_ok=True)
    if force or not _snapshot_is_current(DUCKDB_PATH):
        if _snapshot_rebuild_disabled():
            raise RuntimeError(
                "DuckDB snapshot is missing or stale. Build fixtures/duckdb/gold_slice.duckdb "
                f"before deploy; {DISABLE_REBUILD_ENV}=1 disables Athena snapshot rebuilds at runtime."
            )
        _build_snapshot_from_athena()
    return DUCKDB_PATH


DB_PATH = DUCKDB_PATH


if __name__ == "__main__":
    print(load_database())
