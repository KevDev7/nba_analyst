"""Stable entrypoint for the silver boxscore game transform."""

from __future__ import annotations

from boxscore.game import (
    TARGET_SCHEMA,
    add_metadata_columns,
    build_game_row,
    build_latest_game_rows,
    main,
    quality_score,
    validate_and_dedupe_rows,
    write_parquet_to_s3,
)


if __name__ == "__main__":
    main()

