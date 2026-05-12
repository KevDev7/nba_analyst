"""Stable entrypoint for the silver BoxScoreMatchupsV3 transform."""

from __future__ import annotations

from boxscore.matchups import (
    TARGET_SCHEMA,
    add_metadata_columns,
    boxscore_matchups_root,
    build_all_source_rows,
    build_rows_from_archive,
    build_rows_from_payload,
    clean_name,
    extract_game_id_from_key,
    grain_key,
    main,
    normalize_game_id,
    normalize_source_row,
    quality_score,
    validate_and_dedupe_rows,
    write_parquet_to_s3,
)


if __name__ == "__main__":
    main()

