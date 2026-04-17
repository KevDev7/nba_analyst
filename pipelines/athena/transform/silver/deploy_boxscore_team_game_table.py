"""
Register the silver boxscore_team_game parquet as an Athena external table.

This reads the Athena-friendly parquet copy written by build_silver_boxscore_team_game.py:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game/data.parquet
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
    from pipelines.athena.transform.gold.athena_view_helpers import (
        AthenaClient,
        load_settings,
    )
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.athena.transform.gold.athena_view_helpers import (
        AthenaClient,
        load_settings,
    )

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"
DATA_KEY = "silver/boxscore_team_game/data.parquet"
TABLE_NAME = "boxscore_team_game"
TABLE_LOCATION = f"s3://{S3_BUCKET}/silver/boxscore_team_game/"


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
    payload = s3.get_object(Bucket=S3_BUCKET, Key=DATA_KEY)["Body"].read()
    return pq.read_schema(io.BytesIO(payload))


def build_create_table_ddl(schema: pa.Schema) -> str:
    column_lines = []
    for field in schema:
        column_lines.append(f'  `{field.name}` {athena_type_for_field(field)}')
    columns_sql = ",\n".join(column_lines)
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
    schema = fetch_schema()
    athena_client.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    athena_client.execute(build_create_table_ddl(schema).replace(f'CREATE EXTERNAL TABLE "{TABLE_NAME}"', f"CREATE EXTERNAL TABLE {TABLE_NAME}"))
    print(f"Created or replaced external table: {settings.database}.{TABLE_NAME}")


if __name__ == "__main__":
    main()
