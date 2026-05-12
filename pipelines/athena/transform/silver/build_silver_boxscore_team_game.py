"""Stable entrypoint for the silver boxscore team-game transform."""

from __future__ import annotations

from boxscore.team_game import (
    TARGET_SCHEMA,
    TEAM_STAT_FLOAT_FIELDS,
    TEAM_STAT_INT_FIELDS,
    TEAM_STAT_STRING_FIELDS,
    add_metadata_columns,
    build_latest_team_rows,
    main,
    quality_score,
    to_team_row,
    validate_and_dedupe_rows,
    write_parquet_to_s3,
)


if __name__ == "__main__":
    main()

