"""Stable entrypoint for the silver boxscore player-game transform."""

from __future__ import annotations

from boxscore.player_game import (
    TARGET_SCHEMA,
    add_metadata_columns,
    build_latest_player_rows,
    is_minutes_duration,
    main,
    minutes_duration_seconds,
    quality_score,
    to_player_rows,
    validate_and_dedupe_rows,
    write_parquet_to_s3,
)


if __name__ == "__main__":
    main()

