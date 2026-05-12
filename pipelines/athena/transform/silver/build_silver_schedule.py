"""Stable entrypoint for the silver schedule transform."""

from __future__ import annotations

from schedule.league import (
    TARGET_SCHEMA,
    add_metadata_columns,
    build_rows,
    main,
    parse_game_date,
    parse_utc_timestamp,
    quality_score,
    read_source_payload,
    validate_and_dedupe_rows,
    write_parquet_to_s3,
)


if __name__ == "__main__":
    main()

