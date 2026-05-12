"""
Transform one raw NBA player movement snapshot JSON into a silver parquet file.

This file stays as the stable script entrypoint. Domain logic lives in
`player_movement/`.
"""

from __future__ import annotations

try:
    from player_movement.contracts import (
        DESTINATION_KEY,
        META_SCHEMA_VERSION,
        META_SOURCE_SYSTEM,
        S3_BUCKET,
        SNAPSHOT_PARTITION,
        SOURCE_KEY,
        TABLE_NAME,
        TARGET_SCHEMA,
    )
    from player_movement.pipeline import build_audit_row, main, read_source_payload, write_parquet_to_s3
    from player_movement.transform import (
        add_metadata_columns,
        build_rows,
        null_if_empty,
        parse_transaction_datetime,
        to_int_or_none,
    )
except ModuleNotFoundError:
    from pipelines.athena.transform.silver.player_movement.contracts import (
        DESTINATION_KEY,
        META_SCHEMA_VERSION,
        META_SOURCE_SYSTEM,
        S3_BUCKET,
        SNAPSHOT_PARTITION,
        SOURCE_KEY,
        TABLE_NAME,
        TARGET_SCHEMA,
    )
    from pipelines.athena.transform.silver.player_movement.pipeline import (
        build_audit_row,
        main,
        read_source_payload,
        write_parquet_to_s3,
    )
    from pipelines.athena.transform.silver.player_movement.transform import (
        add_metadata_columns,
        build_rows,
        null_if_empty,
        parse_transaction_datetime,
        to_int_or_none,
    )


if __name__ == "__main__":
    main()
