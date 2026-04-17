#!/usr/bin/env python3
# Purpose:
# Ensure the live gold-derived DuckDB snapshot exists and matches the slice-4 schema contract.
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

from pathlib import Path

import duckdb

try:
    from .build_gold_slice_snapshot import DUCKDB_DIR, DUCKDB_PATH, build_snapshot
except ImportError:  # pragma: no cover - direct script execution
    from build_gold_slice_snapshot import DUCKDB_DIR, DUCKDB_PATH, build_snapshot


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TABLES = {
    "player",
    "team",
    "game",
    "player_game",
    "team_game",
    "player_season",
    "player_season_team",
    "team_season",
    "snapshot_meta",
}
REQUIRED_PLAYER_GAME_COLUMNS = {
    "game_id",
    "person_id",
    "team_id",
    "game_date",
    "season_year",
    "season_type",
    "minutes_played_decimal",
    "points",
}
REQUIRED_TEAM_GAME_COLUMNS = {
    "game_id",
    "team_id",
    "opponent_team_id",
    "game_date",
    "season_year",
    "season_type",
    "team_abbreviation",
    "score",
}
REQUIRED_PLAYER_SEASON_COLUMNS = {
    "person_id",
    "player_name",
    "season_year",
    "season_type",
    "games_played",
    "total_points",
    "average_points",
}
REQUIRED_PLAYER_SEASON_TEAM_COLUMNS = {
    "person_id",
    "team_id",
    "player_name",
    "team_name",
    "season_year",
    "season_type",
    "games_played",
    "total_points",
}
REQUIRED_TEAM_SEASON_COLUMNS = {
    "team_id",
    "team_name",
    "season_year",
    "season_type",
    "games_played",
    "wins",
    "losses",
    "win_percentage",
    "average_points",
}


def _snapshot_is_current(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
            if not REQUIRED_TABLES.issubset(tables):
                return False
            player_game_columns = {
                row[0] for row in conn.execute("DESCRIBE player_game").fetchall()
            }
            team_game_columns = {
                row[0] for row in conn.execute("DESCRIBE team_game").fetchall()
            }
            player_season_columns = {
                row[0] for row in conn.execute("DESCRIBE player_season").fetchall()
            }
            player_season_team_columns = {
                row[0] for row in conn.execute("DESCRIBE player_season_team").fetchall()
            }
            team_season_columns = {
                row[0] for row in conn.execute("DESCRIBE team_season").fetchall()
            }
            return (
                REQUIRED_PLAYER_GAME_COLUMNS.issubset(player_game_columns)
                and REQUIRED_TEAM_GAME_COLUMNS.issubset(team_game_columns)
                and REQUIRED_PLAYER_SEASON_COLUMNS.issubset(player_season_columns)
                and REQUIRED_PLAYER_SEASON_TEAM_COLUMNS.issubset(player_season_team_columns)
                and REQUIRED_TEAM_SEASON_COLUMNS.issubset(team_season_columns)
            )
        finally:
            conn.close()
    except duckdb.Error:
        return False


def load_database(force: bool = False) -> Path:
    DUCKDB_DIR.mkdir(parents=True, exist_ok=True)
    if force or not _snapshot_is_current(DUCKDB_PATH):
        build_snapshot(
            region="us-east-1",
            database="semantic_gold",
            output_location="s3://nba-analytics-lakehouse-dev/athena-results/",
            workgroup="primary",
            catalog="AwsDataCatalog",
            force=True,
        )
    return DUCKDB_PATH


DB_PATH = DUCKDB_PATH


if __name__ == "__main__":
    print(load_database())
