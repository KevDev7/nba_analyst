"""Stable entrypoint for the silver shot-location events transform."""

from __future__ import annotations

from shot_location.events import (
    TARGET_SCHEMA,
    add_silver_metadata,
    build_shot_location_rows,
    derive_location_from_coordinates,
    destination_key_for_game,
    extract_game_id_from_key,
    is_field_goal_row,
    is_three_point_attempt,
    list_source_objects,
    main,
    normalize_game_id,
    read_source_rows,
    write_game_parquet_to_s3,
)


if __name__ == "__main__":
    main()

