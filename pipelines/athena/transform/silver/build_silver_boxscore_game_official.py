"""Stable entrypoint for the silver boxscore game-official transform."""

from __future__ import annotations

from boxscore.officials import (
    TARGET_SCHEMA,
    add_metadata_columns,
    build_latest_official_rows,
    main,
    quality_score,
    to_official_rows,
    validate_and_dedupe_rows,
    write_parquet_to_s3,
)


if __name__ == "__main__":
    main()

