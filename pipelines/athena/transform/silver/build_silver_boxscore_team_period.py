"""Stable entrypoint for the silver boxscore team-period transform."""

from __future__ import annotations

from boxscore.team_period import (
    TARGET_SCHEMA,
    add_metadata_columns,
    build_latest_team_period_rows,
    main,
    quality_score,
    to_team_period_rows,
    validate_and_dedupe_rows,
    write_parquet_to_s3,
)


if __name__ == "__main__":
    main()

