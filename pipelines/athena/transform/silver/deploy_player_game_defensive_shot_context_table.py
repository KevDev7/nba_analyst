"""
Register the silver player_game_defensive_shot_context parquet as an Athena external table.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings
    from pipelines.athena.transform.silver.build_silver_player_game_defensive_shot_context import (
        DESTINATION_KEY,
        S3_BUCKET,
        TABLE_NAME,
    )
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings
    from pipelines.athena.transform.silver.build_silver_player_game_defensive_shot_context import (  # type: ignore[no-redef]
        DESTINATION_KEY,
        S3_BUCKET,
        TABLE_NAME,
    )

load_dotenv(override=True)

ATHENA_DATA_KEY = "silver/player_game_defensive_shot_context/data.parquet"
TABLE_LOCATION = f"s3://{S3_BUCKET}/silver/player_game_defensive_shot_context/"


def athena_type_for_field(field: pa.Field) -> str:
    field_type = field.type
    if pa.types.is_string(field_type):
        return "string"
    if pa.types.is_int64(field_type):
        return "bigint"
    if pa.types.is_float64(field_type):
        return "double"
    if pa.types.is_timestamp(field_type):
        return "timestamp"
    raise ValueError(f"Unsupported PyArrow type for Athena DDL: {field.name} -> {field_type}")


def fetch_schema() -> pa.Schema:
    s3 = boto3.client("s3")
    payload = s3.get_object(Bucket=S3_BUCKET, Key=DESTINATION_KEY)["Body"].read()
    return pq.read_schema(io.BytesIO(payload))


def ensure_athena_data_copy() -> None:
    s3 = boto3.client("s3")
    s3.copy_object(
        Bucket=S3_BUCKET,
        CopySource={"Bucket": S3_BUCKET, "Key": DESTINATION_KEY},
        Key=ATHENA_DATA_KEY,
    )


def build_create_table_ddl(schema: pa.Schema) -> str:
    columns_sql = ",\n".join(f"  `{field.name}` {athena_type_for_field(field)}" for field in schema)
    return f"""
CREATE EXTERNAL TABLE "{TABLE_NAME}" (
{columns_sql}
)
STORED AS PARQUET
LOCATION '{TABLE_LOCATION}'
"""


def main() -> None:
    settings = load_settings()
    athena_client = AthenaClient(settings)
    ensure_athena_data_copy()
    schema = fetch_schema()
    athena_client.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    athena_client.execute(
        build_create_table_ddl(schema).replace(
            f'CREATE EXTERNAL TABLE "{TABLE_NAME}"',
            f"CREATE EXTERNAL TABLE {TABLE_NAME}",
        )
    )
    print(f"Created or replaced external table: {settings.database}.{TABLE_NAME}")


if __name__ == "__main__":
    main()
